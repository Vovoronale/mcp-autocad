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


def _draw_line(payload):
    start = payload.get("start")
    end = payload.get("end")
    if not isinstance(start, list) or not isinstance(end, list):
        raise ValueError("start and end must be lists.")
    if len(start) not in (2, 3) or len(end) not in (2, 3):
        raise ValueError("start and end must be [x, y] or [x, y, z].")
    if len(start) == 2:
        start = [start[0], start[1], 0.0]
    if len(end) == 2:
        end = [end[0], end[1], 0.0]
    start = [float(v) for v in start]
    end = [float(v) for v in end]

    app = _get_app()
    doc = _ensure_doc(app)
    model_space = doc.ModelSpace

    line = model_space.AddLine(_to_variant_point(start), _to_variant_point(end))

    layer = payload.get("layer")
    if layer:
        _ensure_layer(doc, layer)
        line.Layer = layer

    color = payload.get("color")
    if color is not None:
        line.Color = int(color)

    doc.Regen(0)
    return {"handle": line.Handle}


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
        if self.path != "/draw-line":
            self._send_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(body) if body else {}
            result = _draw_line(payload)
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
