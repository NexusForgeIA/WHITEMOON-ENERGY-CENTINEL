"""Instantánea de lo que REE publica (REData) para auditar sus correcciones.

Guarda en data/snapshots/AAAAMMDDTHHMMZ.json, por día de los últimos 10: generación por tecnología, total, emisiones totales (tCO2 eq.) y el factor
tCO2/MWh que publica REE, más el precio spot medio. Si nada cambió respecto a la instantánea anterior no escribe nada (el repositorio no crece).
Uso: python3 tools/snapshot.py [carpeta]   ·   solo stdlib.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import redata as R  # noqa: E402


def _by_day(data, pick):
    """included → {fecha: valor} por título, con pick(titulo, attrs) que decide la clave de salida (None = ignorar)."""
    out = {}
    for it in (data or {}).get("included") or []:
        a = it.get("attributes") or {}
        key = pick(a.get("title"), a)
        if key is None:
            continue
        for v in a.get("values") or []:
            if v.get("value") is not None:
                out.setdefault(v["datetime"][:10], {})[key] = v["value"]
    return out


def collect(get=R._get, now=None):
    now = now or datetime.now(timezone.utc)
    md = R.madrid_now(now.timestamp())
    today = md.date()
    # end = minuto actual: REE cachea por ventana (start,end) y sirve datos viejos «HIT» durante horas; un end distinto fuerza dato fresco
    start, end = (today - timedelta(days=10)).strftime("%Y-%m-%dT00:00"), md.strftime("%Y-%m-%dT%H:%M")
    gen = _by_day(get(R.url("generacion", "estructura-generacion", start, end, "day", "peninsular")), lambda t, a: t)
    em = _by_day(get(R.url("generacion", "no-renovables-detalle-emisiones-CO2", start, end, "day", "peninsular")),
                 lambda t, a: "co2_t" if t == "Total tCO2 eq." else "co2_factor" if t == "tCO2 eq./MWh" else None)
    days = {}
    for d in sorted(set(gen) | set(em)):
        row = {k: round(v, 3) for k, v in {**gen.get(d, {}), **em.get(d, {})}.items()}
        days[d] = row
    try:  # precio spot medio del día (solo hoy y mañana ya publicados)
        pr = get(R.url("mercados", "precios-mercados-tiempo-real", (today - timedelta(days=1)).strftime("%Y-%m-%dT00:00"),
                       (today + timedelta(days=1)).strftime("%Y-%m-%dT23:59"), "hour"))
        spot = _by_day(pr, lambda t, a: "spot" if t == "Precio mercado spot" else None)
        sums = {}
        for it in pr.get("included") or []:
            if (it.get("attributes") or {}).get("title") == "Precio mercado spot":
                for v in it["attributes"]["values"]:
                    sums.setdefault(v["datetime"][:10], []).append(v["value"])
        for d, vals in sums.items():
            if d in days and len(vals) >= 90:
                days[d]["spot_medio"] = round(sum(vals) / len(vals), 2)
    except Exception:
        pass
    return {"taken": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "apidatos.ree.es (REData), sistema peninsular", "days": days}


def main(folder="data/snapshots"):
    os.makedirs(folder, exist_ok=True)
    snap = collect()
    if not snap["days"]:
        print("sin datos")
        return 1
    prev = sorted(f for f in os.listdir(folder) if f.endswith(".json"))
    if prev:
        last = json.load(open(os.path.join(folder, prev[-1]), encoding="utf-8"))
        if last.get("days") == snap["days"]:
            print("sin cambios respecto a", prev[-1])
            return 0
    name = datetime.strptime(snap["taken"], "%Y-%m-%dT%H:%M:%SZ").strftime("%Y%m%dT%H%MZ") + ".json"
    json.dump(snap, open(os.path.join(folder, name), "w", encoding="utf-8"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    print("guardada", name, len(snap["days"]), "días")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
