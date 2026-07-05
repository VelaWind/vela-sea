"""tests/test_traffic.py — Traffic and separation headless test suite.

Tests:
  1. Open water separation  — 24h, every pair every step, min sep > 0.2 nm
  2. Port separation        — vessels at same port never < 1.5 wu apart
  3. Avoidance frequency    — 0 < avoiding-transitions < 500 in 24h
  4. Shallow-angle convergence — 20-deg oblique approach, min sep > 0.3 nm
  5. Port-approach collision  — two vessels homing to same port, min sep > 0.3 nm
"""

import sys, time, math
sys.path.insert(0, ".")

from engine.world import World
from engine.ship import Vessel
from engine.environment import Environment
from engine.collision import update_collision_avoidance
from data.world_data import (
    populate_world,
    VESSEL_ROUTE_FERRY, VESSEL_ROUTE_CARGO,
    VESSEL_ROUTE_FISHING, VESSEL_ROUTE_SAILBOAT,
    VESSEL_ROUTE_CARGO2, VESSEL_ROUTE_FISHING2,
    VESSEL_ROUTE_TUG, VESSEL_ROUTE_SAILBOAT2,
)
from config import (
    NM_PER_WORLD_UNIT, KNOTS_TO_UNITS_PER_HOUR,
    PORT_DETECT_RADIUS, DRAFT_SAFETY_MARGIN_M,
    PORT_STAY_FERRY_S, PORT_STAY_CARGO_S,
    PORT_STAY_FISHING_S, PORT_STAY_SAILBOAT_S,
    ARRIVAL_DISTANCE,
)

SCENARIO_DT = 1.0    # sim-s per step for scenario tests
FULL_DT     = 10.0   # sim-s per step for the 24-hour run


# ---------------------------------------------------------------------------
# Helpers shared with test_collision.py
# ---------------------------------------------------------------------------

def _make_vessel(name, x, y, heading, speed, vtype="cargo"):
    return Vessel(
        name=name, vessel_type=vtype,
        position=(float(x), float(y)),
        heading=float(heading),
        target_speed=float(speed), current_speed=float(speed),
        max_speed=float(speed) + 2.0,
        acceleration=0.5, deceleration=0.3,
        turn_rate=3.0,
        length_m=80.0, beam_m=15.0, draft_m=4.0,
        fuel=100.0, fuel_capacity=100.0, fuel_consumption_rate=2.0,
    )


def _sep_nm(a, b):
    dx = b.position[0] - a.position[0]
    dy = b.position[1] - a.position[1]
    return math.hypot(dx, dy) * NM_PER_WORLD_UNIT


def _sep_wu(a, b):
    dx = b.position[0] - a.position[0]
    dy = b.position[1] - a.position[1]
    return math.hypot(dx, dy)


def _step_vessels(vessels, env, dt, world=None):
    for v in vessels:
        if v.status == "in_port":
            v.update_route(dt, world)
        if v.status == "avoiding":
            v.turn_toward(v.avoid_heading, dt)
        elif v.destination and v.status == "underway":
            v.turn_toward(v.bearing_to(v.destination), dt)
        v.update_speed(dt, env)
        v.move(dt, env)
        if (world and v.status in ("underway", "avoiding")
                and v.destination
                and v.at_destination(v.destination, tolerance=PORT_DETECT_RADIUS)):
            v.arrive(world)
        if world and v.status in ("underway", "avoiding"):
            if v._port_at(v.position, world) is None:
                depth = world.water_depth_at(v.position, env.tide_level)
                if depth < v.draft_m + DRAFT_SAFETY_MARGIN_M:
                    v.status = "aground"
                    v.current_speed = 0.0
    update_collision_avoidance(vessels)


def _make_all_vessels():
    return [
        Vessel(
            name="MV Tidewater", vessel_type="cargo",
            position=(105.0, 315.0), heading=90.0,
            target_speed=8.0, current_speed=0.0,
            max_speed=12.0, acceleration=0.020, deceleration=0.017,
            turn_rate=1.0, length_m=150.0, beam_m=25.0, draft_m=8.0,
            fuel=100.0, fuel_capacity=100.0, fuel_consumption_rate=3.5,
            route=VESSEL_ROUTE_CARGO, route_index=0,
            port_stay_duration=PORT_STAY_CARGO_S,
            destination=VESSEL_ROUTE_CARGO[0],
        ),
        Vessel(
            name="FV Horizon", vessel_type="fishing",
            position=(330.0, 275.0), heading=135.0,
            target_speed=6.0, current_speed=0.0,
            max_speed=10.0, acceleration=0.10, deceleration=0.06,
            turn_rate=3.0, length_m=40.0, beam_m=8.0, draft_m=3.0,
            fuel=50.0, fuel_capacity=50.0, fuel_consumption_rate=2.8,
            route=VESSEL_ROUTE_FISHING, route_index=1,
            port_stay_duration=PORT_STAY_FISHING_S,
            destination=VESSEL_ROUTE_FISHING[1],
        ),
        Vessel(
            name="SY Windward", vessel_type="sailboat",
            position=(660.0, 600.0), heading=114.0,
            target_speed=5.0, current_speed=0.0,
            max_speed=10.0, acceleration=0.05, deceleration=0.02,
            turn_rate=2.5, length_m=35.0, beam_m=7.0, draft_m=2.5,
            fuel=None, fuel_capacity=None, fuel_consumption_rate=0.0,
            route=VESSEL_ROUTE_SAILBOAT, route_index=2,
            port_stay_duration=PORT_STAY_SAILBOAT_S,
            destination=VESSEL_ROUTE_SAILBOAT[2],
        ),
        Vessel(
            name="MS Coastal Express", vessel_type="ferry",
            position=(500.0, 565.0), heading=335.0,
            target_speed=10.0, current_speed=0.0,
            max_speed=14.0, acceleration=0.08, deceleration=0.04,
            turn_rate=2.0, length_m=80.0, beam_m=15.0, draft_m=4.0,
            fuel=80.0, fuel_capacity=80.0, fuel_consumption_rate=5.0,
            route=VESSEL_ROUTE_FERRY, route_index=3,
            port_stay_duration=PORT_STAY_FERRY_S,
            destination=VESSEL_ROUTE_FERRY[3],
        ),
        Vessel(
            name="MV Carrick Star", vessel_type="cargo",
            position=(480.0, 535.0), heading=208.0,
            target_speed=8.0, current_speed=0.0,
            max_speed=11.0, acceleration=0.018, deceleration=0.015,
            turn_rate=1.2, length_m=130.0, beam_m=22.0, draft_m=6.5,
            fuel=80.0, fuel_capacity=80.0, fuel_consumption_rate=3.0,
            route=VESSEL_ROUTE_CARGO2, route_index=9,
            port_stay_duration=PORT_STAY_CARGO_S,
            destination=VESSEL_ROUTE_CARGO2[9],
        ),
        Vessel(
            name="FV Skerrywatch", vessel_type="fishing",
            position=(300.0, 300.0), heading=90.0,
            target_speed=6.0, current_speed=0.0,
            max_speed=9.0, acceleration=0.09, deceleration=0.05,
            turn_rate=3.5, length_m=32.0, beam_m=7.0, draft_m=2.5,
            fuel=40.0, fuel_capacity=40.0, fuel_consumption_rate=2.5,
            route=VESSEL_ROUTE_FISHING2, route_index=1,
            port_stay_duration=PORT_STAY_FISHING_S,
            destination=VESSEL_ROUTE_FISHING2[1],
        ),
        Vessel(
            name="Ardent Pilot", vessel_type="ferry",
            position=(670.0, 575.0), heading=26.0,
            target_speed=10.0, current_speed=0.0,
            max_speed=12.0, acceleration=0.15, deceleration=0.10,
            turn_rate=5.0, length_m=25.0, beam_m=8.0, draft_m=2.0,
            fuel=25.0, fuel_capacity=25.0, fuel_consumption_rate=4.0,
            route=VESSEL_ROUTE_TUG, route_index=3,
            port_stay_duration=PORT_STAY_FERRY_S,
            destination=VESSEL_ROUTE_TUG[3],
        ),
        Vessel(
            name="SY Morning Breeze", vessel_type="sailboat",
            position=(150.0, 350.0), heading=129.0,
            target_speed=5.0, current_speed=0.0,
            max_speed=8.0, acceleration=0.04, deceleration=0.02,
            turn_rate=2.0, length_m=28.0, beam_m=6.0, draft_m=2.0,
            fuel=None, fuel_capacity=None, fuel_consumption_rate=0.0,
            route=VESSEL_ROUTE_SAILBOAT2, route_index=1,
            port_stay_duration=PORT_STAY_SAILBOAT_S,
            destination=VESSEL_ROUTE_SAILBOAT2[1],
        ),
    ]


# ---------------------------------------------------------------------------
# Tests 1-3: Combined 24-hour run
# ---------------------------------------------------------------------------

def test_24h_run():
    """Run 24 sim-hours; check open-water separation, port separation, avoidance count."""
    print("Tests 1-3: 24-sim-hour full-traffic run ...", flush=True)

    world = World()
    populate_world(world)
    env = Environment()
    env.weather_drift_enabled = False
    vessels = _make_all_vessels()
    for v in vessels:
        world.add_vessel(v)

    n = len(vessels)
    target_s = 24.0 * 3600.0
    sim_time = 0.0

    # Tracking
    min_open_sep_nm  = float("inf")  # Test 1
    min_open_pair    = ("?", "?")
    min_open_time    = 0.0
    min_open_hdgs    = (0.0, 0.0)

    max_port_pair_wu = 0.0           # Test 2 (worst = smallest when both in_port)
    min_port_sep_wu  = float("inf")
    min_port_pair    = ("?", "?")

    avoid_entries    = 0             # Test 3
    prev_avoiding    = {v.name: False for v in vessels}

    t0 = time.perf_counter()

    while sim_time < target_s:
        env.update(FULL_DT)
        _step_vessels(vessels, env, FULL_DT, world)

        # Check every pair this step
        for i in range(n):
            for j in range(i + 1, n):
                a, b = vessels[i], vessels[j]

                # Test 1: open-water separation (both underway or avoiding)
                if a.status in ("underway", "avoiding") and b.status in ("underway", "avoiding"):
                    sep = _sep_nm(a, b)
                    if sep < min_open_sep_nm:
                        min_open_sep_nm = sep
                        min_open_pair   = (a.name, b.name)
                        min_open_time   = sim_time
                        min_open_hdgs   = (a.heading, b.heading)

                # Test 2: port separation (both in_port, close enough to be same port)
                if a.status == "in_port" and b.status == "in_port":
                    wu = _sep_wu(a, b)
                    # Only flag if they're plausibly at the same port (< 20 wu apart)
                    if wu < 20.0 and wu < min_port_sep_wu:
                        min_port_sep_wu = wu
                        min_port_pair   = (a.name, b.name)

        # Test 3: count avoiding transitions
        for v in vessels:
            now_avoiding = (v.status == "avoiding")
            if now_avoiding and not prev_avoiding[v.name]:
                avoid_entries += 1
            prev_avoiding[v.name] = now_avoiding

        sim_time += FULL_DT

    elapsed = time.perf_counter() - t0

    # Report
    print(f"  run time: {elapsed:.1f}s real")

    errors = []

    # Test 1
    print(f"\n  Test 1 — Open-water separation")
    print(f"    Min separation : {min_open_sep_nm:.3f} nm")
    print(f"    Pair           : {min_open_pair[0]} / {min_open_pair[1]}")
    print(f"    At sim-time    : {min_open_time/3600:.2f} h")
    print(f"    Headings       : {min_open_hdgs[0]:.0f}° / {min_open_hdgs[1]:.0f}°")
    if min_open_sep_nm > 0.2:
        print(f"    PASS  (> 0.2 nm)")
    else:
        msg = f"Pair {min_open_pair} came within {min_open_sep_nm:.3f} nm (limit 0.2 nm) at {min_open_time/3600:.2f}h"
        print(f"    FAIL  {msg}")
        errors.append(msg)

    # Test 2
    print(f"\n  Test 2 — Port separation")
    if min_port_sep_wu == float("inf"):
        print(f"    No co-located in_port pairs observed — PASS")
    else:
        print(f"    Min same-port separation : {min_port_sep_wu:.2f} wu")
        print(f"    Pair                     : {min_port_pair[0]} / {min_port_pair[1]}")
        if min_port_sep_wu > 1.5:
            print(f"    PASS  (> 1.5 wu)")
        else:
            msg = f"Port pair {min_port_pair} within {min_port_sep_wu:.2f} wu (limit 1.5 wu)"
            print(f"    FAIL  {msg}")
            errors.append(msg)

    # Test 3
    print(f"\n  Test 3 — Avoidance frequency")
    print(f"    Avoiding-status entries : {avoid_entries}")
    if 0 < avoid_entries < 500:
        print(f"    PASS  (0 < {avoid_entries} < 500)")
    elif avoid_entries == 0:
        msg = "Avoidance never triggered — routes may not be close enough, or system is broken"
        print(f"    FAIL  {msg}")
        errors.append(msg)
    else:
        msg = f"Avoidance triggered {avoid_entries} times (limit < 500) — false-triggering on routes"
        print(f"    FAIL  {msg}")
        errors.append(msg)

    return errors


# ---------------------------------------------------------------------------
# Test 4: Shallow-angle convergence at ~20°
# ---------------------------------------------------------------------------

def test_shallow_angle():
    """Vessels converging at ~20° (not head-on) must maintain > 0.3 nm separation."""
    print("\n  Test 4 — Shallow-angle convergence (20-deg oblique, combined ~14 kn)")

    # A heads east (0°); B heads at 200° (20° past due-west, slightly south).
    # Courses meet at ~20° interior angle.  Initial separation ~3.5 nm.
    a = _make_vessel("A", 200.0, 350.0,   0.0, 7.0)
    b = _make_vessel("B", 223.0, 347.0, 200.0, 7.0)

    env = Environment()
    env.weather_drift_enabled = False
    vessels = [a, b]

    min_sep = _sep_nm(a, b)
    ever_avoiding = False
    sim_time = 0.0
    limit = 2000.0

    while sim_time < limit:
        _step_vessels(vessels, env, SCENARIO_DT)
        sep = _sep_nm(a, b)
        if sep < min_sep:
            min_sep = sep
        if a.status == "avoiding" or b.status == "avoiding":
            ever_avoiding = True
        sim_time += SCENARIO_DT

    print(f"    Min separation : {min_sep:.3f} nm  (avoidance triggered: {ever_avoiding})")
    if min_sep > 0.3:
        print(f"    PASS")
        return []
    else:
        msg = f"Shallow-angle min sep {min_sep:.3f} nm <= 0.3 nm"
        print(f"    FAIL  {msg}")
        return [msg]


# ---------------------------------------------------------------------------
# Test 5: Two vessels converging on the same port from opposite bearings
# ---------------------------------------------------------------------------

def test_port_approach():
    """Vessels from opposite directions homing to Port Ardent must not collide."""
    print("\n  Test 5 — Port-approach from opposite bearings (Port Ardent)")

    world = World()
    populate_world(world)
    port_pos = (648.0, 460.0)   # Port Ardent

    # A approaches from NW (bearing 225° FROM port → A is NW of port, heading SE ~45°)
    # B approaches from SE (bearing 45° FROM port → B is SE of port, heading NW ~225°)
    # offset = 25 wu (≈ 3.75 nm) → A-B separation ≈ 50 wu ≈ 7.5 nm (within 8-nm radar)
    offset = 25.0
    ax = port_pos[0] - offset * math.cos(math.radians(45.0))
    ay = port_pos[1] - offset * math.sin(math.radians(45.0))
    bx = port_pos[0] + offset * math.cos(math.radians(45.0))
    by = port_pos[1] + offset * math.sin(math.radians(45.0))

    env = Environment()
    env.weather_drift_enabled = False

    # Give vessels a port destination so they actually head for the port
    from data.world_data import VESSEL_ROUTE_FERRY
    a = Vessel(
        name="A", vessel_type="ferry",
        position=(ax, ay), heading=45.0,
        target_speed=7.0, current_speed=7.0,
        max_speed=10.0, acceleration=0.08, deceleration=0.04,
        turn_rate=3.0, length_m=80.0, beam_m=15.0, draft_m=4.0,
        fuel=80.0, fuel_capacity=80.0, fuel_consumption_rate=2.0,
        route=[], route_index=0, port_stay_duration=0,
        destination=port_pos,
    )
    b = Vessel(
        name="B", vessel_type="ferry",
        position=(bx, by), heading=225.0,
        target_speed=7.0, current_speed=7.0,
        max_speed=10.0, acceleration=0.08, deceleration=0.04,
        turn_rate=3.0, length_m=80.0, beam_m=15.0, draft_m=4.0,
        fuel=80.0, fuel_capacity=80.0, fuel_consumption_rate=2.0,
        route=[], route_index=0, port_stay_duration=0,
        destination=port_pos,
    )
    world.add_vessel(a)
    world.add_vessel(b)

    vessels = [a, b]
    min_sep = _sep_nm(a, b)
    ever_avoiding = False
    sim_time = 0.0
    limit = 4000.0   # enough time for both to reach port at 7 kn over 7.5 nm

    while sim_time < limit:
        _step_vessels(vessels, env, SCENARIO_DT, world)
        # Only track separation while both are underway
        if a.status in ("underway", "avoiding") and b.status in ("underway", "avoiding"):
            sep = _sep_nm(a, b)
            if sep < min_sep:
                min_sep = sep
        if a.status == "avoiding" or b.status == "avoiding":
            ever_avoiding = True
        # Stop early once both have docked
        if a.status == "in_port" and b.status == "in_port":
            break
        sim_time += SCENARIO_DT

    print(f"    Min underway separation : {min_sep:.3f} nm  (avoidance: {ever_avoiding})")
    print(f"    Final status: A={a.status}  B={b.status}")
    if min_sep > 0.3:
        print(f"    PASS")
        return []
    else:
        msg = f"Port-approach min sep {min_sep:.3f} nm <= 0.3 nm"
        print(f"    FAIL  {msg}")
        return [msg]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run():
    print()
    print("=" * 65)
    print("Traffic & separation — headless test suite")
    print("=" * 65)

    all_errors = []

    errors_24h = test_24h_run()
    all_errors.extend(errors_24h)

    all_errors.extend(test_shallow_angle())
    all_errors.extend(test_port_approach())

    print()
    print("=" * 65)
    if all_errors:
        print(f"FAILURES ({len(all_errors)}):")
        for e in all_errors:
            print(f"  FAIL: {e}")
        print("=" * 65)
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
        print("=" * 65)
    print()


if __name__ == "__main__":
    run()
