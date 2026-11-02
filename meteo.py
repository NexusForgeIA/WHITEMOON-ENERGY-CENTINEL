"""Avisos meteorológicos de España (AEMET, vía el feed público de MeteoAlarm; sin clave). Contexto de riesgo para la red:
viento, tormentas, nieve/hielo, calor o incendios son lo que más líneas tumba y más demanda mueve.
Fuente: MeteoAlarm.org (licencia equivalente a CC BY 4.0). Informativo; el aviso oficial es el de AEMET."""
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

URL = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-spain"
TYPES = {"rain": "Lluvia", "wind": "Viento", "thunderstorm": "Tormentas", "snow/ice": "Nieve/hielo", "high temperature": "Calor", "low temperature": "Frío",
         "coastal event": "Fenómeno costero", "forest fire": "Incendios", "fog": "Niebla", "flood": "Inundación", "tornado": "Tornado", "avalanche": "Aludes"}
LEVELS = {"yellow": "amarillo", "orange": "naranja", "red": "rojo"}
RANK = {"rojo": 0, "naranja": 1, "amarillo": 2}
GRID_TYPES = {"Viento", "Tormentas", "Nieve/hielo", "Calor", "Incendios", "Tornado", "Inundación", "Aludes"}   # los que de verdad afectan a líneas y demanda


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _ts(s):
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def parse(data):
    """Atom de MeteoAlarm → [{area, type, level, onset, expires}] (epoch en segundos)."""
    root = ET.fromstring(data)
    out, seen = [], set()
    for e in root.iter():
        if _local(e.tag) != "entry":
            continue
        f = {}
        for c in e.iter():
            f.setdefault(_local(c.tag), (c.text or "").strip())
        m = re.match(r"(Yellow|Orange|Red)\s+(.+?)\s+Warning", f.get("title", ""), re.I)
        if not m:
            continue
        area = f.get("areaDesc") or f.get("title", "").split(" - ", 1)[-1]
        on, ex = _ts(f.get("onset") or f.get("effective")), _ts(f.get("expires"))
        if on is None or ex is None:
            continue
        a = {"area": area, "type": TYPES.get(m.group(2).lower(), m.group(2).capitalize()), "level": LEVELS[m.group(1).lower()], "onset": on, "expires": ex}
        k = (a["area"], a["type"], a["level"], a["onset"])
        if k not in seen:
            seen.add(k)
            out.append(a)
    return out


def _get(url=URL):
    req = urllib.request.Request(url, headers={"User-Agent": "RedSentinel/1.0 (https://whitemoon.es)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


class Meteo:
    def __init__(self, get=_get, period=900, now=time.time):
        self.get, self.period, self.now = get, period, now
        self.items, self.status, self.lock = [], {"state": "pendiente"}, threading.Lock()

    def refresh(self):
        try:
            items = parse(self.get())
            with self.lock:
                self.items, self.status = items, {"state": "ok", "fetched": int(self.now() * 1000)}
        except Exception as ex:
            with self.lock:
                self.status = {**self.status, "state": "error" if not self.items else "desfasado", "error": str(ex)[:100]}

    def _loop(self):
        while True:
            self.refresh()
            time.sleep(self.period)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="meteo").start()

    def view(self):
        now = self.now()
        with self.lock:
            its = [i for i in self.items if i["expires"] > now and i["onset"] <= now + 24 * 3600]
            st = dict(self.status)
        for i in its:
            i["active"] = i["onset"] <= now
        counts = {"rojo": 0, "naranja": 0, "amarillo": 0}
        grid = {"rojo": 0, "naranja": 0}
        for i in its:
            counts[i["level"]] += 1
            if i["level"] in grid and i["type"] in GRID_TYPES and i["active"]:
                grid[i["level"]] += 1
        top = sorted([i for i in its if i["level"] != "amarillo"], key=lambda i: (RANK[i["level"]], i["onset"]))[:30]
        yellow = {}
        for i in its:
            if i["level"] == "amarillo":
                yellow[i["type"]] = yellow.get(i["type"], 0) + 1
        return {"counts": counts, "grid": grid, "top": top, "yellow_by_type": yellow, "status": st,
                "source": "AEMET vía MeteoAlarm.org (CC BY 4.0). Informativo; el aviso oficial es el de AEMET."}
