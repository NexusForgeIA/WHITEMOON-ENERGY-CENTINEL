import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import grid

SAMPLE = json.load(open(os.path.join(os.path.dirname(__file__), "overpass_lines_sample.json")))


def test_units():
    assert grid.mw_of("1003 MW") == 1003
    assert grid.mw_of("1.2 GW") == 1200
    assert grid.mw_of("500 kW") == 0.5
    assert grid.mw_of("24;30 MW") == 24
    assert grid.mw_of("yes") is None and grid.mw_of(None) is None
    assert grid.kv_of("400000;220000") == 400
    assert grid.kv_of("132000") == 132 and grid.kv_of(None) == 0


def test_reduce_real_lines_and_plants():
    lines, plants, subs = {}, {}, {}
    grid.reduce(SAMPLE, plants, lines, subs)
    assert len(lines) > 10 and all(l["kv"] >= 380 and len(l["p"]) >= 2 for l in lines.values())
    n_pts = sum(len(l["p"]) for l in lines.values())
    assert n_pts < sum(len(e["geometry"]) for e in SAMPLE)          # se simplifica
    grid.reduce(SAMPLE, plants, lines, subs)                          # dedupe entre teselas
    assert len(lines) == len({f'{e["type"]}{e["id"]}' for e in SAMPLE})
    els = [{"type": "way", "id": 1, "center": {"lat": 40.7, "lon": -2.6}, "tags": {"power": "plant", "plant:source": "nuclear", "plant:output:electricity": "1003 MW", "name": "T"}},
           {"type": "way", "id": 2, "center": {"lat": 38, "lon": -3}, "tags": {"power": "plant", "plant:source": "solar", "plant:output:electricity": "5 MW"}},
           {"type": "way", "id": 3, "center": {"lat": 38.5, "lon": -3}, "tags": {"power": "plant", "plant:source": "solar", "plant:output:electricity": "50 MW", "name": "S"}},
           {"type": "node", "id": 4, "lat": 40.1, "lon": -3.1, "tags": {"power": "substation", "voltage": "400000", "name": "Sub"}},
           {"type": "node", "id": 5, "lat": 40.2, "lon": -3.1, "tags": {"power": "substation", "voltage": "132000"}}]
    p, l, s = {}, {}, {}
    grid.reduce(els, p, l, s)
    assert {v["g"] for v in p.values()} == {"nuclear", "solar"} and len(p) == 2    # solar de 5 MW fuera
    assert len(s) == 1 and list(s.values())[0]["kv"] == 400


def test_grid_with_fake_opener_and_seed():
    calls = []

    def opener(ep, q):
        calls.append(ep)
        return {"elements": SAMPLE}
    d = tempfile.mkdtemp()
    g = grid.Grid(cache=os.path.join(d, "g.json"), opener=opener, pause=0)
    g.run()
    v = g.view()
    assert v["status"]["state"] == "ok" and v["counts"]["lines"] > 10
    nuc = [p for p in v["plants"] if p["g"] == "nuclear"]
    assert len(nuc) == 7 and sum(1 for p in nuc if p["off"]) == 2     # 5 en servicio + Garoña y Lemoiz
    assert v["totals_mw"]["nuclear"] == 1957 + 1988 + 1092 + 1087 + 1003
    assert os.path.exists(os.path.join(d, "g.json"))
    g2 = grid.Grid(cache=os.path.join(d, "g.json"), opener=lambda *a: 1 / 0, pause=0)    # segunda vez: usa la caché
    g2.run()
    assert g2.view()["counts"]["lines"] == v["counts"]["lines"]


def test_grid_overpass_down():
    def opener(ep, q):
        raise OSError("caído")
    g = grid.Grid(cache=os.path.join(tempfile.mkdtemp(), "g.json"), opener=opener, pause=0)
    g.run()
    assert g.status["state"] == "error"


def test_seed_loaded_and_partial_not_published(tmp_path):
    g = grid.Grid(cache=str(tmp_path / "g.json"), opener=lambda ep, q: {"elements": []}, pause=0, use_seed=True)
    g.start()
    import time as _t
    for _ in range(50):
        if g.status["state"] in ("ok", "error"):
            break
        _t.sleep(.05)
    v = g.view()
    assert v["counts"]["lines"] > 1000 and v["counts"]["plants"] > 1000      # el seed sigue ahí aunque la descarga nueva venga vacía
    assert any(p["g"] == "nuclear" and p["mw"] for p in v["plants"])


def test_null_geometry_nodes_do_not_break_tile():
    el = [{"type": "way", "id": 7, "tags": {"power": "line", "voltage": "400000"}, "geometry": [{"lat": 40, "lon": -3}, None, {"lat": 40.1, "lon": -3.1}]}]
    lines, p, s = {}, {}, {}
    grid.reduce(el, p, lines, s)
    assert len(lines) == 1 and len(lines["way7"]["p"]) == 2
