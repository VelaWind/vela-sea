"""Headless test harness to validate scaled timestep and vessel movement.

This script does not initialize Pygame; it reproduces the same timing and
update logic from `main.py` but runs in the terminal and prints vessel
positions so we can tune `TIME_COMPRESSION` without opening a window.
"""
import time
import sys
from pathlib import Path

# Ensure project root is on sys.path so local packages (engine, data, etc.) import correctly
PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.world import World
from engine.ship import Vessel
from engine.environment import Environment
from data.world_data import populate_world
from config import SIM_TIMESTEP, TIME_COMPRESSION


def create_test_world():
    world = World()
    populate_world(world)

    cargo = Vessel(
        name="MV Tidewater",
        vessel_type="cargo",
        position=(120.0, 300.0),
        heading=45.0,
        target_speed=8.0,
        current_speed=8.0,
        max_speed=12.0,
        acceleration=2.0,
        turn_rate=10.0,
        length_m=150.0,
        beam_m=25.0,
        draft_m=8.0,
        fuel=80.0,
        fuel_capacity=100.0,
        fuel_consumption_rate=2.5,
        destination=(648.0, 460.0),
    )
    world.add_vessel(cargo)

    ferry = Vessel(
        name="MS Coastal Express",
        vessel_type="ferry",
        position=(105.0, 295.0),
        heading=45.0,
        target_speed=10.0,
        current_speed=10.0,
        max_speed=14.0,
        acceleration=1.5,
        turn_rate=8.0,
        length_m=80.0,
        beam_m=15.0,
        draft_m=4.0,
        fuel=60.0,
        fuel_capacity=80.0,
        fuel_consumption_rate=2.0,
        destination=(648.0, 460.0),
    )
    world.add_vessel(ferry)

    sailboat = Vessel(
        name="SY Windward",
        vessel_type="sailboat",
        position=(350.0, 400.0),
        heading=0.0,
        target_speed=6.0,
        current_speed=6.0,
        max_speed=10.0,
        acceleration=1.0,
        turn_rate=8.0,
        length_m=35.0,
        beam_m=7.0,
        draft_m=2.5,
        fuel=None,
        fuel_capacity=None,
        fuel_consumption_rate=0.0,
        destination=(512.0, 654.0),
    )
    world.add_vessel(sailboat)

    return world


def run(duration_seconds: int = 10):
    world = create_test_world()
    env = Environment()

    start = time.time()
    last_print = start
    now = start
    accumulator = 0.0

    print(f"TIME_COMPRESSION={TIME_COMPRESSION}, SIM_TIMESTEP={SIM_TIMESTEP}")
    print("Running headless simulation for %d seconds..." % duration_seconds)

    while now - start < duration_seconds:
        t0 = time.time()
        time.sleep(0.05)
        t1 = time.time()
        real_dt = t1 - t0

        sim_speed = env.time_speed_multiplier
        scaled_dt = real_dt * sim_speed * TIME_COMPRESSION

        if scaled_dt <= 0:
            now = time.time()
            continue

        accumulator += scaled_dt

        while accumulator >= SIM_TIMESTEP:
            env.update(SIM_TIMESTEP)
            for v in world.vessels:
                if v.destination and v.status == "underway":
                    tb = v.bearing_to(v.destination)
                    v.turn_toward(tb, SIM_TIMESTEP)
                v.update_speed(SIM_TIMESTEP)
                v.move(SIM_TIMESTEP)
                # arrival latching
                if v.destination and v.at_destination(v.destination):
                    v.current_speed = 0.0
                    v.status = "docked"
                    v.destination = None
            accumulator -= SIM_TIMESTEP

        now = time.time()
        if now - last_print >= 1.0:
            last_print = now
            print(f"t={now-start:.1f}s")
            for v in world.vessels:
                print(f"  {v.name}: pos={v.position}, speed={v.current_speed:.2f}, status={v.status}")


if __name__ == '__main__':
    run(10)
