"""Informe de correcciones: compara, día a día, la primera vez que REE publicó cada dato con la última versión (y comprueba el factor de CO2).
Uso: python3 tools/revisions.py [carpeta]"""
import json
import os
import sys

KEYS = [("Generación total", "total"), ("Ciclo combinado", "cc"), ("Eólica", "eol"), ("Solar fotovoltaica", "sol"), ("Nuclear", "nuc"),
        ("co2_t", "co2"), ("spot_medio", "spot")]


def load(folder):
    snaps = []
    for f in sorted(os.listdir(folder)):
        if f.endswith(".json"):
            snaps.append(json.load(open(os.path.join(folder, f), encoding="utf-8")))
    return snaps


def revisions(snaps):
    """→ {fecha: {métrica: {first, last, pct, n}}} sólo con las métricas que cambiaron."""
    first, last, count = {}, {}, {}
    for s in snaps:
        for d, row in s["days"].items():
            for k, v in row.items():
                if k not in first.setdefault(d, {}):
                    first[d][k] = (v, s["taken"])
                last.setdefault(d, {})[k] = (v, s["taken"])
                if first[d][k][0] != v:
                    count.setdefault(d, {}).setdefault(k, set()).add(v)
    out = {}
    for d in sorted(first):
        for k in first[d]:
            a, b = first[d][k][0], last[d][k][0]
            if a != b and a:
                out.setdefault(d, {})[k] = {"first": a, "last": b, "pct": round((b - a) / abs(a) * 100, 1), "since": first[d][k][1]}
    return out


def factor_check(snaps, tol=0.03):
    """Días de la última instantánea en que factor × generación total no coincide con las emisiones totales (error de REE, no de cálculo)."""
    bad = []
    for d, r in sorted(snaps[-1]["days"].items()):
        t, g, f = r.get("co2_t"), r.get("Generación total"), r.get("co2_factor")
        if t and g and f and abs(f * g / t - 1) > tol:
            bad.append((d, round(f * 1000), round(t / g * 1000)))
    return bad


def report(snaps):
    if not snaps:
        return "Sin instantáneas todavía."
    lines = [f"{len(snaps)} instantáneas · de {snaps[0]['taken']} a {snaps[-1]['taken']}", ""]
    rev = revisions(snaps)
    lines.append("CORRECCIONES (primera publicación → última):")
    for d, ms in rev.items():
        for k, m in ms.items():
            lines.append(f"  {d}  {k:<20} {m['first']:>12,.1f} → {m['last']:>12,.1f}  ({m['pct']:+.1f} %)  visto por 1ª vez {m['since']}")
    if not rev:
        lines.append("  ninguna todavía")
    lines += ["", "FACTOR DE CO2 (g/kWh publicado por REE vs emisiones ÷ generación):"]
    bad = factor_check(snaps)
    lines += [f"  {d}  REE {f} g/kWh · correcto {c} g/kWh" for d, f, c in bad] or ["  coherente en todos los días"]
    return "\n".join(lines)


if __name__ == "__main__":
    print(report(load(sys.argv[1] if len(sys.argv) > 1 else "data/snapshots")))
