#!/usr/bin/env python3
"""Corre el ojo de 2001 sobre todas las escenas embrujadas y mide el error.

    python3 correr2001.py corridas/ resultados/        # compila ojo2001.c si hace falta

Por cada caso (fantasma y nivel) y cada variante (filtro, con o sin
cancelador de eco) escribe una línea por cuadro en resultados/ojo2001.jsonl, y
un resumen por caso y variante en resultados/resumen2001.json: error mediano y
p95 en píxeles contra la posición real, y cuántos cuadros perdió (sin píxeles o
con más de PERDIDO px de error).
"""
import json
import math
import platform
import socket
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FILTROS = ["ninguno", "media", "mediana", "laplaciano", "minima"]
UMBRAL = {"ninguno": 130, "media": 130, "mediana": 130, "laplaciano": 120, "minima": 128}
PERDIDO = 25.0
# En la Mac de pruebas el SDK por omisión no enlaza; en Linux no hace falta.
SYSROOT = ["-isysroot", "/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk"] if platform.system() == "Darwin" else []


def compilar():
    binario = AQUI / "ojo2001"
    fuente = AQUI / "ojo2001.c"
    if not binario.exists() or binario.stat().st_mtime < fuente.stat().st_mtime:
        subprocess.run(["cc", "-O2", "-std=c99", *SYSROOT, "-o", str(binario), str(fuente)], check=True)
    return binario


def percentil(v, p):
    if not v:
        return None
    v = sorted(v)
    k = (len(v) - 1) * p
    i = int(k)
    return v[i] if i + 1 >= len(v) else v[i] + (v[i + 1] - v[i]) * (k - i)


def main(corridas, resultados):
    binario = compilar()
    resultados.mkdir(parents=True, exist_ok=True)
    salida = (resultados / "ojo2001.jsonl").open("w")
    resumen = []
    for caso in sorted(p for p in corridas.iterdir() if (p / "verdad.json").exists()):
        verdad = json.loads((caso / "verdad.json").read_text())
        cuadros = {f"f{c['cuadro']:03d}.pgm": c for c in verdad["cuadros"]}
        lista = "\n".join(str(caso / n) for n in sorted(cuadros)) + "\n"
        for filtro in FILTROS:
            for cancelar in (0, 1):
                r = subprocess.run([str(binario), filtro, str(cancelar), str(UMBRAL[filtro])],
                                   input=lista, capture_output=True, text=True, check=True)
                errores, perdidos, ms = [], 0, []
                for linea in r.stdout.splitlines():
                    o = json.loads(linea)
                    c = cuadros[Path(o["archivo"]).name]
                    if o.get("x") is None:
                        err = None
                        perdidos += 1
                    else:
                        err = math.hypot(o["x"] - c["x"], o["y"] - c["y"])
                        errores.append(err)
                        if err > PERDIDO:
                            perdidos += 1
                    ms.append(o["ms"])
                    salida.write(json.dumps({"caso": caso.name, "fantasma": verdad["fantasma"],
                                             "nivel": verdad["nivel"], "filtro": filtro,
                                             "cancelar": cancelar, "cuadro": c["cuadro"],
                                             "real": [c["x"], c["y"]], "visto": [o.get("x"), o.get("y")],
                                             "error_px": None if err is None else round(err, 2),
                                             "pixeles": o["pixeles"], "eco_d": o["eco_d"],
                                             "eco_a": o["eco_a"], "ms": o["ms"]}) + "\n")
                resumen.append({"caso": caso.name, "fantasma": verdad["fantasma"], "nivel": verdad["nivel"],
                                "filtro": filtro, "cancelar": cancelar, "cuadros": len(cuadros),
                                "error_mediano": round(percentil(errores, 0.5), 2) if errores else None,
                                "error_p95": round(percentil(errores, 0.95), 2) if errores else None,
                                "perdidos": perdidos, "ms_mediano": round(percentil(ms, 0.5), 2)})
    salida.close()
    (resultados / "resumen2001.json").write_text(json.dumps({
        "equipo": socket.gethostname(), "maquina": platform.machine(), "perdido_px": PERDIDO,
        "umbral": UMBRAL, "resumen": resumen}, indent=1, ensure_ascii=False))
    print(len(resumen), "combinaciones →", resultados / "resumen2001.json")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
