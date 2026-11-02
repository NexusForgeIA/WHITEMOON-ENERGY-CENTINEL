import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import risk, redata as R

T0 = "2026-11-02T12:00:00.000+01:00"


def hist(vals, fc=None, step=5):
    out = []
    for i, v in enumerate(vals):
        m = 12 * 60 + i * step
        out.append({"t": f"2026-11-02T{m // 60:02d}:{m % 60:02d}:00.000+01:00", "real": v, "forecast": (fc or [v] * len(vals))[i]})
    return out


def rt_of(h):
    last = h[-1]
    return {"mw": last["real"], "at": last["t"], "deviation": round((last["real"] - last["forecast"]) / last["forecast"], 3), "history": h}


def test_normal_day_is_normal():
    h = hist([30000, 30100, 30150, 30200, 30250, 30300])
    r = risk.compute(rt_of(h), 120, [], now=risk.ts_of(h[-1]["t"]) + 120)
    assert r["score"] == 0 and r["level"] == "Normal" and r["driver"] is None


def test_sudden_drop_is_critical():
    h = hist([30000, 30000, 30000, 29900, 20000, 5000], fc=[30000] * 6)
    r = risk.compute(rt_of(h), None, [], now=risk.ts_of(h[-1]["t"]) + 60)
    assert r["level"] == "Crítico" and r["driver"] in ("Demanda vs previsión", "Variación en 15 min")
    assert max(x["score"] for x in r["series"]) == 100 and r["series"][0]["score"] == 0


def test_stale_rules_and_price():
    h = hist([30000] * 4)
    now = risk.ts_of(h[-1]["t"])
    assert risk.compute(rt_of(h), None, [], now=now + 30 * 60)["score"] == 30            # lectura vieja → atención
    dia = [{"rule": "R-SYS", "sev": "alta"}]
    rt = [{"rule": "R-DEM-DROP", "sev": "muy alta"}]
    assert risk.compute(rt_of(h), None, dia, now=now)["score"] == 25
    assert risk.compute(rt_of(h), None, rt, now=now)["level"] == "Crítico"
    r = risk.compute(rt_of(h), -5, [], now=now)
    assert r["score"] == 20 and r["level"] == "Normal"                                      # el precio solo es contexto


def test_backtest_28a_hourly_data_flags_after_the_collapse():
    v = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "case_28a.json")))["demand"]["values"]
    h = [{"t": f"2025-04-28T{i:02d}:00:00.000+02:00", "real": x, "forecast": None} for i, x in enumerate(v[:24])]
    s = risk.series(h)
    assert max(x["score"] for x in s[:12]) < 25            # la mañana del 28-A no daba ninguna señal previa
    assert s[12]["score"] >= 75                            # la lectura de las 12:00 (ya con el colapso) sí es crítica


def test_prices_parse():
    def pts(day, vals, step):
        return [{"value": x, "datetime": f"{day}T{m // 60:02d}:{m % 60:02d}:00.000+01:00"} for m, x in vals]
    spot = pts("2026-11-02", [(0, 200), (15, 190), (600, 1), (615, 1), (1080, 300), (1095, 310)], 15)
    d = {"included": [{"type": "Precio mercado spot", "attributes": {"values": spot}}, {"type": "PVPC", "attributes": {"values": pts("2026-11-02", [(0, 260), (600, -10)], 60)}}]}
    p = R.parse_prices(d)
    day = p["days"][0]
    assert day["stats"]["min"]["v"] == 1 and day["stats"]["max"]["at"] == "18:15" and day["stats"]["cheap"] == [10] and day["stats"]["dear"][0] in (0, 18)
    assert len(p["pts"]) == 6 and day["pvpc"] == [[0, 260], [10, -10]]


def test_redata_price_now_and_fast_refresh():
    import time
    t = time.mktime(time.strptime("2026-11-02 12:05", "%Y-%m-%d %H:%M"))
    off = time.strftime("%z", time.localtime(t)); off = off[:3] + ":" + off[3:]
    spot = [{"value": 1.5, "datetime": f"2026-11-02T12:00:00.000{off}"}, {"value": 9, "datetime": f"2026-11-02T13:00:00.000{off}"}]
    rt = {"included": [{"type": "Real", "attributes": {"values": [{"datetime": f"2026-11-02T12:00:00.000{off}", "value": 30000}]}}]}

    def get(u):
        return {"included": [{"type": "Precio mercado spot", "attributes": {"values": spot}}]} if "precios" in u else rt
    r = R.RedData(get=get, cache=os.path.join(os.path.dirname(__file__), "none.json"), now=lambda: t)
    r.refresh_fast()
    assert r.price_now() == 1.5 and r.view()["prices"]["now"] == 1.5 and "pts" not in r.view()["prices"] and r.view()["realtime"]["mw"] == 30000
