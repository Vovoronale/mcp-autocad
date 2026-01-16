import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

import pythoncom
import win32com.client

AUTOCAD_PROGID = os.getenv("AUTOCAD_PROGID", "AutoCAD.Application.25.1")
AUTOCAD_VISIBLE = os.getenv("AUTOCAD_VISIBLE", "1").lower() not in ("0", "false", "no")
HOST = os.getenv("BRIDGE_HOST", "127.0.0.1")
PORT = int(os.getenv("BRIDGE_PORT", "8765"))


def _to_variant_point(values):
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, values)


def _get_app():
    try:
        app = win32com.client.GetActiveObject(AUTOCAD_PROGID)
    except Exception:
        app = win32com.client.Dispatch(AUTOCAD_PROGID)
    app.Visible = AUTOCAD_VISIBLE
    return app


def _ensure_doc(app):
    if app.Documents.Count == 0:
        return app.Documents.Add()
    return app.ActiveDocument


def _ensure_layer(doc, name):
    try:
        return doc.Layers.Item(name)
    except Exception:
        return doc.Layers.Add(name)


def _normalize_point(values, *, name="point"):
    if not isinstance(values, list):
        raise ValueError(f"{name} must be a list.")
    if len(values) not in (2, 3):
        raise ValueError(f"{name} must be [x, y] or [x, y, z].")
    if len(values) == 2:
        values = [values[0], values[1], 0.0]
    return [float(v) for v in values]


def _apply_entity_props(doc, entity, payload):
    layer = payload.get("layer")
    if layer:
        _ensure_layer(doc, layer)
        entity.Layer = layer

    color = payload.get("color")
    if color is not None:
        entity.Color = int(color)


def _draw_line(payload):
    start = _normalize_point(payload.get("start"), name="start")
    end = _normalize_point(payload.get("end"), name="end")

    app = _get_app()
    doc = _ensure_doc(app)
    model_space = doc.ModelSpace

    line = model_space.AddLine(_to_variant_point(start), _to_variant_point(end))
    _apply_entity_props(doc, line, payload)

    doc.Regen(0)
    return {"handle": line.Handle}


def _draw_circle(payload):
    center = _normalize_point(payload.get("center"), name="center")
    radius = payload.get("radius")
    if radius is None:
        raise ValueError("radius is required.")
    radius = float(radius)

    app = _get_app()
    doc = _ensure_doc(app)
    model_space = doc.ModelSpace

    circle = model_space.AddCircle(_to_variant_point(center), radius)
    _apply_entity_props(doc, circle, payload)

    doc.Regen(0)
    return {"handle": circle.Handle}


def _draw_rectangle(payload):
    corner1 = _normalize_point(payload.get("corner1"), name="corner1")
    corner2 = _normalize_point(payload.get("corner2"), name="corner2")

    x1, y1, z1 = corner1
    x2, y2, z2 = corner2
    z = z1 if abs(z1 - z2) < 1e-9 else z1

    points = [
        [x1, y1, z],
        [x2, y1, z],
        [x2, y2, z],
        [x1, y2, z],
    ]
    payload = dict(payload)
    payload["points"] = points
    payload["closed"] = True
    return _draw_polyline(payload)


def _flatten_points(points):
    flat = []
    for pt in points:
        flat.extend(pt)
    return flat


def _draw_polyline(payload):
    points = payload.get("points")
    if not isinstance(points, list) or len(points) < 2:
        raise ValueError("points must be a list with at least 2 points.")
    normalized = [_normalize_point(p, name="point") for p in points]

    app = _get_app()
    doc = _ensure_doc(app)
    model_space = doc.ModelSpace

    has_z = any(abs(pt[2]) > 1e-9 for pt in normalized)
    polyline = None
    if has_z and hasattr(model_space, "Add3DPoly"):
        polyline = model_space.Add3DPoly(_to_variant_point(_flatten_points(normalized)))
    else:
        flat_2d = []
        for pt in normalized:
            flat_2d.extend([pt[0], pt[1]])
        polyline = model_space.AddLightWeightPolyline(_to_variant_point(flat_2d))

    if payload.get("closed"):
        try:
            polyline.Closed = True
        except Exception:
            pass

    _apply_entity_props(doc, polyline, payload)

    doc.Regen(0)
    return {"handle": polyline.Handle}


def _get_entities_by_handles(doc, payload):
    handles = payload.get("handles")
    if handles is None:
        handle = payload.get("handle")
        if handle is not None:
            handles = [handle]
    if not isinstance(handles, list) or not handles:
        raise ValueError("handles must be a non-empty list.")
    entities = []
    for handle in handles:
        if not isinstance(handle, str):
            raise ValueError("handle must be a string.")
        entities.append(doc.HandleToObject(handle))
    return entities


def _get_move_points(payload):
    if "delta" in payload:
        delta = _normalize_point(payload.get("delta"), name="delta")
        return [0.0, 0.0, 0.0], delta
    from_pt = _normalize_point(payload.get("from"), name="from")
    to_pt = _normalize_point(payload.get("to"), name="to")
    return from_pt, to_pt


def _copy_entities(payload):
    app = _get_app()
    doc = _ensure_doc(app)
    entities = _get_entities_by_handles(doc, payload)
    from_pt, to_pt = _get_move_points(payload)

    new_handles = []
    for ent in entities:
        new_ent = ent.Copy()
        new_ent.Move(_to_variant_point(from_pt), _to_variant_point(to_pt))
        new_handles.append(new_ent.Handle)

    doc.Regen(0)
    return {"handles": new_handles}


def _move_entities(payload):
    app = _get_app()
    doc = _ensure_doc(app)
    entities = _get_entities_by_handles(doc, payload)
    from_pt, to_pt = _get_move_points(payload)

    for ent in entities:
        ent.Move(_to_variant_point(from_pt), _to_variant_point(to_pt))

    doc.Regen(0)
    return {"handles": [ent.Handle for ent in entities]}


class BridgeHandler(BaseHTTPRequestHandler):
    def _send_json(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"ok": True})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        routes = {
            "/draw-line": _draw_line,
            "/draw-circle": _draw_circle,
            "/draw-rectangle": _draw_rectangle,
            "/draw-polyline": _draw_polyline,
            "/copy-entities": _copy_entities,
            "/move-entities": _move_entities,
        }
        if self.path not in routes:
            self._send_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(body) if body else {}
            result = routes[self.path](payload)
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})
            return
        self._send_json(200, result)

    def log_message(self, fmt, *args):
        sys.stdout.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))


def main():
    pythoncom.CoInitialize()
    server = HTTPServer((HOST, PORT), BridgeHandler)
    print(f"Host bridge listening on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
