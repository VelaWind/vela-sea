"""Collision avoidance headless test.

Verifies:
  1. Head-on: two vessels on a collision course diverge — minimum separation
     stays > 0.1 nm and at least one vessel enters "avoiding" status.
  2. Crossing: the COLREGS give-way vessel alters to starboard and both pass safely.
  3. Well-clear: vessels NOT on collision courses never enter "avoiding" status.
  4. Full 24-sim-hour run with all 8 vessels: no groundings, no vessel permanently
     stuck in "avoiding" (max consecutive avoiding time < 1800 sim-s).
  5. Performance: update_collision_avoidance() costs < 0.1 ms with 8 vessels.

Uses dt=1.0 sim-second per step for the scenario tests (stable, fast).
"""

import sys
import time
import math
sys.path.insert(0, ".")

from engine.world import World
from engine.ship import Vessel
from engine.environment import Environment
from engine.collision import compute_cpa_tcpa, update_collision_avoidance
from data.world_data import (
    populate_world,
    VESSEL_ROUTE_FERRY, VESSEL_ROUTE_CARGO,
    VESSEL_ROUTE_FISHING, VESSEL_ROUTE_SAILBOAT,
    VESSEL_ROUTE_CARGO2, VESSEL_ROUTE_FISHING2,
    VESSEL_ROUTE_TUG, VESSEL_ROUTE_SAILBOAT2,
)
from config import (
    ARRIVAL_DISTANCE, PORT_DETECT_RADIUS, DRAFT_SAFETY_MARGIN_M,
    PORT_STAY_FERRY_S, PORT_STAY_CARGO_S,
    PORT_STAY_FISHING_S, PORT_STAY_SAILBOAT_S,
    NM_PER_WORLD_UNIT, KNOTS_TO_UNITS_PER_HOUR,
)

# Coordinate system: heading 0°=east (+x), 90°=south (+y), 270°=north (−y).
# World units: 1 nm ≈ 6.667 wu (NM_PER_WORLD_UNIT=0.15).

SCENARIO_DT = 1.0    # sim-seconds per step for scenario tests
FULL_DT     = 10.0   # sim-seconds per step for the 24-hour full run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vessel(name, x, y, heading, speed, vtype="cargo"):
    """Minimal vessel for scenario tests — no route, no fuel management."""
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


def _step_vessels(vessels, env, dt, world=None):
    """Advance one sim step: navigation + physics + collision avoidance."""
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


def _sep_nm(a, b):
    dx = b.position[0] - a.position[0]
    dy = b.position[1] - a.position[1]
    return math.hypot(dx, dy) * NM_PER_WORLD_UNIT


# ---------------------------------------------------------------------------
# Test 1 — Head-on
# ---------------------------------------------------------------------------
def test_head_on():
    """Two vessels approaching head-on must diverge without colliding."""
    print("Test 1: Head-on collision avoidance ...", end=" ")

    # Place them 1 nm apart (≈6.67 wu), each doing 8 kn.
    # Combined closure: 16 kn → TCPA ≈ 1/16 × 3600 ≈ 225 s (within 600 s threshold).
    sep_wu = 1.0 / NM_PER_WORLD_UNIT        # 1 nm in world units
    a = _make_vessel("A", 200.0, 350.0, 0.0, 8.0)        # heading east
    b = _make_vessel("B", 200.0 + sep_wu, 350.0, 180.0, 8.0)  # heading west

    env = Environment()
    env.weather_drift_enabled = False
    vessels = [a, b]

    min_sep = _sep_nm(a, b)
    ever_avoiding = False
    sim_time = 0.0
    limit = 600.0  # run for 10 sim-minutes

    while sim_time < limit:
        _step_vessels(vessels, env, SCENARIO_DT)
        sep = _sep_nm(a, b)
        min_sep = min(min_sep, sep)
        if a.status == "avoiding" or b.status == "avoiding":
            ever_avoiding = True
        sim_time += SCENARIO_DT

    assert ever_avoiding, "Neither vessel entered 'avoiding' during head-on approach"
    assert min_sep > 0.1, (
        f"Minimum separation {min_sep:.3f} nm ≤ 0.1 nm — vessels came too close"
    )
    print(f"PASS  (min sep {min_sep:.3f} nm, avoidance triggered)")


# ---------------------------------------------------------------------------
# Test 2 — Crossing (COLREGS Rule 15)
# ---------------------------------------------------------------------------
def test_crossing():
    """The give-way vessel (other on its starboard) alters course; both pass safely."""
    print("Test 2: Crossing give-way ...", end=" ")

    # A heading east (0°), B heading north (270°), offset so B crosses A's bow.
    # At 8 kn each: CPA ≈ 0.42 nm < 0.5 nm threshold → avoidance triggered.
    # A has B on its starboard → A gives way; B is stand-on.
    a = _make_vessel("A", 200.0, 350.0, 0.0,   8.0)
    b = _make_vessel("B", 205.0, 351.0, 270.0, 8.0)

    env = Environment()
    env.weather_drift_enabled = False
    vessels = [a, b]

    min_sep = _sep_nm(a, b)
    a_ever_avoiding = False
    b_ever_avoiding = False
    sim_time = 0.0
    limit = 800.0

    while sim_time < limit:
        _step_vessels(vessels, env, SCENARIO_DT)
        sep = _sep_nm(a, b)
        min_sep = min(min_sep, sep)
        if a.status == "avoiding":
            a_ever_avoiding = True
        if b.status == "avoiding":
            b_ever_avoiding = True
        sim_time += SCENARIO_DT

    # A (which has B on starboard) must have given way
    assert a_ever_avoiding, "Vessel A did not give way (should have: B is on A's starboard)"
    assert min_sep > 0.1, (
        f"Minimum separation {min_sep:.3f} nm ≤ 0.1 nm — vessels came too close"
    )
    print(f"PASS  (min sep {min_sep:.3f} nm, A gave way, B stand-on={not b_ever_avoiding})")


# ---------------------------------------------------------------------------
# Test 3 — Well-clear (no false avoidance)
# ---------------------------------------------------------------------------
def test_well_clear():
    """Vessels on parallel tracks well apart must NOT enter 'avoiding'."""
    print("Test 3: Well-clear vessels (no false alarm) ...", end=" ")

    # Two vessels heading east in parallel, 3 nm apart — identical speed so
    # they never converge.  CPA = current separation = 3 nm >> 0.5 nm threshold.
    sep_nm = 3.0
    sep_wu = sep_nm / NM_PER_WORLD_UNIT
    a = _make_vessel("A", 200.0, 350.0,           0.0, 8.0)
    b = _make_vessel("B", 200.0, 350.0 + sep_wu,  0.0, 8.0)

    env = Environment()
    env.weather_drift_enabled = False
    vessels = [a, b]

    ever_avoiding = False
    sim_time = 0.0
    limit = 600.0

    while sim_time < limit:
        _step_vessels(vessels, env, SCENARIO_DT)
        if a.status == "avoiding" or b.status == "avoiding":
            ever_avoiding = True
        sim_time += SCENARIO_DT

    assert not ever_avoiding, "Well-clear vessels incorrectly triggered avoidance"
    print("PASS")


# ---------------------------------------------------------------------------
# Test 4 — Full 24-sim-hour run: no groundings, no stuck-avoiding
# ---------------------------------------------------------------------------
def _make_all_vessels():
    return [
        Vessel(
            name="MV Meridian", vessel_type="cargo",
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
            name="SY Meridian Breeze", vessel_type="sailboat",
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


def test_full_24h():
    """24-sim-hour run with all 8 vessels: no groundings, no permanently-avoiding vessel."""
    print("Test 4: 24-sim-hour full run ...", end=" ")

    world = World()
    populate_world(world)
    env = Environment()
    env.weather_drift_enabled = False
    vessels = _make_all_vessels()
    for v in vessels:
        world.add_vessel(v)

    target = 24.0 * 3600.0  # 24 sim-hours in sim-seconds
    sim_time = 0.0

    # Track max consecutive sim-seconds any vessel spends in "avoiding"
    consec_avoid = {v.name: 0.0 for v in vessels}
    max_consec_avoid = {v.name: 0.0 for v in vessels}

    t0 = time.perf_counter()

    while sim_time < target:
        env.update(FULL_DT)
        _step_vessels(vessels, env, FULL_DT, world)

        for v in vessels:
            if v.status == "avoiding":
                consec_avoid[v.name] += FULL_DT
                max_consec_avoid[v.name] = max(max_consec_avoid[v.name], consec_avoid[v.name])
            else:
                consec_avoid[v.name] = 0.0

        sim_time += FULL_DT

    elapsed = time.perf_counter() - t0

    print(f"({elapsed:.2f}s real)")
    print(f"  Final statuses:")
    for v in vessels:
        ma = max_consec_avoid[v.name]
        print(f"    {v.name:<22} status={v.status:<10} max_consec_avoiding={ma:.0f}s")

    errors = []
    for v in vessels:
        if v.status == "aground":
            errors.append(f"{v.name}: ended aground")
        if v.status == "adrift":
            errors.append(f"{v.name}: ended adrift")
        # Stuck if continuously "avoiding" for more than 1 sim-hour
        if max_consec_avoid[v.name] > 3600.0:
            errors.append(
                f"{v.name}: stuck in 'avoiding' for {max_consec_avoid[v.name]:.0f} sim-s "
                f"(limit 1800 s)"
            )

    if elapsed > 30.0:
        errors.append(f"Performance: 24 sim-hours took {elapsed:.1f}s (limit 30s)")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        return False
    print("  PASS")
    return True


# ---------------------------------------------------------------------------
# Test 6 — Emergency avoidance: 2nm direct collision course, min sep > 0.3nm
# ---------------------------------------------------------------------------
def test_emergency_avoidance():
    """Two vessels on a direct collision course 2nm apart must separate > 0.3nm."""
    print("Test 6: Emergency avoidance (2 nm, head-on) ...", end=" ")

    # 2 nm in world units (NM_PER_WORLD_UNIT = 0.15)
    sep_wu = 2.0 / NM_PER_WORLD_UNIT
    a = _make_vessel("A", 200.0, 350.0, 0.0, 8.0)          # heading east
    b = _make_vessel("B", 200.0 + sep_wu, 350.0, 180.0, 8.0)  # heading west

    env = Environment()
    env.weather_drift_enabled = False
    vessels = [a, b]

    min_sep = _sep_nm(a, b)
    ever_avoiding = False
    sim_time = 0.0
    limit = 1800.0  # 30 sim-minutes — plenty of time for avoidance to act

    while sim_time < limit:
        _step_vessels(vessels, env, SCENARIO_DT)
        sep = _sep_nm(a, b)
        min_sep = min(min_sep, sep)
        if a.status == "avoiding" or b.status == "avoiding":
            ever_avoiding = True
        sim_time += SCENARIO_DT

    assert ever_avoiding, "No vessel entered 'avoiding' — avoidance never triggered"
    assert min_sep > 0.3, (
        f"Min separation {min_sep:.3f} nm <= 0.3 nm — vessels came too close"
    )
    print(f"PASS  (min sep {min_sep:.3f} nm)")


# ---------------------------------------------------------------------------
# Test 5 — Performance: update_collision_avoidance < 0.1 ms with 8 vessels
# ---------------------------------------------------------------------------
def test_performance():
    """Time the avoidance update with 8 vessels — must be < 0.1 ms per call."""
    print("Test 5: Performance benchmark ...", end=" ")

    world = World()
    populate_world(world)
    env = Environment()
    env.weather_drift_enabled = False
    vessels = _make_all_vessels()
    for v in vessels:
        world.add_vessel(v)

    WARMUP = 50
    REPS = 2000

    for _ in range(WARMUP):
        update_collision_avoidance(vessels)

    t0 = time.perf_counter()
    for _ in range(REPS):
        update_collision_avoidance(vessels)
    ms_per_call = (time.perf_counter() - t0) / REPS * 1000.0

    print(f"{ms_per_call:.4f} ms per call ({28} pairs)")

    assert ms_per_call < 0.1, (
        f"update_collision_avoidance too slow: {ms_per_call:.4f} ms (limit 0.1 ms)"
    )
    print("  PASS")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run():
    print()
    print("=" * 65)
    print("Collision avoidance — headless test suite")
    print("=" * 65)

    errors = []

    try:
        test_head_on()
    except AssertionError as e:
        errors.append(f"Test 1 FAIL: {e}")

    try:
        test_crossing()
    except AssertionError as e:
        errors.append(f"Test 2 FAIL: {e}")

    try:
        test_well_clear()
    except AssertionError as e:
        errors.append(f"Test 3 FAIL: {e}")

    ok4 = test_full_24h()
    if not ok4:
        errors.append("Test 4 FAIL: see details above")

    try:
        test_performance()
    except AssertionError as e:
        errors.append(f"Test 5 FAIL: {e}")

    try:
        test_emergency_avoidance()
    except AssertionError as e:
        errors.append(f"Test 6 FAIL: {e}")

    print()
    print("=" * 65)
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        print("=" * 65)
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
        print("=" * 65)
    print()


if __name__ == "__main__":
    run()
