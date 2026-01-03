import asyncio
import json
import traceback
from src.services.rabbitmq_rpc_client import RabbitMQRPCClient

def _json_safe(value):
    """Recursively convert objects to JSON-serializable forms."""
    try:
        json.dumps(value)
        return value
    except Exception:
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(v) for v in value]
        try:
            return str(value)
        except Exception:
            return "<unserializable>"

class ChatSession:
    def __init__(self, websocket, llm_provider="openai", use_rabbitmq=True):
        self.websocket = websocket
        self.llm_provider = llm_provider
        self.use_rabbitmq = use_rabbitmq
        self.rpc_client: RabbitMQRPCClient = None
        self.query = None
        self.orchestration_task = None
        self.user_response_future = None
        self.is_processing = False
        self.silent_mode = False
        self.session_id = f"websocket_{id(websocket)}"
        print(f"\n🆕 NEW CHAT SESSION {self.session_id} | LLM: {llm_provider} | RabbitMQ: {use_rabbitmq}")

    async def send(self, type_: str, message: str, extra: dict = None):
        """Send JSON-safe payload over websocket (with silent mode filtering)."""
        important_types = ["question","result","error","session_closed","system","info","progress","agent_thinking"]
        if self.silent_mode and type_ not in important_types:
            return

        payload = {"type": type_, "message": message}
        if extra:
            try:
                payload.update(_json_safe(extra))
            except Exception as e:
                payload["extra"] = f"<extra not serializable: {e}>"

        try:
            await self.websocket.send_json(payload)
        except Exception as e:
            print(f"❌ Failed to send WebSocket message: {e}")

    async def handle_user_message(self, text: str):
        # Allow user to explicitly close the session
        if text.strip().lower() in {"exit", "quit", "close"}:
            await self.send("session_closed", "👋 Session closed by user")
            await self.close_session()
            return

        # If we are waiting for an answer to ask_user, resolve it here
        if self.user_response_future and not self.user_response_future.done():
            self.user_response_future.set_result(text)
            return

        # Prevent overlaps
        if self.is_processing:
            await self.send("system", "⚠️ Still processing your request. Please wait...")
            return

        # New query - start orchestration
        if not self.query or not self.is_processing:
            self.query = text
            self.is_processing = True
            self.orchestration_task = asyncio.create_task(self.run_orchestration())
            return

    async def run_orchestration(self):
        try:
            await self.send("info", "🤖 Initializing agent...")
            print(f"\n{'='*60}\n🎯 Starting orchestration for query: {self.query}\n{'='*60}\n")

            if self.use_rabbitmq:
                # ✅ NEW: Use RabbitMQ worker mode
                await self._run_via_rabbitmq()
            else:
                # OLD: Direct orchestrator call (legacy mode)
                await self._run_direct()

        except Exception as e:
            error_msg = f"Unexpected error in orchestration: {str(e)}"
            tb = traceback.format_exc()
            print(f"\n{'='*60}\n❌ CRITICAL ERROR\n{'='*60}\nError: {error_msg}\nTraceback:\n{tb}\n{'='*60}\n")
            await self.send("error", error_msg)
        finally:
            self.is_processing = False

    async def _run_via_rabbitmq(self):
        """NEW: Send orchestration request to RabbitMQ worker"""
        try:
            # Initialize RabbitMQ client
            if not self.rpc_client:
                self.rpc_client = RabbitMQRPCClient()
                await self.rpc_client.connect()
                print("✅ Connected to RabbitMQ")

            await self.send("progress", "📨 Sending request to orchestrator worker...")

            # Send request to worker
            result = await self.rpc_client.call(
                queue_name="orchestrator",
                payload={
                    "query": self.query,
                    "session_id": self.session_id
                },
                timeout=300.0  # 5 minutes timeout
            )

            print(f"✅ Received response from worker: {result.get('status')}")
            print(f"📊 Full result keys: {result.keys()}")
            print(f"🔍 Status value: '{result.get('status')}'")

            # Process result
            status = result.get("status")
            
            if status == "needs_input":
                # Worker needs user input
                question = result.get("question", "Please provide additional information")
                parameter_name = result.get("parameter_name", "input")
                print(f"❓ Asking user: {question}")
                await self.send("question", question, extra={
                    "session_id": self.session_id,
                    "parameter_name": parameter_name
                })
                await self.send("info", "⏳ Waiting for your input...")
                
            elif status == "success":
                orchestration_result = result.get("result", {})
                safe_result = _json_safe(orchestration_result)
                output_text = orchestration_result.get("output", "")
                
                # Also check if the output itself indicates needs_input
                if "needs_user_input" in str(output_text):
                    print("⚠️ Found needs_user_input in output despite status=success")
                    await self.send("warning", "The system needs additional information but cannot ask interactively in worker mode.")
                
                await self.send("result", output_text, extra={"data": safe_result})
                await self.send("info", "✅ Done. You can ask a follow-up or type 'exit' to close.")
                
            else:
                error_details = result.get("error", "Unknown error")
                print(f"\n{'='*60}\n❌ ORCHESTRATION ERROR\n{'='*60}\nError: {error_details}\n{'='*60}\n")
                await self.send("error", f"{error_details}")

        except Exception as e:
            error_msg = f"RabbitMQ orchestration failed: {str(e)}"
            print(f"❌ {error_msg}")
            traceback.print_exc()
            await self.send("error", error_msg)

    async def _run_direct(self):
        """OLD: Direct orchestrator call (no RabbitMQ)"""
        from src.agents.langchain_orchestrator import LangChainOrchestrator
        
        orchestrator = None
        try:
            orchestrator = LangChainOrchestrator(
                user_input_callback=self.ask_user_callback,
                llm_provider=self.llm_provider,
                enable_streaming=False,
                session_id=self.session_id
            )
            print("✅ Orchestrator initialized")

            await self.send("progress", "🔌 Connecting to services...")
            await orchestrator.connect_services()
            print("✅ Services connected")

            await self.send("progress", "🛠️ Setting up agent tools...")
            await orchestrator.setup_agent()
            print("✅ Agent setup complete")

            await self.send("progress", "🧠 Agent is thinking...")
            print("🧠 Running orchestration flow...")

            result = await orchestrator.orchestrate_flow(self.query)
            print(f"✅ Orchestration complete: {result.get('status')}")

            if result.get("status") == "success":
                safe_result = _json_safe(result)
                await self.send("result", result.get("output", ""), extra={"data": safe_result})
                await self.send("info", "✅ Done. You can ask a follow-up or type 'exit' to close.")
            else:
                error_details = result.get("error", "Unknown error")
                traceback_info = result.get("traceback", "No traceback available")
                print(f"\n{'='*60}\n❌ ORCHESTRATION ERROR\n{'='*60}\nError: {error_details}\nTraceback:\n{traceback_info}\n{'='*60}\n")
                await self.send("error", f"{error_details}")

        finally:
            if orchestrator:
                try:
                    await orchestrator.cleanup()
                    print("✅ Orchestrator cleanup complete")
                except Exception as e:
                    print(f"⚠️ Cleanup error: {e}")

    async def ask_user_callback(self, question: str) -> str:
        """Tool callback for asking user questions (only works in direct mode)"""
        payload = {"type": "question", "message": question, "awaiting_response": True}
        await self.websocket.send_json(payload)
        self.user_response_future = asyncio.Future()
        answer = await self.user_response_future
        self.user_response_future = None
        return answer

    async def close_session(self):
        try:
            await self.websocket.close()
        except Exception:
            pass

    async def cleanup(self):
        if self.user_response_future and not self.user_response_future.done():
            self.user_response_future.set_exception(Exception("Session closed"))
        if self.orchestration_task and not self.orchestration_task.done():
            self.orchestration_task.cancel()
            try:
                await self.orchestration_task
            except asyncio.CancelledError:
                pass
        if self.rpc_client:
            try:
                await self.rpc_client.disconnect()
            except Exception:
                pass