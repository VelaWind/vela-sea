"""Verify the course-over-ground (COG) maths headlessly: no Pygame, no display.

Tests engine.navigation.cog_direction, the function itself (it used to be a
hand-copied body of a function in render/chart.py, which could drift from the
original without anyone noticing).

Two checks:

1. Known answer.  Vessel heading 0 deg (east in world coords) at 6 kn, current
   3 kn toward 90 deg (south), no wind:
       vx = cos(0)*6 + cos(90)*3 = 6
       vy = sin(0)*6 + sin(90)*3 = 3
       COG = atan2(3, 6) = 26.565 deg, so drift from heading = 26.565 deg

2. Agreement with the physics.  cog_direction() and Vessel.move() compute the
   same velocity (heading + current + wind drift) separately.  One real move()
   step is taken with wind added, and the direction and speed of the actual
   displacement must match what cog_direction() reports.  If either side
   changes alone, this check fails.

Exit status is 0 only when both checks pass (CI relies on it).
"""

import copy
import os
import sys
from math import atan2, cos, degrees, hypot, radians, sin

# The repository root, two levels up, so engine/ and config.py import.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

from config import CURRENT_INFLUENCE, KNOTS_TO_UNITS_PER_HOUR
from engine.environment import Environment
from engine.navigation import cog_direction
from engine.ship import Vessel

TOLERANCE_DEG = 0.001   # angle agreement for check 1 (pure arithmetic)
MOVE_DT_S = 1.0         # one sim-second for the move() comparison in check 2
MOVE_TOL_DEG = 0.01     # move() vs cog_direction() direction agreement
MOVE_TOL_KN = 0.001     # move() vs cog_direction() speed agreement


def make_vessel() -> Vessel:
    return Vessel(
        name="Test",
        vessel_type="cargo",
        position=(500.0, 350.0),
        heading=0.0,           # 0 deg = east in world coords
        target_speed=6.0,
        current_speed=6.0,     # already at cruise, no ramp needed
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
    )


print("=" * 55)
print("COG MATH VERIFICATION (engine.navigation.cog_direction)")
print("=" * 55)

# ---------------------------------------------------------------------------
# Check 1: known answer, current only
# ---------------------------------------------------------------------------
vessel = make_vessel()
env = Environment(
    current_speed=3.0,        # 3 kn
    current_direction=90.0,   # southward in world coords (0=east, 90=south)
    wind_speed=0.0,           # no wind: isolate the current
    wind_direction=0.0,
)
expected_vx = cos(radians(0.0)) * 6.0 + cos(radians(90.0)) * 3.0 * CURRENT_INFLUENCE
expected_vy = sin(radians(0.0)) * 6.0 + sin(radians(90.0)) * 3.0 * CURRENT_INFLUENCE
expected_drift = degrees(atan2(expected_vy, expected_vx)) - vessel.heading

result = cog_direction(vessel, env)
print(f"  Check 1: heading {vessel.heading:.1f} deg at {vessel.current_speed:.1f} kn, "
      f"current {env.current_speed:.1f} kn toward {env.current_direction:.1f} deg")
print(f"    expected drift:  {expected_drift:.3f} deg")
if result is None:
    check1 = False
    print("    actual:          cog_direction returned None (no drift reported)")
else:
    actual_drift = (degrees(result[0]) - vessel.heading + 180.0) % 360.0 - 180.0
    check1 = abs(actual_drift - expected_drift) < TOLERANCE_DEG
    print(f"    actual drift:    {actual_drift:.3f} deg  -> {'PASS' if check1 else 'FAIL'}")

# ---------------------------------------------------------------------------
# Check 2: cog_direction agrees with one real Vessel.move() step (wind on)
# ---------------------------------------------------------------------------
vessel2 = make_vessel()
env2 = Environment(
    current_speed=1.5, current_direction=120.0,
    wind_speed=12.0, wind_direction=200.0,
)
predicted = cog_direction(vessel2, env2)
mover = copy.deepcopy(vessel2)
x0, y0 = mover.position
mover.move(MOVE_DT_S, env2)
dx, dy = mover.position[0] - x0, mover.position[1] - y0
# Displacement over MOVE_DT_S, converted back to knots.
moved_speed_kn = hypot(dx, dy) / (KNOTS_TO_UNITS_PER_HOUR * MOVE_DT_S / 3600.0)
moved_dir = degrees(atan2(dy, dx))
print(f"  Check 2: one move() step with current and wind")
if predicted is None:
    check2 = False
    print("    cog_direction returned None, but this scenario has clear drift  -> FAIL")
else:
    pred_dir = degrees(predicted[0])
    dir_err = abs((moved_dir - pred_dir + 180.0) % 360.0 - 180.0)
    spd_err = abs(moved_speed_kn - predicted[1])
    check2 = dir_err < MOVE_TOL_DEG and spd_err < MOVE_TOL_KN
    print(f"    cog_direction:   {pred_dir:.3f} deg at {predicted[1]:.3f} kn")
    print(f"    move() actual:   {moved_dir:.3f} deg at {moved_speed_kn:.3f} kn")
    print(f"    difference:      {dir_err:.5f} deg, {spd_err:.5f} kn  "
          f"-> {'PASS' if check2 else 'FAIL'}")

print()
ok = check1 and check2
print(f"  VERDICT: {'COG maths correct and consistent with move()' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
