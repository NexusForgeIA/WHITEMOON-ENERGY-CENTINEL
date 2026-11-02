import json
from datetime import date, datetime, timedelta

import rules
import redata as R


def mk(vals, fc=None, start="2026-11-02T08:00:00"):
    t0 = datetime.fromisoformat(start)
    return [{"t": (t0 + timedelta(minutes=5 * i)).isoformat() + "+01:00", "real": v, "forecast": (fc[i] if fc else v)} for i, v in enumerate(vals)]


def now_of(h):
    return datetime.fromisoformat(h[-1]["t"]).timestamp() + 60


def ids(al):
    return {a["rule"]: a["sev"] for a in al}


def test_quiet_day_has_no_alerts():
    h = mk([30000 + i * 5 for i in range(80)])
    assert rules.realtime_rules({"history": h}, now_of(h)) == []


def test_sudden_drop_is_red_and_expires():
    h = mk([30000] * 60 + [29000, 27000, 25000])
    al = rules.realtime_rules({"history": h}, now_of(h))
    assert ids(al)["R-DEM-DROP"] == "muy alta"
    assert rules.realtime_rules({"history": h}, now_of(h) + 3 * 3600) == []          # sin lectura reciente no hay alerta


def test_amber_drop_like_real_20_55_case():
    h = mk([31700] * 60 + [31500, 30900, 29643], fc=[31500] * 63)
    a = rules.realtime_rules({"history": h}, now_of(h))
    assert ids(a)["R-DEM-DROP"] in ("alta", "muy alta")


def test_deviation_needs_two_readings():
    h = mk([30000] * 60 + [28000], fc=[30000] * 61)
    assert "R-DEM-DEV" not in ids(rules.realtime_rules({"history": h}, now_of(h)))
    h = mk([30000] * 59 + [28000, 27500], fc=[30000] * 61)
    assert ids(rules.realtime_rules({"history": h}, now_of(h)))["R-DEM-DEV"] == "alta"


def test_oscillation():
    calm = [30000 + i * 3 for i in range(70)]
    osc = calm[:58] + [30000 + (700 if i % 2 else -700) for i in range(12)]
    h = mk(osc)
    assert "R-OSC" in ids(rules.realtime_rules({"history": h}, now_of(h)))
    assert "R-OSC" not in ids(rules.realtime_rules({"history": mk(calm)}, now_of(mk(calm))))


def test_system_rule_uses_same_weekday():
    vals = [(f"2026-10-{d:02d}", 1000 if date(2026, 10, d).weekday() < 5 else 800) for d in range(1, 29)]
    vals.append(("2026-10-29", 700))           # jueves: debería rondar 1000
    s = R.summarize(vals)
    assert s["dow_mean"] == 1000 and s["dow_dev"] == -0.3
    al = rules.system_rules({"canarias": {"name": "Canarias", **s}}, date(2026, 11, 1))
    assert al[0]["sev"] == "muy alta" and al[0]["lat"] == 28.3
    assert rules.system_rules({"canarias": {"name": "Canarias", **s}}, date(2026, 12, 1)) == []     # dato demasiado viejo


def test_nuclear_drop_marks_plants():
    nuc = [(f"2026-10-{d}", 145000) for d in range(24, 31)] + [("2026-10-31", 120000)]
    sites = [{"n": "Almaraz", "c": [39.8, -5.7]}, {"n": "Garoña", "c": [42.7, -3.2], "off": True}]
    a = rules.nuclear_rules(nuc, sites, date(2026, 11, 2))
    assert a[0]["sev"] == "alta" and a[0]["points"] == [[39.8, -5.7, "Almaraz"]]
    assert rules.nuclear_rules(nuc[:-1] + [("2026-10-31", 144000)], sites, date(2026, 11, 2)) == []


def test_parse_nuclear():
    d = {"included": [{"attributes": {"title": "Eólica", "values": [{"value": 1, "datetime": "2026-10-30T00:00:00"}]}},
                      {"attributes": {"title": "Nuclear", "values": [{"value": 145000, "datetime": "2026-10-30T00:00:00.000+01:00"}]}}]}
    assert R.parse_nuclear(d) == [("2026-10-30", 145000)]
