#!/usr/bin/env python3
"""Arma las escenas embrujadas: un objeto que se mueve sobre fondo uniforme,
640x480 en grises, como pedía el anteproyecto de 2001, y sus fantasmas.

Cada cuadro guarda en sus primeras 8 líneas una referencia, como el intervalo
de borrado vertical de la televisión: negro con un pulso blanco conocido. El
eco la deforma igual que al resto de la imagen, y así el cancelador puede
medir el fantasma antes de quitarlo (la idea de la señal de referencia para
cancelar fantasmas de la TV analógica).

    python3 escena.py corridas/            # todos los casos
    python3 escena.py corridas/ --cuadros 20 --semilla 7

Sin dependencias: escribe PGM (P5) y un verdad.json por caso.
"""
import argparse
import json
import math
import random
from pathlib import Path

ANCHO, ALTO = 640, 480
REF = 8                      # líneas de referencia arriba ("borrado vertical")
FONDO, OBJETO = 60, 200      # fondo uniforme y objeto brillante
NEGRO, BLANCO = 16, 235      # niveles de la referencia
PULSO = (20, 28)             # columnas del pulso blanco de referencia
RADIO = 22

# Los fantasmas y sus intensidades, de menos a más.
CASOS = [("limpio", None)]
CASOS += [("eco", a) for a in (0.2, 0.35, 0.5, 0.7)]          # amplitud del eco
CASOS += [("impulsivo", p) for p in (0.01, 0.03, 0.08, 0.15)]  # fracción de píxeles
CASOS += [("gaussiano", s) for s in (10, 20, 35, 50)]           # sigma
CASOS += [("barras", A) for A in (10, 25, 45, 70)]              # amplitud de la interferencia
CASOS += [("combinado", 1)]
RETRASO_ECO = 40            # píxeles: el rebote llega 40 muestras después
PERIODO_BARRAS = 24         # píxeles


def camino(t, n):
    """Centro del objeto en el cuadro t de n (una curva que recorre la imagen)."""
    x = ANCHO / 2 + 220 * math.sin(2 * math.pi * t / n)
    y = REF + (ALTO - REF) / 2 + 150 * math.sin(4 * math.pi * t / n + math.pi / 4)
    return x, y


def limpio(cx, cy):
    """Cuadro sin fantasmas como lista de filas (bytearray). El disco va con
    bordes suavizados (4x4 submuestras), así su centroide es el centro."""
    filas = []
    for y in range(ALTO):
        if y < REF:
            f = bytearray([NEGRO]) * ANCHO
            if 2 <= y <= 5:
                f[PULSO[0]:PULSO[1]] = bytes([BLANCO]) * (PULSO[1] - PULSO[0])
            filas.append(f)
            continue
        f = bytearray([FONDO]) * ANCHO
        dy = y - cy
        if abs(dy) <= RADIO + 1:
            x0, x1 = max(0, int(cx - RADIO - 2)), min(ANCHO, int(cx + RADIO + 3))
            for x in range(x0, x1):
                dentro = 0
                for sy in (-0.375, -0.125, 0.125, 0.375):
                    for sx in (-0.375, -0.125, 0.125, 0.375):
                        if (x + sx - cx) ** 2 + (y + sy - cy) ** 2 <= RADIO * RADIO:
                            dentro += 1
                f[x] = round(FONDO + (OBJETO - FONDO) * dentro / 16)
        filas.append(f)
    return filas


def a_float(filas):
    return [[float(v) for v in f] for f in filas]


def eco(img, a, d=RETRASO_ECO):
    """Multitrayecto: a cada línea se le suma una copia retrasada d muestras y
    atenuada a. Afecta también a la referencia, como en el aire."""
    for f in img:
        orig = f[:]
        for x in range(d, ANCHO):
            f[x] = orig[x] + a * (orig[x - d] - NEGRO)
    return img


def impulsivo(img, p, rnd):
    for y in range(REF, ALTO):          # el ruido de chispa no toca la referencia
        f = img[y]
        for x in range(ANCHO):
            if rnd.random() < p:
                f[x] = 255.0 if rnd.random() < 0.5 else 0.0
    return img


def gaussiano(img, s, rnd):
    for y in range(REF, ALTO):
        f = img[y]
        for x in range(ANCHO):
            f[x] += rnd.gauss(0, s)
    return img


def barras(img, A, fase):
    tabla = [A * math.sin(2 * math.pi * x / PERIODO_BARRAS + fase) for x in range(ANCHO)]
    for y in range(REF, ALTO):
        f = img[y]
        for x in range(ANCHO):
            f[x] += tabla[x]
    return img


def a_pgm(img, ruta):
    datos = bytearray()
    for f in img:
        datos += bytes(max(0, min(255, round(v))) for v in f)
    ruta.write_bytes(b"P5\n%d %d\n255\n" % (ANCHO, ALTO) + bytes(datos))


def generar(salida, cuadros, semilla):
    salida.mkdir(parents=True, exist_ok=True)
    for nombre, nivel in CASOS:
        caso = f"{nombre}" if nivel is None else f"{nombre}-{nivel}"
        d = salida / caso
        d.mkdir(exist_ok=True)
        rnd = random.Random(f"{semilla}-{caso}")
        verdad = []
        for t in range(cuadros):
            cx, cy = camino(t, cuadros)
            img = a_float(limpio(cx, cy))
            if nombre == "eco":
                eco(img, nivel)
            elif nombre == "impulsivo":
                impulsivo(img, nivel, rnd)
            elif nombre == "gaussiano":
                gaussiano(img, nivel, rnd)
            elif nombre == "barras":
                barras(img, nivel, fase=0.7 * t)
            elif nombre == "combinado":
                eco(img, 0.35)
                impulsivo(img, 0.03, rnd)
                gaussiano(img, 15, rnd)
            a_pgm(img, d / f"f{t:03d}.pgm")
            verdad.append({"cuadro": t, "x": round(cx, 3), "y": round(cy, 3)})
        (d / "verdad.json").write_text(json.dumps({"caso": caso, "fantasma": nombre, "nivel": nivel,
                                                   "cuadros": verdad}, indent=1))
        print(caso, cuadros, "cuadros")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("salida", type=Path)
    ap.add_argument("--cuadros", type=int, default=20)
    ap.add_argument("--semilla", type=int, default=2001)
    a = ap.parse_args()
    generar(a.salida, a.cuadros, a.semilla)
