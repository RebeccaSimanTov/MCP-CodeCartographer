"""
Standalone RabbitMQ Worker
Handles both get_schema and call_tool requests
"""
import asyncio
import json
import os
import sys
import traceback
from pathlib import Path

# Add service directory to path
service_path = Path("/app/service")
if service_path.exists():
    sys.path.insert(0, str(service_path))

import aio_pika
from aio_pika import IncomingMessage


async def process_message(message: IncomingMessage, worker_instance, channel):
    """
    Process incoming RabbitMQ message
    Routes to get_schema or call_tool
    """
    async with message.process():
        try:
            # Parse request
            body = message.body.decode()
            payload = json.loads(body)
            
            print(f"\n📩 Received request: {payload.get('method')}")
            
            # Route to worker
            response = await worker_instance.handle_message(payload)
            
            # Send response back
            if message.reply_to:
                await channel.default_exchange.publish(
                    aio_pika.Message(
                        body=json.dumps(response).encode(),
                        correlation_id=message.correlation_id
                    ),
                    routing_key=message.reply_to
                )
                print(f"✅ Response sent: {response.get('status')}")
            
        except Exception as e:
            print(f"❌ Error processing message: {e}")
            traceback.print_exc()
            
            # Send error response
            if message.reply_to:
                error_response = {
                    "status": "error",
                    "error": str(e),
                    "trace": traceback.format_exc()
                }
                await channel.default_exchange.publish(
                    aio_pika.Message(
                        body=json.dumps(error_response).encode(),
                        correlation_id=message.correlation_id
                    ),
                    routing_key=message.reply_to
                )


async def main():
    """Main worker loop"""
    
    # Get configuration from environment
    service_name = os.getenv("SERVICE_NAME", "unknown")
    queue_name = os.getenv("QUEUE_NAME", service_name)
    rabbitmq_host = os.getenv("RABBITMQ_HOST", "localhost")
    rabbitmq_port = int(os.getenv("RABBITMQ_PORT", 5672))
    rabbitmq_user = os.getenv("RABBITMQ_USER", "guest")
    rabbitmq_password = os.getenv("RABBITMQ_PASSWORD", "guest")
    worker_prefetch = int(os.getenv("WORKER_PREFETCH", 1))
    
    print(f"🚀 Starting {service_name} worker")
    print(f"   Queue: {queue_name}")
    print(f"   RabbitMQ: {rabbitmq_host}:{rabbitmq_port}")
    
    # Import worker class dynamically
    try:
        # Use a generic workerxxxxxxxxxxxcts to local MCP service
        from src.services.workers.mcp_bridge_worker import MCPBridgeWorker
        
        # Get the local MCP port from environment
        mcp_port = int(os.getenv("MCP_PORT", 8000))
        service_url = f"http://localhost:{mcp_port}"
        
        worker_instance = MCPBridgeWorker(service_name=service_name, service_url=service_url)
        
        print(f"✅ Worker class loaded: {worker_instance.__class__.__name__}")
        print(f"   Will connect to local MCP at: {service_url}")
        
    except Exception as e:
        print(f"❌ Failed to load worker class: {e}")
        traceback.print_exc()
        return
    
    # Connect to RabbitMQ
    while True:
        try:
            connection = await aio_pika.connect_robust(
                host=rabbitmq_host,
                port=rabbitmq_port,
                login=rabbitmq_user,
                password=rabbitmq_password
            )
            
            print("✅ Connected to RabbitMQ")
            
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=worker_prefetch)
            
            # Declare queue with same settings as orchestrator_worker
            queue = await channel.declare_queue(
                queue_name,
                durable=True,
                arguments={
                    "x-max-priority": 10,
                    "x-message-ttl": 600000,  # 10 minutes (match orchestrator_worker)
                }
            )
            
            print(f"🎯 Listening on queue: {queue_name}")
            print(f"⚙️ Prefetch count: {worker_prefetch}")
            print("Ready to receive messages...\n")
            
            # Start consuming
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    await process_message(message, worker_instance, channel)
            
        except Exception as e:
            print(f"❌ Connection error: {e}")
            print("Retrying in 5 seconds...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Worker stopped by user")