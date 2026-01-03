"""
Standalone RabbitMQ Worker for Orchestrator
Routes: WebSocket → RabbitMQ → Worker → LangChain Agent
"""

import asyncio
import json
import signal
import sys
import os
from typing import Dict, Any, Optional
from datetime import datetime
import aio_pika
from aio_pika import Message, DeliveryMode
from aio_pika.abc import AbstractIncomingMessage

# Fix import path
try:
    from src.agents.langchain_orchestrator import LangChainOrchestrator
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from src.agents.langchain_orchestrator import LangChainOrchestrator


def make_json_safe(obj: Any) -> Any:
    """
    Convert any object to JSON-safe format
    Handles LangChain objects, dataclasses, and other non-serializable types
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    
    if isinstance(obj, (list, tuple)):
        return [make_json_safe(item) for item in obj]
    
    if isinstance(obj, dict):
        return {key: make_json_safe(value) for key, value in obj.items()}
    
    # Handle datetime
    if isinstance(obj, datetime):
        return obj.isoformat()
    
    # Try to get dict representation
    if hasattr(obj, '__dict__'):
        return make_json_safe(obj.__dict__)
    
    # Try to get string representation
    if hasattr(obj, '__str__'):
        return str(obj)
    
    # Last resort
    return repr(obj)


class OrchestratorWorker:
    """
    Worker that consumes orchestration requests from RabbitMQ
    """
    
    def __init__(
        self,
        queue_name: str = "orchestrator",
        rabbitmq_host: str = "rabbitmq",
        rabbitmq_port: int = 5672,
        rabbitmq_user: str = "admin",
        rabbitmq_password: str = "admin123",
        prefetch_count: int = 1,
        llm_provider: str = "openai"
    ):
        self.queue_name = queue_name
        
        self.rabbitmq_host = rabbitmq_host
        self.rabbitmq_port = rabbitmq_port
        self.rabbitmq_user = rabbitmq_user
        self.rabbitmq_password = rabbitmq_password
        self.prefetch_count = prefetch_count
        self.llm_provider = llm_provider
        
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self.queue: Optional[aio_pika.Queue] = None
        
        self.is_running = False
        self.processed_count = 0
        self.error_count = 0
        
        # Active orchestrators by session_id
        self.orchestrators: Dict[str, LangChainOrchestrator] = {}
        
        print(f"\n{'='*70}")
        print(f"🎯 ORCHESTRATOR WORKER INITIALIZED")
        print(f"{'='*70}")
        print(f"   Queue: {queue_name}")
        print(f"   LLM Provider: {llm_provider}")
        print(f"   Prefetch: {prefetch_count}")
        print(f"{'='*70}\n")
    
    async def connect(self):
        """Connect to RabbitMQ with retry logic"""
        max_retries = 10
        retry_delay = 3
        
        for attempt in range(1, max_retries + 1):
            try:
                connection_url = f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}@{self.rabbitmq_host}:{self.rabbitmq_port}/"
                
                print(f"Connecting to RabbitMQ at {self.rabbitmq_host}:{self.rabbitmq_port}... (attempt {attempt}/{max_retries})")
                
                self.connection = await aio_pika.connect_robust(
                    connection_url,
                    timeout=30,
                    reconnect_interval=5
                )
                
                self.channel = await self.connection.channel()
                await self.channel.set_qos(prefetch_count=self.prefetch_count)
                
                # Declare queue
                self.queue = await self.channel.declare_queue(
                    name=self.queue_name,
                    durable=True,
                    arguments={
                        "x-max-priority": 10,
                        "x-message-ttl": 600000,  # 10 minutes (original setting)
                    }
                )
                
                print(f"✅ Connected to RabbitMQ queue '{self.queue_name}'")
                break
                
            except Exception as e:
                if attempt < max_retries:
                    print(f"Connection attempt {attempt} failed: {e}")
                    print(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    print(f"❌ Failed to connect to RabbitMQ after {max_retries} attempts: {e}")
                    raise
    
    async def start(self):
        """Start consuming messages from the queue"""
        if not self.connection or not self.queue:
            await self.connect()
        
        self.is_running = True
        
        print(f"\n{'='*70}")
        print(f"🚀 ORCHESTRATOR WORKER STARTED")
        print(f"{'='*70}")
        print(f"   Listening on: {self.queue_name}")
        print(f"   Ready to process orchestration requests...")
        print(f"{'='*70}\n")
        
        try:
            await self.queue.consume(self._process_message)
            
            while self.is_running:
                await asyncio.sleep(1)
                
        except Exception as e:
            print(f"❌ Error in worker loop: {e}")
            raise
    
    async def _process_message(self, message: AbstractIncomingMessage):
        """Process a single orchestration request"""
        async with message.process():
            start_time = datetime.utcnow()
            correlation_id = "unknown"
            
            try:
                payload = json.loads(message.body.decode())
                correlation_id = payload.get("correlation_id", "unknown")
                query = payload.get("query")
                session_id = payload.get("session_id", f"worker_{correlation_id}")
                timestamp = payload.get("timestamp", "")
                
                print(f"\n{'='*70}")
                print(f"📥 NEW ORCHESTRATION REQUEST")
                print(f"{'='*70}")
                print(f"   Correlation ID: {correlation_id}")
                print(f"   Session ID: {session_id}")
                print(f"   Query: {query}")
                print(f"   Timestamp: {timestamp}")
                print(f"{'='*70}\n")
                
                # Get or create orchestrator for this session
                if session_id not in self.orchestrators:
                    print(f"🔧 Creating new orchestrator for session {session_id}")
                    orchestrator = LangChainOrchestrator(
                        user_input_callback=None,  # No interactive callback for worker mode
                        llm_provider=self.llm_provider,
                        enable_streaming=False,
                        session_id=session_id
                    )
                    await orchestrator.connect_services()
                    await orchestrator.setup_agent()
                    self.orchestrators[session_id] = orchestrator
                else:
                    orchestrator = self.orchestrators[session_id]
                    print(f"♻️ Reusing existing orchestrator for session {session_id}")
                
                # Execute orchestration
                print(f"⚙️ Running orchestration flow...")
                result = await orchestrator.orchestrate_flow(query)
                
                execution_time = (datetime.utcnow() - start_time).total_seconds()
                
                # Make result JSON-safe
                safe_result = make_json_safe(result)
                
                # Check if result contains a request for user input
                needs_input = False
                user_question = None
                parameter_name = None
                
                # Check in the steps for ask_user calls
                steps = safe_result.get("steps", [])
                for step_list in steps:
                    if isinstance(step_list, list):
                        for item in step_list:
                            # Check if this is an ask_user response
                            if isinstance(item, str) and "needs_user_input" in item:
                                try:
                                    parsed = json.loads(item)
                                    if parsed.get("needs_user_input"):
                                        needs_input = True
                                        user_question = parsed.get("question")
                                        parameter_name = parsed.get("parameter_name")
                                        print(f"🔔 Detected user input needed: {user_question}")
                                        break
                                except:
                                    pass
                    if needs_input:
                        break
                
                # Also check in output
                if not needs_input:
                    output_str = safe_result.get("output", "")
                    try:
                        if isinstance(output_str, str) and "needs_user_input" in output_str:
                            parsed = json.loads(output_str)
                            if parsed.get("needs_user_input"):
                                needs_input = True
                                user_question = parsed.get("question")
                                parameter_name = parsed.get("parameter_name")
                    except:
                        pass
                
                # Prepare response
                if needs_input and user_question:
                    print(f"📤 Returning needs_input response with question")
                    response = {
                        "status": "needs_input",
                        "question": user_question,
                        "parameter_name": parameter_name,
                        "result": safe_result,
                        "correlation_id": correlation_id,
                        "session_id": session_id,
                        "execution_time": execution_time,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                else:
                    response = {
                        "status": safe_result.get("status", "success"),
                        "result": safe_result,
                        "correlation_id": correlation_id,
                        "session_id": session_id,
                        "execution_time": execution_time,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                
                print(f"\n{'='*70}")
                print(f"✅ ORCHESTRATION COMPLETED")
                print(f"{'='*70}")
                print(f"   Execution time: {execution_time:.2f}s")
                print(f"   Status: {result.get('status', 'success').upper()}")
                print(f"{'='*70}\n")
                
                self.processed_count += 1
                
            except Exception as e:
                execution_time = (datetime.utcnow() - start_time).total_seconds()
                
                print(f"\n{'='*70}")
                print(f"❌ ORCHESTRATION FAILED")
                print(f"{'='*70}")
                print(f"   Error: {e}")
                print(f"   Execution time: {execution_time:.2f}s")
                print(f"{'='*70}\n")
                
                self.error_count += 1
                
                response = {
                    "status": "error",
                    "error": str(e),
                    "correlation_id": correlation_id,
                    "execution_time": execution_time,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                import traceback
                traceback.print_exc()
            
            # Send response back
            try:
                if message.reply_to:
                    response_message = Message(
                        body=json.dumps(response, ensure_ascii=False).encode('utf-8'),
                        correlation_id=message.correlation_id,
                        delivery_mode=DeliveryMode.PERSISTENT,
                        content_type="application/json"
                    )
                    
                    await self.channel.default_exchange.publish(
                        response_message,
                        routing_key=message.reply_to
                    )
                    
                    print(f"📤 Response sent to queue '{message.reply_to}'")
                else:
                    print("⚠️ No reply_to address - response not sent")
                    
            except Exception as e:
                print(f"❌ Failed to send response: {e}")
            
            # Print statistics
            total = self.processed_count + self.error_count
            success_rate = (self.processed_count / total * 100) if total > 0 else 0
            
            print(f"\n📊 WORKER STATISTICS")
            print(f"{'='*70}")
            print(f"   Total Processed: {self.processed_count}")
            print(f"   Total Errors: {self.error_count}")
            print(f"   Success Rate: {success_rate:.1f}%")
            print(f"   Active Sessions: {len(self.orchestrators)}")
            print(f"{'='*70}\n")
    
    async def stop(self):
        """Stop the worker gracefully"""
        print(f"\n{'='*70}")
        print(f"🛑 STOPPING ORCHESTRATOR WORKER")
        print(f"{'='*70}")
        
        self.is_running = False
        
        try:
            # Cleanup all orchestrators
            for session_id, orchestrator in self.orchestrators.items():
                try:
                    await orchestrator.cleanup()
                    print(f"✅ Cleaned up orchestrator for session {session_id}")
                except Exception as e:
                    print(f"⚠️ Error cleaning up session {session_id}: {e}")
            
            self.orchestrators.clear()
            
            # Close RabbitMQ
            if self.channel and not self.channel.is_closed:
                await self.channel.close()
                print("✅ RabbitMQ channel closed")
            
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
                print("✅ RabbitMQ connection closed")
            
            # Print final statistics
            total = self.processed_count + self.error_count
            success_rate = (self.processed_count / total * 100) if total > 0 else 0
            
            print(f"\n{'='*70}")
            print(f"📊 FINAL STATISTICS")
            print(f"{'='*70}")
            print(f"   Total Requests: {total}")
            print(f"   Successful: {self.processed_count}")
            print(f"   Failed: {self.error_count}")
            print(f"   Success Rate: {success_rate:.1f}%")
            print(f"{'='*70}\n")
            
        except Exception as e:
            print(f"⚠️ Error during cleanup: {e}")


async def main():
    """Main entry point for orchestrator worker"""
    
    # Get configuration from environment
    queue_name = os.getenv("QUEUE_NAME", "orchestrator")
    rabbitmq_host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    rabbitmq_port = int(os.getenv("RABBITMQ_PORT", "5672"))
    rabbitmq_user = os.getenv("RABBITMQ_USER", "admin")
    rabbitmq_password = os.getenv("RABBITMQ_PASSWORD", "admin123")
    prefetch_count = int(os.getenv("WORKER_PREFETCH", "1"))
    llm_provider = os.getenv("LLM_PROVIDER", "openai")
    
    # Create worker
    worker = OrchestratorWorker(
        queue_name=queue_name,
        rabbitmq_host=rabbitmq_host,
        rabbitmq_port=rabbitmq_port,
        rabbitmq_user=rabbitmq_user,
        rabbitmq_password=rabbitmq_password,
        prefetch_count=prefetch_count,
        llm_provider=llm_provider
    )
    
    # Setup signal handlers
    loop = asyncio.get_event_loop()
    
    def signal_handler(sig, frame):
        print(f"\n⚠️ Received signal {sig} - initiating shutdown...")
        asyncio.create_task(worker.stop())
        loop.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start worker
    try:
        await worker.start()
    except KeyboardInterrupt:
        print("\n⚠️ Keyboard interrupt received")
        await worker.stop()
    except Exception as e:
        print(f"\n❌ Worker crashed: {e}")
        import traceback
        traceback.print_exc()
        await worker.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())