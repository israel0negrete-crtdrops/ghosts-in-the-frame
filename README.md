# ghosts-in-the-frame

A bright disk moves over a uniform background, 640×480 grayscale. Each frame is
haunted: the multipath echo of analog television, impulse noise, Gaussian noise,
interference bars. Three eyes look for the disk in the same frames:

- **The 2001 eye:** 3×3 window filters and the centroid, with an echo canceler
  that measures the ghost on a reference signal, the way analog TV did. These are
  the techniques of a project proposal Israel wrote in 2001 for a robot with
  visual feedback, written now in C99 with nothing but the standard library.
- **Two of today's vision models,** running locally in Ollama on an Intel N100
  mini PC: Qwen2.5-VL 3B and Gemma 3 4B. Nothing leaves the lab.

Every frame is synthetic and generated with a fixed seed, so the true position
is known exactly.

This is the code exactly as it ran on October 26 and 27, 2026, with every answer
each eye gave. It is not a cleaned-up version: names, comments and logs are in
Spanish, as they ran; the prompts to the models are in English.

See it frame by frame: [Ghosts in the frame](https://crtdrops.mx/fantasmas/)
(English and Spanish on the same page).

Built with Claude Code as a pair: the scene and the 2001 techniques come from
Israel's proposal; Claude wrote most of the code and ran it on the lab machines
with him.

## What came out

On the same 72 frames (18 cases, four frames each), on the N100:

| Eye | Median error | Time per frame |
|---|---:|---:|
| 2001 · median filter + echo canceler | 0.1 px (worst case 7.8 px, Gaussian σ 50) | 37.5 ms |
| Qwen2.5-VL 3B | 1.3 px where it gave the center, 2.8 px where it gave only the corner | 146 s |
| Gemma 3 4B | 177.8 px | 104 s |

- **Qwen does see the disk, but answers in another scale.** Ollama hands it the
  image enlarged to 1,036×784 (37×28 = 1,036 image tokens of 28×28 px; 1,122 input
  tokens with the prompt) and Qwen answers in that image, even though the prompt
  says 640×480. Without rescaling, its median error looked like 366 px.
  `comparar.py` rescales it.
- **The echo fools Qwen before it fools the 2001 eye.** The ghost is a copy of the
  disk 40 px to the right. On 10 of the 11 echo frames where Qwen gave a full box,
  the box takes in the disk and its ghost together (about 86 px wide) and its
  center shifts by about 20 px, starting with the weakest echo (20 %). The 2001
  eye without its canceler withstands the 20 and 35 % echoes and shifts the same
  20 px at 50 and 70 %; with the canceler it stays within a pixel.
- **Gemma answered (320, 240) on all 72 frames,** the clean ones too: the exact
  center of the image. With this prompt it does not locate the disk.
- **Not every 2001 variant works.** With the Laplacian or minimum-distance filter
  and a fixed threshold, it loses the disk as soon as there is noise, even
  Gaussian σ 10. The median + canceler variant was picked after seeing the
  results, as the one with the lowest worst case; all ten are in `resumen2001.json`.

## Files

| File | What it does |
|---|---|
| `escena.py` | Builds the scenes: 18 cases (clean, 4 ghosts × 4 strengths, combined), 20 frames each, as PGM plus a `verdad.json` (true positions) per case. The top 8 rows carry a reference signal (black with a white pulse), like the TV's vertical blanking interval; the echo distorts it like the rest of the frame, so the canceler can measure it. Standard library only. |
| `ojo2001.c` | The 2001 eye: echo canceler calibrated on the reference (recursive filter), 3×3 filters (mean, median, Laplacian, minimum distance), threshold and centroid. C99, standard library only. |
| `correr2001.py` | Compiles `ojo2001.c` and runs its 10 variants (5 filters, with and without the canceler) on every case; error against the true position. |
| `ojo2026.py` | Sends the same frames to a vision model through Ollama (local, temperature 0, seed 42, 4,096-token context). It can be stopped and resumed, and it only runs from 7:00 to 21:30 so it never competes with the lab's night shift. |
| `comparar.py` | Lines up the three eyes on the same frames (0 to 3 of each case) and writes `comparacion.json`. Re-reads Qwen's raw answers: they come in several shapes and in the 1,036×784 scale. |
| `sitio_fantasmas.py` | Prepares the page's data and WebP frames from the results (needs Pillow). |

`resultados/israel-MINI-N100C/` is the N100: the 2001 eye on all 20 frames of each
case (`ojo2001.jsonl`, `resumen2001.json`), Gemma (`ojo2026.jsonl`), Qwen
(`ojo2026-qwen2.5vl-3b.jsonl`), the comparison, and the logs. `resultados/pios/`
is the 2001 eye on a Raspberry Pi 5.

## Run it

    python3 escena.py corridas --cuadros 20                  # about 100 MB of PGM
    python3 correr2001.py corridas resultados/<machine>
    python3 ojo2026.py corridas resultados/<machine> --cuadros 4                         # Gemma 3 4B
    python3 ojo2026.py corridas resultados/<machine> --cuadros 4 --modelo qwen2.5vl:3b
    python3 comparar.py resultados/<machine>

Checked before publishing:

- `escena.py` gives byte-identical frames on the N100 (Python 3.12) and on a Mac.
- `ojo2001.c` gives exactly the same points on the N100 (gcc 13.3) and the Pi 5
  (gcc 14.2). On a Mac (Apple clang), 13 of 3,600 points differ, all with the
  canceler on and the Laplacian or minimum-distance filter: after floating-point
  rounding, a pixel right at the threshold lands on the other side, and the
  centroid moves by up to 0.18 px. The median + canceler variant and the
  unfiltered one come out identical.
- `comparar.py` on a Mac reproduces `comparacion.json` byte for byte.

## Setup and limits

- Intel N100, 8 GB of RAM, Ubuntu 24.04; Ollama 0.40.6. Models: `gemma3:4b`
  (id `68ceab7e468a`, Q4_K_M) and `qwen2.5vl:3b` (id `fb90415cde1e`, Q4_K_M),
  one at a time.
- The prompts differ: Gemma is asked for the center as `{"x", "y"}`; Qwen, for its
  bounding box, which is how it was trained to locate objects. Gemma was tried
  with a single prompt; another one might do better.
- Qwen does not always answer the same way: on 37 frames it gave both corners
  (the center is measured), on 32 only the top-left corner with a separate width
  and height (that corner is measured against the true corner, which cannot see
  the echo), and on 3 it kept repeating the same structure until it filled the
  context, with no coordinates.
- `ojo2026.py` saved only the first 300 characters of each answer; 4 of Qwen's
  are cut there.
- Gemma's run was interrupted on October 26 by an HTTP 500 from Ollama (the
  traceback is in `ojo2026.log`) and resumed on October 27 without repeating
  frames; the frame that failed went through on the second try.
- The models saw four frames per case because each one takes minutes; the 2001
  eye ran all 20, and the comparison uses the same four.

## License

MIT. See `LICENSE`.
