#!/usr/bin/env python3
"""Prepara lo que muestra crtdrops.mx/fantasmas/ con lo que corrió de verdad.

Toma los cuadros 0 a 3 de cada caso (los mismos que vieron los tres ojos), los
pasa a WebP para la página y escribe datos.js con lo que contestó cada ojo:
el de 2001 sin filtro y con mediana + cancelador, Qwen2.5-VL 3B y Gemma 3 4B.
No vuelve a preguntar a ningún modelo.

    python3 sitio_fantasmas.py corridas resultados/<equipo> salida/
    rsync -a salida/ ../sitio/fantasmas/        # desde hope_x

Necesita Pillow (sólo para el WebP).
"""
import json
import statistics
import sys
from pathlib import Path

from PIL import Image

import comparar

VARIANTES = {"crudo": ("ninguno", 0), "mediana": ("mediana", 1)}
CALIDAD = 70


def main():
    corridas, res, salida = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    (salida / "cuadros").mkdir(parents=True, exist_ok=True)
    leer = lambda n: [json.loads(l) for l in open(res / n)]
    g = {(r["caso"], r["cuadro"]): r for r in leer("ojo2026.jsonl")}
    q = {(r["caso"], r["cuadro"]): r for r in leer("ojo2026-qwen2.5vl-3b.jsonl")}
    o = {}
    todas = {}
    for r in leer("ojo2001.jsonl"):
        v = (r["filtro"], r["cancelar"])
        todas.setdefault(v, []).append(r)
        o[(v, r["caso"], r["cuadro"])] = r
    claves = sorted(set(g) & set(q))
    uno = lambda v: round(v, 1)

    casos = {}
    for caso, n in claves:
        r = q[(caso, n)]
        forma, x, y, recuadro = comparar.qwen(r["respuesta"])
        rx, ry = r["real"]
        if forma == "centro":
            qe = {"forma": forma, "punto": [uno(x), uno(y)], "recuadro": [uno(v) for v in recuadro],
                  "error": uno(((x - rx) ** 2 + (y - ry) ** 2) ** .5)}
        elif forma == "esquina":
            qe = {"forma": forma, "punto": [uno(x), uno(y)],
                  "error": uno(((x - rx + comparar.RADIO) ** 2 + (y - ry + comparar.RADIO) ** 2) ** .5)}
        else:
            qe = {"forma": None}
        qe.update(seg=r["seg"], respuesta=r["respuesta"])
        cuadro = {"n": n, "real": [uno(rx), uno(ry)], "imagen": f"cuadros/{caso}-{n}.webp",
                  "qwen": qe,
                  "gemma": {"punto": g[(caso, n)]["visto"], "error": g[(caso, n)]["error_px"],
                            "seg": g[(caso, n)]["seg"], "respuesta": g[(caso, n)]["respuesta"]}}
        for nombre, v in VARIANTES.items():
            a = o[(v, caso, n)]
            cuadro[nombre] = {"punto": [uno(c) for c in a["visto"]], "error": a["error_px"], "ms": a["ms"]}
        casos.setdefault(caso, {"caso": caso, "fantasma": r["fantasma"], "nivel": r["nivel"], "cuadros": []})
        casos[caso]["cuadros"].append(cuadro)
        Image.open(corridas / caso / f"f{n:03d}.pgm").save(salida / "cuadros" / f"{caso}-{n}.webp",
                                                            quality=CALIDAD, method=6)

    # Las diez variantes del ojo de 2001, sobre los mismos cuadros
    variantes = []
    for (filtro, cancelar), rs in sorted(todas.items()):
        rs = [r for r in rs if (r["caso"], r["cuadro"]) in g]
        por_caso = {}
        for r in rs:
            por_caso.setdefault(r["caso"], []).append(r["error_px"])
        peor = max((statistics.median(e), c) for c, e in por_caso.items())
        variantes.append({"filtro": filtro, "cancelar": cancelar,
                          "mediana": round(statistics.median(r["error_px"] for r in rs), 2),
                          "peor": uno(peor[0]), "peor_caso": peor[1],
                          "ms": round(statistics.median(r["ms"] for r in rs), 2)})

    datos = {"equipo": res.name, "radio": comparar.RADIO, "escala_qwen": [1036, 784],
             "cuadros": len(claves),
             "tiempos": {"mediana_ms": next(v["ms"] for v in variantes if (v["filtro"], v["cancelar"]) == ("mediana", 1)),
                         "qwen_s": round(statistics.median(q[k]["seg"] for k in claves), 1),
                         "gemma_s": round(statistics.median(g[k]["seg"] for k in claves), 1)},
             "variantes": variantes,
             "casos": list(casos.values())}
    (salida / "datos.js").write_text(
        "// Generado por fantasmas/sitio_fantasmas.py con los resultados reales; no se edita a mano.\n"
        "window.FANTASMAS = " + json.dumps(datos, ensure_ascii=False, indent=1) + ";\n")
    print(len(claves), "cuadros ·", salida)


if __name__ == "__main__":
    main()
