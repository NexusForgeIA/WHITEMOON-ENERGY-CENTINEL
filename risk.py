"""Índice de vigilancia de la red (0-100) a partir de datos públicos. NO predice apagones: detecta anomalías a los pocos minutos.

Cada factor puntúa 0-100 y el índice es el MÁXIMO de los factores (criterio conservador: basta una señal fuerte). Niveles:
<25 normal · 25-49 atención · 50-74 alto · ≥75 crítico. Señales que de verdad preceden a un colapso (frecuencia, tensión, inercia,
flujos por línea) no son públicas en tiempo real; aquí solo hay demanda cada 5 min, previsión, precio y reglas calculadas sobre esos datos."""
import time
from datetime import datetime

LEVELS = [(75, "Crítico"), (50, "Alto"), (25, "Atención"), (0, "Normal")]


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return None if not n else xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def oscillation(vals, win=12):
    """Media del valor absoluto de la segunda diferencia (MW) en la última ventana, y la habitual del resto de la serie (mediana de ventanas)."""
    d2 = [abs(vals[i] - 2 * vals[i - 1] + vals[i - 2]) for i in range(2, len(vals))]
    if len(d2) < win + 24:
        return None, None
    cur = sum(d2[-win:]) / win
    base = median([sum(d2[k:k + win]) / win for k in range(0, len(d2) - win, win // 2)]) or 0
    return cur, base


def level(score):
    return next(n for t, n in LEVELS if score >= t)


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def ts_of(iso):
    return datetime.fromisoformat(iso).timestamp()


def ramp(hist, i, minutes):
    """Cambio relativo de la demanda real frente al punto de hace `minutes` min, por cada 15 min (None si no hay)."""
    t = ts_of(hist[i]["t"])
    for j in range(i - 1, -1, -1):
        if t - ts_of(hist[j]["t"]) >= minutes * 60 - 30:
            a, b = hist[j]["real"], hist[i]["real"]
            dt = (t - ts_of(hist[j]["t"])) / 60
            return (b - a) / a * 15 / dt if a and dt else None      # normalizado a «cada 15 min» (con lecturas horarias dt=60)
    return None


def f_dev(dev):
    """Demanda real frente a la prevista: por debajo de la previsión es la señal más preocupante."""
    if dev is None:
        return 0
    s = clamp((abs(dev) - 0.03) / 0.09 * 100)
    return round(s if dev < 0 else s * 0.6)


def f_ramp(r):
    """Caída (o subida) brusca en 15 min. Lo normal en el día es ≤2 % cada 15 min en caídas y ≤4 % en subidas."""
    if r is None:
        return 0
    if r > 0:      # las subidas de la mañana (hasta ~3,5 % cada 15 min) son normales
        return round(clamp((r - 0.04) / 0.06 * 100) * 0.5)
    return round(clamp((abs(r) - 0.02) / 0.06 * 100))


def point_score(hist, i):
    h = hist[i]
    dev = (h["real"] - h["forecast"]) / h["forecast"] if h.get("forecast") else None
    return max(f_dev(dev), f_ramp(ramp(hist, i, 15)))


def series(hist):
    return [{"t": h["t"][11:16], "score": point_score(hist, i)} for i, h in enumerate(hist)]


def f_price(p):
    """Precio mayorista a ~0 en horas de sol = mucho excedente renovable (poca generación síncrona). Solo contexto: tope 20."""
    if p is None:
        return 0
    return 20 if p <= 0 else 14 if p <= 2 else 6 if p <= 10 else 0


def f_osc(cur, base):
    """Oscilación (MW de variación media entre lecturas de 5 min en la última hora) frente a la habitual del día."""
    if cur is None or cur < 250:
        return 0
    return round(clamp((cur - 250) / 750 * 100) * (1 if cur >= 3 * max(base or 0, 60) else 0.4))


def f_rules(alerts):
    """Reglas activas (rules.py). Las de tiempo real pesan más que las diarias, que llegan con retraso."""
    s, who = 0, None
    for a in alerts or []:
        rt = a.get("rule") in ("R-DEM-DROP", "R-DEM-DEV", "R-OSC")
        v = (75 if rt else 50) if a.get("sev") == "muy alta" else (45 if rt else 25)
        if v > s:
            s, who = v, a
    return s, who


def f_stale(age_min):
    return 0 if age_min is None or age_min <= 20 else 30 if age_min <= 60 else 50


def compute(rt, price_now, alerts, now=None):
    now = now or time.time()
    hist = (rt or {}).get("history") or []
    fac = []
    age = (now - ts_of(rt["at"])) / 60 if rt else None
    if rt and hist:
        dev, r15 = rt.get("deviation"), ramp(hist, len(hist) - 1, 15)
        fac.append({"id": "dev", "name": "Demanda vs previsión", "score": f_dev(dev), "value": None if dev is None else round(dev * 100, 1), "unit": "%",
                    "hint": "Por debajo de la previsión es la señal más preocupante. Alarma plena en −12 %."})
        fac.append({"id": "ramp", "name": "Variación en 15 min", "score": f_ramp(r15), "value": None if r15 is None else round(r15 * 100, 1), "unit": "%",
                    "hint": "Lo normal es ≤2 % cada 15 min. Alarma plena en caídas de −8 %."})
    fac.append({"id": "stale", "name": "Lectura reciente", "score": f_stale(age) if rt else 30, "value": None if age is None else round(age), "unit": "min",
                "hint": "Si Red Eléctrica deja de publicar la lectura, se pierde la vigilancia (no implica fallo eléctrico)."})
    fac.append({"id": "price", "name": "Excedente renovable (precio)", "score": f_price(price_now), "value": price_now, "unit": "€/MWh",
                "hint": "Precio mayorista cerca de 0: mucha solar y eólica; contexto, nunca sube el nivel por sí solo."})
    if rt and hist:
        cur, base = oscillation([h["real"] for h in hist])
        fac.append({"id": "osc", "name": "Oscilación de la demanda (1 h)", "score": f_osc(cur, base), "value": None if cur is None else round(cur), "unit": "MW",
                    "hint": "Variación media entre lecturas de 5 min; ámbar desde ~400 MW si triplica lo habitual del día."})
    ps, who = f_rules(alerts)
    fac.append({"id": "rules", "name": "Reglas de caída activas", "score": ps, "value": who and who.get("rule"), "unit": "",
                "hint": "R-DEM-DROP, R-DEM-DEV, R-OSC (península, 5 min) y R-SYS, R-NUC (diarias, con retraso)."})
    score = max(f["score"] for f in fac)
    rules_on = [{"rule": a.get("rule"), "sev": a.get("sev"), "zone": a.get("zone"), "title": a.get("title")} for a in alerts or []]
    top = max(fac, key=lambda f: f["score"])
    return {"score": score, "level": level(score), "driver": top["name"] if score >= 25 else None, "factors": fac,
            "series": series(hist), "mw": (rt or {}).get("mw"), "forecast_mw": (rt or {}).get("forecast_mw"), "rules": rules_on,
            "driver_detail": who.get("title") if who and top["id"] == "rules" else None, "age_min": None if age is None else round(age), "now": int(now * 1000),
            "limits": ["Frecuencia, tensión, inercia y flujos por línea no son públicos en tiempo real.",
                       "No predice: detecta en minutos desviaciones y caídas bruscas de la demanda peninsular.",
                       "Sin datos por central ni subestación: las reglas se aplican a la Península (5 min), a cada sistema (diario) y a la nuclear (diario)."]}
