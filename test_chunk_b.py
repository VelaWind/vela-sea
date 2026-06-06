"""Headless verification for Chunk B — wind & current forces.

Tests:
  1. Set-and-drift: vessel heading vs actual COG; drift angle matches theory.
  2. Wind drift only: cargo ship pushed sideways by beam wind.
  3. Sailboat polar: effective_wind_speed at a range of wind angles.
  4. Sailboat in-irons: vessel decelerates to zero when pointed into no-go zone.

No Pygame required.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from math import atan2, cos, sin, degrees, radians, sqrt

from config import (
    SIM_TIMESTEP, KNOTS_TO_UNITS_PER_HOUR,
    SAIL_NO_GO_ANGLE, SAIL_EFFICIENCY, SAIL_RUN_FACTOR,
    ARRIVAL_DISTANCE,
)
from engine.ship import Vessel
from engine.environment import Environment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_cargo(heading=0.0, speed=8.0, pos=(500.0, 350.0)):
    return Vessel(
        name="Test Cargo", vessel_type="cargo",
        position=pos, heading=heading,
        target_speed=speed, current_speed=speed,
        max_speed=12.0, acceleration=0.020, deceleration=0.017,
        turn_rate=1.0, length_m=150.0, beam_m=25.0, draft_m=8.0,
        fuel=100.0, fuel_capacity=100.0, fuel_consumption_rate=3.5,
    )

def make_sailboat(heading=0.0, speed=0.0, pos=(500.0, 350.0)):
    return Vessel(
        name="Test Sail", vessel_type="sailboat",
        position=pos, heading=heading,
        target_speed=6.0, current_speed=speed,
        max_speed=10.0, acceleration=0.05, deceleration=0.02,
        turn_rate=2.5, length_m=35.0, beam_m=7.0, draft_m=2.5,
        fuel=None, fuel_capacity=None, fuel_consumption_rate=0.0,
    )

def run_steps(vessel, env, n, turn=False):
    """Advance n SIM_TIMESTEPs, optionally turning toward destination."""
    for _ in range(n):
        if turn and vessel.destination and vessel.status == "underway":
            vessel.turn_toward(vessel.bearing_to(vessel.destination), SIM_TIMESTEP)
        vessel.update_speed(SIM_TIMESTEP, env)
        vessel.move(SIM_TIMESTEP, env)

def cog_from_displacement(x0, y0, x1, y1):
    """Course-over-ground from start to end position (degrees)."""
    dx, dy = x1 - x0, y1 - y0
    return degrees(atan2(dy, dx)) % 360.0

def signed_angle_diff(a, b):
    """Shortest signed difference a − b, in (−180, 180]."""
    d = (a - b + 180.0) % 360.0 - 180.0
    return d


# ===========================================================================
# Test 1 — Set-and-drift: COG vs heading
# ===========================================================================
print("=" * 60)
print("TEST 1: Set-and-drift (current only, no wind)")
print("=" * 60)

# Vessel heading east (0°) at 8 kn; current flowing south (90°) at 1 kn.
# Expected COG = atan2(1, 8) ≈ 7.13° south of east.
env_current = Environment(
    wind_speed=0.0,           # isolate current only
    wind_direction=0.0,
    current_speed=1.0,
    current_direction=90.0,   # flows southward
)

v = make_cargo(heading=0.0, speed=8.0)
x0, y0 = v.position
N = 200
run_steps(v, env_current, N)
x1, y1 = v.position

cog = cog_from_displacement(x0, y0, x1, y1)
drift = signed_angle_diff(cog, v.heading)
expected_drift = degrees(atan2(1.0, 8.0))   # 7.125°

# Also verify numerically: displacement components
total_dt = N * SIM_TIMESTEP
hours = total_dt / 3600.0
expected_dx = 8.0 * KNOTS_TO_UNITS_PER_HOUR * hours           # eastward
expected_dy = 1.0 * KNOTS_TO_UNITS_PER_HOUR * hours           # southward (current)
expected_cog = degrees(atan2(expected_dy, expected_dx)) % 360.0

print(f"  Heading:           {v.heading:7.2f}°")
print(f"  Actual COG:        {cog:7.2f}°")
print(f"  Drift angle:       {drift:+7.2f}°  (expected {expected_drift:+.2f}°)")
print(f"  Expected COG:      {expected_cog:7.2f}°")
print(f"  Displacement:      dx={x1-x0:.4f}  dy={y1-y0:.4f}")
print(f"  Expected disp:     dx={expected_dx:.4f}  dy={expected_dy:.4f}")
ok1 = abs(drift - expected_drift) < 0.05
print(f"  PASS: {ok1}  (drift error < 0.05°)")


# ===========================================================================
# Test 2 — Wind drift on a cargo ship
# ===========================================================================
print()
print("=" * 60)
print("TEST 2: Wind drift (current=0, wind from north pushing south)")
print("=" * 60)

# Wind from 270° (westerly — blows eastward) → push direction = (270+180)%360 = 90° (south? no...)
# Let's use: wind from 0° (easterly, blows west) → push direction 180° (west).
# Vessel heading east (0°), wind drift should push it WEST → negative dx contribution.
env_wind = Environment(
    wind_speed=10.0,           # 10 kn wind for clear signal
    wind_direction=0.0,        # wind FROM east → pushes vessel west
    current_speed=0.0,
    current_direction=0.0,
)

from config import WINDAGE_CARGO
v2 = make_cargo(heading=0.0, speed=8.0)
x0, y0 = v2.position
run_steps(v2, env_wind, N)
x1, y1 = v2.position

cog2 = cog_from_displacement(x0, y0, x1, y1)
drift2 = signed_angle_diff(cog2, v2.heading)

# Expected: wind push = 10 kn × 0.040 = 0.4 kn westward (180°)
wind_push_kn = 10.0 * WINDAGE_CARGO
hours2 = (N * SIM_TIMESTEP) / 3600.0
expected_wind_dx = cos(radians(180.0)) * wind_push_kn * KNOTS_TO_UNITS_PER_HOUR * hours2
expected_vessel_dx = 8.0 * KNOTS_TO_UNITS_PER_HOUR * hours2
expected_drift2 = degrees(atan2(0.0, expected_vessel_dx + expected_wind_dx))   # push is along x only

print(f"  Wind speed: 10 kn, from 0° (easterly), windage={WINDAGE_CARGO}")
print(f"  Wind push:  {wind_push_kn:.3f} kn westward")
print(f"  Heading:    {v2.heading:.1f}°  COG: {cog2:.2f}°  Drift: {drift2:+.3f}°")
print(f"  dx actual={x1-x0:.5f}  expected_vessel_dx={expected_vessel_dx:.5f}  expected_wind_dx={expected_wind_dx:.5f}")
ok2 = abs((x1-x0) - (expected_vessel_dx + expected_wind_dx)) < 1e-6
print(f"  PASS: {ok2}  (combined dx matches theory)")


# ===========================================================================
# Test 3 — Sailboat polar: effective speed at key wind angles
# ===========================================================================
print()
print("=" * 60)
print("TEST 3: Sailboat polar — effective_wind_speed vs wind angle")
print("=" * 60)

# Wind from 0° (easterly). Vessel at various headings relative to wind.
env_polar = Environment(
    wind_speed=10.0,
    wind_direction=0.0,   # wind comes FROM east
    current_speed=0.0,
    current_direction=0.0,
)

# Map: vessel heading → expected wind angle (wind_direction − heading, normalised)
test_angles = [
    (  0.0, "head-to-wind (in irons)"),
    ( 44.0, "just inside no-go zone"),
    ( 45.0, "no-go boundary"),
    ( 67.5, "close reach (halfway to beam)"),
    ( 90.0, "beam reach (max drive)"),    # heading 360-90=270... wait
    (135.0, "broad reach"),
    (180.0, "dead run"),
]

# wind_direction=0, heading H → wind_angle = 0 − H = −H (mod ±180)
# I want abs_angle = A, so heading = (0 − A) = −A → 360−A (mod 360)
# or heading = +A (then wind_angle = 0 − A = −A, abs=A). Let's use heading = A directly.

print(f"  Wind: 10 kn from 0° (easterly).  SAIL_NO_GO_ANGLE={SAIL_NO_GO_ANGLE}°")
print(f"  {'Heading':>8}  {'Wind angle':>11}  {'Eff speed':>10}  {'Note'}")
print(f"  {'-'*8}  {'-'*11}  {'-'*10}  {'-'*30}")

for heading, note in test_angles:
    sail = make_sailboat(heading=heading)
    eff = sail._effective_wind_speed(env_polar)
    wangle = sail._wind_angle_to_heading(env_polar)
    print(f"  {heading:>8.1f}°  {wangle:>+10.1f}°  {eff:>9.3f} kn  {note}")

# Spot-check: beam reach (heading=90, abs_angle=90) should be max
sail_beam = make_sailboat(heading=90.0)
eff_beam = sail_beam._effective_wind_speed(env_polar)
expected_beam = min(10.0, 10.0 * SAIL_EFFICIENCY) * 1.0   # factor=1 at beam
ok3a = abs(eff_beam - expected_beam) < 0.001
print(f"\n  Beam reach check: {eff_beam:.3f} kn == {expected_beam:.3f} kn  PASS:{ok3a}")

sail_run = make_sailboat(heading=180.0)
eff_run = sail_run._effective_wind_speed(env_polar)
expected_run = min(10.0, 10.0 * SAIL_EFFICIENCY) * SAIL_RUN_FACTOR
ok3b = abs(eff_run - expected_run) < 0.001
print(f"  Dead run check:   {eff_run:.3f} kn == {expected_run:.3f} kn  PASS:{ok3b}")

sail_irons = make_sailboat(heading=0.0)
eff_irons = sail_irons._effective_wind_speed(env_polar)
ok3c = eff_irons == 0.0
print(f"  In-irons check:   {eff_irons:.3f} kn == 0.000 kn  PASS:{ok3c}")


# ===========================================================================
# Test 4 — Sailboat stalls when pointed into no-go zone
# ===========================================================================
print()
print("=" * 60)
print("TEST 4: Sailboat decelerates to zero when in irons")
print("=" * 60)

# Wind from 0°; sailboat heading=0° (directly into wind) at 5 kn.
# Effective target = 0 → should decelerate at 0.02 kn/sim-s.
# Steps to stop from 5 kn ≈ 5 / 0.02 = 250 sim-s = 15625 steps.
env_irons = Environment(
    wind_speed=10.0, wind_direction=0.0,
    current_speed=0.0, current_direction=0.0,
)

sail4 = make_sailboat(heading=0.0, speed=5.0)
MAX_IRONS = 20_000
stopped_at = None
for step in range(MAX_IRONS):
    sail4.update_speed(SIM_TIMESTEP, env_irons)
    sail4.move(SIM_TIMESTEP, env_irons)
    if sail4.current_speed == 0.0 and stopped_at is None:
        stopped_at = step

sim_s = (stopped_at or MAX_IRONS) * SIM_TIMESTEP
expected_stop_sim_s = 5.0 / 0.02   # 250 sim-s
ok4 = stopped_at is not None
print(f"  Started at 5 kn heading 0° (into 10-kn wind)")
print(f"  Stopped at step {stopped_at}  ({sim_s:.1f} sim-s)")
print(f"  Expected stop: ~{expected_stop_sim_s:.0f} sim-s (decel={0.02} kn/sim-s)")
print(f"  PASS: {ok4}  (vessel reached zero speed)")


# ===========================================================================
# Summary
# ===========================================================================
print()
print("=" * 60)
all_ok = ok1 and ok2 and ok3a and ok3b and ok3c and ok4
print(f"ALL TESTS PASSED: {all_ok}")
