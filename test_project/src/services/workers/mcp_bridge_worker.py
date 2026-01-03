"""
Generic MCP Bridge Worker
Works with any FastMCP service running locally in the same container
"""
import json
from typing import Dict, Any
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport


class MCPBridgeWorker:
    """
    Generic RabbitMQ worker that bridges to any local MCP service
    """
    
    def __init__(self, service_name: str, service_url: str = "http://localhost:8000"):
        self.service_name = service_name
        self.service_url = service_url.rstrip("/")
        self.transport = None
        self.client = None
        
    async def _ensure_connected(self):
        """Ensure MCP client is connected to local service"""
        if self.client is None:
            print(f"🔌 [{self.service_name}] Connecting to local MCP at {self.service_url}/mcp")
            self.transport = StreamableHttpTransport(f"{self.service_url}/mcp")
            self.client = Client(self.transport)
            await self.client.__aenter__()
            print(f"✅ [{self.service_name}] Connected to local MCP service")
        
    async def handle_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle incoming RabbitMQ RPC message
        Routes to get_schema or call_tool
        """
        method = payload.get("method")
        params = payload.get("params", {})
        
        print(f"📋 [{self.service_name}] {method}")
        
        try:
            await self._ensure_connected()
            
            if method == "get_schema":
                return await self.get_schema()
            elif method == "call_tool":
                return await self.call_tool(params)
            else:
                return {
                    "status": "error",
                    "error": f"Unknown method: {method}"
                }
                
        except Exception as e:
            print(f"❌ [{self.service_name}] Worker error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def get_schema(self) -> Dict[str, Any]:
        """
        Get tool schema from local MCP service
        """
        try:
            print(f"   → [{self.service_name}] Getting tools list from MCP...")
            
            # List tools from FastMCP
            tools = await self.client.list_tools()
            
            print(f"   ✅ [{self.service_name}] Got {len(tools)} tools")
            
            # Convert to schema format expected by orchestrator
            tools_schema = []
            for tool in tools:
                tool_schema = {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": getattr(tool, 'inputSchema', {})
                }
                tools_schema.append(tool_schema)
                print(f"      - {tool.name}: {tool.description[:60]}...")
                print(f"        Input Schema: {json.dumps(tool_schema['inputSchema'])}")
            return {
                "status": "success",
                "schema": {
                    "tools": tools_schema
                }
            }
                
        except Exception as e:
            print(f"   ❌ [{self.service_name}] Failed to get schema: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute tool via local MCP service
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        print(f"   → [{self.service_name}] Calling tool '{tool_name}' with args: {arguments}")
        
        try:
            # Call tool via FastMCP client
            result = await self.client.call_tool(tool_name, arguments)
            
            print(f"   ✅ [{self.service_name}] Tool execution successful")
            
            # Convert FastMCP result to simple dict
            if hasattr(result, 'content') and result.content:
                # Extract text content from MCP result
                content_text = []
                for item in result.content:
                    if hasattr(item, 'text'):
                        content_text.append(item.text)
                    else:
                        content_text.append(str(item))
                
                return {
                    "status": "success", 
                    "result": "\n".join(content_text)
                }
            elif hasattr(result, 'structured_content') and result.structured_content:
                # Use structured content if available
                return {
                    "status": "success",
                    "result": result.structured_content
                }
            else:
                # Fallback to string representation
                return {
                    "status": "success",
                    "result": str(result)
                }
                
        except Exception as e:
            error_msg = str(e)
            print(f"   ❌ [{self.service_name}] Tool execution exception: {error_msg}")
            import traceback
            traceback.print_exc()
            
            return {
                "status": "error",
                "error": error_msg
            }

    async def cleanup(self):
        """Cleanup MCP client"""
        try:
            if self.client:
                await self.client.__aexit__(None, None, None)
                print(f"🔌 [{self.service_name}] MCP client disconnected")
        except Exception as e:
            print(f"⚠️ [{self.service_name}] Error during cleanup: {e}")