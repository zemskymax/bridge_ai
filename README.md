# Bridge AI
AI Agent collaboration space

## Overview
Bridge AI provides a proxy server based on the Model Context Protocol (MCP), enabling unified access to multiple FastMCP-compatible servers. It aggregates tools, resources, and prompts from several upstream servers, presenting them through a single API endpoint.

## Proxy Server: MultiFastMCP
The proxy server (`proxy_server.py`) acts as an aggregator for multiple FastMCPProxy instances (each pointing to a real FastMCP server). It exposes a unified API for tools, resources, and prompts, delegating requests to the appropriate upstream server.

### Features
- Aggregates multiple FastMCP-compatible servers
- Unified view of all tools, resources, and prompts
- Delegates execution and queries to the correct upstream server
- Supports MCP protocol (SSE endpoints)

## Usage

### Requirements
- Python 3.8+
- Dependencies listed in `pyproject.toml` (notably: `fastmcp`, `mcp`, `uvicorn`)

### Running the Proxy Server
By default, the proxy server connects to three upstream FastMCP servers (adjustable in code):
- `http://127.0.0.1:8003/sse`
- `http://127.0.0.1:8001/sse`
- `http://127.0.0.1:8002/sse`

To start the proxy server on port 9000:

```bash
python src/proxy_server.py
```

The server will attempt to connect to the upstream servers. If none are available, it will exit with an error.

### Configuration
To change the upstream servers, modify the `server_urls` list in `create_proxy_server()` inside `src/proxy_server.py`.

### Endpoints
- MCP-compatible SSE endpoint (default: `http://0.0.0.0:9000/sse`)
- All MCP protocol endpoints exposed by FastMCP

## Example
Start three FastMCP servers on ports 8001, 8002, and 8003, then run the proxy as above. All tools, resources, and prompts from the upstream servers will be accessible via the proxy’s API.

