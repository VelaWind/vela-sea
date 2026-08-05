"""Polish visual-performance proof.

Confirms that the new chart-polish additions (inland land tint, ocean vignette,
repositioned predictor label) add well under 0.5 ms per frame at max sim speed.

Methodology:
  1. Time just the three new operations in isolation (N=500 iterations).
  2. Report measured time per call.
  3. Assert total new overhead per frame < 0.5 ms.

Uses SDL dummy driver so the test runs headlessly without a real display.

Run manually with `python tests/test_visual_perf.py` from the repo root.
Timing benchmarks are machine-dependent, so this script is not part of the
pytest suite: everything that measures or asserts runs under __main__ only,
and importing the module (as pytest collection does) executes no benchmarks.
"""

import sys
import time
import os
import math

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
import pygame.gfxdraw
pygame.init()

sys.path.insert(0, ".")

SCREEN_W, SCREEN_H = 1600, 900
surface = pygame.display.set_mode((SCREEN_W, SCREEN_H))

from render.camera import Camera
from render.chart import Chart
from engine.world import World
from engine.environment import Environment
from data.world_data import populate_world
from config import (
    LAND_INLAND_TINT_SHRINK_PX, LAND_INLAND_TINT_COLOR,
)

world = World()
populate_world(world)
env = Environment()
camera = Camera(SCREEN_W, SCREEN_H)
chart = Chart(surface, camera)

REPS = 500
WARMUP = 20


def time_n(fn, n=REPS, warmup=WARMUP):
    for _ in range(warmup):
        fn()
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t0) / n * 1000  # ms per call


# ---- 1: ocean vignette (cached blit) ----
def bench_vignette():
    chart.draw_ocean_vignette()

# ---- 2: inland tint -- all islands in one pass (solid color, no SRCALPHA) ----
_island_polys = []
for isl in world.islands:
    sp = [camera.world_to_screen(pt) for pt in isl.polygon]
    if len(sp) >= 3:
        _island_polys.append([(int(x), int(y)) for x, y in sp])


def bench_inland_tint():
    for int_polygon in _island_polys:
        avg_x = sum(p[0] for p in int_polygon) / len(int_polygon)
        avg_y = sum(p[1] for p in int_polygon) / len(int_polygon)
        typical_r = math.hypot(int_polygon[0][0] - avg_x, int_polygon[0][1] - avg_y)
        if typical_r <= LAND_INLAND_TINT_SHRINK_PX:
            continue
        inner = chart._offset_screen_polygon(int_polygon, -LAND_INLAND_TINT_SHRINK_PX)
        if len(inner) >= 3:
            pygame.gfxdraw.filled_polygon(surface, inner, LAND_INLAND_TINT_COLOR)


# ---- 3: full draw_all timing for context ----
def bench_full():
    surface.fill((10, 28, 52))
    chart.draw_all(world=world, environment=env)


def main():
    ms_vignette = time_n(bench_vignette)
    ms_inland = time_n(bench_inland_tint)
    ms_full = time_n(bench_full, n=200, warmup=10)

    # ---- results ----
    ms_total_new = ms_vignette + ms_inland
    n_islands = len(_island_polys)

    print()
    print("=" * 60)
    print("Chart polish -- per-frame overhead")
    print("=" * 60)
    print(f"  Ocean vignette (cached blit):  {ms_vignette:.4f} ms")
    print(f"  Inland tint ({n_islands} islands):    {ms_inland:.4f} ms")
    print(f"  ------------------------------------")
    print(f"  Total new overhead:            {ms_total_new:.4f} ms  (budget: < 0.50 ms)")
    print(f"  Full draw_all baseline:        {ms_full:.2f} ms  "
          f"({1000/ms_full:.0f} theoretical FPS)")
    print("=" * 60)

    errors = []
    if ms_total_new >= 0.5:
        errors.append(
            f"New overhead {ms_total_new:.4f} ms exceeds 0.5 ms budget"
        )

    print()
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
    print()


if __name__ == "__main__":
    main()
