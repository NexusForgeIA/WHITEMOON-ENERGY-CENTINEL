"""WHITEMOON-ENERGY-CENTINEL: panel público de energía en España (informativo). Datos: Red Eléctrica (REData); alertas calculadas por reglas sobre esos datos.
Python estándar, sin dependencias. Uso: python3 server.py --port 8080 ; RG_OFFLINE=1 para no consultar fuentes externas (pruebas)."""
import argparse
import json
import mimetypes
import os
import gzip
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import rules
import grid
import risk
import redata

ROOT = os.path.dirname(os.path.abspath(__file__))
RED = GRID = None


def load_case(cid):
    try:
        return json.load(open(os.path.join(ROOT, "data", f"case_{cid}.json"), encoding="utf-8"))
    except OSError:
        return None


def rule_alerts():
    if not RED:
        return []
    v = RED.view()
    sites = [p for p in (GRID.view().get("plants") if GRID else []) if p.get("g") == "nuclear"]
    try:
        return rules.evaluate(v.get("realtime"), v.get("systems"), RED.nuclear_series(), sites, time.time(), redata.madrid_now().date())
    except Exception:
        return []


def api(path, query):
    """Devuelve (status, objeto) o None si la ruta no es de la API."""
    if path == "/healthz":
        return 200, {"ok": True}
    if path == "/api/alertas":
        return 200, {"alerts": rule_alerts(), "rules": rules.RULES,
                     "source": "Reglas calculadas con datos de Red Eléctrica (REData). Informativo; sin datos por central o subestación."}
    if path == "/api/red":
        return 200, GRID.view() if GRID else {"plants": [], "lines": [], "subs": [], "status": {"state": "desactivado"}}
    if path == "/api/control":
        v = RED.view() if RED else {}
        return 200, risk.compute(v.get("realtime"), RED.price_now() if RED else None, rule_alerts())
    if path == "/api/sistemas":
        return 200, RED.view() if RED else {"systems": {}, "status": {"state": "desactivado"}}
    if path == "/api/resumen":
        v = RED.view() if RED else {}
        return 200, {"alerts": rule_alerts(), "rules": rules.RULES, "systems": v.get("systems"), "generation": v.get("generation"),
                     "realtime": v.get("realtime"), "history": v.get("history"), "prices": v.get("prices"), "status": v.get("status"), "now": int(time.time() * 1000)}
    if path.startswith("/api/caso/"):
        c = load_case(path.rsplit("/", 1)[-1])
        return (200, c) if c else (404, {"error": "caso no encontrado"})
    return None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj=None, raw=None, ctype="application/json; charset=utf-8"):
        body = raw if raw is not None else json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
        gz = len(body) > 4000 and "gzip" in (self.headers.get("Accept-Encoding") or "")
        if gz:
            body = gzip.compress(body, 6)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if raw is None else "public, max-age=300")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        r = api(u.path, urllib.parse.parse_qs(u.query))
        if r:
            return self._send(r[0], r[1])
        name = "index.html" if u.path in ("/", "/index.html") else u.path.lstrip("/")
        f = os.path.normpath(os.path.join(ROOT, "web", name))
        if not f.startswith(os.path.join(ROOT, "web")) or not os.path.isfile(f):
            return self._send(404, {"error": "no encontrado"})
        ct = mimetypes.guess_type(f)[0] or "application/octet-stream"
        return self._send(200, raw=open(f, "rb").read(), ctype=ct + ("; charset=utf-8" if ct.startswith("text/") else ""))


def main():
    global RED, GRID
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)))
    a = ap.parse_args()
    GRID = grid.Grid(cache=os.path.join(ROOT, "data", "grid_cache.json"), use_seed=True)
    RED = redata.RedData(cache=os.path.join(ROOT, "data", "redata_cache.json"))
    if os.environ.get("RG_OFFLINE") != "1":
        RED.start()
        GRID.start()
    else:
        GRID._set({"plants": [], "lines": [], "subs": []})
    print(f"WHITEMOON-ENERGY-CENTINEL en http://{a.host}:{a.port}")
    ThreadingHTTPServer((a.host, a.port), H).serve_forever()


if __name__ == "__main__":
    main()
