"""Headless SAR (Search and Rescue) test suite.

Tests:
  A. Auto-dispatch: nearest underway vessel is assigned as rescuer when a vessel grounds.
  B. Rescue arrival: rescuer reaches grounded vessel, refloats it, resumes own route.
  C. Tide refloating: depth rises above draft threshold → vessel refloats without rescuer.
"""
import sys
sys.path.insert(0, ".")

from engine.ship import Vessel
from engine.world import World
from engine.environment import Environment
from data.world_data import (populate_world,
    VESSEL_ROUTE_CARGO, VESSEL_ROUTE_FERRY, VESSEL_ROUTE_FISHING)
from config import (
    PORT_DETECT_RADIUS, SIM_TIMESTEP, PORT_STAY_CARGO_S, PORT_STAY_FERRY_S,
    PORT_STAY_FISHING_S, DRAFT_SAFETY_MARGIN_M, KNOTS_TO_UNITS_PER_HOUR,
    SAR_DISPATCH_RANGE_NM,
)

# Import SAR helpers from main (avoids re-implementing the logic)
sys.path.insert(0, ".")
from main import _sar_dispatch, _sar_refloat

ERRORS = []

def check(cond: bool, msg: str) -> None:
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"  {tag}  {msg}")
    if not cond:
        ERRORS.append(msg)


# ---------------------------------------------------------------------------
# Build a world with two vessels: one that will ground, one that will rescue.
# ---------------------------------------------------------------------------
world = World()
populate_world(world)

env = Environment()
env.time_speed_multiplier = 1.0
env.current_speed = 0.0
env.wind_speed    = 0.0

# Casualty vessel — placed at Skerry Bank, deep draft so it grounds even at
# mid-tide (Skerry depth at tide=0 is 5.0 m; draft+margin = 6.5 m → aground).
SKERRY = (445.0, 335.0)
casualty = Vessel(
    name="MV Casualty", vessel_type="cargo",
    position=SKERRY, heading=0.0,
    target_speed=0.0, current_speed=0.0,
    max_speed=12.0, acceleration=0.020, deceleration=0.017,
    turn_rate=1.0, length_m=150.0, beam_m=25.0, draft_m=6.0,
    fuel=100.0, fuel_capacity=100.0, fuel_consumption_rate=3.5,
    route=VESSEL_ROUTE_CARGO, route_index=0,
    port_stay_duration=PORT_STAY_CARGO_S,
    destination=VESSEL_ROUTE_CARGO[0],
    status="aground",   # start grounded
)
# Rescuer — underway at open water ~100 wu south of Skerry
rescuer = Vessel(
    name="MV Rescuer", vessel_type="ferry",
    position=(445.0, 450.0), heading=270.0,
    target_speed=10.0, current_speed=10.0,
    max_speed=14.0, acceleration=0.08, deceleration=0.04,
    turn_rate=2.0, length_m=80.0, beam_m=15.0, draft_m=4.0,
    fuel=80.0, fuel_capacity=80.0, fuel_consumption_rate=5.0,
    route=VESSEL_ROUTE_FERRY, route_index=0,
    port_stay_duration=PORT_STAY_FERRY_S,
    destination=VESSEL_ROUTE_FERRY[0],
    status="underway",
)
world.add_vessel(casualty)
world.add_vessel(rescuer)

# ============================================================
# TEST A — Auto-dispatch
# ============================================================
print("\n============================================================")
print("TEST A — Auto-dispatch")
print("============================================================")

casualty.distress = True

range_wu = SAR_DISPATCH_RANGE_NM * KNOTS_TO_UNITS_PER_HOUR
_sar_dispatch(world.vessels, range_wu)

check(casualty.rescue_vessel is rescuer,
      f"Rescuer dispatched: rescue_vessel = {getattr(casualty.rescue_vessel, 'name', None)}")
check(rescuer.player_commanded,
      "Rescuer player_commanded set True")
check(rescuer.destination == SKERRY or (rescuer.destination is not None
      and abs(rescuer.destination[0] - SKERRY[0]) < 0.01
      and abs(rescuer.destination[1] - SKERRY[1]) < 0.01),
      f"Rescuer destination set to casualty position {rescuer.destination}")

# ============================================================
# TEST B — Rescue arrival and refloating
# ============================================================
print("\n============================================================")
print("TEST B — Rescue arrival")
print("============================================================")

SIM_LIMIT_S = 48 * 3600.0
elapsed = 0.0
rescued = False

while elapsed < SIM_LIMIT_S:
    # Steer rescuer toward destination
    if rescuer.destination and rescuer.status == "underway":
        rescuer.turn_toward(rescuer.bearing_to(rescuer.destination), SIM_TIMESTEP)
    rescuer.update_speed(SIM_TIMESTEP, env)
    rescuer.move(SIM_TIMESTEP, env)

    # Rescuer arrival
    if (rescuer.status in ("underway", "avoiding")
            and rescuer.destination
            and rescuer.at_destination(rescuer.destination, tolerance=PORT_DETECT_RADIUS)):
        # Rescue completion (mirrors main.py logic)
        if rescuer.player_commanded:
            for grounded in world.vessels:
                if (grounded is not rescuer
                        and grounded.distress
                        and grounded.rescue_vessel is rescuer
                        and grounded.status == "aground"):
                    _sar_refloat(grounded)
                    rescued = True
                    break
        rescuer.arrive(world)
        break

    elapsed += SIM_TIMESTEP

print(f"  Rescue arrived after {elapsed / 3600:.2f} sim-hours")
check(rescued, "Grounded vessel refloated on rescue arrival")
check(casualty.status == "underway",
      f"Casualty status after rescue: {casualty.status}")
check(not casualty.distress, "Casualty distress cleared after rescue")
check(casualty.rescue_vessel is None, "Casualty rescue_vessel cleared")
check(not rescuer.player_commanded,
      "Rescuer player_commanded cleared after rescue")
check(rescuer.destination in rescuer.route or rescuer.destination == VESSEL_ROUTE_FERRY[0],
      f"Rescuer resumed scheduled route: destination={rescuer.destination}")

# ============================================================
# TEST C — Tide refloating (no rescuer involved)
# ============================================================
print("\n============================================================")
print("TEST C — Tide refloating")
print("============================================================")

# Fresh casualty at Skerry, no rescuer
tide_casualty = Vessel(
    name="MV TideCasualty", vessel_type="cargo",
    position=SKERRY, heading=0.0,
    target_speed=0.0, current_speed=0.0,
    max_speed=12.0, acceleration=0.020, deceleration=0.017,
    turn_rate=1.0, length_m=150.0, beam_m=25.0, draft_m=6.0,
    fuel=100.0, fuel_capacity=100.0, fuel_consumption_rate=3.5,
    route=VESSEL_ROUTE_CARGO, route_index=0,
    port_stay_duration=PORT_STAY_CARGO_S,
    destination=VESSEL_ROUTE_CARGO[0],
    status="aground",
)
tide_casualty.distress = True

# At Skerry tide=0: depth=5.0 m.  draft+margin=6.5 m → aground.
depth_lw = world.water_depth_at(SKERRY, tide_level=0.0)
check(depth_lw < tide_casualty.draft_m + DRAFT_SAFETY_MARGIN_M,
      f"Vessel aground at low tide (depth={depth_lw:.1f} m < {tide_casualty.draft_m + DRAFT_SAFETY_MARGIN_M:.1f} m required)")

# At HW (tide_level=4.0): depth=7.0 m > 6.5 m required → should refloat.
from config import TIDE_RANGE
hw_tide = TIDE_RANGE
depth_hw = world.water_depth_at(SKERRY, tide_level=hw_tide)
check(depth_hw >= tide_casualty.draft_m + DRAFT_SAFETY_MARGIN_M,
      f"Depth sufficient at HW (depth={depth_hw:.1f} m >= {tide_casualty.draft_m + DRAFT_SAFETY_MARGIN_M:.1f} m required)")

# Simulate the tide refloat check (mirrors main.py aground branch)
if depth_hw >= tide_casualty.draft_m + DRAFT_SAFETY_MARGIN_M:
    _sar_refloat(tide_casualty)

check(tide_casualty.status == "underway",
      f"Tide refloat: vessel status = {tide_casualty.status}")
check(not tide_casualty.distress, "Tide refloat: distress cleared")
check(tide_casualty.rescue_vessel is None, "Tide refloat: no rescue_vessel")

# ============================================================
# Summary
# ============================================================
print("\n============================================================")
if ERRORS:
    for e in ERRORS:
        print(f"  FAIL: {e}")
    print(f"\n{len(ERRORS)} FAILURE(S)")
    sys.exit(1)

print("ALL CHECKS PASSED")
