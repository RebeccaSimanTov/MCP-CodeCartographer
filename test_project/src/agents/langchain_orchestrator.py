import asyncio
import json
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from langchain_core.messages import SystemMessage
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.callbacks import get_openai_callback

from common.utils.json_utils import dumps_safe
from src.services.db_utils import save_execution_to_db
from src.llm.llm_factory import LLMFactory
from src.services.rabbitmq_rpc_client import RabbitMQRPCClient
from src.services.nl_to_dsl_service import NL2DSLService
from src.services.tools_registry import MCPToolsRegistry


class LangChainOrchestrator:
    """
    Pure RabbitMQ orchestrator - no HTTP/MCP dependencies
    """

    def __init__(
        self,
        user_input_callback: Optional[Callable[[str], Any]] = None,
        llm_provider: Optional[str] = None,
        enable_streaming: bool = False,
        session_id: Optional[str] = None
    ):
        self.user_input_callback = user_input_callback
        self.llm_provider = llm_provider or "openai"
        self.enable_streaming = enable_streaming
        self.session_id = session_id or f"session_{id(self)}"

        # RabbitMQ only
        self.rpc_client = RabbitMQRPCClient()
        self.tools_registry: Optional[MCPToolsRegistry] = None

        # LangChain settings
        self.agent: Optional[AgentExecutor] = None
        self.nl_to_dsl_service = NL2DSLService(ctx=None)
        self.memory = InMemoryChatMessageHistory()
        self.query: Optional[str] = None

        self.stats = {
            "total_queries": 0,
            "successful_flows": 0,
            "failed_flows": 0,
            "total_tool_calls": 0
        }

        # Init LLM
        self.llm = (
            LLMFactory.create_streaming_llm(self.llm_provider)
            if self.enable_streaming
            else LLMFactory.create_llm(self.llm_provider)
        )

    # ==================== INITIALIZATION ====================

    async def connect_services(self):
        """Connect to RabbitMQ only - no HTTP"""
        print("🔌 Connecting to RabbitMQ...")
        
        await self.rpc_client.connect()
        print("✅ Connected to RabbitMQ")
        
        # Create Tools Registry (RabbitMQ only)
        self.tools_registry = MCPToolsRegistry(self.rpc_client)
        if self.user_input_callback:
            self.tools_registry.set_ask_user_callback(self.user_input_callback)
        
        print("✅ Tools Registry initialized (RabbitMQ mode)")

    # ==================== AGENT SETUP ====================

    async def setup_agent(self):
        """Create LangChain Agent with tools from RabbitMQ workers"""
        from langchain_core.callbacks import StdOutCallbackHandler

        class DebugCallback(StdOutCallbackHandler):
            def on_tool_start(self, serialized, input_str, **kwargs):
                print(f"\n🔧 TOOL CALL: {serialized.get('name')} — input: {input_str}")

        self.llm = LLMFactory.create_llm(
            provider=self.llm_provider,
            callbacks=[DebugCallback()]
        )

        # ✅ Fetch all tools from RabbitMQ workers
        tools = await self.tools_registry.register_all_tools()
        
        print(f"🔧 Registered {len(tools)} tools:")
        for tool in tools:
            print(f"   - {tool.name}: {tool.description[:80]}...")
        
        if not tools:
            print("⚠️ WARNING: No tools registered! Agent will have limited capabilities.")
        
        # Create prompt for Agent
        instructions = self._load_instructions().replace("{", "{{").replace("}", "}}")

        prompt = ChatPromptTemplate.from_messages([
            ("system", instructions),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        agent = create_openai_functions_agent(
            llm=self.llm,
            tools=tools,
            prompt=prompt
        )

        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True,
            return_intermediate_steps=True
        )

        self.agent = RunnableWithMessageHistory(
            agent_executor,
            lambda session_id: self.memory,
            input_messages_key="input",
            history_messages_key="chat_history",
        )

    # ==================== FLOW EXECUTION ====================

    async def orchestrate_flow(self, query: str) -> Dict[str, Any]:
        """Execute full orchestration flow"""
        self.stats["total_queries"] += 1
        self.query = query

        try:
            # Connect to RabbitMQ if not connected
            if not self.rpc_client.connection or self.rpc_client.connection.is_closed:
                await self.connect_services()
            
            # Create Agent if not exists
            if not self.agent:
                await self.setup_agent()

            # NL->DSL parsing (optional)
            try:
                dsl_result = await self.nl_to_dsl_service.parse_natural_language(query)
                context = f"DSL Parsed: {dumps_safe(dsl_result.output)}"
                self.add_context(context)
            except Exception as e:
                print(f"⚠️ DSL parse failed: {e}")
                dsl_result = None

            # Execute Agent
            if self.llm_provider == "openai":
                with get_openai_callback() as cb:
                    result = await self.agent.ainvoke(
                        {"input": query},
                        config={"configurable": {"session_id": self.session_id}}
                    )
                    result["token_usage"] = {
                        "total_tokens": cb.total_tokens,
                        "prompt_tokens": cb.prompt_tokens,
                        "completion_tokens": cb.completion_tokens,
                        "total_cost": cb.total_cost
                    }
            else:
                result = await self.agent.ainvoke(
                    {"input": query},
                    config={"configurable": {"session_id": self.session_id}}
                )

            def serialize_step(step):
                if hasattr(step, 'to_dict'):
                    return step.to_dict()
                return str(step)  

            intermediate_steps_serializable = [serialize_step(s) for s in result.get("intermediate_steps", [])]

            final_json = {
                "output": result.get("output", ""),
                "intermediate_steps": intermediate_steps_serializable,
                "dsl_result": dsl_result.model_dump() if dsl_result else None
            }

            await save_execution_to_db(final_json)

            intermediate_steps = result.get("intermediate_steps", [])
            self.stats["total_tool_calls"] += len(intermediate_steps)
            self.stats["successful_flows"] += 1

            return {
                "status": "success",
                "query": query,
                "output": result.get("output", ""),
                "steps": intermediate_steps,
                "dsl_result": dsl_result.model_dump() if dsl_result else None
            }

        except Exception as e:
            self.stats["failed_flows"] += 1
            traceback.print_exc()
            return {"status": "error", "error": str(e), "trace": traceback.format_exc()}

    # ==================== MEMORY ====================

    def add_context(self, context: str):
        self.memory.add_message(SystemMessage(content=context))

    def _load_instructions(self) -> str:
        """Load orchestrator instructions"""
        try:
            path = Path(__file__).resolve().parents[2] / "prompts" / "orchestrator_instructions.md"
            if path.exists():
                return path.read_text(encoding="utf-8")
            print("⚠️ No orchestrator_instructions.md found, using default.")
            return "You are a LangChain orchestrator managing distributed tool calls via RabbitMQ."
        except Exception as e:
            print(f"⚠️ Error loading instructions: {e}")
            return "Default instructions fallback."

    async def cleanup(self):
        """Close RabbitMQ connection"""
        if self.tools_registry:
            await self.tools_registry.cleanup()
        
        if self.rpc_client and self.rpc_client.connection:
            await self.rpc_client.disconnect()
            print("✅ RabbitMQ connection closed")