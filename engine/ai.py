"""AI vessel decisions: random emergencies, mission status and captain logic.

Pure Python, no Pygame.  Moved out of main.py unchanged in behaviour; main.py
calls these through their former underscore names.  Logging goes through an
event-log object (see engine/events.py).  random is the module-level RNG the
game seeds, so moving the code leaves every random draw where it was.
"""

import random

from config import (MOB_SEARCH_DURATION_S, TRAWL_DURATION_S,
                    TRAWL_WANDER_INTERVAL_S, TRAWL_SPEED_KN,
                    SAIL_ANCHOR_DURATION_S, PERSONALITY_CAUTIOUS_SPEED,
                    PERSONALITY_LEISURE_SPEED)
from .events import EVENT_MAYDAY, EVENT_MEDICAL, sim_time_str


def trigger_random_event(vessel, world, environment, event_log=None) -> None:
    """Trigger one random emergency event on an underway vessel.

    Three types (equal probability among eligible events):
      0 — Engine failure (powered vessels only; sailboats are ineligible)
      1 — Medical emergency (divert to nearest port)
      2 — Man overboard (stop, turn 180°, slow search for MOB_SEARCH_DURATION_S)
    """
    t = sim_time_str(environment)

    # Sailboats have no engine — they can only get medical or MOB.
    eligible = [1, 2] if vessel.fuel is None else [0, 1, 2]
    event_type = random.choice(eligible)

    if event_type == 0:  # Engine failure
        vessel.status = "adrift"
        vessel.engine_failure = True
        vessel.distress = True
        if event_log is not None:
            event_log.add(t, f"ENGINE FAILURE — {vessel.name}", EVENT_MAYDAY)

    elif event_type == 1:  # Medical emergency — head to nearest port
        nearest = min(world.ports, key=lambda p: vessel.distance_to(p.position))
        vessel.destination = nearest.position
        vessel.player_commanded = True
        vessel.command_reason = "medical"
        if event_log is not None:
            event_log.add(t, f"MEDICAL EMERGENCY — {vessel.name} → {nearest.name}",
                          EVENT_MEDICAL)

    else:  # Man overboard
        vessel.mob_position = vessel.position
        vessel.mob_timer = MOB_SEARCH_DURATION_S
        vessel.target_speed = 0.0
        vessel.heading = (vessel.heading + 180.0) % 360.0
        if event_log is not None:
            event_log.add(t, f"MAN OVERBOARD — {vessel.name}", EVENT_MAYDAY)


# ---------------------------------------------------------------------------
# Mission helpers
# ---------------------------------------------------------------------------

def set_port_mission_status(vessel) -> None:
    """Set mission_status when vessel enters port, based on mission_type."""
    mt = vessel.mission_type
    if mt == "cargo_run":
        # Alternate LOADING / UNLOADING each port visit.
        vessel.mission_status = "LOADING" if vessel.port_visit_count % 2 == 1 else "UNLOADING"
    elif mt == "ferry_run":
        vessel.mission_status = "BOARDING"
    elif mt == "fishing_trip":
        vessel.mission_status = "UNLOADING CATCH"
    elif mt == "sailing_cruise":
        vessel.mission_status = "AT ANCHOR"
    elif mt == "tug_duty":
        vessel.mission_status = "STANDBY"
    elif mt == "patrol":
        vessel.mission_status = "ON STATION"


def set_underway_mission_status(vessel) -> None:
    """Set mission_status when vessel departs port or resumes open-sea navigation."""
    mt = vessel.mission_type
    if mt == "cargo_run":
        vessel.mission_status = "UNDERWAY"
    elif mt == "ferry_run":
        vessel.mission_status = "ON SCHEDULE"
    elif mt == "fishing_trip":
        vessel.mission_status = "TRANSIT"
    elif mt == "sailing_cruise":
        vessel.mission_status = "SAILING"
    elif mt == "tug_duty":
        vessel.mission_status = "ESCORTING"
    elif mt == "patrol":
        vessel.mission_status = "PATROLLING"


def start_waypoint_pause(vessel) -> None:
    """Start a trawling or anchoring pause when a mission vessel reaches an open-sea WP."""
    mt = vessel.mission_type
    if mt == "fishing_trip":
        vessel.trawling_timer         = TRAWL_DURATION_S
        vessel.trawling_heading_timer = TRAWL_WANDER_INTERVAL_S
        vessel.mission_status         = "TRAWLING"
        vessel.target_speed           = TRAWL_SPEED_KN
    elif mt == "sailing_cruise":
        vessel.trawling_timer = SAIL_ANCHOR_DURATION_S
        vessel.mission_status = "ANCHORED"
        vessel.target_speed   = 0.0


# VIP charter commentary — shown in the captain's log, cycling every 600 sim-s.
VIP_MESSAGES = [
    "Guests enjoying the crossing",
    "Favorable winds — making good progress",
    "Guests requesting refreshments",
    "Perfect sailing conditions",
]


def apply_smart_decisions(vessel, world, environment, sim_time: str, state: dict) -> None:
    """Apply intelligent speed adjustments and log reasoning to captain_log.

    Called each sim step.  state is a per-vessel mutable dict that persists
    across calls; boolean flags prevent duplicate log entries.

    Priority order (highest first):
      A  Weather awareness — fog/low-vis speed reduction
      B  Fuel efficiency   — cargo/tanker economy mode (skipped while A active)
      C  Traffic awareness — log collision-avoidance transitions
      D  Port congestion   — slow on approach to a busy berth
      E  Scenic stops      — SY Windward / SY Blue Horizon anchor/depart log
      F  Wind seeking      — sailboat tack-log when heading near no-go zone
      G  VIP commentary    — periodic log messages for SY Blue Horizon guests
    """
    # Only apply to actively navigating vessels not under special control.
    if vessel.status not in ("underway", "avoiding"):
        return
    if vessel.player_commanded or vessel.distress or vessel.engine_failure:
        return
    if vessel.mob_timer > 0:
        return

    # (E) Scenic stops — detect anchor/depart transitions for leisure yachts.
    # Must run BEFORE the trawling_timer early-return so we catch the step when
    # the vessel first enters or leaves its anchor pause.
    if vessel.vessel_type == "sailboat" and vessel.name in ("SY Blue Horizon", "SY Windward"):
        _was_anch = state.get("anchored", False)
        _is_anch = (vessel.trawling_timer > 0
                    and getattr(vessel, "mission_status", "") == "ANCHORED")
        if _is_anch and not _was_anch:
            state["anchored"] = True
            vessel.log_decision(sim_time, "Dropping anchor — scenic stop")
        elif not _is_anch and _was_anch:
            state["anchored"] = False
            vessel.log_decision(sim_time, "Weighing anchor — continuing cruise")

    # Speed/routing decisions skip vessels on anchor pause or MOB search.
    if vessel.trawling_timer > 0:
        return

    vis = environment.visibility

    # (A) Weather awareness — reduce to 60 % max in low vis, restore at 200 m.
    if vis < 150.0 and not state.get("low_vis"):
        state["low_vis"] = True
        vessel.target_speed = vessel.max_speed * 0.6
        vessel.log_decision(sim_time, f"Reducing speed — low visibility ({vis:.0f}m)")
    elif vis >= 200.0 and state.get("low_vis"):
        state["low_vis"] = False
        vessel.target_speed = vessel.max_speed
        vessel.log_decision(sim_time, "Visibility clear — resuming cruise speed")

    # (B) Fuel efficiency — cargo/tanker only; skip while low-vis override is active.
    # Always reapply speed so recovery from (A) doesn't leave the wrong rate.
    if vessel.vessel_type in ("cargo", "tanker") and not state.get("low_vis"):
        next_port = None
        if vessel.route:
            for offset in range(len(vessel.route)):
                wp = vessel.route[(vessel.route_index + offset) % len(vessel.route)]
                for port in world.ports:
                    if abs(wp[0] - port.position[0]) < 2 and abs(wp[1] - port.position[1]) < 2:
                        next_port = port
                        break
                if next_port:
                    break
        if next_port is not None:
            dist = vessel.distance_to(next_port.position)
            if dist > 200.0:
                if not state.get("economy"):
                    state["economy"] = True
                    state["near_port"] = False
                    vessel.log_decision(sim_time, "Long passage — fuel economy mode")
                vessel.target_speed = vessel.max_speed * 0.75
            elif dist < 50.0:
                if not state.get("near_port"):
                    state["near_port"] = True
                    state["economy"] = False
                    vessel.log_decision(sim_time, "Approaching port — increasing speed")
                vessel.target_speed = vessel.max_speed * 0.9
            else:
                state["economy"] = False
                state["near_port"] = False

    # (C) Traffic awareness — log when collision avoidance activates or clears.
    is_avoiding = vessel.status == "avoiding"
    if is_avoiding and not state.get("was_avoiding"):
        nearest_name = "unknown vessel"
        nearest_dist = float("inf")
        for other in world.vessels:
            if other is vessel:
                continue
            d = vessel.distance_to(other.position)
            if d < nearest_dist:
                nearest_dist = d
                nearest_name = other.name
        vessel.log_decision(
            sim_time, f"Altering course — vessel {nearest_name} on collision bearing"
        )
        state["was_avoiding"] = True
    elif not is_avoiding and state.get("was_avoiding"):
        vessel.log_decision(sim_time, "Course resumed — traffic clear")
        state["was_avoiding"] = False

    # (D) Port congestion — slow to 30 % max on approach to a busy port.
    if vessel.status == "underway" and vessel.route:
        wp = vessel.route[vessel.route_index]
        dest_port = None
        for port in world.ports:
            if abs(wp[0] - port.position[0]) < 2 and abs(wp[1] - port.position[1]) < 2:
                dest_port = port
                break
        if dest_port is not None:
            dist_to_port = vessel.distance_to(dest_port.position)
            docked_count = sum(
                1 for v in world.vessels if v._docked_port_name == dest_port.name
            )
            if dist_to_port < 60.0 and docked_count >= 2 and not state.get("congested"):
                state["congested"] = True
                vessel.target_speed = max(2.0, vessel.max_speed * 0.3)
                vessel.log_decision(sim_time, "Port congested — reducing approach speed")
            elif state.get("congested") and (dist_to_port >= 60.0 or docked_count < 2):
                state["congested"] = False
                vessel.log_decision(sim_time, "Port clear — proceeding to berth")
            if state.get("congested"):
                vessel.target_speed = max(2.0, vessel.max_speed * 0.3)
        elif state.get("congested"):
            state["congested"] = False

    # ── Yacht-specific underway behaviors ─────────────────────────────────────
    if vessel.vessel_type == "sailboat":
        # (F) Wind seeking — check every 300 sim-s; nudge toward beam reach when
        # within 30° of the no-go zone boundary.
        state["wind_ticks"] = state.get("wind_ticks", 0) + 1
        if state["wind_ticks"] >= 300:
            state["wind_ticks"] = 0
            wind_ang = abs(vessel._wind_angle_to_heading(environment))
            if wind_ang < 30.0:
                vessel.log_decision(sim_time, "Tacking — seeking better wind angle")
                # 3° nudge toward the nearer beam-reach heading.
                opt1 = (environment.wind_direction + 90.0) % 360.0
                opt2 = (environment.wind_direction - 90.0) % 360.0
                d1 = abs(vessel.heading - opt1); d1 = min(d1, 360.0 - d1)
                d2 = abs(vessel.heading - opt2); d2 = min(d2, 360.0 - d2)
                best = opt1 if d1 <= d2 else opt2
                delta = best - vessel.heading
                if delta > 180.0:
                    delta -= 360.0
                elif delta < -180.0:
                    delta += 360.0
                vessel.heading = (vessel.heading + max(-3.0, min(3.0, delta))) % 360.0

        # (G) VIP commentary — SY Blue Horizon, one rotating message per 600 sim-s.
        if vessel.name == "SY Blue Horizon":
            state["vip_ticks"] = state.get("vip_ticks", 0) + 1
            if state["vip_ticks"] >= 600:
                state["vip_ticks"] = 0
                idx = state.get("vip_msg_idx", 0)
                vessel.log_decision(sim_time, VIP_MESSAGES[idx])
                state["vip_msg_idx"] = (idx + 1) % len(VIP_MESSAGES)

    # (H) Personality-driven cruise-speed baseline — applied only when no
    # higher-priority override (fog, fuel economy, port congestion) is active.
    # Cautious captains ease off the throttle; aggressive ones always push hard.
    _no_override = (not state.get("low_vis") and not state.get("economy")
                    and not state.get("near_port") and not state.get("congested"))
    if _no_override:
        _pers = getattr(vessel, "personality", "efficient")
        if _pers == "cautious":
            vessel.target_speed = vessel.max_speed * PERSONALITY_CAUTIOUS_SPEED
        elif _pers == "aggressive":
            vessel.target_speed = vessel.max_speed  # full rated speed at all times
        elif _pers == "leisure":
            vessel.target_speed = vessel.max_speed * PERSONALITY_LEISURE_SPEED
        # "efficient" falls through — the default max_speed is already appropriate

    # (I) Memory: warn when approaching a previously grounded position.
    _gpos_list = getattr(vessel, "memory", {}).get("grounded_positions", [])
    if _gpos_list:
        _near_gnd = any(vessel.distance_to(gp) < 80.0 for gp in _gpos_list)
        if _near_gnd and not state.get("warned_grounding"):
            state["warned_grounding"] = True
            vessel.log_decision(sim_time, "Caution — approaching previously grounded area")
        elif not _near_gnd:
            state["warned_grounding"] = False
