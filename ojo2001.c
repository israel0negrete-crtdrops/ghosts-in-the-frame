/* El ojo de 2001: filtros de ventana de 3x3 y el método del centroide,
 * como en el anteproyecto de un robot con retroalimentación visual
 * (640x480 en grises, un objeto sobre fondo uniforme).
 *
 *   ojo2001 FILTRO CANCELAR UMBRAL < lista_de_pgm > resultados.jsonl
 *
 *   FILTRO   ninguno | media | mediana | laplaciano | minima
 *   CANCELAR 0 | 1   (1: mide el eco en la referencia y lo quita antes)
 *   UMBRAL   nivel de gris (o de borde) a partir del cual un píxel cuenta
 *
 * Lee rutas de PGM (P5, 640x480) por la entrada estándar, una por línea, y
 * escribe una línea JSON por cuadro: centroide, píxeles que contaron, el eco
 * que midió y lo que tardó. C99 y la biblioteca estándar, nada más.
 */
#define _POSIX_C_SOURCE 200809L   /* clock_gettime en Linux con -std=c99 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define ANCHO 640
#define ALTO 480
#define REF 8              /* líneas de referencia arriba */
#define NEGRO 16
#define BLANCO 235
#define PULSO_INI 20
#define PULSO_FIN 28
#define RADIO_MINIMA 30    /* radio de comparación de mínima distancia */

static unsigned char crudo[ALTO][ANCHO];
static float img[ALTO][ANCHO], tmp[ALTO][ANCHO];

static int leer_pgm(const char *ruta) {
    FILE *f = fopen(ruta, "rb");
    if (!f) return -1;
    int w, h, m;
    if (fscanf(f, "P5 %d %d %d", &w, &h, &m) != 3 || w != ANCHO || h != ALTO) { fclose(f); return -2; }
    fgetc(f);
    size_t n = fread(crudo, 1, sizeof crudo, f);
    fclose(f);
    if (n != sizeof crudo) return -3;
    for (int y = 0; y < ALTO; y++)
        for (int x = 0; x < ANCHO; x++) img[y][x] = crudo[y][x];
    return 0;
}

/* Mide el eco en la referencia: el pulso blanco conocido reaparece d muestras
 * después con amplitud a. Promedia las 4 líneas del pulso. */
static void medir_eco(int *d, float *a) {
    float mejor = 0; int mx = 0;
    for (int x = PULSO_FIN + 4; x < ANCHO; x++) {
        float s = 0;
        for (int y = 2; y <= 5; y++) s += img[y][x] - NEGRO;
        s /= 4;
        if (s > mejor) { mejor = s; mx = x; }
    }
    /* el máximo cae dentro de la copia del pulso: se retrocede a su inicio */
    int ini = mx;
    while (ini > PULSO_FIN && img[3][ini - 1] - NEGRO > mejor * 0.5f) ini--;
    *d = ini - PULSO_INI;
    *a = mejor / (float)(BLANCO - NEGRO);
    if (*a < 0.03f) { *a = 0; *d = 0; }     /* no hay eco que valga la pena */
}

/* Quita el eco: y[x] = g[x] - a (y[x-d] - negro), la inversa exacta de un
 * solo rebote, línea por línea. Es un filtro recursivo (IIR). */
static void cancelar_eco(int d, float a) {
    if (a <= 0 || d <= 0) return;
    for (int y = 0; y < ALTO; y++)
        for (int x = d; x < ANCHO; x++)
            img[y][x] = img[y][x] - a * (img[y][x - d] - NEGRO);
}

static int cmp(const void *p, const void *q) {
    float a = *(const float *)p, b = *(const float *)q;
    return (a > b) - (a < b);
}

/* Filtros de ventana de 3x3 sobre la zona activa (debajo de la referencia).
 * Los bordes de la imagen se quedan como están. */
static void filtrar(const char *filtro) {
    if (!strcmp(filtro, "ninguno")) return;
    memcpy(tmp, img, sizeof img);
    for (int y = REF + 1; y < ALTO - 1; y++) {
        for (int x = 1; x < ANCHO - 1; x++) {
            float v[9]; int k = 0;
            for (int j = -1; j <= 1; j++)
                for (int i = -1; i <= 1; i++) v[k++] = img[y + j][x + i];
            if (!strcmp(filtro, "media")) {
                float s = 0; for (k = 0; k < 9; k++) s += v[k];
                tmp[y][x] = s / 9;
            } else if (!strcmp(filtro, "mediana")) {
                qsort(v, 9, sizeof(float), cmp);
                tmp[y][x] = v[4];
            } else if (!strcmp(filtro, "laplaciano")) {
                /* segunda derivada: 4 vecinos menos 4 veces el centro, en magnitud */
                float l = v[1] + v[3] + v[5] + v[7] - 4 * v[4];
                tmp[y][x] = l < 0 ? -l : l;
            } else if (!strcmp(filtro, "minima")) {
                /* comparación de mínima distancia: es borde si algún vecino
                 * vertical u horizontal difiere del centro más que el radio */
                int borde = 0;
                for (int n = 1; n < 9; n += 2) {
                    float dd = v[n] - v[4]; if (dd < 0) dd = -dd;
                    if (dd > RADIO_MINIMA) borde = 1;
                }
                tmp[y][x] = borde ? 255 : 0;
            }
        }
    }
    memcpy(img, tmp, sizeof img);
}

int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "uso: ojo2001 FILTRO CANCELAR UMBRAL < lista\n");
        return 2;
    }
    const char *filtro = argv[1];
    int cancelar = atoi(argv[2]);
    float umbral = (float)atof(argv[3]);
    char ruta[4096];
    while (fgets(ruta, sizeof ruta, stdin)) {
        ruta[strcspn(ruta, "\r\n")] = 0;
        if (!*ruta) continue;
        int e = leer_pgm(ruta);
        if (e) { printf("{\"archivo\":\"%s\",\"error\":%d}\n", ruta, e); continue; }
        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);
        int d = 0; float a = 0;
        if (cancelar) { medir_eco(&d, &a); cancelar_eco(d, a); }
        filtrar(filtro);
        double sx = 0, sy = 0; long n = 0;
        for (int y = REF + 1; y < ALTO - 1; y++)
            for (int x = 1; x < ANCHO - 1; x++)
                if (img[y][x] > umbral) { sx += x; sy += y; n++; }
        clock_gettime(CLOCK_MONOTONIC, &t1);
        double ms = (t1.tv_sec - t0.tv_sec) * 1e3 + (t1.tv_nsec - t0.tv_nsec) / 1e6;
        if (n)
            printf("{\"archivo\":\"%s\",\"x\":%.3f,\"y\":%.3f,\"pixeles\":%ld,\"eco_d\":%d,\"eco_a\":%.3f,\"ms\":%.2f}\n",
                   ruta, sx / n, sy / n, n, d, a, ms);
        else
            printf("{\"archivo\":\"%s\",\"x\":null,\"y\":null,\"pixeles\":0,\"eco_d\":%d,\"eco_a\":%.3f,\"ms\":%.2f}\n",
                   ruta, d, a, ms);
        fflush(stdout);
    }
    return 0;
}
