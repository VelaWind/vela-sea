"""Per-step navigation rules shared by the game loop, the chart and the tests.

Pure Python, no Pygame (see CLAUDE.md layering rule), so headless tests and
the verification scripts import these exact functions instead of keeping
hand-copied versions that could drift away from what the game runs.

    cog_direction(vessel, environment)        course and speed over ground
    steer_ai_vessel(vessel, dt)               one AI steering step
    below_safe_depth(vessel, world, tide)     the grounding rule
    within_rescue_range(rescuer, casualty)    whether a rescue may complete

Callers: main.py (Game.update_simulation), render/chart.py (COG vector),
tests/test_collision.py, tests/test_traffic.py, tools/verify/verify_cog_math.py.
"""

import math

from config import (
    ARRIVAL_DISTANCE, CURRENT_INFLUENCE, COG_MIN_DRIFT_DEG,
    DRAFT_SAFETY_MARGIN_M,
    APPROACH_SLOWDOWN_RADIUS_FACTOR, APPROACH_SPEED_FRACTION,
    APPROACH_MIN_SPEED_KN, RESCUE_COMPLETE_RANGE_WU,
)


def cog_direction(vessel, environment):
    """Return (cog_angle_rad, cog_speed_kn) when the vessel's actual track over
    ground diverges meaningfully from its heading, otherwise None.

    Mirrors the physics in ship.py move(): heading vector + current set-and-
    drift + wind drift.  Read-only.  The chart draws the result as the COG
    vector; tools/verify/verify_cog_math.py checks it against move().
    """
    if environment is None or vessel.current_speed <= 0:
        return None

    h_rad = math.radians(vessel.heading)
    vx = math.cos(h_rad) * vessel.current_speed
    vy = math.sin(h_rad) * vessel.current_speed

    # Current set-and-drift (toward current_direction)
    c_rad = math.radians(environment.current_direction)
    vx += math.cos(c_rad) * environment.current_speed * CURRENT_INFLUENCE
    vy += math.sin(c_rad) * environment.current_speed * CURRENT_INFLUENCE

    # Wind drift (away from wind_direction, same sign as ship.py)
    push_rad = math.radians((environment.wind_direction + 180.0) % 360.0)
    wind_kn = environment.wind_speed * vessel._windage_factor()
    vx += math.cos(push_rad) * wind_kn
    vy += math.sin(push_rad) * wind_kn

    cog_rad = math.atan2(vy, vx)
    cog_speed = math.hypot(vx, vy)

    # Shortest signed arc between COG and heading; skip if negligible
    drift = (math.degrees(cog_rad) - vessel.heading + 180.0) % 360.0 - 180.0
    if abs(drift) < COG_MIN_DRIFT_DEG:
        return None

    return cog_rad, cog_speed


def steer_ai_vessel(vessel, dt: float) -> None:
    """One steering step for an AI vessel in normal navigation.

    - "avoiding": turn toward the collision-avoidance heading.
    - "underway" with a destination: turn toward it, and near it bleed speed
      so the vessel does not overshoot; away from it, restore cruise speed so
      target_speed never stays pinned low after a waypoint pass.
    - anything else: no change.

    The game calls this after its higher-priority branches (man-overboard
    search, trawling and anchoring), which take over steering when active.
    """
    if vessel.status == "avoiding":
        vessel.turn_toward(vessel.avoid_heading, dt)
    elif vessel.destination and vessel.status == "underway":
        target_bearing = vessel.bearing_to(vessel.destination)
        vessel.turn_toward(target_bearing, dt)
        dist_to_dest = vessel.distance_to(vessel.destination)
        if dist_to_dest < ARRIVAL_DISTANCE * APPROACH_SLOWDOWN_RADIUS_FACTOR:
            vessel.target_speed = max(APPROACH_MIN_SPEED_KN,
                                      vessel.current_speed * APPROACH_SPEED_FRACTION)
        elif vessel.target_speed < vessel.max_speed:
            vessel.target_speed = vessel.max_speed


def below_safe_depth(vessel, world, tide_level: float) -> bool:
    """The grounding rule: True when the vessel is outside every port approach
    and the water under it (at this tide) is shallower than its draft plus
    DRAFT_SAFETY_MARGIN_M.

    Port approaches are exempt so a vessel berthing in shallow harbour water
    is never flagged.  The game adds its own exceptions on top (the tutorial
    forgives the player) and handles the consequences (distress, SAR, damage).
    """
    if vessel._port_at(vessel.position, world) is not None:
        return False
    depth = world.water_depth_at(vessel.position, tide_level)
    return depth < vessel.draft_m + DRAFT_SAFETY_MARGIN_M


def within_rescue_range(rescuer, casualty) -> bool:
    """True when rescuer is close enough to casualty to complete the rescue.

    The game checks this when a SAR rescuer reaches a waypoint.  Reaching an
    intermediate hop of a multi-hop route is not reaching the casualty, so the
    rescue continues; only an arrival within RESCUE_COMPLETE_RANGE_WU counts.
    """
    return rescuer.distance_to(casualty.position) <= RESCUE_COMPLETE_RANGE_WU
