"""Verify _cog_direction() math headlessly — no pygame / no display.

Exact copy of the render/chart.py function body so the logic is tested
directly without needing to import pygame.

Setup:  vessel heading=0° (east in world coords), speed=6 kn
        current_direction=90° (southward), speed=3 kn
        wind=0 (isolated)

Expected COG:
  vx = cos(0°)*6 + cos(90°)*3  =  6 + 0  = 6
  vy = sin(0°)*6 + sin(90°)*3  =  0 + 3  = 3
  COG angle = atan2(3, 6) ≈ 26.565°
  Drift     = 26.565° - 0°    ≈ 26.6°

If drift ≈ 0° the current vector is not being added — the bug is in _cog_direction.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from math import atan2, cos, sin, degrees, radians, hypot
from engine.ship import Vessel
from engine.environment import Environment
from config import CURRENT_INFLUENCE, COG_MIN_DRIFT_DEG


# ---------------------------------------------------------------------------
# Exact copy of _cog_direction from render/chart.py (no pygame dependency)
# ---------------------------------------------------------------------------
def _cog_direction(vessel, environment):
    if environment is None or vessel.current_speed <= 0:
        return None

    h_rad = radians(vessel.heading)
    vx = cos(h_rad) * vessel.current_speed
    vy = sin(h_rad) * vessel.current_speed

    c_rad = radians(environment.current_direction)
    vx += cos(c_rad) * environment.current_speed * CURRENT_INFLUENCE
    vy += sin(c_rad) * environment.current_speed * CURRENT_INFLUENCE

    push_rad = radians((environment.wind_direction + 180.0) % 360.0)
    wind_kn = environment.wind_speed * vessel._windage_factor()
    vx += cos(push_rad) * wind_kn
    vy += sin(push_rad) * wind_kn

    cog_rad = atan2(vy, vx)
    cog_speed = hypot(vx, vy)

    drift = (degrees(cog_rad) - vessel.heading + 180.0) % 360.0 - 180.0
    if abs(drift) < COG_MIN_DRIFT_DEG:
        return None

    return cog_rad, cog_speed


# ---------------------------------------------------------------------------
# Test scenario: heading=0, speed=6 kn; current 3 kn at 90°; no wind
# ---------------------------------------------------------------------------
vessel = Vessel(
    name="Test",
    vessel_type="cargo",
    position=(500.0, 350.0),
    heading=0.0,           # 0° = east in world coords
    target_speed=6.0,
    current_speed=6.0,     # already at cruise — no ramp needed
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

env = Environment(
    current_speed=3.0,        # 3 kn
    current_direction=90.0,   # southward in world coords (0=east, 90=south)
    wind_speed=0.0,           # no wind — isolate current effect
    wind_direction=0.0,
)

# Manual expected values
expected_vx  = cos(radians(0.0)) * 6.0 + cos(radians(90.0)) * 3.0  # = 6
expected_vy  = sin(radians(0.0)) * 6.0 + sin(radians(90.0)) * 3.0  # = 3
expected_cog = degrees(atan2(expected_vy, expected_vx))             # ≈ 26.565°
expected_drift = expected_cog - vessel.heading                       # ≈ 26.565°

result = _cog_direction(vessel, env)

print("=" * 55)
print("COG MATH VERIFICATION")
print("=" * 55)
print(f"  Vessel heading:        {vessel.heading:.1f}°")
print(f"  Vessel speed:          {vessel.current_speed:.1f} kn")
print(f"  Current direction:     {env.current_direction:.1f}°  (toward)")
print(f"  Current speed:         {env.current_speed:.1f} kn")
print(f"  CURRENT_INFLUENCE:     {CURRENT_INFLUENCE}")
print()
print(f"  Expected velocity vector:  ({expected_vx:.3f}, {expected_vy:.3f}) kn")
print(f"  Expected COG angle:        {expected_cog:.3f}°")
print(f"  Expected drift:            {expected_drift:.3f}°")
print()

if result is None:
    print("  _cog_direction returned None")
    if vessel.current_speed <= 0:
        print("  REASON: current_speed is 0")
    else:
        h_rad = radians(vessel.heading)
        vx = cos(h_rad) * vessel.current_speed
        vy = sin(h_rad) * vessel.current_speed
        c_rad = radians(env.current_direction)
        vx += cos(c_rad) * env.current_speed * CURRENT_INFLUENCE
        vy += sin(c_rad) * env.current_speed * CURRENT_INFLUENCE
        cog_rad = atan2(vy, vx)
        actual_drift = (degrees(cog_rad) - vessel.heading + 180.0) % 360.0 - 180.0
        print(f"  Computed drift before threshold check: {actual_drift:.3f}°")
        print(f"  COG_MIN_DRIFT_DEG threshold: {COG_MIN_DRIFT_DEG}°")
        if abs(actual_drift) < COG_MIN_DRIFT_DEG:
            print("  REASON: drift is below display threshold (would not render)")
        else:
            print("  REASON: unknown — check function body")
    print()
    print(f"  VERDICT: BUG — current vector not contributing drift")
else:
    cog_rad, cog_speed = result
    actual_cog_deg = degrees(cog_rad)
    actual_drift = (actual_cog_deg - vessel.heading + 180.0) % 360.0 - 180.0

    print(f"  Actual COG angle:          {actual_cog_deg:.3f}°")
    print(f"  Actual COG speed:          {cog_speed:.3f} kn")
    print(f"  Actual drift angle:        {actual_drift:.3f}°")
    print()

    error = abs(actual_drift - expected_drift)
    ok = error < 0.001
    print(f"  Drift matches expected:    {ok}  (error={error:.6f}°)")
    print()
    if ok:
        print(f"  VERDICT: COG math is correct -- drift ~26.6 deg as expected.")
        print("  COG line will render as a solid teal-green line (COLOR_COG_VECTOR)")
        print("  diverging ~26 deg from the dashed blue heading predictor for this scenario.")
    else:
        print(f"  VERDICT: BUG -- expected ~{expected_drift:.1f} deg, got {actual_drift:.1f} deg")
