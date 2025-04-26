import asyncio
from fastmcp.client import Client
from fastmcp.client.transports import SSETransport

async def fetch_all_resources(proxy_url: str):
    client = Client(transport=SSETransport(proxy_url))
    async with client:
        # List all resources using the MCP protocol
        result = await client.session.list_resources()
        print(f"Resources from proxy server {proxy_url}:")
        for resource in result.resources:
            print(f"  URI: {resource.uri}, Name: {resource.name}, Description: {resource.description}")

if __name__ == "__main__":
    # Connect to the running MultiUpstreamProxy (default: localhost:9000)
    proxy_url = "http://127.0.0.1:9000/sse"
    asyncio.run(fetch_all_resources(proxy_url))
