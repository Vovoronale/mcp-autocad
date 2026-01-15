# mcp-autocad

MCP server in Docker -> host bridge on Windows -> AutoCAD 2026 COM automation.

## What this does
- The MCP server runs in Docker and forwards tool calls to a local HTTP bridge.
- The bridge runs on Windows and talks to AutoCAD through COM.
- AutoCAD must be running in the interactive desktop session.

## Prereqs
- AutoCAD 2026 installed (ProgID: AutoCAD.Application.25.1)
- Docker Desktop installed and running
- Python 3.11+ on the host
- pip available for Python
- Internet access only needed for first-time pip install

## Step-by-step setup and run

### 0) Open a PowerShell in the repo

```
cd C:\Users\V\Desktop\mcp-autocad
```

### 1) Install host bridge dependencies (one-time)

```
python -m pip install -r host_bridge\requirements.txt
```

### 2) Start AutoCAD and open a drawing
- Launch AutoCAD 2026 normally.
- If no drawing is open, create a new one (any template).

### 3) Start the host bridge

```
python host_bridge\server.py
```

You should see: "Host bridge listening on http://127.0.0.1:8765"

### 4) Verify the bridge health (optional)

```
Invoke-RestMethod http://127.0.0.1:8765/health
```

Expected: {"ok": true}

### 5) Build the MCP server image (one-time or after code changes)

```
docker build -t mcp-autocad .
```

### 6) Register the MCP server in Codex

```
codex mcp add autocad -- docker run --rm -i -e BRIDGE_URL=http://host.docker.internal:8765 mcp-autocad
```

This stores the MCP server config in Codex. Codex will run the container when needed.

### 7) Use the tool (example)

```
{"tool": "draw_line", "arguments": {"start": [0, 0, 0], "end": [100, 0, 0], "layer": "TEST", "color": 1}}
```

### 8) Stop services
- Stop the host bridge with Ctrl+C in its PowerShell window.
- If you manually started a container, stop it with Ctrl+C or `docker stop`.

## ChatGPT setup (Custom Tool)
ChatGPT expects a streamable HTTP MCP endpoint, not stdio.

### 1) Run the MCP server in streamable HTTP mode

```
docker run --rm -p 18000:18000 ^
  -e BRIDGE_URL=http://host.docker.internal:8765 ^
  -e MCP_TRANSPORT=streamable-http ^
  -e MCP_HOST=0.0.0.0 ^
  -e MCP_PORT=18000 ^
  mcp-autocad
```

The MCP server URL will be:

```
http://localhost:18000/mcp
```

### 2) Create the tool in ChatGPT
- Name: AutoCAD Bridge (or any name you want)
- Description: Draw lines in AutoCAD 2026 via a local MCP server
- MCP Server URL: `http://localhost:18000/mcp`
- Authentication: None
- Accept the warning and click Create

### 3) If ChatGPT cannot reach localhost
ChatGPT web calls the MCP server from OpenAI's servers, so localhost will not work.
Use a tunnel (ngrok, cloudflared, or similar) to expose port 18000, then use the
public HTTPS URL with `/mcp` in the MCP Server URL field.

## Optional configuration
Environment variables for the host bridge:
- AUTOCAD_PROGID (default AutoCAD.Application.25.1)
- AUTOCAD_VISIBLE (default 1)
- BRIDGE_HOST (default 127.0.0.1)
- BRIDGE_PORT (default 8765)

Environment variables for the MCP server:
- BRIDGE_URL (default http://host.docker.internal:8765)
- MCP_TRANSPORT (stdio, sse, streamable-http; default stdio)
- MCP_HOST (default 127.0.0.1)
- MCP_PORT (default 8000; override if 8000 is busy)
- MCP_MOUNT_PATH (optional; only used for SSE)

## Troubleshooting
- If the bridge cannot connect to AutoCAD, ensure AutoCAD is running in your current desktop session.
- If you get COM errors, try closing AutoCAD and restarting the bridge.
- If Docker cannot reach the bridge, confirm host.docker.internal works in Docker Desktop on Windows.
