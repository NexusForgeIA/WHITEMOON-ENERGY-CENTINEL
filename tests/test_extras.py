import time
from datetime import date, datetime, timedelta

import meteo
import notify
import risk
import rules
import server

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">
<entry><title>Orange Wind Warning issued for Spain - Litoral gallego</title><cap:areaDesc>Litoral gallego</cap:areaDesc><cap:onset>2026-11-02T18:00:00+00:00</cap:onset><cap:expires>2026-11-03T18:00:00+00:00</cap:expires></entry>
<entry><title>Yellow Rain Warning issued for Spain - Vega del Segura</title><cap:areaDesc>Vega del Segura</cap:areaDesc><cap:onset>2026-11-02T18:00:00+00:00</cap:onset><cap:expires>2026-11-03T18:00:00+00:00</cap:expires></entry>
<entry><title>Red Snow/Ice Warning issued for Spain - Picos</title><cap:areaDesc>Picos</cap:areaDesc><cap:onset>2026-11-05T18:00:00+00:00</cap:onset><cap:expires>2026-11-06T18:00:00+00:00</cap:expires></entry>
<entry><title>Algo raro</title></entry></feed>"""


def test_meteo_parse_and_view():
    it = meteo.parse(ATOM)
    assert [(i["type"], i["level"]) for i in it] == [("Viento", "naranja"), ("Lluvia", "amarillo"), ("Nieve/hielo", "rojo")]
    now = datetime.fromisoformat("2026-11-02T20:00:00+00:00").timestamp()
    m = meteo.Meteo(get=lambda: ATOM, now=lambda: now)
    m.refresh()
    v = m.view()
    assert v["counts"] == {"rojo": 0, "naranja": 1, "amarillo": 1}            # el rojo es dentro de 3 días: aún no
    assert v["grid"]["naranja"] == 1 and v["yellow_by_type"] == {"Lluvia": 1}
    assert risk.f_meteo(v) == 15 and risk.f_meteo({"grid": {"rojo": 1}}) == 30
    bad = meteo.Meteo(get=lambda: (_ for _ in ()).throw(OSError("x")))
    bad.refresh()
    assert bad.view()["status"]["state"] == "error"


def al(i="R-DEM-DROP-peninsular", sev="alta", at="t1", rule="R-DEM-DROP"):
    return {"id": i, "rule": rule, "sev": sev, "title": "T", "detail": "D", "at": at}


def test_notifier_dedupe_escalation_and_baseline():
    sent, clock = [], [1000.0]
    n = notify.Notifier("https://x.es", "topic", "tok", "chat", post=lambda u, o: sent.append((u, o)), now=lambda: clock[0])
    assert n.check([al()]) == [] and sent == []                              # primera pasada: solo toma nota
    assert n.check([al()]) == []                                              # sin cambios
    assert len(n.check([al(sev="muy alta")])) == 1 and len(sent) == 2         # escalada → ntfy + telegram
    clock[0] += 4 * 3600
    assert len(n.check([al(sev="muy alta")])) == 1                            # recordatorio a las 3 h
    d = al("R-SYS-baleares", rule="R-SYS", at="2026-10-30")
    assert len(n.check([d])) == 1 and n.check([d]) == []                      # diaria: una vez
    assert sent[0][0] == "https://ntfy.sh/" and "api.telegram.org" in sent[1][0]


def test_atom_and_routes():
    x = notify.atom([al()], "https://x.es").decode()
    assert "<entry>" in x and "T" in x
    code, o, raw, ct = server.api("/alertas.atom", {})
    assert code == 200 and ct.startswith("application/atom+xml") and raw.startswith(b"<?xml")
    assert server.api("/api/config", {})[1]["ntfy"]["url"].startswith("https://ntfy.sh/")
    assert server.api("/api/historial", {})[1]["realtime"]["episodes"] == []


def test_replay_and_daily_hits():
    t0 = datetime(2026, 11, 2, 8, 0)
    vals = [30000] * 60 + [29000, 27000, 25000] + [25000] * 10
    h = [{"t": (t0 + timedelta(minutes=5 * i)).isoformat() + "+01:00", "real": v, "forecast": 30000} for i, v in enumerate(vals)]
    ep = rules.replay_realtime({"history": h})
    assert any(e["rule"] == "R-DEM-DROP" and e["sev"] == "muy alta" for e in ep)
    daily = [[(date(2026, 10, 1) + timedelta(days=k)).isoformat(), 1000] for k in range(28)]
    daily[-1][1] = 600
    hits, days = rules.daily_hits({"canarias": {"name": "Canarias", "daily": daily}})
    assert days == 28 and hits[0]["zone"] == "Canarias" and hits[0]["sev"] == "muy alta" and not hits[0]["holiday"]


def test_holiday_is_not_alerted():
    s = {"canarias": {"name": "Canarias", "date": "2026-10-12", "mwh": 700, "dow_mean": 1000, "dow_dev": -0.3}}
    assert rules.system_rules(s, date(2026, 10, 13)) == []


def test_provisional_last_readings_do_not_alert():
    """Las últimas lecturas de REE son provisionales (hoy 29.643 pasó a 31.668): no deben disparar reglas ni índice hasta consolidarse."""
    t0 = datetime(2026, 11, 2, 8, 0)
    vals = [31700] * 60 + [29600]                       # última lectura anómala (provisional)
    h = [{"t": (t0 + timedelta(minutes=5 * i)).isoformat() + "+01:00", "real": v, "forecast": 31500} for i, v in enumerate(vals)]
    last = risk.ts_of(h[-1]["t"])
    assert rules.realtime_rules({"history": h}, last + 60) == []                 # recién publicada
    assert rules.realtime_rules({"history": h}, last + 10 * 60) == []
    rt = {"mw": 29600, "at": h[-1]["t"], "history": h}
    assert risk.compute(rt, None, [], now=last + 10 * 60)["score"] == 0
    h[-1]["real"] = 25000                                                          # si la caída sigue ahí 25 min después, sí es real
    assert any(a["rule"] == "R-DEM-DROP" for a in rules.realtime_rules({"history": h}, last + 26 * 60))


def test_seasonal_decline_does_not_alert():
    """Baleares en octubre: baja el turismo semana a semana; no es una caída anómala (sí lo es frente a ambas bases)."""
    bal = [20334, 21028, 21786, 21912, 20663, 19307, 18568, 20019, 19691, 19216, 17169, 17002, 15869, 15245, 15782, 17222, 17368, 16367, 17029, 16358, 15889,
           16696, 16681, 15812, 15876, 15875, 14933, 14463, 15200, 15267, 15322, 15271, 14899]
    daily = [[(date(2026, 9, 28) + timedelta(days=i)).isoformat(), x] for i, x in enumerate(bal)]
    hits, _ = rules.daily_hits({"b": {"name": "Baleares", "daily": daily}})
    assert [h["date"] for h in hits if not h["holiday"]] == []
    daily[-1][1] = 11000                                                           # un hundimiento real sí salta
    assert rules.daily_hits({"b": {"name": "Baleares", "daily": daily}})[0][0]["sev"] in ("alta", "muy alta")


def test_meteo_type_normalised():
    x = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Yellow Coastal Event Warning issued for Spain - X</title><onset>2026-11-02T00:00:00+00:00</onset><expires>2026-11-03T00:00:00+00:00</expires></entry></feed>'
    assert meteo.parse(x)[0]["type"] == "Fenómeno costero"
