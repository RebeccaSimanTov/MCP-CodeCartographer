"""
RabbitMQ RPC Client for Orchestrator
Simple async client for sending tasks to workers and receiving responses
"""

import asyncio
import json
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
import aio_pika
from aio_pika import Message, DeliveryMode
from aio_pika.abc import AbstractIncomingMessage


class RabbitMQRPCClient:
    """
    Simple RPC client for calling workers via RabbitMQ
    Uses correlation IDs for request-response pattern
    """
    
    def __init__(
        self,
        host: str = "rabbitmq",
        port: int = 5672,
        username: str = "admin",
        password: str = "admin123"
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self.callback_queue: Optional[aio_pika.Queue] = None
        
        # Pending requests: correlation_id -> Future
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.consumer_tag: Optional[str] = None
        
        print("🐰 RabbitMQ RPC Client initialized")
    
    async def connect(self):
        """Connect to RabbitMQ and setup callback queue"""
        if self.connection and not self.connection.is_closed:
            print("✅ Already connected to RabbitMQ")
            return
        
        try:
            connection_url = f"amqp://{self.username}:{self.password}@{self.host}:{self.port}/"
            
            self.connection = await aio_pika.connect_robust(
                connection_url,
                timeout=30
            )
            
            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=1)
            
            # Create exclusive callback queue for responses
            self.callback_queue = await self.channel.declare_queue(
                name="",  # RabbitMQ generates unique name
                exclusive=True,
                auto_delete=True
            )
            
            # Start consuming responses
            self.consumer_tag = await self.callback_queue.consume(
                self._on_response,
                no_ack=True
            )
            
            print(f"✅ Connected to RabbitMQ at {self.host}:{self.port}")
            print(f"📬 Callback queue: {self.callback_queue.name}")
            
        except Exception as e:
            print(f"❌ Failed to connect to RabbitMQ: {e}")
            raise
    
    async def call(
        self,
        queue_name: str,
        payload: Dict[str, Any],
        timeout: float = 120.0,
        priority: int = 5
    ) -> Dict[str, Any]:
        """
        Send RPC request to worker and wait for response
        
        Args:
            queue_name: Target queue (e.g., "plan_generator")
            payload: Request payload with tool_name and args
            timeout: Max wait time in seconds
            priority: Message priority (0-10)
        
        Returns:
            Response dict from worker
        """
        if not self.channel or not self.callback_queue:
            await self.connect()
        
        correlation_id = str(uuid.uuid4())
        
        # Create future for this request
        future = asyncio.Future()
        self.pending_requests[correlation_id] = future
        
        # Add metadata to payload
        full_payload = {
            **payload,
            "correlation_id": correlation_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            # Create message
            message = Message(
                body=json.dumps(full_payload, ensure_ascii=False).encode('utf-8'),
                correlation_id=correlation_id,
                reply_to=self.callback_queue.name,
                delivery_mode=DeliveryMode.PERSISTENT,
                priority=priority,
                content_type="application/json",
                timestamp=datetime.utcnow()
            )
            
            # Publish to worker queue
            await self.channel.default_exchange.publish(
                message,
                routing_key=queue_name
            )
            
            print(f"📤 Sent RPC request to '{queue_name}' [correlation_id={correlation_id[:8]}...]")
            
            # Wait for response
            try:
                result = await asyncio.wait_for(future, timeout=timeout)
                print(f"✅ Received response from '{queue_name}' [correlation_id={correlation_id[:8]}...]")
                return result
                
            except asyncio.TimeoutError:
                print(f"⏱️ RPC request to '{queue_name}' timed out after {timeout}s")
                return {
                    "status": "error",
                    "error": f"Request timed out after {timeout}s",
                    "correlation_id": correlation_id
                }
        
        except Exception as e:
            print(f"❌ Error in RPC call to '{queue_name}': {e}")
            return {
                "status": "error",
                "error": str(e),
                "correlation_id": correlation_id
            }
        
        finally:
            # Cleanup
            self.pending_requests.pop(correlation_id, None)
    
    async def _on_response(self, message: AbstractIncomingMessage):
        """Handle response messages from workers"""
        try:
            correlation_id = message.correlation_id
            
            if not correlation_id or correlation_id not in self.pending_requests:
                print(f"⚠️ Received response with unknown correlation_id: {correlation_id}")
                return
            
            # Parse response
            response_data = json.loads(message.body.decode('utf-8'))
            
            # Resolve future
            future = self.pending_requests[correlation_id]
            if not future.done():
                future.set_result(response_data)
            
        except Exception as e:
            print(f"❌ Error processing response: {e}")
            import traceback
            traceback.print_exc()
    
    async def disconnect(self):
        """Close connection to RabbitMQ"""
        try:
            if self.consumer_tag and self.callback_queue:
                await self.callback_queue.cancel(self.consumer_tag)
            
            if self.channel and not self.channel.is_closed:
                await self.channel.close()
            
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
            
            print("🔌 Disconnected from RabbitMQ")
            
        except Exception as e:
            print(f"⚠️ Error during disconnect: {e}")
    
    async def __aenter__(self):
        """Context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        await self.disconnect()
