"""Compara el ojo de 2001 con los de 2026 sobre los mismos cuadros.

Lee lo que ya quedó en resultados/<equipo>/ (no vuelve a preguntar a ningún modelo):
ojo2001.jsonl, ojo2026.jsonl (Gemma) y ojo2026-qwen2.5vl-3b.jsonl. Las respuestas de
Qwen se vuelven a leer desde el texto crudo porque llegan en varias formas y en la
escala de la imagen que Ollama le arma al modelo, no en la de 640x480.

    python3 comparar.py resultados/<equipo>
"""
import json
import math
import re
import statistics
import sys
from pathlib import Path

RADIO = 22                       # el de escena.py
# Ollama le pasa a Qwen2.5-VL la imagen agrandada a 1036x784: 37x28 parches de 28 px,
# los 1036 tokens de imagen que reporta (1122 de entrada con la pregunta).
QWEN_ESCALA = (1036 / 640, 784 / 480)


def qwen(texto):
    """Devuelve (forma, x, y, recuadro) en 640x480. forma: "centro" si dio dos esquinas
    (recuadro = [x1, y1, x2, y2]), "esquina" si dio sólo la de arriba a la izquierda
    con un ancho inventado (recuadro = None)."""
    try:
        pendientes = [json.loads(texto)]
    except json.JSONDecodeError:            # a veces se corta o repite: se toma el primer recuadro del texto
        m = re.search(r"\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]", texto)
        pendientes = [[int(v) for v in m.groups()]] if m else []
        if not m:
            c = {k: int(v) for k, v in re.findall(r"\"(xmin|xmax|ymin|ymax)\":\s*(\d+)", texto)[:4]}
            pendientes = [c] if c else []
    while pendientes:
        c = pendientes.pop(0)
        if isinstance(c, list) and len(c) == 4 and all(isinstance(v, (int, float)) for v in c):
            return centro_de(c)
        if isinstance(c, list):
            pendientes += c
        elif isinstance(c, dict):
            if all(k in c for k in ("xmin", "xmax", "ymin", "ymax")):
                return centro_de([c["xmin"], c["ymin"], c["xmax"], c["ymax"]])
            if "xmin" in c and "ymin" in c:
                return "esquina", c["xmin"] / QWEN_ESCALA[0], c["ymin"] / QWEN_ESCALA[1], None
            pendientes += [c[k] for k in ("bbox_2d", "bbox") if k in c]
    return None, None, None, None


def centro_de(c):
    r = [c[0] / QWEN_ESCALA[0], c[1] / QWEN_ESCALA[1], c[2] / QWEN_ESCALA[0], c[3] / QWEN_ESCALA[1]]
    return "centro", (r[0] + r[2]) / 2, (r[1] + r[3]) / 2, r


def main():
    d = Path(sys.argv[1])
    leer = lambda n: [json.loads(l) for l in open(d / n)]
    g = {(r["caso"], r["cuadro"]): r for r in leer("ojo2026.jsonl")}
    q = {(r["caso"], r["cuadro"]): r for r in leer("ojo2026-qwen2.5vl-3b.jsonl")}
    cuadros = sorted(set(g) & set(q))
    v2001 = {}
    for r in leer("ojo2001.jsonl"):
        if (r["caso"], r["cuadro"]) in g:
            v2001.setdefault((r["filtro"], r["cancelar"]), {})[(r["caso"], r["cuadro"])] = r["error_px"]

    filas = []
    for caso in sorted({c for c, _ in cuadros}):
        ks = [k for k in cuadros if k[0] == caso]
        med = lambda xs: round(statistics.median(xs), 1) if xs else None
        crudo = med([v2001[("ninguno", 0)][k] for k in ks])
        mejor = min(((med([v[k] for k in ks]), f"{f}{'+cancelador' if c else ''}") for (f, c), v in v2001.items()))
        centros, esquinas, sin = [], [], 0
        for k in ks:
            forma, x, y, _ = qwen(q[k]["respuesta"])
            rx, ry = q[k]["real"]
            if forma == "centro":
                centros.append(math.dist((x, y), (rx, ry)))
            elif forma == "esquina":
                esquinas.append(math.dist((x, y), (rx - RADIO, ry - RADIO)))
            else:
                sin += 1
        filas.append({"caso": caso, "cuadros": len(ks),
                      "ojo2001_crudo": crudo, "ojo2001_mejor": mejor[0], "ojo2001_mejor_variante": mejor[1],
                      "qwen_centro": med(centros), "qwen_centro_n": len(centros),
                      "qwen_esquina": med(esquinas), "qwen_esquina_n": len(esquinas), "qwen_sin": sin,
                      "gemma": med([g[k]["error_px"] for k in ks]),
                      "gemma_respuestas": sorted({tuple(g[k]["visto"]) for k in ks})})
    seg = lambda m: round(statistics.median(m[k]["seg"] for k in cuadros), 1)
    ms = round(statistics.median(r["ms"] for r in leer("ojo2001.jsonl")
                                 if (r["filtro"], r["cancelar"]) == ("mediana", 1)), 2)
    salida = {"equipo": d.name, "cuadros": len(cuadros), "qwen_escala": QWEN_ESCALA,
              "tiempo_por_cuadro": {"ojo2001_mediana_cancelador_ms": ms, "qwen_s": seg(q), "gemma_s": seg(g)}, "casos": filas}
    (d / "comparacion.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1))

    print(f"{'caso':16}{'2001 crudo':>11}{'2001 mejor':>11}  {'variante':22}{'Qwen ctr':>9}{'n':>3}{'Qwen esq':>9}{'n':>3}{'Gemma':>8}")
    for f in filas:
        n = lambda v: f"{v:.1f}" if v is not None else "—"
        print(f"{f['caso']:16}{n(f['ojo2001_crudo']):>11}{n(f['ojo2001_mejor']):>11}  {f['ojo2001_mejor_variante']:22}"
              f"{n(f['qwen_centro']):>9}{f['qwen_centro_n']:>3}{n(f['qwen_esquina']):>9}{f['qwen_esquina_n']:>3}{n(f['gemma']):>8}")
    print("tiempo por cuadro:", salida["tiempo_por_cuadro"])
    print("Gemma contestó:", sorted({tuple(r["visto"]) for r in g.values()}))


if __name__ == "__main__":
    main()
