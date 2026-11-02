import time
import alerts as E

NOW = 1_800_000_000
RSS = lambda items: "<rss><channel>" + "".join(
    f"<item><title>{t} - {s}</title><pubDate>{d}</pubDate><link>http://x/{i}</link><source url='https://{s.lower()}.es'>{s}</source></item>"
    for i, (t, s, d) in enumerate(items)) + "</channel></rss>"


def D(age_min):
    return time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(NOW - age_min * 60))


def test_parse_filters_noise():
    x = RSS([("Cero eléctrico en toda la isla de La Palma", "RTVC", D(30)), ("El precio de la luz sube mañana", "ABC", D(10)),
             ("Apagón analógico: cómo ver la tele", "El País", D(5)), ("Apagón en Ciudad de México", "Infobae", D(5))])
    r = E.parse(x)
    assert [i["t"] for i in r] == ["Cero eléctrico en toda la isla de La Palma"]


def test_build_red_for_big_recent():
    items = [{"t": "Cero eléctrico en toda la isla de La Palma", "s": "RTVC", "ts": (NOW - 1800), "u": "u"}]
    a = E.build(items, NOW)
    assert a[0]["sev"] == "muy alta" and a[0]["place"] == "La Palma" and a[0]["title"].startswith("Apagón")


def test_build_alta_single_source_not_big_and_old_dropped():
    items = [{"t": "Apagón en un barrio de Valencia", "s": "Las Provincias", "ts": (NOW - 1800), "u": "u"},
             {"t": "Apagón en Tenerife", "s": "X", "ts": (NOW - 30 * 3600), "u": "u"},
             {"t": "Apagón sin lugar conocido", "s": "X", "ts": (NOW - 600), "u": "u"}]
    a = E.build(items, NOW)
    assert len(a) == 1 and a[0]["place"] == "Valencia" and a[0]["sev"] == "alta"


def _it(t, ago_h, s="A", now=1_800_000_000):
    return {"t": t, "s": s, "ts": int(now - ago_h * 3600), "u": "http://x/" + str(abs(hash(t)))}


def test_only_current_events():
    now = 1_800_000_000
    fresh = [_it("Apagón en La Palma: la isla entera sin luz", 1, "A"), _it("Cero energético en La Palma", 1.2, "B")]
    assert [a["sev"] for a in E.build(fresh, now)] == ["muy alta"]
    assert E.build([_it("Apagón en La Palma", 8, "A"), _it("Cero energético en La Palma", 9, "B")], now) == []      # ya pasó (más de 6 h)
    mid = E.build([_it("Apagón en La Palma", 4, "A")], now)
    assert mid and mid[0]["sev"] == "alta"                                                                              # 3-6 h: ya no es roja
    rest = fresh + [_it("Se restablece el suministro eléctrico en La Palma tras el apagón", 0.3, "C")]
    assert E.build(rest, now) == []                                                                                # restablecido
    again = rest + [_it("Nuevo apagón en La Palma: otra vez sin luz", 0.1, "D")]
    assert E.build(again, now)                                                                                     # si vuelve a caerse, vuelve la alerta


def test_retrospectives_are_ignored():
    xml = ("<rss><channel>" + "".join(f"<item><title>{t} - La Razón</title><source url='https://larazon.es'>La Razón</source><pubDate>Mon, 02 Nov 2026 17:00:00 GMT</pubDate><link>http://x/{i}</link></item>"
           for i, t in enumerate(["Cero energético en Canarias: así han sido los apagones de las islas en los últimos años", "Qué pasó en el apagón de La Palma hace dos años", "Apagón en Tenerife"])) + "</channel></rss>")
    got = E.parse(xml)
    assert [g["t"] for g in got] == ["Apagón en Tenerife"]
