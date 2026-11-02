"""Centrales y red de transporte de España desde OpenStreetMap (Overpass), con caché en disco.

- Centrales: power=plant (fuente plant:source, potencia plant:output:electricity).
- Líneas: power=line de 200 kV o más (400 kV y 220 kV).
- Subestaciones: power=substation de 300 kV o más.
Informativo: OSM es colaborativo, no es el inventario oficial de Red Eléctrica; faltan o sobran elementos."""
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request

ENDPOINTS = ["https://overpass.openstreetmap.fr/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
             "https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
# Península + Baleares + Canarias, en teselas (sur, oeste, norte, este)
STEP = 2.0
BOXES = [(36.0, -9.5, 44.0, 3.5), (38.5, 1.0, 40.2, 4.5), (27.4, -18.4, 29.5, -13.2)]
TOL = 0.0008           # ~90 m en grados
TTL_S = 30 * 86400

SRC = {"nuclear": "nuclear", "hydro": "hidraulica", "water": "hidraulica", "pumped_storage": "hidraulica", "wind": "eolica",
       "solar": "solar", "gas": "termica", "coal": "termica", "oil": "termica", "diesel": "termica", "waste": "termica",
       "biomass": "otras", "biogas": "otras", "geothermal": "otras", "tidal": "otras", "wave": "otras", "battery": "otras"}
NOMBRE = {"nuclear": "Nuclear", "hidraulica": "Hidráulica", "termica": "Térmica (gas, carbón, fuel)", "eolica": "Eólica", "solar": "Solar", "otras": "Otras"}


def tiles():
    for (s0, w0, n0, e0) in BOXES:
        la = s0
        while la < n0:
            lo = w0
            while lo < e0:
                yield (la, lo, min(la + STEP, n0), min(lo + STEP, e0))
                lo += STEP
            la += STEP


def query(b):
    bb = "(%s,%s,%s,%s)" % b
    return ('[out:json][timeout:90];'
            f'nwr["power"="plant"]{bb};out center tags qt;'
            f'way["power"="line"]["voltage"~"^[2-9][0-9]{{5}}"]{bb};out tags geom qt;'
            f'nwr["power"="substation"]["voltage"~"^[3-9][0-9]{{5}}"]{bb};out center tags qt;')


def mw_of(v):
    """'1003 MW', '1.2 GW', '500 kW', '24;30 MW' -> MW (float) o None."""
    if not v:
        return None
    txt = str(v).strip()
    m = re.match(r"\s*([\d.,]+)", txt)
    if not m:
        return None
    um = re.search(r"(GW|MW|kW|W)\b", txt, re.I)
    try:
        x = float(m.group(1).replace(",", "."))
    except ValueError:
        return None
    u = (um.group(1) if um else "W").lower()
    return round(x * {"gw": 1000, "mw": 1, "kw": 1e-3, "w": 1e-6}[u], 3)


def kv_of(v):
    """Mayor tensión de 'voltage' en kV (puede venir '400000;220000')."""
    best = 0
    for p in str(v or "").split(";"):
        try:
            best = max(best, int(float(p)))
        except ValueError:
            pass
    return best // 1000


def src_of(t):
    s = (t.get("plant:source") or t.get("generator:source") or "").split(";")[0].strip().lower()
    return SRC.get(s), s


def simplify(pts, tol=TOL):
    """Douglas-Peucker iterativo sobre [(lat,lon)]."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ay, ax), (by, bx) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        L = (dx * dx + dy * dy) ** .5 or 1e-12
        far, fi = -1.0, -1
        for i in range(a + 1, b):
            d = abs(dy * (pts[i][1] - ax) - dx * (pts[i][0] - ay)) / L
            if d > far:
                far, fi = d, i
        if far > tol:
            keep[fi] = True
            stack += [(a, fi), (fi, b)]
    return [p for p, k in zip(pts, keep) if k]


def _centre(e):
    c = e.get("center") or e
    if "lat" in c and "lon" in c:
        return round(c["lat"], 4), round(c["lon"], 4)
    return None


def reduce(elements, plants, lines, subs):
    """Acumula en los dicts (dedupe entre teselas por tipo+id)."""
    for e in elements:
        t = e.get("tags") or {}
        key = f'{e.get("type")}{e.get("id")}'
        p = t.get("power") or t.get("disused:power")
        if e.get("type") == "way" and t.get("power") == "line" and e.get("geometry"):
            kv = kv_of(t.get("voltage"))
            if kv < 200 or key in lines:
                continue
            pts = simplify([(round(g["lat"], 4), round(g["lon"], 4)) for g in e["geometry"]])
            if len(pts) >= 2:
                lines[key] = {"kv": kv, "p": [[a, b] for a, b in pts]}
        elif t.get("power") == "substation":
            c = _centre(e)
            kv = kv_of(t.get("voltage"))
            if c and kv >= 300 and key not in subs:
                subs[key] = {"n": t.get("name") or "", "kv": kv, "c": list(c)}
        elif p == "plant":
            c = _centre(e)
            grp, raw = src_of(t)
            if not c or key in plants:
                continue
            mw = mw_of(t.get("plant:output:electricity")) or mw_of(t.get("generator:output:electricity"))
            off = bool(t.get("disused") or t.get("disused:power") or t.get("abandoned") or t.get("construction"))
            # Solo se guardan las que se ven y aportan: nuclear/hidro/térmicas siempre; eólica/solar/otras si pasan de 20 MW
            if grp in (None,):
                continue
            if grp not in ("nuclear", "hidraulica", "termica") and (mw is None or mw < 20):
                continue
            plants[key] = {"n": t.get("name") or t.get("name:es") or "", "g": grp, "s": raw, "mw": mw, "op": t.get("operator") or "",
                           "c": list(c), "off": off, "y": (t.get("start_date") or "")[:4]}


def seed():
    """Centrales nucleares (datos propios, públicos). Se muestran aunque OSM no responda."""
    try:
        return json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nuclear_seed.json"), encoding="utf-8"))
    except Exception:
        return []


class Grid:
    def __init__(self, cache="data/grid_cache.json", opener=None, pause=1.0):
        self.cache = cache
        self.pause = pause
        self.open = opener or self._http
        self.data = None
        self.status = {"state": "pendiente", "tiles_done": 0, "tiles_total": sum(1 for _ in tiles())}
        self.lock = threading.Lock()

    @staticmethod
    def _http(ep, q):
        req = urllib.request.Request(ep, data=("data=" + urllib.parse.quote(q)).encode(),
                                     headers={"User-Agent": "WhiteMoonEnergia/1.0 (https://whitemoon.es)"})
        with urllib.request.urlopen(req, timeout=100) as r:
            return json.load(r)

    def _tile(self, b):
        last = None
        for _ in range(2):
            for ep in ENDPOINTS:
                try:
                    return self.open(ep, query(b))["elements"]
                except Exception as ex:
                    last = ex
                    self.status.setdefault("errors_by_host", {})[ep.split("/")[2]] = repr(ex)[:80]
                    time.sleep(self.pause * 2)
        raise RuntimeError(f"tesela {b}: {last!r}")

    def run(self):
        try:
            if os.path.exists(self.cache) and time.time() - os.path.getmtime(self.cache) < TTL_S:
                self._set(json.load(open(self.cache, encoding="utf-8")))
                return
            self.status["state"] = "descargando"
            plants, lines, subs, failed, streak = {}, {}, {}, [], 0
            for b in tiles():
                if streak >= 4 and not lines and not plants:
                    self.status.update(state="error", error="Overpass inaccesible desde este servidor (4 zonas seguidas fallidas)")
                    return
                try:
                    reduce(self._tile(b), plants, lines, subs)
                    streak = 0
                except Exception as ex:
                    failed.append(str(ex)[:120])
                    streak += 1
                self.status["tiles_done"] += 1
                time.sleep(self.pause)
            data = {"plants": list(plants.values()), "lines": list(lines.values()), "subs": list(subs.values()),
                    "failed_tiles": len(failed), "fetched": int(time.time())}
            if data["lines"] or data["plants"]:
                os.makedirs(os.path.dirname(self.cache) or ".", exist_ok=True)
                json.dump(data, open(self.cache, "w", encoding="utf-8"), separators=(",", ":"))
            self._set(data)
            if failed:
                self.status["errors"] = failed[:3]
        except Exception as ex:
            self.status.update(state="error", error=repr(ex)[:200])

    def _set(self, data):
        d = dict(data)
        # las nucleares de OSM se sustituyen por las del fichero propio (potencias y reactores verificados)
        seeds = seed()
        near = lambda a, b: abs(a[0] - b[0]) < .08 and abs(a[1] - b[1]) < .08
        d["plants"] = [p for p in d.get("plants", []) if not (p["g"] == "nuclear" and any(near(p["c"], s["c"]) for s in seeds))] + seeds
        tot = {}
        for p in d["plants"]:
            if p.get("mw") and not p.get("off"):
                tot[p["g"]] = round(tot.get(p["g"], 0) + p["mw"])
        d["totals_mw"] = tot
        d["counts"] = {"plants": len(d["plants"]), "lines": len(d.get("lines", [])), "subs": len(d.get("subs", []))}
        with self.lock:
            self.data = d
            self.status["state"] = "ok"

    def start(self):
        # mientras Overpass responde, ya se ven las nucleares (fichero propio)
        self._set({"plants": [], "lines": [], "subs": []})
        self.status["state"] = "descargando"
        threading.Thread(target=self.run, daemon=True).start()

    def view(self):
        with self.lock:
            d = self.data or {"plants": [], "lines": [], "subs": []}
        return {**d, "status": dict(self.status), "names": NOMBRE,
                "source": "OpenStreetMap (ODbL) · © colaboradores de OpenStreetMap. No es el inventario oficial de Red Eléctrica; puede haber centrales o líneas que falten o estén desactualizadas."}
