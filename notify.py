"""Avisos de las alertas: ntfy.sh (canal público, sin cuenta) y Telegram (si hay token), más un feed Atom.
Solo se envía una alerta nueva, una escalada de nivel o, si sigue activa, un recordatorio cada 3 h (las diarias, una sola vez)."""
import json
import threading
import time
import urllib.request
from datetime import datetime, timezone
from xml.sax.saxutils import escape

REMIND_S = 3 * 3600
REALTIME = ("R-DEM-DROP", "R-DEM-DEV", "R-OSC")


def _post(url, obj, timeout=15):
    req = urllib.request.Request(url, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json", "User-Agent": "RedSentinel/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status


def message(a, site):
    lvl = "ALERTA ROJA" if a["sev"] == "muy alta" else "Atención"
    return f"{lvl} · {a['title']}\n{a['detail']}\nInformativo, no oficial. {site}"


class Notifier:
    def __init__(self, site, ntfy_topic=None, tg_token=None, tg_chat=None, post=_post, now=time.time):
        self.site, self.topic, self.tg_token, self.tg_chat, self.post, self.now = site.rstrip("/"), ntfy_topic, tg_token, tg_chat, post, now
        self.state, self.first, self.sent = {}, True, []

    def due(self, alerts):
        out = []
        for a in alerts:
            s, t = self.state.get(a["id"]), self.now()
            rt = a["rule"] in REALTIME
            new = s is None or (s["sev"] != "muy alta" and a["sev"] == "muy alta") or (not rt and s["at"] != a.get("at")) or (rt and t - s["t"] > REMIND_S)
            if new:
                out.append(a)
            if new or s is None:
                self.state[a["id"]] = {"sev": a["sev"], "t": t, "at": a.get("at")}
        return out

    def send(self, a):
        text, ok = message(a, self.site), False
        if self.topic:
            try:
                self.post("https://ntfy.sh/", {"topic": self.topic, "title": ("🚨 " if a["sev"] == "muy alta" else "⚠️ ") + a["title"], "message": a["detail"] + "\nInformativo, no oficial.",
                                              "priority": 5 if a["sev"] == "muy alta" else 3, "tags": ["zap"], "click": self.site})
                ok = True
            except Exception:
                pass
        if self.tg_token and self.tg_chat:
            try:
                self.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage", {"chat_id": self.tg_chat, "text": text, "disable_web_page_preview": True})
                ok = True
            except Exception:
                pass
        if ok:
            self.sent.append({"id": a["id"], "t": int(self.now() * 1000), "title": a["title"]})
            self.sent = self.sent[-50:]
        return ok

    def check(self, alerts):
        """La primera pasada solo toma nota de lo que ya está activo (un reinicio no repite avisos)."""
        due = self.due(alerts)
        if self.first:
            self.first = False
            return []
        return [a for a in due if self.send(a)]

    def _loop(self, get_alerts):
        while True:
            try:
                self.check(get_alerts())
            except Exception:
                pass
            time.sleep(60)

    def start(self, get_alerts):
        threading.Thread(target=self._loop, args=(get_alerts,), daemon=True, name="notify").start()


def atom(alerts, site, now=None):
    now = now or time.time()
    upd = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ents = "".join(f"<entry><id>{escape(site)}/#{escape(a['id'])}-{escape(str(a.get('at')))}</id><title>{escape(a['title'])}</title><updated>{upd}</updated>"
                   f"<link href=\"{escape(site)}\"/><summary>{escape(a['detail'])}</summary></entry>" for a in alerts)
    return ('<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Red-Sentinel · alertas de la red eléctrica</title>'
            f'<id>{escape(site)}/alertas.atom</id><updated>{upd}</updated><link href="{escape(site)}"/><subtitle>Reglas de caída calculadas con datos de Red Eléctrica. Informativo, no oficial.</subtitle>{ents}</feed>').encode()
