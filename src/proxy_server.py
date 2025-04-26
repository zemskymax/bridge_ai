import asyncio
from typing import Any, Dict, Optional
from fastmcp.server.proxy import ProxyTool, FastMCPProxy
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.client.transports import SSETransport
from mcp.shared.exceptions import McpError
from mcp.types import GetPromptResult, TextContent, ImageContent, EmbeddedResource
from mcp.server.lowlevel.helper_types import ReadResourceContents
from pydantic.networks import AnyUrl
from fastmcp.prompts import Prompt
from fastmcp.resources import Resource, ResourceTemplate
from fastmcp.tools.tool import Tool
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


# all_from_real_server remains the same as in the original proxy_server.py
async def all_from_real_server(client: "Client") -> list["ProxyTool"]:
    async with client:
        result = await client.session.list_tools()
        return [
            await ProxyTool.from_client(client, tool)
            for tool in result.tools
        ]

class MultiFastMCP(FastMCP):
    """
    FastMCP-compatible proxy that aggregates multiple FastMCPProxy instances (one per real server).
    It presents a unified view of tools, resources, and prompts, and delegates
    execution requests to the appropriate upstream server.
    Supports the MCP protocol (SSE/WS endpoints).
    """
    def __init__(self, proxies: list[FastMCPProxy], name="MultiFastMCP"):
        """
        Initializes the MultiFastMCP.

        Args:
            proxies: A list of FastMCPProxy instances, each connected to an upstream server.
            name: The name for this aggregating proxy server.
        """
        super().__init__(name)

        if not proxies:
            logger.warning("MultiFastMCP initialized with no upstream proxies.")
        self.proxies: list[FastMCPProxy] = proxies

        # Internal caches and maps to track which proxy owns which item
        self._tool_map: Optional[Dict[str, FastMCPProxy]] = None
        self._resource_map: Optional[Dict[str, FastMCPProxy]] = None
        self._prompt_map: Optional[Dict[str, FastMCPProxy]] = None
        self._resource_template_map: Optional[Dict[str, FastMCPProxy]] = None # Added for templates

        # Aggregated views (cached after first calculation)
        self._aggregated_tools: Optional[Dict[str, Tool]] = None
        self._aggregated_resources: Optional[Dict[str, Resource]] = None
        self._aggregated_prompts: Optional[Dict[str, Prompt]] = None
        self._aggregated_resource_templates: Optional[Dict[str, ResourceTemplate]] = None # Added

        # Locks to prevent race conditions during map/cache population
        self._tools_lock = asyncio.Lock()
        self._resources_lock = asyncio.Lock()
        self._prompts_lock = asyncio.Lock()
        self._templates_lock = asyncio.Lock() # Added

    async def _build_tool_map(self):
        """Builds the map of tool names to the proxy that provides them."""
        async with self._tools_lock:
            if self._tool_map is not None:
                return

            logger.info("Building tool map for MultiFastMCP...")
            tool_map: Dict[str, FastMCPProxy] = {}
            aggregated_tools: Dict[str, Tool] = {}
            tasks = [proxy.get_tools() for proxy in self.proxies]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                proxy = self.proxies[i]
                if isinstance(result, Exception):
                    logger.error(f"Failed to get tools from proxy {proxy.name} (client: {proxy.client.transport.base_url}): {result}")
                    continue
                if isinstance(result, dict):
                    for tool_name, tool_instance in result.items():
                        if tool_name in tool_map:
                            logger.warning(f"Tool name conflict: '{tool_name}' exists on multiple upstream servers. Using the one from {proxy.name}.")
                        tool_map[tool_name] = proxy
                        aggregated_tools[tool_name] = tool_instance # Use the actual Tool instance
                else:
                     logger.error(f"Unexpected result type {type(result)} when getting tools from proxy {proxy.name}")

            self._tool_map = tool_map
            self._aggregated_tools = aggregated_tools
            logger.info(f"Tool map built. Found {len(self._tool_map)} unique tools.")

    async def get_tools(self) -> dict[str, Tool]:
        """Gets aggregated tools, building the internal map if needed."""
        if self._tool_map is None:
            await self._build_tool_map()
        # Ensure map and cache are not None after build attempt
        return self._aggregated_tools if self._aggregated_tools is not None else {}

    async def _build_resource_map(self):
        """Builds the map of resource URIs/template URIs to the proxy that provides them."""
        async with self._resources_lock:
            if self._resource_map is not None:
                return

            logger.info("Building resource map for MultiFastMCP...")
            resource_map: Dict[str, FastMCPProxy] = {}
            aggregated_resources: Dict[str, Resource] = {}
            tasks = [proxy.get_resources() for proxy in self.proxies]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                logger.debug(f"Processing resources from proxy {self.proxies[i].name}...")
                proxy = self.proxies[i]
                if isinstance(result, Exception):
                    logger.error(f"Failed to get resources from proxy {proxy.name}: {result}")
                    for exc in result.exceptions:
                        logger.error("TaskGroup sub-exception: %s", exc, exc_info=True)
                    continue
                if isinstance(result, dict):
                    for res_uri, res_instance in result.items():
                        if res_uri in resource_map:
                            logger.warning(f"Resource URI conflict: '{res_uri}' exists on multiple upstream servers. Using the one from {proxy.name}.")
                        resource_map[res_uri] = proxy
                        aggregated_resources[res_uri] = res_instance
                else:
                    logger.error(f"Unexpected result type {type(result)} when getting resources from proxy {proxy.name}")

            self._resource_map = resource_map
            self._aggregated_resources = aggregated_resources
            logger.info(f"Resource map built. Found {len(self._resource_map)} unique resources.")

        # --- Also build resource template map ---
        async with self._templates_lock:
            if self._resource_template_map is not None:
                return

            logger.info("Building resource template map for MultiFastMCP...")
            template_map: Dict[str, FastMCPProxy] = {}
            aggregated_templates: Dict[str, ResourceTemplate] = {}
            tasks_templates = [proxy.get_resource_templates() for proxy in self.proxies]
            results_templates = await asyncio.gather(*tasks_templates, return_exceptions=True)

            for i, result in enumerate(results_templates):
                proxy = self.proxies[i]
                if isinstance(result, Exception):
                    logger.error(f"Failed to get resource templates from proxy {proxy.name}: {result}")
                    continue
                if isinstance(result, dict):
                    for template_uri, template_instance in result.items():
                        if template_uri in template_map:
                            logger.warning(f"Resource template URI conflict: '{template_uri}' exists on multiple upstream servers. Using the one from {proxy.name}.")
                        template_map[template_uri] = proxy
                        aggregated_templates[template_uri] = template_instance
                else:
                     logger.error(f"Unexpected result type {type(result)} when getting resource templates from proxy {proxy.name}")

            self._resource_template_map = template_map
            self._aggregated_resource_templates = aggregated_templates
            logger.info(f"Resource template map built. Found {len(self._resource_template_map)} unique templates.")


    async def get_resources(self) -> dict[str, Resource]:
        """Gets aggregated resources, building the internal map if needed."""
        if self._resource_map is None:
            await self._build_resource_map()
        return self._aggregated_resources if self._aggregated_resources is not None else {}

    async def get_resource_templates(self) -> dict[str, ResourceTemplate]:
        """Gets aggregated resource templates, building the internal map if needed."""
        # Ensure the main resource map build runs first, as it includes templates
        if self._resource_template_map is None:
             await self._build_resource_map() # This function now builds both maps
        return self._aggregated_resource_templates if self._aggregated_resource_templates is not None else {}


    async def _build_prompt_map(self):
        """Builds the map of prompt names to the proxy that provides them."""
        async with self._prompts_lock:
            # Double check locking pattern
            if self._prompt_map is not None:
                return

            logger.info("Building prompt map for MultiFastMCP...")
            prompt_map: Dict[str, FastMCPProxy] = {}
            aggregated_prompts: Dict[str, Prompt] = {}
            tasks = [proxy.get_prompts() for proxy in self.proxies]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                proxy = self.proxies[i]
                if isinstance(result, Exception):
                    logger.error(f"Failed to get prompts from proxy {proxy.name}: {result}")
                    continue
                if isinstance(result, dict):
                    for prompt_name, prompt_instance in result.items():
                        if prompt_name in prompt_map:
                            logger.warning(f"Prompt name conflict: '{prompt_name}' exists on multiple upstream servers. Using the one from {proxy.name}.")
                        prompt_map[prompt_name] = proxy
                        aggregated_prompts[prompt_name] = prompt_instance
                else:
                     logger.error(f"Unexpected result type {type(result)} when getting prompts from proxy {proxy.name}")

            self._prompt_map = prompt_map
            self._aggregated_prompts = aggregated_prompts
            logger.info(f"Prompt map built. Found {len(self._prompt_map)} unique prompts.")

    async def get_prompts(self) -> dict[str, Prompt]:
        """Gets aggregated prompts, building the internal map if needed."""
        if self._prompt_map is None:
            await self._build_prompt_map()
        return self._aggregated_prompts if self._aggregated_prompts is not None else {}

    # --- MCP Method Implementations ---

    async def _mcp_call_tool(
        self, key: str, arguments: dict[str, Any]
    ) -> list[TextContent | ImageContent | EmbeddedResource]:
        """Finds the correct upstream proxy and delegates the tool call."""
        if self._tool_map is None:
            await self._build_tool_map() # Ensure map is built

        if self._tool_map is None: # Check again after build attempt
             raise McpError(f"Tool map could not be built.")

        target_proxy = self._tool_map.get(key)
        if target_proxy:
            logger.debug(f"Delegating tool call '{key}' to proxy {target_proxy.name}")
            # Delegate to the specific proxy's _mcp_call_tool method
            # The FastMCPProxy._mcp_call_tool already handles calling the client
            return await target_proxy._mcp_call_tool(key, arguments)
        else:
            logger.error(f"Tool '{key}' not found on any upstream server.")
            # Raise McpError as expected by MCP if the tool isn't found
            raise McpError(f"Unknown tool: {key}")

    async def _mcp_read_resource(self, uri: AnyUrl | str) -> list[ReadResourceContents]:
        """Finds the correct upstream proxy and delegates the resource read."""
        uri_str = str(uri) # Ensure we have a string for map lookup

        # Check exact match in static resources first
        if self._resource_map is None:
            await self._build_resource_map() # Builds both resource and template maps

        if self._resource_map is None: # Check again after build attempt
             raise McpError(f"Resource map could not be built.")

        target_proxy = self._resource_map.get(uri_str)
        if target_proxy:
            logger.debug(f"Delegating resource read '{uri_str}' to proxy {target_proxy.name}")
            return await target_proxy._mcp_read_resource(uri)

        # If not found in static resources, check templates
        if self._resource_template_map is None:
             # This should have been built by _build_resource_map already, but check just in case
             await self._build_resource_map()

        if self._resource_template_map is None: # Check again
             raise McpError(f"Resource template map could not be built.")

        # Find a matching template
        # This requires iterating and checking if the URI matches a template pattern.
        # The base FastMCP server handles this matching logic internally using registered templates.
        # We need to find the proxy that *owns* the matching template.
        matching_template_proxy: Optional[FastMCPProxy] = None
        matching_template_uri: Optional[str] = None

        # Iterate through the templates registered *on this multi-proxy*
        # which are actually the aggregated templates from upstream
        aggregated_templates = await self.get_resource_templates()
        for template_uri, template_instance in aggregated_templates.items():
             if template_instance.matches(uri_str):
                 # Now find which *upstream* proxy owns this template_uri
                 proxy_owner = self._resource_template_map.get(template_uri)
                 if proxy_owner:
                     matching_template_proxy = proxy_owner
                     matching_template_uri = template_uri # Store the template URI for logging
                     break # Found the first match
                 else:
                     # This case should ideally not happen if maps are built correctly
                     logger.error(f"Found matching template '{template_uri}' but couldn't find its owning proxy!")


        if matching_template_proxy and matching_template_uri:
            logger.debug(f"Delegating resource read '{uri_str}' (matching template '{matching_template_uri}') to proxy {matching_template_proxy.name}")
            # Delegate to the proxy that owns the template
            return await matching_template_proxy._mcp_read_resource(uri)
        else:
            logger.error(f"Resource URI '{uri_str}' not found as static resource or matching template on any upstream server.")
            raise McpError(f"Unknown resource: {uri_str}")


    async def _mcp_get_prompt(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> GetPromptResult:
        """Finds the correct upstream proxy and delegates the prompt rendering."""
        if self._prompt_map is None:
            await self._build_prompt_map() # Ensure map is built

        if self._prompt_map is None: # Check again after build attempt
             raise McpError(f"Prompt map could not be built.")

        target_proxy = self._prompt_map.get(name)
        if target_proxy:
            logger.debug(f"Delegating prompt render '{name}' to proxy {target_proxy.name}")
            # Delegate to the specific proxy's _mcp_get_prompt method
            return await target_proxy._mcp_get_prompt(name, arguments)
        else:
            logger.error(f"Prompt '{name}' not found on any upstream server.")
            raise McpError(f"Unknown prompt: {name}")

# --- Server Setup and Running Logic --- (from original proxy_server.py)

async def create_proxy_server():
    """Create and return a FastMCP-compatible proxy that aggregates multiple FastMCPProxy instances."""
    # Example: Assume 3 real FastMCP servers are running on ports 8001, 8002, 8003
    # In a real scenario, these would likely be separate processes/machines.
    # For testing, you might need to run instances of a simple FastMCP server on these ports.
    server_urls = [
        "http://127.0.0.1:8003/sse",
        "http://127.0.0.1:8001/sse",
        "http://127.0.0.1:8002/sse",
    ]
    proxies = []
    print("Attempting to connect to upstream servers:")
    for url in server_urls:
        print(f" - {url}")
        # Use a timeout for client creation to avoid hanging indefinitely
        try:
            # Note: SSETransport might need adjustments based on actual server capabilities (WS?)
            client = Client(transport=SSETransport(url))
            # FastMCPProxy.from_client is now implicitly handled by FastMCPProxy's init/methods
            # We just need the client instance for the FastMCPProxy
            # The FastMCPProxy itself needs to be initialized, not just created from client
            # Let's assume FastMCPProxy can take a client directly or we adapt its creation
            # Looking at the provided proxy.py, FastMCPProxy takes client in __init__
            proxy_instance = FastMCPProxy(client=client, name=f"ProxyToServerAt-{url}") # Give distinct names
            proxies.append(proxy_instance)
            print(f"   ... Connected to {url}")
        except Exception as e:
            print(f"   ... FAILED to connect to {url}: {e}")
            # Decide if you want to continue without this server or fail entirely
            # continue

    if not proxies:
         print("\nERROR: No upstream servers could be connected. Exiting.")
         exit(1) # Or raise an exception

    print(f"\nSuccessfully connected to {len(proxies)} upstream servers.")
    return MultiFastMCP(proxies)


def run_proxy_server():
    try:
        proxy_server = asyncio.run(create_proxy_server())
        print(f"\nStarting {proxy_server.name} server on http://0.0.0.0:9000 ...")
        asyncio.run(proxy_server.run_sse_async(host="0.0.0.0", port=9000))
    except Exception as e:
        print(f"\nAn error occurred during server setup or run: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_proxy_server()
