import json

import server


def test_api_routes_without_sources():
    assert server.api("/healthz", {}) == (200, {"ok": True})
    code, c = server.api("/api/caso/28a", {})
    assert code == 200 and len(c["demand"]["values"]) == 48 and c["demand"]["values"][13] == 518
    assert server.api("/api/caso/zzz", {})[0] == 404
    assert server.api("/nada", {}) is None
    code, r = server.api("/api/resumen", {})
    assert code == 200 and r["alerts"] == []
