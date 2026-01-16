param(
  [int]$Port = 8010
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$out = Join-Path $repoRoot "host_bridge\\bridge.out.log"
$err = Join-Path $repoRoot "host_bridge\\bridge.err.log"

docker stop mcp-autocad-http 2>$null | Out-Null
docker rm mcp-autocad-http 2>$null | Out-Null

Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like "*host_bridge\\server.py*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Start-Process -FilePath python -ArgumentList "host_bridge\\server.py" `
  -WorkingDirectory $repoRoot `
  -RedirectStandardOutput $out `
  -RedirectStandardError $err `
  -WindowStyle Hidden

docker run --rm -d --name mcp-autocad-http -p "$Port`:$Port" `
  -e "MCP_PORT=$Port" `
  -e MCP_HOST=0.0.0.0 `
  -e MCP_TRANSPORT=streamable-http `
  -e BRIDGE_URL=http://host.docker.internal:8765 `
  mcp-autocad
