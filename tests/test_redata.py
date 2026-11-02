import redata as R

RESP = lambda vals: {"included": [{"attributes": {"values": [{"value": v, "datetime": f"2026-10-{20 + i}T00:00:00.000+01:00"} for i, v in enumerate(vals)]}}]}


def test_url_geo_params():
    u = R.url("demanda", "evolucion", "2026-10-30T00:00", "2026-11-02T23:59", "day", "canarias")
    assert "geo_limit=canarias&geo_ids=8742" in u and "geo_trunc=electric_system" in u and "demanda/evolucion" in u
    assert "geo_" not in R.url("demanda", "evolucion", "a", "b")


def test_summarize_and_alert():
    s = R.summarize(R.daily_values(RESP([100, 100, 100, 60])))
    assert s["deviation"] == -0.4 and s["mwh"] == 60
    rd = R.RedData(get=lambda u: RESP([100, 100, 100, 60]), cache="/tmp/rd_test.json")
    rd.refresh()
    a = rd.alerts()
    assert len(a) == 5 and a[0]["type"] == "red-electrica" and "-40 %" in a[0]["title"]


def test_errors_are_tolerated():
    def bad(u):
        raise OSError("x")
    rd = R.RedData(get=bad, cache="/tmp/rd_test2.json")
    rd.refresh()
    assert rd.view()["status"]["state"] == "error" and rd.alerts() == []


GEN = {"included": [
    {"attributes": {"title": "Eólica", "type": "Renovable", "color": "#6fb114", "values": [{"value": 44040.6, "percentage": 0.0629, "datetime": "2026-10-30T00:00:00.000+01:00"}]}},
    {"attributes": {"title": "Ciclo combinado", "type": "No-Renovable", "color": "#ffcc66", "values": [{"value": 209840.6, "percentage": 0.2995, "datetime": "2026-10-30T00:00:00.000+01:00"}]}},
    {"attributes": {"title": "Solar fotovoltaica", "type": "Renovable", "color": "#e48500", "values": [{"value": 156570.3, "percentage": 0.2235, "datetime": "2026-10-30T00:00:00.000+01:00"}]}},
    {"attributes": {"title": "Generación total", "type": "total", "values": [{"value": 700633.9, "percentage": 1, "datetime": "2026-10-30T00:00:00.000+01:00"}]}}]}


def test_parse_generation():
    g = R.parse_generation(GEN)
    assert g["date"] == "2026-10-30" and g["items"][0]["name"] == "Ciclo combinado"
    assert g["renewable_pct"] == round((44041 + 156570) / 700634, 3) and R.parse_generation({}) is None


def test_parse_realtime_and_refresh_collects_everything():
    rt = {"included": [{"type": "Real", "attributes": {"values": [{"value": 30000, "datetime": "2026-11-02T10:00:00+01:00"}]}},
                       {"type": "Prevista", "attributes": {"values": [{"value": 31000, "datetime": "2026-11-02T10:00:00+01:00"}]}}]}
    r = R.parse_realtime(rt)
    assert r["mw"] == 30000 and r["deviation"] == round(-1000 / 31000, 3)

    def get(u):
        return GEN if "estructura-generacion" in u else rt if "demanda-tiempo-real" in u else RESP([100, 100, 100, 60])
    rd = R.RedData(get=get, cache="/tmp/rd_test3.json")
    rd.refresh()
    v = rd.view()
    assert v["generation"]["total_mwh"] == 700634 and v["realtime"]["mw"] == 30000 and len(v["history"]) == 4


def test_realtime_stats_and_yesterday():
    def pts(day, vals):
        return [{"datetime": f"{day}T{h:02d}:00:00.000+01:00", "value": v} for h, v in vals]
    real = pts("2026-11-01", [(10, 100), (11, 110), (12, 120)]) + pts("2026-11-02", [(10, 200), (11, 260), (12, 240), (13, 300)])
    fc = pts("2026-11-02", [(13, 250)])
    d = {"included": [{"type": "Real", "attributes": {"values": real}}, {"type": "Prevista", "attributes": {"values": fc}}]}
    r = R.parse_realtime(d)
    assert r["mw"] == 300 and r["max"] == {"mw": 300, "at": "13:00"} and r["min"]["mw"] == 200
    assert r["avg_mw"] == 250 and r["delta_1h"] == 60 and r["yesterday_same_mw"] == 120 and r["deviation"] == 0.2
    assert len(r["history"]) == 4 and len(r["yesterday"]) >= 1


def test_summarize_series():
    s = R.summarize(R.daily_values(RESP([100, 120, 90, 110])))
    assert [x["mwh"] for x in s["series"]] == [100, 120, 90, 110] and s["max"]["mwh"] == 120 and s["min"]["mwh"] == 90
