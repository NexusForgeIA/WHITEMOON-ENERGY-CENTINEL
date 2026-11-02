"""Reglas de caída calculadas con datos públicos de Red Eléctrica (REData). Sin titulares de prensa.

Límite verificado: REData NO publica datos por central ni por subestación en tiempo real. Las reglas se aplican a lo que sí hay:
  · Península: demanda cada 5 min frente a su previsión (caída brusca, desviación sostenida, oscilación anómala).
  · Cada sistema (Península, Canarias, Baleares, Ceuta, Melilla): demanda diaria frente a la mediana del mismo día de la semana.
  · Nuclear: generación diaria frente a la mediana de los 7 días previos (un reactor ≈ 1 GW ≈ 14 % del parque).
Cada alerta indica regla, valor, umbral y zona. Informativo; no sustituye a los avisos del operador."""
import time
from datetime import date, datetime

import redata
import risk

ZONES = {"peninsular": ("Península", 40.0, -3.7), "canarias": ("Canarias", 28.3, -15.9), "baleares": ("Baleares", 39.55, 2.9),
         "ceuta": ("Ceuta", 35.89, -5.32), "melilla": ("Melilla", 35.29, -2.94)}
WINDOW_MIN = 60          # una alerta en tiempo real deja de mostrarse 60 min después de la última lectura anómala
MAX_LAG_DAYS = 5         # los datos diarios llegan con retraso; más viejos que esto son historia, no se muestran

RULES = [
    {"id": "R-DEM-DROP", "name": "Caída de demanda en 15 min", "scope": "Península · 5 min", "amber": "≤ −5 %", "red": "≤ −8 %"},
    {"id": "R-DEM-DEV", "name": "Demanda por debajo de la previsión (2 lecturas seguidas)", "scope": "Península · 5 min", "amber": "≤ −6 %", "red": "≤ −10 %"},
    {"id": "R-OSC", "name": "Oscilación anómala de la demanda (última hora)", "scope": "Península · 5 min", "amber": "≥ 400 MW y ×3 lo habitual", "red": "≥ 800 MW y ×5"},
    {"id": "R-SYS", "name": "Demanda diaria del sistema frente al mismo día de la semana", "scope": "Los 5 sistemas · diario", "amber": "≤ −10 %", "red": "≤ −25 %"},
    {"id": "R-NUC", "name": "Generación nuclear diaria (posible parada de un reactor)", "scope": "Parque nuclear · diario", "amber": "≤ −10 %", "red": "≤ −25 %"},
]


def n(x):
    """Entero con punto de millares (formato español)."""
    return f"{round(x):,}".replace(",", ".")


HOLIDAYS = {"01-01", "01-06", "05-01", "08-15", "10-12", "11-01", "12-06", "12-08", "12-25"}      # festivos nacionales: la demanda baja y es normal


def is_holiday(d):
    return d[5:10] in HOLIDAYS


def _alert(rule, zone, sev, title, detail, value, threshold, at=None, **kw):
    name, lat, lon = ZONES.get(zone, (zone, None, None))
    return {"id": f"{rule}-{zone}", "type": "regla", "rule": rule, "zone": name, "place": name, "sev": sev, "lat": lat, "lon": lon,
            "title": title, "detail": detail, "value": value, "threshold": threshold, "at": at, "trains": [], **kw}


def _mins_ago(at, now):
    return max(0, round((now - risk.ts_of(at)) / 60))


def realtime_rules(rt, now):
    out = []
    hist = risk.consolidated((rt or {}).get("history"), now)            # las lecturas de los últimos 25 min son provisionales
    if not hist or (now - risk.ts_of(hist[-1]["t"])) / 60 > 90 + risk.LAG_MIN:       # sin lectura reciente no hay regla en tiempo real
        return out
    recent = [i for i, h in enumerate(hist) if (now - risk.ts_of(h["t"])) / 60 <= WINDOW_MIN]
    # R-DEM-DROP: la peor caída a 15 min dentro de la última hora
    worst = None
    for i in recent:
        r = risk.ramp(hist, i, 15)
        if r is not None and (worst is None or r < worst[0]):
            worst = (r, i)
    if worst and worst[0] <= -0.05:
        r, i = worst
        sev = "muy alta" if r <= -0.08 else "alta"
        out.append(_alert("R-DEM-DROP", "peninsular", sev, f"Caída de demanda peninsular {r * 100:.1f} % en 15 min".replace(".", ","),
                          f"{n(hist[i]['real'])} MW a las {hist[i]['t'][11:16]} (hace {_mins_ago(hist[i]['t'], now)} min, lectura consolidada). Lo normal es ≤ 2 % cada 15 min. Regla R-DEM-DROP: ámbar ≤ −5 %, roja ≤ −8 %.",
                          round(r * 100, 1), -5, hist[i]["t"]))
    # R-DEM-DEV: desviación frente a la previsión en las dos últimas lecturas
    devs = [(h, (h["real"] - h["forecast"]) / h["forecast"]) for h in hist[-2:] if h.get("forecast")]
    if len(devs) == 2 and all(d <= -0.06 for _, d in devs):
        d = max(d for _, d in devs)
        sev = "muy alta" if d <= -0.10 else "alta"
        h = devs[-1][0]
        out.append(_alert("R-DEM-DEV", "peninsular", sev, f"Demanda peninsular {d * 100:.1f} % bajo la previsión".replace(".", ","),
                          f"{n(h['real'])} MW frente a {n(h['forecast'])} MW previstos a las {h['t'][11:16]}, dos lecturas seguidas. Regla R-DEM-DEV: ámbar ≤ −6 %, roja ≤ −10 %.",
                          round(d * 100, 1), -6, h["t"]))
    # R-OSC: la oscilación de la última hora frente a la habitual del día
    cur, base = risk.oscillation([h["real"] for h in hist])
    if cur is not None and cur >= 400 and cur >= 3 * max(base, 60):
        sev = "muy alta" if cur >= 800 and cur >= 5 * max(base, 60) else "alta"
        out.append(_alert("R-OSC", "peninsular", sev, f"Oscilación anómala de la demanda: {round(cur)} MW",
                          f"Variación media entre lecturas de 5 min en la última hora: {round(cur)} MW, habitual hoy ~{round(base)} MW. Regla R-OSC: ámbar ≥ 400 MW y ×3, roja ≥ 800 MW y ×5.",
                          round(cur), 400, hist[-1]["t"]))
    return out


def system_rules(systems, today):
    out = []
    for k, s in (systems or {}).items():
        dev, d = s.get("dow_dev"), s.get("date")
        if dev is None or not d or k not in ZONES:
            continue
        try:
            age = (today - date.fromisoformat(d)).days
        except ValueError:
            continue
        if age > MAX_LAG_DAYS or dev > -0.10 or is_holiday(d):
            continue
        sev = "muy alta" if dev <= -0.25 else "alta"
        out.append(_alert("R-SYS", k, sev, f"Demanda de {s['name']} {dev * 100:.0f} % el {d[8:10]}/{d[5:7]}".replace(".", ","),
                          f"{n(s['mwh'])} MWh frente a ~{n(s['dow_mean'])} MWh (mediana de los 3 mismos días previos) y ~{n(s.get('near_mean') or s['dow_mean'])} MWh (media de los días recientes). Dato diario con retraso; un festivo puede explicarlo. Regla R-SYS: ámbar ≤ −10 %, roja ≤ −25 % frente a ambas.",
                          round(dev * 100, 1), -10, d))
    return out


def nuclear_rules(nuclear, sites, today):
    """nuclear: [(fecha, MWh)] diarios; sites: centrales nucleares en servicio [{n, c:[lat,lon], mw}]."""
    vals = [(d[:10], v) for d, v in (nuclear or [])]
    if len(vals) < 5:
        return []
    d, last = vals[-1]
    base = risk.median([v for _, v in vals[-8:-1]])
    try:
        age = (today - date.fromisoformat(d)).days
    except ValueError:
        return []
    if not base or age > MAX_LAG_DAYS:
        return []
    dev = (last - base) / base
    if dev > -0.10:
        return []
    sev = "muy alta" if dev <= -0.25 else "alta"
    a = _alert("R-NUC", "peninsular", sev, f"Generación nuclear {dev * 100:.0f} % el {d[8:10]}/{d[5:7]}: posible parada de un reactor".replace(".", ","),
               f"{n(last)} MWh frente a ~{n(base)} MWh de mediana de los 7 días previos (un reactor ≈ 14 % del parque). Puede ser una recarga programada; "
               f"los datos públicos no dicen cuál. Regla R-NUC: ámbar ≤ −10 %, roja ≤ −25 %.", round(dev * 100, 1), -10, d)
    a["points"] = [[s["c"][0], s["c"][1], s["n"]] for s in sites if not s.get("off")]
    a["lat"] = a["lon"] = None
    return [a]


def evaluate(rt, systems, nuclear, sites, now=None, today=None):
    now = now or time.time()
    today = today or datetime.fromtimestamp(now).date()
    out = realtime_rules(rt, now) + system_rules(systems, today) + nuclear_rules(nuclear, sites, today)
    out.sort(key=lambda a: (a["sev"] != "muy alta", a["rule"]))
    return out


def replay_realtime(rt):
    """Reproduce las reglas de tiempo real sobre las lecturas de hoy → episodios [{rule, sev, start, end, n, value, title}], el más reciente primero."""
    hist = (rt or {}).get("history") or []
    ev = {}
    for i in range(24, len(hist)):
        for a in realtime_rules({"history": hist[:i + 1]}, risk.ts_of(hist[i]["t"]) + (risk.LAG_MIN + 1) * 60):
            k = (a["rule"], a["at"])
            if k not in ev or a["sev"] == "muy alta":
                ev[k] = a
    out = []
    for a in sorted(ev.values(), key=lambda a: (a["rule"], a["at"])):
        last = out[-1] if out else None
        if last and last["rule"] == a["rule"] and risk.ts_of(a["at"]) - risk.ts_of(last["end"]) <= 1800:
            last["end"], last["n"] = a["at"], last["n"] + 1
            if a["sev"] == "muy alta":
                last["sev"] = "muy alta"
            if abs(a["value"]) > abs(last["value"]):
                last["value"], last["title"] = a["value"], a["title"]
        else:
            out.append({"rule": a["rule"], "sev": a["sev"], "start": a["at"], "end": a["at"], "n": 1, "value": a["value"], "title": a["title"]})
    out.sort(key=lambda e: e["start"], reverse=True)
    return out


def daily_hits(systems):
    """Días de los últimos ~35 en que la demanda diaria de un sistema cayó ≥10 % bajo la mediana de su mismo día de la semana."""
    out, days = [], 0
    for k, s in (systems or {}).items():
        daily = s.get("daily") or []
        days = max(days, len(daily))
        for i in range(14, len(daily)):
            d, v = daily[i]
            bl = redata.daily_baseline(daily, i)
            if not bl:
                continue
            dev = bl["dev"]
            if dev <= -0.10:
                out.append({"date": d, "zone": s.get("name", k), "dev": round(dev * 100, 1), "sev": "muy alta" if dev <= -0.25 else "alta", "holiday": is_holiday(d)})
    out.sort(key=lambda h: h["date"], reverse=True)
    return out, days


def history(rt, systems):
    ep = replay_realtime(rt)
    hits, days = daily_hits(systems)
    hist = (rt or {}).get("history") or []
    return {"realtime": {"episodes": ep, "readings": len(hist), "since": hist[0]["t"][11:16] if hist else None},
            "daily": {"hits": hits, "days": days}, "rules": RULES,
            "note": "Reconstruido con las lecturas de hoy y los datos diarios de REData; no hay base de datos de histórico largo. Una regla que salta no confirma un apagón."}
