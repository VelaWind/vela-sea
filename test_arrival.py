"""Headless arrival test — no pygame window required.

Mirrors main.py's update_simulation() loop exactly, using the real engine.
Drives MV Tidewater (cargo, start (120,300), destination Port Ardent (648,460))
and reports distance-to-destination every 60 steps until docked or 15 000 steps.
"""

import sys
import os

# Ensure the project root is on the path so all engine/config imports resolve.
sys.path.insert(0, os.path.dirname(__file__))

from config import SIM_TIMESTEP, ARRIVAL_DISTANCE, TIME_COMPRESSION
from engine.ship import Vessel
from engine.world import World
from engine.environment import Environment

# ---------------------------------------------------------------------------
# Build a minimal world (no islands needed for this test — we only care about
# arrival logic, not grounding).
# ---------------------------------------------------------------------------
world = World()
environment = Environment()

DESTINATION = (648.0, 460.0)   # Port Ardent coords used in main.py

cargo = Vessel(
    name="MV Tidewater",
    vessel_type="cargo",
    position=(120.0, 300.0),
    heading=45.0,
    target_speed=8.0,
    current_speed=8.0,          # start at cruise speed (same as main.py auto-start)
    max_speed=12.0,
    acceleration=0.020,
    deceleration=0.017,
    turn_rate=1.0,
    length_m=150.0,
    beam_m=25.0,
    draft_m=8.0,
    fuel=80.0,
    fuel_capacity=100.0,
    fuel_consumption_rate=3.5,
    destination=DESTINATION,
)
world.add_vessel(cargo)

# ---------------------------------------------------------------------------
# Simulate — same logic as main.py update_simulation(), sim_speed = 1.0
# ---------------------------------------------------------------------------
PRINT_EVERY   = 200_000  # print a row every N steps
MAX_STEPS     = 3_000_000  # covers ~12 sim-hours at 8 kn across 150 nm sea

sim_time      = 0.0
min_dist      = float("inf")
min_dist_step = 0
latched       = False

print(f"{'Step':>6}  {'SimTime(s)':>10}  {'Dist(wu)':>10}  "
      f"{'Heading':>8}  {'Speed(kn)':>10}  {'Status':<10}")
print("-" * 64)

for step in range(MAX_STEPS):
    vessel = cargo   # single vessel

    # --- identical to main.py inner loop ---
    if vessel.destination and vessel.status == "underway":
        target_bearing = vessel.bearing_to(vessel.destination)
        vessel.turn_toward(target_bearing, SIM_TIMESTEP)

    vessel.update_speed(SIM_TIMESTEP)
    vessel.move(SIM_TIMESTEP)

    if vessel.destination and vessel.at_destination(vessel.destination, tolerance=ARRIVAL_DISTANCE):
        vessel.current_speed = 0.0
        vessel.status = "docked"
        vessel.destination = None
        latched = True

    if world.point_in_island(vessel.position):
        vessel.status = "aground"
        vessel.current_speed = 0.0
    # --- end of mirrored loop ---

    sim_time += SIM_TIMESTEP
    dist = vessel.distance_to(DESTINATION)

    if dist < min_dist:
        min_dist = dist
        min_dist_step = step

    if step % PRINT_EVERY == 0 or latched or vessel.status == "aground":
        print(f"{step:>6}  {sim_time:>10.1f}  {dist:>10.3f}  "
              f"{vessel.heading:>8.1f}  {vessel.current_speed:>10.3f}  {vessel.status:<10}")

    if latched or vessel.status == "aground":
        break

print("-" * 64)
print(f"\nMinimum distance achieved: {min_dist:.3f} wu  (at step {min_dist_step})")
print(f"ARRIVAL_DISTANCE tolerance: {ARRIVAL_DISTANCE} wu")
print(f"Latched to docked: {latched}")
print(f"Final status: {cargo.status}")
print(f"Total simulated time: {sim_time:.1f} s  ({sim_time/3600:.2f} h)")
print()

if latched:
    print("RESULT: ARRIVED CLEANLY — vessel docked within tolerance.")
elif cargo.status == "aground":
    print("RESULT: GROUNDED before reaching destination.")
elif min_dist <= ARRIVAL_DISTANCE * 3 and not latched:
    print("RESULT: POSSIBLE DEATH-SPIRAL — got close but never latched. "
          f"Min dist={min_dist:.3f} vs tolerance={ARRIVAL_DISTANCE}.")
else:
    print(f"RESULT: DID NOT ARRIVE in {MAX_STEPS} steps. "
          f"Closest approach: {min_dist:.3f} wu.")
