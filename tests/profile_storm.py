"""Storm rendering profiler -- identifies which draw_all sub-call adds latency during storm.

Compares each sub-call calm vs storm, prints the delta table.
Headless (SDL dummy driver), no display required.
"""

import os
import sys
import time

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

world = World()
populate_world(world)

env_calm = Environment()
env_calm.wind_speed = 5.0
env_calm.current_speed = 0.5
env_calm.visibility = 5000.0
env_calm.fog = False

env_storm = Environment()
env_storm.wind_speed = 28.0
env_storm.current_speed = 3.5
env_storm.visibility = 50.0
env_storm.fog = True

camera = Camera(SCREEN_W, SCREEN_H)
chart = Chart(surface, camera)

REPS = 300
WARMUP = 20


def timed(fn, n=REPS, warmup=WARMUP):
    for _ in range(warmup):
        fn()
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t0) / n * 1000


# Individual sub-calls
cases = [
    ("draw_background",
     lambda: chart.draw_background(world),
     lambda: chart.draw_background(world)),
    ("draw_ocean_vignette",
     lambda: chart.draw_ocean_vignette(),
     lambda: chart.draw_ocean_vignette()),
    ("draw_depth_zones",
     lambda: chart.draw_depth_zones(world, env_calm),
     lambda: chart.draw_depth_zones(world, env_storm)),
    ("draw_grid",
     lambda: chart.draw_grid(),
     lambda: chart.draw_grid()),
    ("draw_depth_contours",
     lambda: chart.draw_depth_contours(world, env_calm),
     lambda: chart.draw_depth_contours(world, env_storm)),
    ("draw_islands",
     lambda: chart.draw_islands(world),
     lambda: chart.draw_islands(world)),
    ("draw_depth_soundings",
     lambda: chart.draw_depth_soundings(world, env_calm),
     lambda: chart.draw_depth_soundings(world, env_storm)),
    ("draw_zones",
     lambda: chart.draw_zones(world),
     lambda: chart.draw_zones(world)),
    ("draw_current_arrows",
     lambda: chart.draw_current_arrows(env_calm),
     lambda: chart.draw_current_arrows(env_storm)),
    ("draw_ports",
     lambda: chart.draw_ports(world),
     lambda: chart.draw_ports(world)),
    ("draw_nav_marks",
     lambda: chart.draw_nav_marks(world),
     lambda: chart.draw_nav_marks(world)),
    ("draw_vessels",
     lambda: chart.draw_vessels(world, None, env_calm),
     lambda: chart.draw_vessels(world, None, env_storm)),
    ("resolve_labels",
     lambda: (chart._label_candidates.clear(), None),
     lambda: (chart._label_candidates.clear(), None)),
    ("draw_scale_bar",
     lambda: chart.draw_scale_bar(),
     lambda: chart.draw_scale_bar()),
    ("draw_compass_rose",
     lambda: chart.draw_compass_rose(),
     lambda: chart.draw_compass_rose()),
    ("draw_status_bar",
     lambda: chart.draw_status_bar(env_calm, None),
     lambda: chart.draw_status_bar(env_storm, None)),
    ("day_night_tint (day)",
     lambda: None,
     lambda: None),
]

# Full draw_all
def full_calm():
    surface.fill((10, 28, 52))
    chart.draw_all(world=world, environment=env_calm)

def full_storm():
    surface.fill((10, 28, 52))
    chart.draw_all(world=world, environment=env_storm)

print()
print("=" * 68)
print("Storm rendering sub-call breakdown")
print("=" * 68)
print(f"  {'sub-call':<28} {'calm':>7}  {'storm':>7}  {'delta':>8}")
print(f"  {'-'*28} {'-'*7}  {'-'*7}  {'-'*8}")

total_calm = 0.0
total_storm = 0.0

for label, fn_calm, fn_storm in cases:
    mc = timed(fn_calm)
    ms = timed(fn_storm)
    total_calm += mc
    total_storm += ms
    flag = "  <-- !" if (ms - mc) > 1.0 else ""
    print(f"  {label:<28} {mc:7.3f}  {ms:7.3f}  {ms-mc:+8.3f}{flag}")

print(f"  {'-'*28} {'-'*7}  {'-'*7}  {'-'*8}")
print(f"  {'subtotal':<28} {total_calm:7.3f}  {total_storm:7.3f}  {total_storm-total_calm:+8.3f}")

mc_full = timed(full_calm, n=200, warmup=10)
ms_full = timed(full_storm, n=200, warmup=10)
print(f"  {'draw_all (full)':<28} {mc_full:7.3f}  {ms_full:7.3f}  {ms_full-mc_full:+8.3f}")
print("=" * 68)
print()
