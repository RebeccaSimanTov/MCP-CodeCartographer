"""
MCPToolsRegistry - Pure RabbitMQ version (no HTTP)
"""
import json
from typing import Any, Callable, Dict, List, Optional
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.services.rabbitmq_rpc_client import RabbitMQRPCClient


class MCPToolsRegistry:
    """
    Registry that fetches tool schemas from workers via RabbitMQ
    and converts them to LangChain tools
    """

    def __init__(self, rpc_client: RabbitMQRPCClient):
        self.rpc_client = rpc_client
        self.tools: List[StructuredTool] = []
        self.ask_user_callback: Optional[Callable[[str], Any]] = None
        
        # Define which queues to fetch schemas from
        self.service_queues = [
            "plan_generator",
            "plan_reviewer", 
            "ui_agent",
            "persona_search"
        ]

    def set_ask_user_callback(self, callback: Callable[[str], Any]):
        """Set callback for user interaction"""
        self.ask_user_callback = callback

    def _register_ask_user_tool(self):
        """Register the ask_user tool for LLM to ask missing information"""
        class AskUserInput(BaseModel):
            question: str = Field(description="The question to ask the user")

        async def ask_user_impl(question: str) -> str:
            """Ask the user for missing information"""
            print(f"\n[ask_user] Question: {question}")
            print(f"[ask_user] Callback configured: {self.ask_user_callback is not None}")
            
            if not self.ask_user_callback:
                print("[ask_user] No callback - returning error for worker mode")
                return json.dumps({
                    "needs_user_input": True,
                    "question": question,
                    "error": "Worker mode: cannot ask user interactively. Please provide input via WebSocket."
                })
            
            try:
                print(f"[ask_user] Calling callback...")
                answer = await self.ask_user_callback(question)
                print(f"[ask_user] Got answer: {answer}")
                # Return answer in a format that prompts the LLM to continue with the actual task
                return f"User provided answer: {answer}\n\nNow proceed with the original task using this information."
            except Exception as e:
                print(f"[ask_user] Exception: {e}")
                return f"Error: {str(e)}"

        tool = StructuredTool(
            name="ask_user",
            description="Ask the user for missing information or clarifications. After getting the answer, continue with the task.",
            coroutine=ask_user_impl,
            args_schema=AskUserInput,
        )
        self.tools.append(tool)

    async def register_all_tools(self) -> List[StructuredTool]:
        """
        Fetch schemas from all workers via RabbitMQ and register tools
        """
        print("🔧 Fetching tool schemas from RabbitMQ workers...")
        
        for queue_name in self.service_queues:
            try:
                # Request schema from worker
                print(f"   → Requesting schema from '{queue_name}'...")
                
                response = await self.rpc_client.call(
                    queue_name=queue_name,
                    payload={
                        "method": "get_schema",
                        "params": {}
                    },
                    timeout=10.0
                )
                
                if response and response.get("status") == "success":
                    schema = response.get("schema", {})
                    tools_schema = schema.get("tools", [])
                    
                    print(f"   ✅ Got {len(tools_schema)} tools from '{queue_name}'")
                    
                    # Convert each tool to LangChain format
                    for tool_def in tools_schema:
                        langchain_tool = self._convert_to_langchain_tool(
                            tool_def, 
                            queue_name
                        )
                        self.tools.append(langchain_tool)
                else:
                    print(f"   ⚠️ No schema from '{queue_name}': {response}")
                    
            except Exception as e:
                print(f"   ❌ Failed to get schema from '{queue_name}': {e}")
                # Continue with other services
                continue
        
        # Register ask_user tool
        self._register_ask_user_tool()
        
        print(f"✅ Registered {len(self.tools)} total tools\n")
        return self.tools

    def _convert_to_langchain_tool(
        self, 
        tool_def: Dict[str, Any], 
        queue_name: str
    ) -> StructuredTool:
        """
        Convert MCP tool definition to LangChain StructuredTool
        """
        tool_name = tool_def.get("name")
        description = tool_def.get("description", "No description")
        input_schema = tool_def.get("inputSchema", {})

        # Create the tool function
        async def tool_func(**kwargs) -> str:
            """Execute tool via RabbitMQ"""
            try:
                print(f"\n🔧 Executing tool '{tool_name}' on queue '{queue_name}'")
                print(f"   Input: {kwargs}")
                
                response = await self.rpc_client.call(
                    queue_name=queue_name,
                    payload={
                        "method": "call_tool",
                        "params": {
                            "name": tool_name,
                            "arguments": kwargs
                        }
                    },
                    timeout=3000.0  # 5 minutes for long operations
                )
                
                if response and response.get("status") == "success":
                    result = response.get("result", {})
                    print(f"   ✅ Tool succeeded")
                    
                    # Handle different result types
                    if isinstance(result, dict):
                        if "content" in result:
                            # MCP standard format
                            content = result["content"]
                            if isinstance(content, list):
                                return "\n".join([
                                    item.get("text", str(item)) 
                                    for item in content
                                ])
                            return str(content)
                        return json.dumps(result, indent=2)
                    
                    return str(result)
                else:
                    error_msg = response.get("error", "Unknown error")
                    print(f"   ❌ Tool failed: {error_msg}")
                    return f"Error: {error_msg}"
                    
            except Exception as e:
                print(f"   ❌ Exception in tool execution: {e}")
                return f"Error executing tool: {str(e)}"
        
        # Create LangChain tool
        return StructuredTool(
            name=tool_name,
            description=description,
            args_schema=input_schema,
            coroutine=tool_func
        )

    async def cleanup(self):
        """Cleanup resources"""
        # RPC client cleanup handled by orchestrator
        pass