import asyncio
import mcp.types
import uvicorn
from fastmcp.server.proxy import ProxyTool, FastMCPProxy
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.client.transports import FastMCPTransport, WSTransport, SSETransport
from mcp.server.sse import SseServerTransport
from typing import Any
from fastapi import FastAPI

USERS = [
    {"id": "1", "name": "Alice", "active": True},
    {"id": "2", "name": "Bob", "active": True},
    {"id": "3", "name": "Charlie", "active": False},
]

def create_demo_fastmcp_server():
    server = FastMCP("TestServer")

    # --- Resources ---
    @server.resource(uri="resource://wave")
    def wave() -> str:
        return "👋"

    @server.resource(uri="data://users")
    async def get_users() -> list[dict[str, Any]]:
        return USERS

    @server.resource(uri="data://user/{user_id}")
    async def get_user(user_id: str) -> dict[str, Any] | None:
        return next((user for user in USERS if user["id"] == user_id), None)

    return server


async def all_from_real_server(client: "Client") -> list["ProxyTool"]:
    """
    Query the real server for its tools and create ProxyTool instances for each.
    """
    async with client:
        result = await client.session.list_tools()
        return [
            await ProxyTool.from_client(client, tool)
            for tool in result.tools
        ]


class MultiUpstreamFastMCP(FastMCP):
    """
    FastMCP-compatible proxy that aggregates multiple FastMCPProxy instances (one per real server).
    Supports the MCP protocol (SSE/WS endpoints).
    """
    def __init__(self, proxies, name="MultiUpstreamProxy"):
        super().__init__(name)
        self.proxies = proxies

    async def get_tools(self) -> dict[str, Any]:
        tools = {}
        for proxy in self.proxies:
            t = await proxy.get_tools()
            tools.update(t)
        return tools

    async def get_resources(self) -> dict[str, Any]:
        resources = {}
        for proxy in self.proxies:
            r = await proxy.get_resources()
            resources.update(r)
        return resources

    async def get_prompts(self) -> dict[str, Any]:
        prompts = {}
        for proxy in self.proxies:
            p = await proxy.get_prompts()
            prompts.update(p)
        return prompts


async def create_proxy_server():
    """Create and return a FastMCP-compatible proxy that aggregates multiple FastMCPProxy instances."""
    server_urls = [
        "http://0.0.0.0:8001/sse",
        "http://0.0.0.0:8002/sse",
        "http://0.0.0.0:8003/sse",
    ]
    proxies = []
    for url in server_urls:
        client = Client(transport=SSETransport(url))
        proxy_clients = FastMCPProxy.from_client(client)
        proxies.append(proxy_clients)
    return MultiUpstreamFastMCP(proxies)


def run_proxy_server():
    proxy_server = asyncio.run(create_proxy_server())
    uvicorn.run(proxy_server.app, host="0.0.0.0", port=9000)


if __name__ == "__main__":
    print("Starting FastMCPProxy server on http://0.0.0.0:9000 ...")
    run_proxy_server()
