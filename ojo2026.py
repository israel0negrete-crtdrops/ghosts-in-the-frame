#!/usr/bin/env python3
"""El ojo de 2026: un modelo abierto con visión (Gemma 3 4B en Ollama, local)
mira los mismos cuadros embrujados y dice dónde está el objeto.

    python3 ojo2026.py corridas/ resultados/ [--cuadros 8] [--modelo gemma3:4b]

Convierte cada PGM a PNG (sin dependencias), se lo pasa al modelo con la misma
pregunta, temperatura 0 y semilla fija, y guarda la respuesta cruda, la
posición que dio, el error contra la real y lo que tardó, en
resultados/ojo2026.jsonl. Se puede cortar y volver a correr: salta lo hecho.
"""
import argparse
import base64
import json
import math
import re
import socket
import struct
import time
import urllib.request
import sys
import zlib
from datetime import datetime
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434/api/generate"
PREGUNTA = (
    "This is a 640x480 grayscale video frame. The top 8 rows are a test signal; ignore them. "
    "There is exactly one real object: a bright round disk on a uniform background. The frame may "
    "be haunted by interference: noise, bars, or a fainter ghost copy of the disk shifted to the right. "
    "Give the pixel coordinates of the center of the real disk, with x from 0 (left) to 639 and "
    "y from 0 (top) to 479. Answer only with JSON like {\"x\": 123, \"y\": 456}."
)


# Qwen2.5-VL está entrenado para ubicar objetos con un recuadro en píxeles.
PREGUNTA_QWEN = (
    "This 640x480 grayscale video frame has one real object: a bright round disk on a uniform background. "
    "Ignore the top 8 rows (a test signal), any noise, bars, and any fainter ghost copy of the disk. "
    "Locate the real disk and output its bbox coordinates in JSON format."
)


def pregunta(modelo):
    return PREGUNTA_QWEN if "qwen" in modelo else PREGUNTA


def centro(texto):
    """Saca (x, y) de la respuesta: {"x","y"} de Gemma o el recuadro bbox_2d de Qwen."""
    j = json.loads(texto)
    if isinstance(j, dict) and "x" in j and "y" in j:
        return float(j["x"]), float(j["y"])
    pendientes = j if isinstance(j, list) else [j]
    while pendientes:                      # Qwen a veces anida el recuadro un nivel más
        c = pendientes.pop(0)
        if isinstance(c, list) and len(c) == 4 and all(isinstance(v, (int, float)) for v in c):
            return (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
        if isinstance(c, list):
            pendientes += c
        elif isinstance(c, dict):
            pendientes += [c[k] for k in ("bbox_2d", "bbox") if k in c]
    raise ValueError("sin coordenadas")


def leer_pgm(ruta):
    datos = ruta.read_bytes()
    cab = re.match(rb"P5\s+(\d+)\s+(\d+)\s+(\d+)\s", datos)
    w, h = int(cab.group(1)), int(cab.group(2))
    return w, h, datos[cab.end():cab.end() + w * h]


def a_png(w, h, gris):
    def trozo(tipo, d):
        return struct.pack(">I", len(d)) + tipo + d + struct.pack(">I", zlib.crc32(tipo + d) & 0xFFFFFFFF)
    filas = b"".join(b"\x00" + gris[y * w:(y + 1) * w] for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + trozo(b"IDAT", zlib.compress(filas, 6)) + trozo(b"IEND", b""))


def preguntar(modelo, png):
    cuerpo = json.dumps({"model": modelo, "prompt": pregunta(modelo), "images": [base64.b64encode(png).decode()],
                         "format": "json", "stream": False,
                         "options": {"temperature": 0, "seed": 42, "num_ctx": 4096}}).encode()
    req = urllib.request.Request(OLLAMA, data=cuerpo, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        o = json.loads(r.read())
    return o, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corridas", type=Path)
    ap.add_argument("resultados", type=Path)
    ap.add_argument("--cuadros", type=int, default=8)
    ap.add_argument("--modelo", default="gemma3:4b")
    a = ap.parse_args()
    a.resultados.mkdir(parents=True, exist_ok=True)
    ruta = a.resultados / ("ojo2026.jsonl" if a.modelo == "gemma3:4b" else f"ojo2026-{a.modelo.replace(':', '-')}.jsonl")
    hechos = set()
    if ruta.exists():
        for linea in ruta.read_text().splitlines():
            o = json.loads(linea)
            hechos.add((o["caso"], o["cuadro"]))
    salida = ruta.open("a")
    for caso in sorted(p for p in a.corridas.iterdir() if (p / "verdad.json").exists()):
        verdad = json.loads((caso / "verdad.json").read_text())
        for c in verdad["cuadros"][:a.cuadros]:
            if (caso.name, c["cuadro"]) in hechos:
                continue
            ahora = datetime.now().strftime("%H:%M")
            if ahora >= "21:30" or ahora < "07:00":
                # de noche corre el turno de noche en este mismo equipo: no se le mete carga
                print(f"{ahora}: fuera del horario (7:00 a 21:30); se retoma mañana sin repetir lo hecho")
                sys.exit(0)
            w, h, gris = leer_pgm(caso / f"f{c['cuadro']:03d}.pgm")
            o, seg = preguntar(a.modelo, a_png(w, h, gris))
            texto = o.get("response", "")
            x = y = None
            try:
                x, y = centro(texto)
            except (ValueError, KeyError, TypeError, AttributeError):
                pass
            err = None if x is None else math.hypot(x - c["x"], y - c["y"])
            salida.write(json.dumps({
                "equipo": socket.gethostname(), "modelo": a.modelo, "caso": caso.name,
                "fantasma": verdad["fantasma"], "nivel": verdad["nivel"], "cuadro": c["cuadro"],
                "real": [c["x"], c["y"]], "visto": [x, y], "error_px": None if err is None else round(err, 2),
                "respuesta": texto[:300], "seg": round(seg, 2),
                "tokens_entrada": o.get("prompt_eval_count"), "tokens_salida": o.get("eval_count"),
                "carga_s": round(o.get("load_duration", 0) / 1e9, 2)}, ensure_ascii=False) + "\n")
            salida.flush()
            print(caso.name, c["cuadro"], "error", None if err is None else round(err, 1), f"{seg:.1f} s")


if __name__ == "__main__":
    main()
