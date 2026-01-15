import json
import os
import urllib.request
from typing import List, Sequence

from mcp.server.fastmcp import FastMCP

BRIDGE_URL = os.getenv("BRIDGE_URL", "http://host.docker.internal:8765").rstrip("/")

mcp = FastMCP("autocad-bridge")


def _normalize_point(pt: Sequence[float]) -> List[float]:
    if len(pt) == 2:
        return [float(pt[0]), float(pt[1]), 0.0]
    if len(pt) == 3:
        return [float(pt[0]), float(pt[1]), float(pt[2])]
    raise ValueError("Point must be [x, y] or [x, y, z].")


def _call_bridge(payload: dict) -> dict:
    url = f"{BRIDGE_URL}/draw-line"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


@mcp.tool()
def draw_line(start: list[float], end: list[float], layer: str | None = None, color: int | None = None) -> dict:
    """Draw a line in AutoCAD via the host bridge."""
    start_pt = _normalize_point(start)
    end_pt = _normalize_point(end)
    payload = {"start": start_pt, "end": end_pt, "layer": layer, "color": color}
    return _call_bridge(payload)


@mcp.tool()
def bridge_health() -> dict:
    """Check the host bridge health."""
    url = f"{BRIDGE_URL}/health"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


if __name__ == "__main__":
    mcp.run()
