"""Cliente de la API REData de Red Eléctrica (https://www.ree.es/es/datos/apidatos) y resumen por sistema eléctrico.

Formato: GET https://apidatos.ree.es/{lang}/datos/{categoría}/{widget}?start_date&end_date&time_trunc[&geo_trunc=electric_system&geo_limit&geo_ids]
Para pedir una región hay que enviar los tres parámetros geo_*. Gratuita y sin clave; solo GET. Fuente: Red Eléctrica (REData).

LÍMITE VERIFICADO (2 nov 2026): los sistemas no peninsulares (Canarias, Baleares, Ceuta, Melilla) solo publican datos DIARIOS con retraso de
horas o días y sin desglose por isla; la demanda en tiempo real y por horas solo existe para la península. Por eso un apagón de una isla
NO se ve aquí a tiempo: para eso están los titulares de medios (energia.py). Aquí se ve el sistema entero con retraso (p. ej. «ayer»).
"""
import json
import os
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://apidatos.ree.es/es/datos/"
GEO = {"peninsular": 8741, "canarias": 8742, "baleares": 8743, "ceuta": 8744, "melilla": 8745}
NAMES = {"peninsular": "Península", "canarias": "Canarias", "baleares": "Baleares", "ceuta": "Ceuta", "melilla": "Melilla"}
# Catálogo de widgets de la API (según la documentación oficial)
CATALOG = {
    "balance": ["balance-electrico"],
    "demanda": ["evolucion", "variacion-componentes", "variacion-componentes-movil", "ire-general", "ire-general-anual", "ire-general-movil",
                "ire-industria", "ire-servicios", "ire-otras", "demanda-maxima-diaria", "demanda-maxima-horaria", "perdidas-transporte",
                "potencia-maxima-instantanea", "variacion-demanda", "demanda-tiempo-real"],
    "generacion": ["estructura-generacion", "evolucion-renovable-no-renovable", "estructura-renovables", "estructura-generacion-emisiones-asociadas",
                   "evolucion-estructura-generacion-emisiones-asociadas", "no-renovables-detalle-emisiones-CO2", "maxima-renovable", "potencia-instalada"],
    "intercambios": ["francia-frontera", "portugal-frontera", "marruecos-frontera", "andorra-frontera", "enlace-baleares", "todas-fronteras-fisicos"],
    "transporte": ["energia-no-suministrada-ens", "indice-indisponibilidad", "tiempo-interrupcion-medio-tim", "kilometros-lineas", "indice-disponibilidad",
                   "numero-cortes", "ens-tim", "indice-disponibilidad-total"],
    "mercados": ["componentes-precio-energia-cierre-desglose", "energia-gestionada-servicios-ajuste", "precios-mercados-tiempo-real"],
}


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "RailGuard/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def url(category, widget, start, end, trunc="day", system=None):
    q = f"?start_date={start}&end_date={end}&time_trunc={trunc}"
    if system:
        q += f"&geo_trunc=electric_system&geo_limit={system}&geo_ids={GEO[system]}"
    return BASE + f"{category}/{widget}" + q


def daily_values(data):
    """Primera serie de un widget → [(datetime_iso, valor)]; vacía si la API devolvió un error."""
    inc = (data or {}).get("included") or []
    vals = ((inc[0].get("attributes") or {}).get("values") or []) if inc else []
    return [(v["datetime"], v["value"]) for v in vals if v.get("value") is not None]


def summarize(vals):
    """vals: demanda diaria (MWh) ordenada. Último día con dato frente a la media de los anteriores."""
    if not vals:
        return None
    last_dt, last = vals[-1]
    prev = [v for _, v in vals[-9:-1]]
    mean = sum(prev) / len(prev) if prev else None
    wd = datetime.fromisoformat(last_dt[:10]).weekday()
    same = sorted(v for d, v in vals[:-1] if datetime.fromisoformat(d[:10]).weekday() == wd)
    dow = None if len(same) < 2 else (same[len(same) // 2] if len(same) % 2 else (same[len(same) // 2 - 1] + same[len(same) // 2]) / 2)
    allv = [v for _, v in vals]
    hi, lo = max(vals, key=lambda x: x[1]), min(vals, key=lambda x: x[1])
    return {"date": last_dt[:10], "mwh": round(last), "mean_prev": round(mean) if mean else None,
            "deviation": round((last - mean) / mean, 3) if mean else None,
            "dow_mean": round(dow) if dow else None, "dow_dev": round((last - dow) / dow, 3) if dow else None,
            "series": [{"date": d[:10], "mwh": round(v)} for d, v in vals[-9:]], "daily": [[d[:10], round(v)] for d, v in vals],
            "max": {"date": hi[0][:10], "mwh": round(hi[1])}, "min": {"date": lo[0][:10], "mwh": round(lo[1])}}


def parse_generation(data):
    """estructura-generacion (día) → último día con total: reparto por tecnología y % renovable."""
    inc = (data or {}).get("included") or []
    rows, total, date = [], None, None
    for it in inc:
        a = it.get("attributes") or {}
        vals = a.get("values") or []
        if not vals:
            continue
        v = vals[-1]
        if a.get("type") == "total":
            total, date = v["value"], v["datetime"][:10]
            continue
        rows.append({"name": a.get("title"), "kind": a.get("type"), "mwh": round(v["value"]), "pct": v.get("percentage"), "color": a.get("color")})
    if not rows or not total:
        return None
    ren = sum(r["mwh"] for r in rows if r["kind"] == "Renovable")
    rows.sort(key=lambda r: -r["mwh"])
    return {"date": date, "total_mwh": round(total), "renewable_pct": round(ren / total, 3), "items": rows}


def parse_nuclear(data):
    """estructura-generacion (día) → [(fecha, MWh)] de la tecnología nuclear."""
    for it in (data or {}).get("included") or []:
        a = it.get("attributes") or {}
        if "nuclear" in (a.get("title") or "").lower():
            return [(v["datetime"][:10], v["value"]) for v in a.get("values") or [] if v.get("value") is not None]
    return []


def parse_realtime(data):
    """demanda-tiempo-real (península) → última lectura, previsión, desviación y estadísticas del día (con ayer para comparar)."""
    series = {s.get("type"): (s.get("attributes") or {}).get("values") or [] for s in (data or {}).get("included") or []}
    real_all, fc = series.get("Real") or [], {v["datetime"]: v["value"] for v in series.get("Prevista") or []}
    if not real_all:
        return None
    last = real_all[-1]
    day = last["datetime"][:10]
    real = [v for v in real_all if v["datetime"][:10] == day]
    yest = [v for v in real_all if v["datetime"][:10] != day]
    exp = fc.get(last["datetime"])
    hhmm = lambda v: v["datetime"][11:16]
    vals = [v["value"] for v in real]
    hi, lo = max(real, key=lambda v: v["value"]), min(real, key=lambda v: v["value"])
    ago = next((v for v in reversed(real) if _mins(hhmm(v)) <= _mins(hhmm(last)) - 60), None)
    ysame = next((v for v in reversed(yest) if hhmm(v) <= hhmm(last)), None)
    return {"mw": round(last["value"]), "forecast_mw": round(exp) if exp else None, "at": last["datetime"],
            "deviation": round((last["value"] - exp) / exp, 3) if exp else None,
            "max": {"mw": round(hi["value"]), "at": hhmm(hi)}, "min": {"mw": round(lo["value"]), "at": hhmm(lo)},
            "avg_mw": round(sum(vals) / len(vals)),
            "delta_1h": round(last["value"] - ago["value"]) if ago else None,
            "yesterday_same_mw": round(ysame["value"]) if ysame else None,
            "yesterday": [{"t": hhmm(v), "real": round(v["value"])} for v in yest[::3]],
            "history": [{"t": v["datetime"], "real": round(v["value"]), "forecast": round(fc[v["datetime"]]) if fc.get(v["datetime"]) else None} for v in real]}


def _mins(hm):
    return int(hm[:2]) * 60 + int(hm[3:5])


def madrid_now(ts=None):
    """Hora local de Madrid (aprox.): si el sistema no trae zonas horarias, UTC+1/+2 por la regla europea del horario de verano."""
    ts = ts or time.time()
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromtimestamp(ts, ZoneInfo("Europe/Madrid")).replace(tzinfo=None)
    except Exception:
        u = datetime.fromtimestamp(ts, timezone.utc)
        last = lambda y, m: max(d for d in (datetime(y, m, x, 1, tzinfo=timezone.utc) for x in range(25, 32)) if d.weekday() == 6)
        dst = last(u.year, 3) <= u < last(u.year, 10)
        return (u + timedelta(hours=2 if dst else 1)).replace(tzinfo=None)


def parse_prices(data):
    """precios-mercados-tiempo-real → {'days': [{date, spot[[min,€]], pvpc[[h,€]], stats}], 'pts': [[epoch,spot,pvpc]]} (spot cada 15 min, PVPC horario)."""
    inc = {s.get("type"): (s.get("attributes") or {}).get("values") or [] for s in (data or {}).get("included") or []}
    spot, pvpc = inc.get("Precio mercado spot") or [], inc.get("PVPC") or []
    if not spot:
        return None
    day = {}
    for v in spot:
        d = v["datetime"][:10]
        m = int(v["datetime"][11:13]) * 60 + int(v["datetime"][14:16])
        day.setdefault(d, {"spot": [], "pvpc": []})["spot"].append([m, round(v["value"], 2)])
    for v in pvpc:
        d = v["datetime"][:10]
        if d in day:
            day[d]["pvpc"].append([int(v["datetime"][11:13]), round(v["value"], 2)])
    out = []
    for d in sorted(day):
        sp = day[d]["spot"]
        hrs = {}
        for m, x in sp:
            hrs.setdefault(m // 60, []).append(x)
        hm = {h: sum(a) / len(a) for h, a in hrs.items()}
        hi, lo = max(sp, key=lambda x: x[1]), min(sp, key=lambda x: x[1])
        out.append({"date": d, "spot": sp, "pvpc": day[d]["pvpc"],
                    "stats": {"min": {"v": lo[1], "at": f"{lo[0] // 60:02d}:{lo[0] % 60:02d}"}, "max": {"v": hi[1], "at": f"{hi[0] // 60:02d}:{hi[0] % 60:02d}"},
                              "avg": round(sum(x[1] for x in sp) / len(sp), 2),
                              "cheap": sorted(h for h, x in hm.items() if x <= 5), "dear": sorted(sorted(hm, key=lambda h: -hm[h])[:3])}})
    pts = [[datetime.fromisoformat(v["datetime"]).timestamp(), v["value"]] for v in spot]
    return {"days": out, "pts": pts}


class RedData:
    def __init__(self, get=_get, cache="data/redata_cache.json", period=1800, now=time.time):
        self.get, self.cache, self.period, self.now = get, cache, period, now
        self.systems, self.status, self.lock = {}, {"state": "pendiente"}, threading.Lock()
        self.generation, self.realtime, self.history = None, None, []
        self.prices = None
        self.nuclear = []
        try:
            d = json.load(open(cache, encoding="utf-8"))
            self.systems, self.status = d["systems"], {"state": "caché", "fetched": d.get("fetched")}
            self.generation, self.realtime, self.history = d.get("generation"), d.get("realtime"), d.get("history") or []
            self.prices = d.get("prices")
            self.nuclear = d.get("nuclear") or []
        except Exception:
            pass

    def refresh(self):
        today = madrid_now(self.now())
        start, end = (today - timedelta(days=8)).strftime("%Y-%m-%dT00:00"), today.strftime("%Y-%m-%dT23:59")
        start35 = (today - timedelta(days=35)).strftime("%Y-%m-%dT00:00")
        out, errs = {}, {}
        for sys_ in GEO:
            try:
                s = summarize(daily_values(self.get(url("demanda", "evolucion", start35, end, "day", sys_))))
                if s:
                    out[sys_] = {"name": NAMES[sys_], **s}
                else:
                    errs[sys_] = "sin datos"
            except Exception as ex:
                errs[sys_] = str(ex)[:80]
        gen = rt = None
        hist = []
        nuc = []
        try:
            graw = self.get(url("generacion", "estructura-generacion", start, end, "day", "peninsular"))
            gen, nuc = parse_generation(graw), parse_nuclear(graw)
        except Exception as ex:
            errs["generacion"] = str(ex)[:80]
        try:
            rt = parse_realtime(self.get(url("demanda", "demanda-tiempo-real", (today - timedelta(days=1)).strftime("%Y-%m-%dT00:00"), end, "hour")))
        except Exception as ex:
            errs["tiempo_real"] = str(ex)[:80]
        pr = self._fetch_prices(today, errs)
        try:
            h0 = (today - timedelta(days=30)).strftime("%Y-%m-%dT00:00")
            hist = [{"date": d[:10], "mwh": round(v)} for d, v in daily_values(self.get(url("demanda", "evolucion", h0, end, "day", "peninsular")))]
        except Exception as ex:
            errs["historico"] = str(ex)[:80]
        with self.lock:
            if gen:
                self.generation = gen
            if nuc:
                self.nuclear = nuc
            if rt:
                self.realtime = rt
            if pr:
                self.prices = pr
            if hist:
                self.history = hist
            if out:
                self.systems = out
            self.status = {"state": "ok" if out else "error", "fetched": int(self.now() * 1000), "errors": errs}
        try:
            os.makedirs(os.path.dirname(self.cache) or ".", exist_ok=True)
            json.dump({"systems": self.systems, "generation": self.generation, "realtime": self.realtime, "history": self.history, "prices": self.prices, "nuclear": self.nuclear, "fetched": self.status.get("fetched")}, open(self.cache, "w", encoding="utf-8"))
        except OSError:
            pass

    def _fetch_prices(self, today, errs):
        """Precios de hoy y, si ya están publicados, de mañana (el mercado diario los publica a primera hora de la tarde)."""
        for end in ((today + timedelta(days=1)).strftime("%Y-%m-%dT23:59"), today.strftime("%Y-%m-%dT23:59")):
            try:
                return parse_prices(self.get(url("mercados", "precios-mercados-tiempo-real", today.strftime("%Y-%m-%dT00:00"), end, "hour")))
            except Exception as ex:
                errs["precios"] = str(ex)[:80]
        return None

    def refresh_fast(self):
        """Cada pocos minutos: demanda en tiempo real (de ayer a hoy, para comparar) y precios."""
        today, errs = madrid_now(self.now()), {}
        rt = None
        try:
            rt = parse_realtime(self.get(url("demanda", "demanda-tiempo-real", (today - timedelta(days=1)).strftime("%Y-%m-%dT00:00"), today.strftime("%Y-%m-%dT23:59"), "hour")))
        except Exception as ex:
            errs["tiempo_real"] = str(ex)[:80]
        pr = self._fetch_prices(today, errs)
        with self.lock:
            if rt:
                self.realtime = rt
            if pr:
                self.prices = pr
            if rt or pr:
                self.status = {**self.status, "fast_fetched": int(self.now() * 1000), "fast_errors": errs}

    def price_now(self):
        with self.lock:
            pr = self.prices
        if not pr:
            return None
        t = self.now()
        cur = [p for p in pr.get("pts", []) if p[0] <= t]
        return cur[-1][1] if cur and t - cur[-1][0] < 3 * 3600 else None

    def view(self):
        with self.lock:
            pr = dict(self.prices) if self.prices else None
        if pr:
            pr.pop("pts", None)
            pr["now"] = self.price_now()
        with self.lock:
            return {"systems": self.systems, "generation": self.generation, "realtime": self.realtime, "history": self.history, "prices": pr,
                    "status": self.status, "catalog": CATALOG,
                    "source": "Red Eléctrica de España · REData (apidatos.ree.es). Demanda diaria en MWh; Canarias, Baleares, Ceuta y Melilla solo con datos diarios."}

    def nuclear_series(self):
        with self.lock:
            return list(self.nuclear)

    def _loop(self):
        while True:
            try:
                self.refresh()
            except Exception:
                pass
            time.sleep(self.period)

    def _fast_loop(self):
        while True:
            time.sleep(300)
            try:
                self.refresh_fast()
            except Exception:
                pass

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="redata").start()
        threading.Thread(target=self._fast_loop, daemon=True, name="redata-fast").start()
