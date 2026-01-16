# mcp-autocad

MCP server in Docker -> Windows host bridge -> AutoCAD 2026 COM automation.

## What this does
- The MCP server runs in Docker and forwards tool calls to a local HTTP bridge.
- The bridge runs on Windows and talks to AutoCAD through COM.
- AutoCAD must be running in your interactive desktop session.

## Prereqs
- AutoCAD 2026 installed (ProgID: AutoCAD.Application.25.1)
- Docker Desktop installed and running
- Python 3.11+ on the host
- pip available for Python
- Internet access only needed for first-time pip install
- Optional: cloudflared (only for ChatGPT or any public tunnel)

## 1) Host bridge (required for both Codex and ChatGPT)

### 1.1 Install host bridge dependencies (one-time)

```
python -m pip install -r host_bridge\requirements.txt
```

### 1.2 Start AutoCAD and open a drawing
- Launch AutoCAD 2026 normally.
- If no drawing is open, create a new one (any template).

### 1.3 Start the host bridge

```
python host_bridge\server.py
```

You should see: `Host bridge listening on http://127.0.0.1:8765`

### 1.4 Optional: verify health

```
Invoke-RestMethod http://127.0.0.1:8765/health
```

Expected: `{"ok": true}`

## 2) Build the MCP server image (one-time or after code changes)

```
docker build -t mcp-autocad .
```

## 3) Use with Codex (local, stdio)
Codex uses stdio, so no port or tunnel is required.

### 3.1 Register the server in Codex
PowerShell line continuation uses the backtick (`). You can also paste the command as a single line.

```
codex mcp add autocad -- docker run --rm -i `
  -e BRIDGE_URL=http://host.docker.internal:8765 `
  mcp-autocad
```

### 3.2 Use the tool (example)

```
{"tool": "draw_line", "arguments": {"start": [0, 0, 0], "end": [100, 0, 0], "layer": "TEST", "color": 1}}
```

## 4) Use with ChatGPT (Custom Tool)
ChatGPT requires a public HTTPS MCP endpoint. `localhost` will not work.

Pick one transport mode and use the matching URL path in ChatGPT:
- streamable-http -> `/mcp`
- sse -> `/sse`

### 4.1 Streamable HTTP (recommended)
Example: run it on port 8010 to avoid 8000/8007/8009 and match your tunnel config below.

```
docker run --rm -p 8010:8010 `
  -e BRIDGE_URL=http://host.docker.internal:8765 `
  -e MCP_TRANSPORT=streamable-http `
  -e MCP_HOST=0.0.0.0 `
  -e MCP_PORT=8010 `
  mcp-autocad
```

Local URL: `http://localhost:8010/mcp`
Public URL (tunnel): `https://ac.dbnassistant.com/mcp`

### 4.2 SSE (only if your ChatGPT UI explicitly expects /sse)

```
docker run --rm -p 8010:8010 `
  -e BRIDGE_URL=http://host.docker.internal:8765 `
  -e MCP_TRANSPORT=sse `
  -e MCP_HOST=0.0.0.0 `
  -e MCP_PORT=8010 `
  mcp-autocad
```

Local URL: `http://localhost:8010/sse`
Public URL (tunnel): `https://ac.dbnassistant.com/sse`

### 4.3 Create the tool in ChatGPT
- Name: AutoCAD Bridge (or any name you want)
- Description: Draw lines in AutoCAD 2026 via a local MCP server
- MCP Server URL: use the public HTTPS URL from above
- Authentication: None
- Accept the warning and click Create

## 5) Cloudflare Tunnel example (matches your config)
If you already have this tunnel, use `ac.dbnassistant.com` for the MCP server.

```
tunnel: normcontrol-tunnel
credentials-file: C:\Users\V\.cloudflared\ed89973a-7222-49bc-889a-fec095457fba.json

ingress:
  - hostname: ac.dbnassistant.com
    service: http://127.0.0.1:8010

  - service: http_status:404
```

Run the tunnel (example; adjust config path if needed):

```
cloudflared tunnel run normcontrol-tunnel
```

Note: Only the MCP server needs to be public. The host bridge (`:8765`) can stay local.

## 6) Stop services
- Stop the host bridge with Ctrl+C in its PowerShell window.
- Stop any running containers with Ctrl+C.

## 7) Restart everything (PowerShell)
This restarts the host bridge and the MCP HTTP container used by ChatGPT.

Quick start:

```
.\scripts\restart-all.ps1
```

Inline version:

```
docker stop mcp-autocad-http 2>$null | Out-Null

Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*host_bridge\\server.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

$workdir = "C:\Users\V\Desktop\mcp-autocad"
$out = Join-Path $workdir "host_bridge\bridge.out.log"
$err = Join-Path $workdir "host_bridge\bridge.err.log"
Start-Process -FilePath python -ArgumentList "host_bridge\server.py" `
  -WorkingDirectory $workdir `
  -RedirectStandardOutput $out `
  -RedirectStandardError $err `
  -WindowStyle Hidden

docker run --rm -d --name mcp-autocad-http -p 8010:8010 `
  -e MCP_PORT=8010 `
  -e MCP_HOST=0.0.0.0 `
  -e MCP_TRANSPORT=streamable-http `
  -e BRIDGE_URL=http://host.docker.internal:8765 `
  mcp-autocad
```

## Optional configuration

Host bridge env vars:
- AUTOCAD_PROGID (default AutoCAD.Application.25.1)
- AUTOCAD_VISIBLE (default 1)
- BRIDGE_HOST (default 127.0.0.1)
- BRIDGE_PORT (default 8765)

MCP server env vars:
- BRIDGE_URL (default http://host.docker.internal:8765)
- MCP_TRANSPORT (stdio, sse, streamable-http; default stdio)
- MCP_HOST (default 0.0.0.0)
- MCP_PORT (default 18000)

## Troubleshooting
- If the bridge cannot connect to AutoCAD, ensure AutoCAD is running in your current desktop session.
- If you get COM errors, close AutoCAD and restart the bridge.
- If Docker cannot reach the bridge, confirm `host.docker.internal` works in Docker Desktop on Windows.
- If ChatGPT cannot connect, verify the tunnel is running and the public URL includes the right path (`/mcp` or `/sse`).
