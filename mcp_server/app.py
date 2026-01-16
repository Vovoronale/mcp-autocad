import json
import os
import urllib.request
from typing import List, Sequence

from mcp.server.fastmcp import FastMCP

BRIDGE_URL = os.getenv("BRIDGE_URL", "http://host.docker.internal:8765").rstrip("/")
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "18000"))

mcp = FastMCP("autocad-bridge", host=MCP_HOST, port=MCP_PORT)


def _get_asgi_app(transport: str, mount_path: str | None) -> object | None:
    if transport == "streamable-http":
        for attr in ("streamable_http_app",):
            if hasattr(mcp, attr):
                app_factory = getattr(mcp, attr)
                return app_factory() if callable(app_factory) else app_factory
    if transport == "sse":
        for attr in ("sse_app",):
            if hasattr(mcp, attr):
                app_factory = getattr(mcp, attr)
                if callable(app_factory):
                    try:
                        return app_factory(mount_path=mount_path)
                    except TypeError:
                        return app_factory()
                return app_factory

    # Fallback for older FastMCP versions
    for attr in ("app", "_app", "asgi_app", "_asgi_app"):
        if hasattr(mcp, attr):
            return getattr(mcp, attr)

    for meth in ("get_app", "get_asgi_app", "asgi"):
        if hasattr(mcp, meth) and callable(getattr(mcp, meth)):
            return getattr(mcp, meth)()

    return None


def _normalize_point(pt: Sequence[float]) -> List[float]:
    if len(pt) == 2:
        return [float(pt[0]), float(pt[1]), 0.0]
    if len(pt) == 3:
        return [float(pt[0]), float(pt[1]), float(pt[2])]
    raise ValueError("Point must be [x, y] or [x, y, z].")


def _call_bridge(path: str, payload: dict) -> dict:
    url = f"{BRIDGE_URL}{path}"
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
    return _call_bridge("/draw-line", payload)


@mcp.tool()
def draw_circle(center: list[float], radius: float, layer: str | None = None, color: int | None = None) -> dict:
    """Draw a circle in AutoCAD via the host bridge."""
    center_pt = _normalize_point(center)
    payload = {"center": center_pt, "radius": float(radius), "layer": layer, "color": color}
    return _call_bridge("/draw-circle", payload)


def _normalize_points(points: list[list[float]]) -> list[list[float]]:
    if not isinstance(points, list) or not points:
        raise ValueError("points must be a non-empty list of points.")
    return [_normalize_point(pt) for pt in points]


@mcp.tool()
def draw_polyline(
    points: list[list[float]],
    closed: bool | None = None,
    layer: str | None = None,
    color: int | None = None,
) -> dict:
    """Draw a polyline in AutoCAD via the host bridge."""
    payload = {"points": _normalize_points(points), "closed": bool(closed) if closed is not None else None}
    payload.update({"layer": layer, "color": color})
    return _call_bridge("/draw-polyline", payload)


@mcp.tool()
def draw_rectangle(
    corner1: list[float],
    corner2: list[float],
    layer: str | None = None,
    color: int | None = None,
) -> dict:
    """Draw an axis-aligned rectangle in AutoCAD via the host bridge."""
    payload = {"corner1": _normalize_point(corner1), "corner2": _normalize_point(corner2)}
    payload.update({"layer": layer, "color": color})
    return _call_bridge("/draw-rectangle", payload)


def _normalize_handles(handles: list[str] | str) -> list[str]:
    if isinstance(handles, str):
        return [handles]
    if not isinstance(handles, list) or not handles:
        raise ValueError("handles must be a non-empty list of strings.")
    return [str(h) for h in handles]


@mcp.tool()
def copy_entities(
    handles: list[str] | str,
    delta: list[float] | None = None,
    from_point: list[float] | None = None,
    to_point: list[float] | None = None,
) -> dict:
    """Copy entities by handle and move them by delta or from->to."""
    payload: dict = {"handles": _normalize_handles(handles)}
    if delta is not None:
        payload["delta"] = _normalize_point(delta, )
    elif from_point is not None and to_point is not None:
        payload["from"] = _normalize_point(from_point)
        payload["to"] = _normalize_point(to_point)
    else:
        raise ValueError("Provide delta or both from_point and to_point.")
    return _call_bridge("/copy-entities", payload)


@mcp.tool()
def move_entities(
    handles: list[str] | str,
    delta: list[float] | None = None,
    from_point: list[float] | None = None,
    to_point: list[float] | None = None,
) -> dict:
    """Move entities by handle using delta or from->to."""
    payload: dict = {"handles": _normalize_handles(handles)}
    if delta is not None:
        payload["delta"] = _normalize_point(delta)
    elif from_point is not None and to_point is not None:
        payload["from"] = _normalize_point(from_point)
        payload["to"] = _normalize_point(to_point)
    else:
        raise ValueError("Provide delta or both from_point and to_point.")
    return _call_bridge("/move-entities", payload)


@mcp.tool()
def bridge_health() -> dict:
    """Check the host bridge health."""
    url = f"{BRIDGE_URL}/health"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    host = MCP_HOST
    port = MCP_PORT
    mount_path = os.getenv("MCP_MOUNT_PATH")

    if transport in ("streamable-http", "sse"):
        import uvicorn

        asgi_app = _get_asgi_app(transport, mount_path)

        if asgi_app is None:
            raise RuntimeError("Cannot locate ASGI app inside FastMCP instance (unsupported FastMCP version).")

        uvicorn.run(asgi_app, host=host, port=port, log_level="info")
    else:
        mcp.run(transport=transport)
