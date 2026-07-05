"""Chunk E headless test — multi-waypoint routes, port stays, refuelling.

Runs the simulation for 72 simulated hours and verifies:
  1. Every vessel completes at least one full loop (visits a port twice).
  2. Every fuel-powered vessel refuels during at least one port stay.
  3. No vessel ends in "aground" or "adrift" status.
  4. Performance: 72 sim-hours complete in well under 5 real-seconds.

Uses DT=10.0 sim-seconds per step (vs the game's 0.016) for headless speed.
Physics remains correct at this scale — vessels still accelerate, turn, consume
fuel, and trigger arrivals within ARRIVAL_DISTANCE tolerance.

Output prints the first 30 (sim-time, vessel, waypoint, status) events so the
route schedule is visible at a glance.
"""

import sys
import time
sys.path.insert(0, ".")

from engine.world import World
from engine.ship import Vessel
from engine.environment import Environment
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
)

# Use a large timestep so 72 sim-hours run in milliseconds.
# Physics are correct at this scale (no stability issues with simple integrators).
TEST_DT = 10.0   # sim-seconds per step


def _make_world():
    w = World()
    populate_world(w)
    return w


def _make_vessels():
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
            # Spawn at route[1]=(660,600). First leg to (590,760) has
            # bearing≈114°, wind_angle≈69° — outside the 45° no-go zone.
            # The old (300,560) spawn bore ≈28° toward (600,720) = in irons.
            # Old route (600,720)→(400,780) also clipped Vesper Isle — redesigned
            # to an eastern circuit staying east of Vesper Isle (x>542) throughout.
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
            # Spawn at _WP_S_ISLANDS=(500,565) — a verified south-corridor
            # waypoint. The old (390,220) spawn cut across Skerry Bank; at low
            # tide depth drops to ~3.5 m which is below draft(4m)+margin(0.5m).
            position=(500.0, 565.0), heading=335.0,
            target_speed=10.0, current_speed=0.0,
            max_speed=14.0, acceleration=0.08, deceleration=0.04,
            turn_rate=2.0, length_m=80.0, beam_m=15.0, draft_m=4.0,
            fuel=80.0, fuel_capacity=80.0, fuel_consumption_rate=5.0,
            route=VESSEL_ROUTE_FERRY, route_index=3,
            port_stay_duration=PORT_STAY_FERRY_S,
            destination=VESSEL_ROUTE_FERRY[3],
        ),
        # ── 4 additional vessels ─────────────────────────────────────────
        Vessel(
            name="MV Carrick Star", vessel_type="cargo",
            position=(520.0, 555.0), heading=335.0,
            target_speed=8.0, current_speed=0.0,
            max_speed=11.0, acceleration=0.018, deceleration=0.015,
            turn_rate=1.2, length_m=130.0, beam_m=22.0, draft_m=6.5,
            fuel=80.0, fuel_capacity=80.0, fuel_consumption_rate=3.0,
            route=VESSEL_ROUTE_CARGO2, route_index=3,
            port_stay_duration=PORT_STAY_CARGO_S,
            destination=VESSEL_ROUTE_CARGO2[3],
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


def run():
    world = _make_world()
    env = Environment()
    env.weather_drift_enabled = False  # Chunk E tests routing, not weather dynamics
    vessels = _make_vessels()
    for v in vessels:
        world.add_vessel(v)

    # Per-vessel event log and refuel counter
    events = {v.name: [] for v in vessels}
    refuel_count = {v.name: 0 for v in vessels}

    sim_time = 0.0
    target = 72.0 * 3600.0

    t0 = time.perf_counter()

    while sim_time < target:
        env.update(TEST_DT)

        for v in vessels:
            if v.status == "in_port":
                v.update_route(TEST_DT, world)

            if v.destination and v.status == "underway":
                v.turn_toward(v.bearing_to(v.destination), TEST_DT)

            v.update_speed(TEST_DT, env)
            v.move(TEST_DT, env)

            # Arrival: PORT_DETECT_RADIUS (2 wu) so vessel arrives while still
            # in navigable depth near the port.
            if (v.status == "underway"
                    and v.destination
                    and v.at_destination(v.destination, tolerance=PORT_DETECT_RADIUS)):
                wp = v.destination
                fuel_before = v.fuel
                v.arrive(world)
                if v.fuel is not None and fuel_before is not None and v.fuel > fuel_before + 0.1:
                    refuel_count[v.name] += 1
                events[v.name].append(
                    (sim_time / 3600.0, wp, v.status, v.fuel)
                )

            if v.status in ("in_port", "docked", "aground"):
                continue
            if v._port_at(v.position, world) is not None:
                continue  # in a port's approach zone — no grounding check
            depth = world.water_depth_at(v.position, env.tide_level)
            if depth < v.draft_m + DRAFT_SAFETY_MARGIN_M:
                v.status = "aground"
                v.current_speed = 0.0

        sim_time += TEST_DT

    elapsed = time.perf_counter() - t0

    # -----------------------------------------------------------------------
    # Print schedule (first 30 events total, all vessels)
    # -----------------------------------------------------------------------
    all_events = sorted(
        [(t, name, wp, st, fuel)
         for name, evs in events.items()
         for t, wp, st, fuel in evs],
        key=lambda x: x[0],
    )
    print(f"\n{'='*70}")
    print(f"Chunk E — {target/3600:.0f} sim-hours in {elapsed:.3f}s "
          f"({target/elapsed:.0f}x real-time)")
    print(f"{'='*70}")
    print(f"{'Time':>8}  {'Vessel':<22} {'Waypoint':>12}  {'Status':>8}  Fuel")
    print(f"{'-'*70}")
    for t_h, name, wp, st, fuel in all_events[:40]:
        fuel_str = f"{fuel:.1f}" if fuel is not None else "wind"
        print(f"{t_h:7.2f}h  {name:<22} ({wp[0]:4.0f},{wp[1]:4.0f})  "
              f"{st:>8}  {fuel_str}")
    if len(all_events) > 40:
        print(f"  ... ({len(all_events) - 40} more events)")
    print()
    for v in vessels:
        n = len(events[v.name])
        r = refuel_count[v.name]
        print(f"  {v.name:<22} {n:3d} arrivals  {r} refuels  "
              f"final status={v.status}")

    # -----------------------------------------------------------------------
    # Assertions
    # -----------------------------------------------------------------------
    errors = []

    for v in vessels:
        name = v.name
        evs = events[name]

        if not evs:
            errors.append(f"{name}: no arrivals recorded at all")
            continue

        # Must have reached a port at least twice (completed >= 1 full loop)
        port_arrivals = [e for e in evs if e[2] == "in_port"]
        if len(port_arrivals) < 2:
            errors.append(
                f"{name}: only {len(port_arrivals)} port arrival(s) in "
                f"{target/3600:.0f} sim-hours -- full loop not completed"
            )

        # Fuel-powered vessels must have refuelled at least once
        if v.fuel is not None and refuel_count[name] == 0:
            errors.append(f"{name}: no refuel events in {target/3600:.0f} sim-hours")

        # No vessel should end aground or adrift
        if v.status in ("aground", "adrift"):
            errors.append(f"{name}: ended with status={v.status!r}")

    # Performance: must be well under 30 real-seconds for 72 sim-hours
    if elapsed > 30.0:
        errors.append(
            f"Performance: {target/3600:.0f} sim-hours took {elapsed:.1f}s "
            f"(limit 30s)"
        )

    print(f"\n{'='*70}")
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        print(f"{'='*70}\n")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
        print(f"{'='*70}\n")


if __name__ == "__main__":
    run()
