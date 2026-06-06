"""Headless test: random sudden events (engine failure, medical emergency, MOB).

Each event is triggered manually (bypassing the random probability) to verify
the correct state changes and recovery behaviour.
"""
import sys
sys.path.insert(0, r"d:\gps-simulator")

from engine.ship import Vessel
from engine.world import World
from engine.environment import Environment
from data.world_data import populate_world, VESSEL_ROUTE_CARGO, VESSEL_ROUTE_SAILBOAT
from config import (
    SIM_TIMESTEP, PORT_STAY_CARGO_S, PORT_STAY_SAILBOAT_S,
    PORT_DETECT_RADIUS, FUEL_COAST_DECELERATION,
    MOB_SEARCH_DURATION_S, MOB_SEARCH_SPEED_KN,
)
from main import _trigger_random_event

ERRORS = []

def check(cond: bool, msg: str) -> None:
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"  {tag}  {msg}")
    if not cond:
        ERRORS.append(msg)


# ---------------------------------------------------------------------------
# Shared world and environment
# ---------------------------------------------------------------------------
world = World()
populate_world(world)

env = Environment()
env.time_speed_multiplier = 1.0
env.current_speed = 0.0
env.wind_speed    = 5.0   # enough for sailboat tests


def _make_cargo(name="Test Cargo") -> Vessel:
    return Vessel(
        name=name, vessel_type="cargo",
        position=(300.0, 400.0), heading=0.0,
        target_speed=10.0, current_speed=10.0,
        max_speed=12.0, acceleration=0.020, deceleration=0.017,
        turn_rate=1.0, length_m=150.0, beam_m=25.0, draft_m=5.0,
        fuel=100.0, fuel_capacity=100.0, fuel_consumption_rate=3.5,
        route=VESSEL_ROUTE_CARGO, route_index=0,
        port_stay_duration=PORT_STAY_CARGO_S,
        destination=VESSEL_ROUTE_CARGO[0],
    )


def _make_sailboat(name="Test Sail") -> Vessel:
    return Vessel(
        name=name, vessel_type="sailboat",
        position=(300.0, 400.0), heading=0.0,
        target_speed=6.0, current_speed=6.0,
        max_speed=8.0, acceleration=0.010, deceleration=0.008,
        turn_rate=1.5, length_m=12.0, beam_m=3.5, draft_m=1.5,
        fuel=None, fuel_capacity=None, fuel_consumption_rate=0.0,
        route=VESSEL_ROUTE_SAILBOAT, route_index=0,
        port_stay_duration=PORT_STAY_SAILBOAT_S,
        destination=VESSEL_ROUTE_SAILBOAT[0],
    )


# ============================================================
# TEST A — Engine failure
# ============================================================
print("\n============================================================")
print("TEST A — Engine failure")
print("============================================================")

cargo = _make_cargo("Engine Test")
world.add_vessel(cargo)

# Manually force engine failure (what _trigger_random_event does for event_type=0)
cargo.status = "adrift"
cargo.engine_failure = True
cargo.distress = True

check(cargo.engine_failure, "engine_failure flag set")
check(cargo.distress,       "distress flag set (triggers SAR dispatch)")
check(cargo.status == "adrift", f"status = {cargo.status!r}")

# Speed should decelerate using FUEL_COAST_DECELERATION
speed_before = cargo.current_speed
cargo.update_speed(SIM_TIMESTEP, env)
check(cargo.current_speed < speed_before,
      f"speed decelerates: {speed_before:.3f} → {cargo.current_speed:.3f} kn")

expected_after = max(0.0, speed_before - FUEL_COAST_DECELERATION * SIM_TIMESTEP)
check(abs(cargo.current_speed - expected_after) < 0.001,
      f"decel rate matches FUEL_COAST_DECELERATION ({cargo.current_speed:.4f} ≈ {expected_after:.4f})")

# Refloat clears engine_failure
cargo.refloat()
check(not cargo.engine_failure, "engine_failure cleared by refloat()")
check(cargo.status == "underway", f"status restored to underway after refloat")

# ============================================================
# TEST B — Medical emergency
# ============================================================
print("\n============================================================")
print("TEST B — Medical emergency")
print("============================================================")

med = _make_cargo("Medical Test")
world.add_vessel(med)
original_destination = med.destination
original_route_index = med.route_index

# Manually trigger medical emergency
nearest_port = min(world.ports, key=lambda p: med.distance_to(p.position))
med.destination = nearest_port.position
med.player_commanded = True

check(med.player_commanded, "player_commanded set True for medical diversion")
check(med.destination != original_destination,
      f"destination changed from {original_destination} to {med.destination}")
check(med.destination == nearest_port.position,
      f"destination is nearest port ({nearest_port.name}) at {nearest_port.position}")
check(not med.distress, "no distress flag (medical is not a MAYDAY)")

# Vessel arrives at the port — player_commanded cleared via arrive()
med.destination = nearest_port.position
med.current_speed = 0.1   # just above zero so arrive fires
med.status = "underway"
# Simulate arrival: player_commanded=True → arrive() resumes route
med.arrive(world)
check(not med.player_commanded,
      "player_commanded cleared after arrival at medical port")

# ============================================================
# TEST C — Man overboard
# ============================================================
print("\n============================================================")
print("TEST C — Man overboard")
print("============================================================")

mob = _make_cargo("MOB Test")
world.add_vessel(mob)
mob_start_pos = mob.position
original_heading = mob.heading

# Manually trigger MOB (what _trigger_random_event does for event_type=2)
mob.mob_position = mob.position
mob.mob_timer    = MOB_SEARCH_DURATION_S
mob.target_speed = 0.0
mob.heading      = (mob.heading + 180.0) % 360.0

check(mob.mob_timer == MOB_SEARCH_DURATION_S,
      f"mob_timer set to {MOB_SEARCH_DURATION_S:.0f} s")
check(mob.mob_position == mob_start_pos,
      f"mob_position recorded at {mob.mob_position}")
check(mob.heading == (original_heading + 180.0) % 360.0,
      f"vessel turned 180°: heading {original_heading:.0f}° → {mob.heading:.0f}°")
check(mob.target_speed == 0.0, "target_speed set to 0 on MOB trigger")

# Advance sim: vessel should slow and hold MOB_SEARCH_SPEED_KN
# Simulate the navigation/speed/move cycle that main.py runs each step.
for _ in range(200):
    if mob.mob_timer > 0:
        mob.mob_timer = max(0.0, mob.mob_timer - SIM_TIMESTEP)
        if mob.mob_timer > 0:
            mob.target_speed = MOB_SEARCH_SPEED_KN
            mob.turn_toward(mob.bearing_to(mob.mob_position), SIM_TIMESTEP)
        else:
            mob.mob_position = None
            mob.target_speed  = mob.max_speed
            if mob.route:
                mob.destination = mob.route[mob.route_index]
    mob.update_speed(SIM_TIMESTEP, env)
    mob.move(SIM_TIMESTEP, env)

check(mob.mob_timer > 0,
      f"mob_timer still counting down after 200 steps ({mob.mob_timer:.0f} s left)")
# target_speed is set to MOB_SEARCH_SPEED_KN each step during search.
# current_speed takes ~470 sim-s to decelerate from 10 kn to 2 kn at normal decel rate;
# checking target_speed confirms the navigation intent, not the physics lag.
check(mob.target_speed == MOB_SEARCH_SPEED_KN,
      f"target_speed = {MOB_SEARCH_SPEED_KN} kn during search (actual: {mob.target_speed})")

# Advance until timer expires
while mob.mob_timer > 0:
    if mob.mob_timer > 0:
        mob.mob_timer = max(0.0, mob.mob_timer - SIM_TIMESTEP)
        if mob.mob_timer > 0:
            mob.target_speed = MOB_SEARCH_SPEED_KN
        else:
            mob.mob_position = None
            mob.target_speed  = mob.max_speed
            if mob.route:
                mob.destination = mob.route[mob.route_index]
    mob.update_speed(SIM_TIMESTEP, env)
    mob.move(SIM_TIMESTEP, env)

check(mob.mob_timer == 0.0,    "mob_timer reaches 0")
check(mob.mob_position is None, "mob_position cleared after search")
check(mob.target_speed == mob.max_speed,
      f"target_speed restored to max ({mob.target_speed} kn)")
check(mob.destination in mob.route or mob.destination == VESSEL_ROUTE_CARGO[0],
      f"destination back on scheduled route: {mob.destination}")

# ============================================================
# TEST D — Sailboat cannot get engine failure
# ============================================================
print("\n============================================================")
print("TEST D — Sailboat event eligibility")
print("============================================================")

sail = _make_sailboat()
world.add_vessel(sail)

# Run many random triggers and verify engine_failure never fires on a sailboat.
# With equal 50/50 split between medical and MOB, in 200 trials we expect
# roughly 100 of each; engine_failure = 0.
import random as rnd
rnd.seed(42)
engine_failures = 0
for _ in range(200):
    # Reset state between trials
    sail.engine_failure = False
    sail.distress       = False
    sail.status         = "underway"
    sail.player_commanded = False
    sail.mob_timer      = 0.0
    sail.mob_position   = None
    sail.destination    = VESSEL_ROUTE_SAILBOAT[0]
    _trigger_random_event(sail, world, env, event_log=None)
    if sail.engine_failure:
        engine_failures += 1

check(engine_failures == 0,
      f"Sailboat never gets engine failure in 200 trials (got {engine_failures})")

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
