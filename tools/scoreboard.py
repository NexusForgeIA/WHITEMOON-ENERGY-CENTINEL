"""Marcador de aciertos público: registra cada alerta diaria R-SYS (demanda de un sistema ≥10 % bajo lo habitual) y, pasados unos días,
comprueba con el dato ya revisado por REE si la caída se mantiene o REE la corrigió. Guarda data/scoreboard.json (lo escribe el bot de GitHub Actions).

Estados:  pendiente (menos de CONFIRM_DAYS días desde el dato) · se_mantiene (REE sigue publicando la caída) · corregida (REE revisó el dato y ya no hay caída).
«se_mantiene» NO prueba un apagón: sólo que el dato no era un error pasajero. Las alertas de tiempo real peninsulares no se pueden contrastar así y no entran.
Uso: python3 tools/scoreboard.py [fichero]   ·   solo stdlib."""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import redata as R  # noqa: E402
import rules  # noqa: E402

CONFIRM_DAYS = 3        # días desde la fecha del dato para dar por buena su última versión
TRACK_DAYS = rules.MAX_LAG_DAYS   # sólo se re-evalúa dentro de la ventana en que detect() ve el dato
THRESHOLD = -0.10


def detect(series, name, zone, today):
    """series: [(fecha, MWh)] diarios. → alertas R-SYS en los últimos MAX_LAG_DAYS: [{date, dev, mwh, base}]."""
    out = []
    for i in range(len(series)):
        d, v = series[i]
        try:
            age = (today - date.fromisoformat(d[:10])).days
        except ValueError:
            continue
        if age > rules.MAX_LAG_DAYS or age < 0 or rules.is_holiday(d[:10]):
            continue
        bl = R.daily_baseline(series, i)
        if bl and bl["dev"] <= THRESHOLD:
            out.append({"date": d[:10], "dev": round(bl["dev"] * 100, 1), "mwh": round(v), "base": bl["dow_mean"]})
    return out


def update(log, found, now):
    """log: {entries:[…]}; found: {zona: [alerta…]} con el dato más reciente de REE. Devuelve el log actualizado."""
    today = now.date()
    by_id = {e["id"]: e for e in log["entries"]}
    for zone, alerts in found.items():
        for a in alerts:
            eid = f"R-SYS-{zone}-{a['date']}"
            if eid not in by_id:
                e = {"id": eid, "rule": "R-SYS", "zone": zone, "date": a["date"], "sev": "muy alta" if a["dev"] <= -25 else "alta",
                     "first_seen": now.strftime("%Y-%m-%dT%H:%MZ"), "first_dev": a["dev"], "first_mwh": a["mwh"], "dev": a["dev"], "mwh": a["mwh"],
                     "status": "pendiente", "checked": now.strftime("%Y-%m-%dT%H:%MZ")}
                log["entries"].append(e)
                by_id[eid] = e
    # re-evaluación de cada entrada con el dato de ahora
    for e in log["entries"]:
        age = (today - date.fromisoformat(e["date"])).days
        if age > TRACK_DAYS:
            continue
        cur = next((a for a in found.get(e["zone"], []) if a["date"] == e["date"]), None)
        fetched = e["zone"] in found
        if not fetched:
            continue
        e["checked"] = now.strftime("%Y-%m-%dT%H:%MZ")
        if cur:
            e["dev"], e["mwh"] = cur["dev"], cur["mwh"]
            e["status"] = "se_mantiene" if age >= CONFIRM_DAYS else "pendiente"
        else:
            e["status"] = "corregida"           # REE ya no publica la caída (dato completado)
            e["dev"] = None
    log["entries"].sort(key=lambda e: e["date"], reverse=True)
    return log


def stats(entries):
    closed = [e for e in entries if e["status"] != "pendiente"]
    n_c = sum(1 for e in closed if e["status"] == "corregida")
    n_m = len(closed) - n_c
    return {"total": len(entries), "pendientes": len(entries) - len(closed), "se_mantiene": n_m, "corregidas": n_c,
            "pct_corregidas": round(100 * n_c / len(closed)) if closed else None}


def collect(get=R._get, now=None):
    now = now or datetime.now(timezone.utc)
    md = R.madrid_now(now.timestamp())
    day0 = md.strftime("%Y-%m-%d")
    start, end = (md - timedelta(days=35)).strftime("%Y-%m-%dT00:00"), md.strftime("%Y-%m-%dT%H:%M")
    found = {}
    for k in R.GEO:
        try:
            series = R.daily_values(R.until_day(get(R.url("demanda", "evolucion", start, end, "day", k)), day0))
        except Exception:
            continue
        if series:
            found[R.NAMES[k]] = detect(series, k, R.NAMES[k], md.date())
    return found


def load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {"entries": []}


def main(path="data/scoreboard.json"):
    now = datetime.now(timezone.utc)
    found = collect(now=now)
    if not found:
        print("sin datos")
        return 1
    log = update(load(path), found, now)
    log["stats"] = stats(log["entries"])
    log["updated"] = now.strftime("%Y-%m-%dT%H:%MZ")
    old = load(path)
    old.pop("updated", None)
    new = {k: v for k, v in log.items() if k != "updated"}
    if old == new:
        print("sin cambios")
        return 0
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    json.dump(log, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("marcador:", log["stats"])
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
