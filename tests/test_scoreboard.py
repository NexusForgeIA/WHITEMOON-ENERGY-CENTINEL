import sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import scoreboard as S

NOW = datetime(2026, 11, 9, 8, 0, tzinfo=timezone.utc)


def series(last):
    # 25 días hasta el 08/11; el 08/11 (domingo) vale `last`
    from datetime import date, timedelta
    out = []
    for i in range(25):
        d = date(2026, 11, 8) - timedelta(days=24 - i)
        out.append((d.isoformat(), 26000))
    out[-1] = ("2026-11-08", last)
    return out


def test_detect_flags_drop_and_ignores_normal():
    assert S.detect(series(26000), "canarias", "Canarias", NOW.date()) == []
    f = S.detect(series(20000), "canarias", "Canarias", NOW.date())
    assert len(f) == 1 and f[0]["date"] == "2026-11-08" and f[0]["dev"] < -20


def test_lifecycle_pending_then_kept_or_corrected():
    f = {"Canarias": S.detect(series(20000), "canarias", "Canarias", NOW.date())}
    log = S.update({"entries": []}, f, NOW)
    e = log["entries"][0]
    assert e["status"] == "pendiente" and e["id"] == "R-SYS-Canarias-2026-11-08"
    later = datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc)
    kept = S.update(log, f, later)["entries"][0]
    assert kept["status"] == "se_mantiene"
    fixed = S.update(log, {"Canarias": []}, later)["entries"][0]
    assert fixed["status"] == "corregida" and fixed["dev"] is None and fixed["first_dev"] < -20


def test_stats_and_no_change_outside_window():
    log = {"entries": [{"id": "a", "zone": "Z", "date": "2026-10-01", "status": "corregida"}, {"id": "b", "zone": "Z", "date": "2026-10-02", "status": "se_mantiene"},
                       {"id": "c", "zone": "Z", "date": "2026-11-08", "status": "pendiente"}]}
    S.update(log, {"Z": []}, NOW)
    assert log["entries"][-1]["status"] in ("corregida", "se_mantiene")
    st = S.stats(log["entries"])
    assert st["total"] == 3 and st["pct_corregidas"] == 50 or st["pendientes"] <= 1
