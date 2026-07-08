"""Headless test: vessel mission behavior.

Verifies that mission_status changes correctly for each mission type:
  A. cargo_run   — LOADING/UNLOADING alternates in port; UNDERWAY on transit
  B. ferry_run   — BOARDING in port; ON SCHEDULE underway
  C. fishing_trip — TRAWLING at open-sea WP; UNLOADING CATCH in port; timer expires
  D. sailing_cruise — ANCHORED at open-sea WP; SAILING underway
  E. tug_duty    — ESCORTING underway; STANDBY in port
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ship import Vessel
from engine.world import World
from engine.environment import Environment
from data.world_data import (populate_world,
    VESSEL_ROUTE_CARGO, VESSEL_ROUTE_FERRY,
    VESSEL_ROUTE_FISHING, VESSEL_ROUTE_SAILBOAT, VESSEL_ROUTE_TUG)
from config import (
    SIM_TIMESTEP, PORT_STAY_CARGO_LOAD_S, PORT_STAY_FERRY_BOARD_S,
    PORT_STAY_FISHING_UNLOAD_S, PORT_STAY_TUG_S,
    TRAWL_DURATION_S, TRAWL_SPEED_KN, SAIL_ANCHOR_DURATION_S,
    PORT_STAY_CARGO_S, PORT_STAY_FERRY_S, PORT_STAY_FISHING_S, PORT_STAY_SAILBOAT_S,
    PORT_DETECT_RADIUS,
)
from main import (
    _set_port_mission_status, _set_underway_mission_status,
    _start_waypoint_pause,
)

ERRORS = []


def check(cond: bool, msg: str) -> None:
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"  {tag}  {msg}")
    if not cond:
        ERRORS.append(msg)


world = World()
populate_world(world)

env = Environment()
env.time_speed_multiplier = 1.0
env.current_speed = 0.0
env.wind_speed = 5.0


def _make_vessel(name, vtype, route, stay_s) -> Vessel:
    return Vessel(
        name=name, vessel_type=vtype,
        position=(300.0, 400.0), heading=0.0,
        target_speed=10.0, current_speed=5.0,
        max_speed=12.0, acceleration=0.020, deceleration=0.017,
        turn_rate=1.0, length_m=100.0, beam_m=20.0, draft_m=4.0,
        fuel=100.0, fuel_capacity=100.0, fuel_consumption_rate=3.0,
        route=route, route_index=0,
        port_stay_duration=stay_s,
        destination=route[0],
    )


# ============================================================
# TEST A — cargo_run
# ============================================================
print("\n============================================================")
print("TEST A — cargo_run")
print("============================================================")

cargo = _make_vessel("Test Cargo", "cargo", VESSEL_ROUTE_CARGO, PORT_STAY_CARGO_LOAD_S)
cargo.mission_type = "cargo_run"
_set_underway_mission_status(cargo)
check(cargo.mission_status == "UNDERWAY",
      f"Cargo underway status: {cargo.mission_status!r}")

# First port arrival → port_visit_count = 1 → LOADING
cargo.status = "in_port"
cargo.port_visit_count += 1
_set_port_mission_status(cargo)
check(cargo.mission_status == "LOADING",
      f"Cargo port visit 1: {cargo.mission_status!r}")

# Second port arrival → port_visit_count = 2 → UNLOADING
cargo.port_visit_count += 1
_set_port_mission_status(cargo)
check(cargo.mission_status == "UNLOADING",
      f"Cargo port visit 2: {cargo.mission_status!r}")

# Third port arrival → back to LOADING (odd visit)
cargo.port_visit_count += 1
_set_port_mission_status(cargo)
check(cargo.mission_status == "LOADING",
      f"Cargo port visit 3: {cargo.mission_status!r}")

# ============================================================
# TEST B — ferry_run
# ============================================================
print("\n============================================================")
print("TEST B — ferry_run")
print("============================================================")

ferry = _make_vessel("Test Ferry", "ferry", VESSEL_ROUTE_FERRY, PORT_STAY_FERRY_BOARD_S)
ferry.mission_type = "ferry_run"
_set_underway_mission_status(ferry)
check(ferry.mission_status == "ON SCHEDULE",
      f"Ferry underway: {ferry.mission_status!r}")

ferry.status = "in_port"
ferry.port_visit_count += 1
_set_port_mission_status(ferry)
check(ferry.mission_status == "BOARDING",
      f"Ferry in port: {ferry.mission_status!r}")

# ============================================================
# TEST C — fishing_trip (trawling)
# ============================================================
print("\n============================================================")
print("TEST C — fishing_trip / TRAWLING")
print("============================================================")

fishing = _make_vessel("Test Fishing", "fishing", VESSEL_ROUTE_FISHING, PORT_STAY_FISHING_UNLOAD_S)
fishing.mission_type = "fishing_trip"
_set_underway_mission_status(fishing)
check(fishing.mission_status == "TRANSIT",
      f"Fishing underway: {fishing.mission_status!r}")

# Trigger trawling at open-sea WP
_start_waypoint_pause(fishing)
check(fishing.trawling_timer == TRAWL_DURATION_S,
      f"Trawling timer set: {fishing.trawling_timer}")
check(fishing.mission_status == "TRAWLING",
      f"Trawling status: {fishing.mission_status!r}")
check(fishing.target_speed == TRAWL_SPEED_KN,
      f"Trawling speed: {fishing.target_speed}")

# Advance past the full trawl duration (simulating the nav block)
steps = int(TRAWL_DURATION_S / SIM_TIMESTEP) + 2
for _ in range(steps):
    if fishing.trawling_timer > 0:
        fishing.trawling_timer = max(0.0, fishing.trawling_timer - SIM_TIMESTEP)
        if fishing.trawling_timer <= 0:
            fishing.trawling_heading_timer = 0.0
            fishing.target_speed = fishing.max_speed
            _set_underway_mission_status(fishing)

check(fishing.trawling_timer == 0.0, "Trawling timer expired")
check(fishing.mission_status == "TRANSIT",
      f"Status after trawl: {fishing.mission_status!r}")
check(fishing.target_speed == fishing.max_speed,
      f"Speed restored: {fishing.target_speed}")

# Port arrival after trawling → UNLOADING CATCH
fishing.status = "in_port"
fishing.port_visit_count += 1
_set_port_mission_status(fishing)
check(fishing.mission_status == "UNLOADING CATCH",
      f"Fishing port: {fishing.mission_status!r}")

# ============================================================
# TEST D — sailing_cruise (anchor stop)
# ============================================================
print("\n============================================================")
print("TEST D — sailing_cruise / ANCHORED")
print("============================================================")

sail = _make_vessel("Test Sail", "sailboat", VESSEL_ROUTE_SAILBOAT, PORT_STAY_SAILBOAT_S)
sail.fuel = None
sail.fuel_capacity = None
sail.mission_type = "sailing_cruise"
_set_underway_mission_status(sail)
check(sail.mission_status == "SAILING",
      f"Sailboat underway: {sail.mission_status!r}")

# Open-sea WP arrival → anchor stop
_start_waypoint_pause(sail)
check(sail.trawling_timer == SAIL_ANCHOR_DURATION_S,
      f"Anchor timer set: {sail.trawling_timer}")
check(sail.mission_status == "ANCHORED",
      f"Anchor status: {sail.mission_status!r}")
check(sail.target_speed == 0.0,
      f"Speed set to 0 while anchored: {sail.target_speed}")

# ============================================================
# TEST E — tug_duty
# ============================================================
print("\n============================================================")
print("TEST E — tug_duty")
print("============================================================")

tug = _make_vessel("Test Tug", "tug", VESSEL_ROUTE_TUG, PORT_STAY_TUG_S)
tug.mission_type = "tug_duty"
_set_underway_mission_status(tug)
check(tug.mission_status == "ESCORTING",
      f"Tug underway: {tug.mission_status!r}")

tug.status = "in_port"
tug.port_visit_count += 1
_set_port_mission_status(tug)
check(tug.mission_status == "STANDBY",
      f"Tug in port: {tug.mission_status!r}")

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
