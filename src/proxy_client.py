import asyncio
from fastmcp.client import Client
from fastmcp.client.transports import SSETransport


async def fetch_all_resources(proxy_url: str):
    print(f"Connecting to proxy server {proxy_url}...")
    client = Client(transport=SSETransport(proxy_url))
    async with client:
        print(f"Fetching data from proxy server {proxy_url}...")
        print("-------------")
        tools = await client.session.list_tools()
        print(f"Tools from proxy server {proxy_url}:")
        for tool in tools.tools:
            print(f"  Name: {tool.name}, Description: {tool.description}")

        prompts = await client.session.list_prompts()
        print(f"Prompts from proxy server {proxy_url}:")
        for prompt in prompts.prompts:
            print(f"  Name: {prompt.name}, Description: {prompt.description}")

        result = await client.session.list_resources()
        print(f"Resources from proxy server {proxy_url}:")
        for resource in result.resources:
            print(f"  URI: {resource.uri}, Name: {resource.name}, Description: {resource.description}")

if __name__ == "__main__":
    # Connect to the running MultiFastMCP server (default: localhost:9000)
    proxy_url = "http://127.0.0.1:9000/sse"
    asyncio.run(fetch_all_resources(proxy_url))
