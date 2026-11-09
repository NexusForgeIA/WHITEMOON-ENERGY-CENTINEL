import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import revisions as V


def S(taken, **row):
    return {"taken": taken, "days": {"2026-11-05": row}}


def test_revisions_first_vs_last_and_unchanged_ignored():
    snaps = [S("2026-11-06T08:00:00Z", **{"Ciclo combinado": 245000, "Nuclear": 145000}), S("2026-11-06T20:00:00Z", **{"Ciclo combinado": 285000, "Nuclear": 145000})]
    r = V.revisions(snaps)["2026-11-05"]
    assert r["Ciclo combinado"]["pct"] == 16.3 and "Nuclear" not in r


def test_factor_check_flags_rotated_factor():
    snaps = [{"taken": "x", "days": {"a": {"co2_t": 100.0, "Generación total": 1000.0, "co2_factor": 0.1}, "b": {"co2_t": 130.0, "Generación total": 740.0, "co2_factor": 0.088}}}]
    assert V.factor_check(snaps) == [("b", 88, 176)]


def test_revisions_ignore_day_in_progress():
    snaps = [S("2026-11-05T06:00:00Z", **{"Generación total": 200000, "Ciclo combinado": 90000}),
             S("2026-11-05T20:00:00Z", **{"Generación total": 600000, "Ciclo combinado": 200000}),
             S("2026-11-06T08:00:00Z", **{"Generación total": 729000, "Ciclo combinado": 245000}),
             S("2026-11-06T20:00:00Z", **{"Generación total": 742000, "Ciclo combinado": 285000})]
    r = V.revisions(snaps)["2026-11-05"]
    assert r["Ciclo combinado"]["first"] == 245000 and r["Ciclo combinado"]["pct"] == 16.3
    assert r["Generación total"]["pct"] == 1.8
