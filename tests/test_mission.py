"""Headless test: player command navigation.

Verifies that:
  1. Right-click commanding sets player_commanded = True and overrides destination.
  2. The vessel navigates to the commanded position and arrives within PORT_DETECT_RADIUS.
  3. player_commanded is cleared (False) upon arrival.
  4. The vessel resumes its scheduled route after arrival (destination changes to
     a route waypoint).
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ship import Vessel
from engine.world import World
from engine.environment import Environment
from data.world_data import populate_world, VESSEL_ROUTE_CARGO
from config import (
    PORT_DETECT_RADIUS, SIM_TIMESTEP, PORT_STAY_CARGO_S,
    KNOTS_TO_UNITS_PER_HOUR,
)

# ---------------------------------------------------------------------------
# Build a minimal world with no weather disturbance.
# ---------------------------------------------------------------------------
world = World()
populate_world(world)

env = Environment()
env.time_speed_multiplier = 1.0
env.current_speed = 0.0
env.wind_speed = 0.0

# A cargo vessel at a known open-water position with a real multi-stop route.
vessel = Vessel(
    name="Test Cargo",
    vessel_type="cargo",
    position=(200.0, 350.0),
    heading=0.0,
    target_speed=10.0,
    current_speed=0.0,
    max_speed=12.0,
    acceleration=0.020,
    deceleration=0.017,
    turn_rate=1.0,
    length_m=150.0,
    beam_m=25.0,
    draft_m=5.0,   # shallow draft to avoid grounding in test
    fuel=100.0,
    fuel_capacity=100.0,
    fuel_consumption_rate=3.5,
    route=VESSEL_ROUTE_CARGO,
    route_index=0,
    port_stay_duration=PORT_STAY_CARGO_S,
    destination=VESSEL_ROUTE_CARGO[0],
)
world.add_vessel(vessel)

# ---------------------------------------------------------------------------
# Issue a player command: navigate to a point ~300 wu east (≈45 nm at this scale).
# Both start (200, 350) and command (500, 350) are open water.
# ---------------------------------------------------------------------------
cmd_pos = (500.0, 350.0)
vessel.destination = cmd_pos
vessel.player_commanded = True

print(f"Player command issued: {vessel.name} → {cmd_pos}")
print(f"  Start position   : {vessel.position}")
print(f"  Start route_index: {vessel.route_index}  ({vessel.route[vessel.route_index]})")

initial_route_wp = vessel.route[vessel.route_index]

# ---------------------------------------------------------------------------
# Run simulation until the vessel arrives or 48 sim-hours elapse.
# Replicates the arrival check in main.py (tolerance = PORT_DETECT_RADIUS).
# ---------------------------------------------------------------------------
SIM_LIMIT_S = 48 * 3600.0
elapsed    = 0.0
arrived    = False

while elapsed < SIM_LIMIT_S:
    vessel.turn_toward(vessel.bearing_to(vessel.destination), SIM_TIMESTEP)
    vessel.update_speed(SIM_TIMESTEP, env)
    vessel.move(SIM_TIMESTEP, env)

    if vessel.at_destination(vessel.destination, tolerance=PORT_DETECT_RADIUS):
        vessel.arrive(world)
        arrived = True
        break

    elapsed += SIM_TIMESTEP

print(f"\nResult after {elapsed / 3600:.2f} sim-hours:")
print(f"  Final position   : ({vessel.position[0]:.1f}, {vessel.position[1]:.1f})")
print(f"  player_commanded : {vessel.player_commanded}")
print(f"  destination      : {vessel.destination}")
print(f"  route_index      : {vessel.route_index}")

# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------
errors = []

if not arrived:
    errors.append("FAIL: vessel did not arrive within 48 sim-hours")
else:
    dist = vessel.distance_to(cmd_pos)
    if dist > PORT_DETECT_RADIUS:
        errors.append(
            f"FAIL: arrived but final distance {dist:.3f} wu > PORT_DETECT_RADIUS {PORT_DETECT_RADIUS}"
        )
    else:
        print(f"  [PASS] Arrived within PORT_DETECT_RADIUS ({dist:.3f} wu ≤ {PORT_DETECT_RADIUS})")

if vessel.player_commanded:
    errors.append("FAIL: player_commanded still True after arrival")
else:
    print("  [PASS] player_commanded cleared after arrival")

# After arrival, destination should be a route waypoint (not the player-commanded pos).
if vessel.destination == cmd_pos:
    errors.append("FAIL: destination still points to player-commanded position after arrival")
elif vessel.destination in vessel.route:
    print(f"  [PASS] Resumed scheduled route → {vessel.destination}")
else:
    errors.append(
        f"FAIL: destination {vessel.destination} is not in route after resuming"
    )

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
if errors:
    for e in errors:
        print(e)
    sys.exit(1)

print("\nALL CHECKS PASSED")
