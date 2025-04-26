import json
import logging
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from typing import Iterable, Any
from pydantic import AnyUrl


USERS = [
    {"id": "1", "name": "Alice", "active": True},
    {"id": "2", "name": "Bob", "active": True},
    {"id": "3", "name": "Charlie", "active": False},
]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("greeting-server")

server = Server("greeting-server")

@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """
    List available resources.
    Each resource specifies its arguments using JSON Schema validation.
    """
    logger.info("handle_list_resources")

    return [
        # types.Resource(
        #     uri=AnyUrl("resource://wave"),
        #     description="A wave of greeting.",
        # ),
        types.Resource(
            uri=AnyUrl("data://users"),
            name="Users",
            description="A list of users.",
            mimeType="text/plain",
        ),
        # types.Resource(
        #     uri=AnyUrl("data://user/{user_id}"),
        #     description="A user by ID.",
        # ),
    ]

@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str | bytes | Iterable[types.TextResourceContents]:
    logger.info("handle_read_resource")
    if uri == "resource://wave":
        return "👋"
    elif uri == "data://users":
        return json.dumps(USERS)
    elif uri == "data://user/{user_id}":
        user_id = uri.split("/")[-1]
        user = next((user for user in USERS if user["id"] == user_id), None)
        return json.dumps(user) if user else ""
    else:
        raise ValueError(f"Unknown resource: {uri}")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    logger.info("handle_list_tools")

    return [
        types.Tool(
            name="greet",
            description="Greet someone by name",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                },
                "required": ["name"],
            },
        ),
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    Tools can modify server state and notify clients of changes.
    """
    logger.info("handle_call_tool")

    if name != "greet":
        raise ValueError(f"Unknown tool: {name}")

    if not arguments:
        raise ValueError("Missing arguments")

    name = arguments.get("name")
    return [
        types.TextContent(
            type="text",
            text=f"Hello, {name}!",
        )
    ]

sse = SseServerTransport("/messages/")

async def handle_sse(request):
    logger.info("handle_sse")

    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())

starlette_app = Starlette(
    debug=True,
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(starlette_app, host="0.0.0.0", port=8003)
