"""Main entry point: sets up the Pygame window and runs the fixed-timestep loop.

This is the glue that ties together:
1. Input handling (keyboard, mouse)
2. Simulation updates (via the engine)
3. Rendering (the chart and panels)

The loop runs at a stable frame rate, but the simulation advances in fixed
timesteps, so physics behaves consistently regardless of FPS.
"""

import asyncio
import math
import os
import pygame
import random
import sys
import time
import traceback
from typing import Optional

from config import (
    WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT, WINDOW_SCALE_FACTOR, WINDOW_TITLE,
    TARGET_FPS, ZOOM_MIN, ZOOM_MAX, ZOOM_SCROLL_SPEED,
    PAN_SPEED, SIM_TIMESTEP, DEFAULT_VIEW_SPAN_WU, CAMERA_START_CENTER,
    MAX_SIM_STEPS_PER_FRAME,
)
from config import ARRIVAL_DISTANCE, PORT_DETECT_RADIUS, SHIP_SELECT_RADIUS
from config import TIME_COMPRESSION
from config import DRAFT_SAFETY_MARGIN_M
from config import SAR_DISPATCH_RANGE_NM, KNOTS_TO_UNITS_PER_HOUR, FUEL_EMERGENCY_REFUEL_FRACTION
from config import RANDOM_EVENT_PROBABILITY, MOB_SEARCH_DURATION_S, MOB_SEARCH_SPEED_KN
from config import PLAYER_THROTTLE_STEP, PLAYER_TURN_RATE, PLAYER_FOLLOW_CAM, THROTTLE_FLASH_MS
from config import HULL_REPAIR_COST_PER_POINT
from config import (ZONE_FINE_NO_ENTRY, ZONE_FINE_SPEED, ZONE_FINE_INTERVAL_S,
                    GROUNDING_HULL_DAMAGE, STORM_WAVE_THRESHOLD,
                    STORM_HULL_DAMAGE_RATE, STORM_MAX_SPEED_KN,
                    HAZMAT_FINE_MULT, CHARTER_MAX_SPEED_KN)
from config import (
    PORT_STAY_CARGO_LOAD_S, PORT_STAY_FERRY_BOARD_S, PORT_STAY_FISHING_UNLOAD_S,
    PORT_STAY_SAIL_ANCHOR_S, PORT_STAY_TUG_S,
    TRAWL_DURATION_S, TRAWL_WANDER_INTERVAL_S, TRAWL_SPEED_KN, SAIL_ANCHOR_DURATION_S,
)
from render.camera import Camera
from render.chart import Chart
from render.fonts import safe_sysfont, ui_px
from engine.world import World
from engine.ship import Vessel
from engine.environment import Environment
from config import SAVE_FILEPATH, PLAYER_DOCKING_MAX_SPEED_KN, PORT_CLICK_RADIUS_PX
from config import FOG_LOW_VIS_THRESHOLD_M
from config import REP_TIER_3, LUCKY_ESCAPE_HULL_MIN
from config import (HULL_CRITICAL_THRESHOLD, HULL_DAMAGE_FLASH_MS,
                    HULL_DAMAGE_FLASH_COLOR, HULL_DAMAGE_FLASH_MAX_ALPHA)
from config import (COLOR_WARNING, FONT_UI_NAME, FONT_SIZE_TITLE, FONT_SIZE_SECTION,
                    FONT_DATA_NAME, FONT_SIZE_SMALL)
from render.panels import VesselInfoPanel, TechnicalSystemsPanel, SettingsPanel, EventLog, FleetStatusPanel, MissionPanel, PlayerHUDPanel, CareerPanel, GameOverScreen, TitleScreen, DockingMenuPanel, MinimapPanel, TutorialOverlayPanel, RewardBannerPanel, SettingsScreen, PauseMenu
from config import COLOR_OBJECTIVE, BANNER_PROMOTE_COLOR, BANNER_DURATION_MS
from config import (FLAVOR_COOLDOWN_S, FLAVOR_PORT_RANGE_WU,
                    FLAVOR_VESSEL_RANGE_WU, FLAVOR_OPEN_WATER_WU)
from config import (TUTORIAL_START_ZOOM, TUTORIAL_CONTRACT_FROM, TUTORIAL_CONTRACT_TO,
                    TUTORIAL_CONTRACT_PAYOUT, TUTORIAL_THROTTLE_SPEED_KN,
                    TUTORIAL_HEADING_TOLERANCE, TUTORIAL_STEPS,
                    TUTORIAL_ROUTE, TUTORIAL_WAYPOINT_RADIUS,
                    TUTORIAL_TRANSIT_TIME_SPEED)
from render.sound import SoundManager
from config import MINIMAP_HEIGHT_PX, MINIMAP_MARGIN_PX
from render.panels import EVENT_COLOR_MAYDAY, EVENT_COLOR_RESCUE, EVENT_COLOR_REFLOAT, EVENT_COLOR_WEATHER, EVENT_COLOR_MEDICAL
from data.world_data import (populate_world,
    VESSEL_ROUTE_FERRY, VESSEL_ROUTE_CARGO,
    VESSEL_ROUTE_FISHING, VESSEL_ROUTE_SAILBOAT,
    VESSEL_ROUTE_CARGO2, VESSEL_ROUTE_FISHING2,
    VESSEL_ROUTE_TUG, VESSEL_ROUTE_SAILBOAT2,
    VESSEL_ROUTE_TANKER, VESSEL_ROUTE_COAST_GUARD,
    VESSEL_ROUTE_THORNWICK, VESSEL_ROUTE_BLUE_HORIZON,
    VESSEL_ROUTE_EASTERN_STAR, VESSEL_ROUTE_NORTH_FISHER, VESSEL_ROUTE_TENDER)
from config import (PORT_STAY_FERRY_S, PORT_STAY_CARGO_S,
                    PORT_STAY_FISHING_S, PORT_STAY_SAILBOAT_S,
                    PORT_STAY_PATROL_S, PORT_STAY_TENDER_S)
from config import (PERSONALITY_CAUTIOUS_SPEED, PERSONALITY_AGGRESSIVE_SPEED,
                    PERSONALITY_LEISURE_SPEED,
                    MOOD_TIRED_AFTER_S, MOOD_CONFIDENT_AFTER_S, MOOD_RESTED_AFTER_S,
                    PARTY_DURATION_MIN_S, PARTY_DURATION_MAX_S, PARTY_TENDER_NAME)
from config import NM_PER_WORLD_UNIT
from config import (IS_WEB, WORLD_WIDTH, WORLD_HEIGHT, WEB_PROFILE,
                    WEB_TARGET_FPS, WEB_FRAME_DT_CLAMP_S,
                    WEB_MAX_SIM_STEPS_PER_FRAME,
                    WEB_FB_MAX_W, WEB_FB_MAX_H, WEB_FB_FALLBACK_W, WEB_FB_FALLBACK_H,
                    WEB_HUD_PERF, WEB_RENDER_SCALE)
from engine.collision import update_collision_avoidance, find_safe_path
from engine.mission import MissionManager
from engine.career import PlayerCareer, JobBoard, save_career, load_career, delete_save
from engine.settings import Settings, DEFAULT_KEYBINDS


# ---------------------------------------------------------------------------
# SAR helpers — module-level so the test suite can import them independently
# ---------------------------------------------------------------------------

def _sim_time_str(environment) -> str:
    """Format environment.time_of_day as HH:MM for event log entries."""
    h = int(environment.time_of_day)
    m = int((environment.time_of_day % 1) * 60)
    return f"{h:02d}:{m:02d}"


def _sar_refloat(grounded, event_log=None, sim_time: str = "") -> None:
    """Refloat a grounded/adrift vessel and release its rescuer (if any).

    Calls vessel.refloat() for the grounded vessel's own state, then
    clears the rescuer's player_commanded flag and restores its schedule.

    Fuel-exhaustion case: when the vessel ran dry (fuel == 0), give it an
    emergency partial refuel so it can motor to the nearest port instead of
    immediately going adrift again the moment the rescuer leaves.
    """
    rescuer = grounded.rescue_vessel
    # Emergency refuel for fuel-exhausted vessels so they can reach a port.
    fuel_rescue = (grounded.fuel is not None
                   and grounded.fuel == 0.0
                   and grounded.fuel_capacity is not None)
    if fuel_rescue:
        grounded.fuel = grounded.fuel_capacity * FUEL_EMERGENCY_REFUEL_FRACTION
    grounded.refloat()
    if rescuer is not None and rescuer.player_commanded:
        rescuer.player_commanded = False
        if rescuer.route:
            rescuer.destination = rescuer.route[rescuer.route_index]
    if event_log is not None:
        msg = (f"RESCUED — {grounded.name} (emergency fuel)"
               if fuel_rescue else f"REFLOATED — {grounded.name}")
        event_log.add(sim_time, msg, EVENT_COLOR_REFLOAT)


def _sar_dispatch(vessels, range_wu: float, event_log=None, sim_time: str = "",
                  player_paths: dict = None, world=None) -> None:
    """Auto-dispatch the nearest eligible vessel to each unrescued distressed vessel.

    Eligibility: underway, not already player_commanded, not already a rescuer.
    Only one rescuer is dispatched per grounded vessel.

    When world is provided, find_safe_path() is used so the rescuer avoids
    islands en-route.  Multi-hop paths are stored in player_paths (keyed by
    id(vessel)) and advanced in the main update loop on each arrival.
    """
    # Build set of vessel IDs already acting as rescuers so we can skip them.
    # Using id() because Vessel is a dataclass with __eq__ and is not hashable.
    active_rescuer_ids = {id(v.rescue_vessel) for v in vessels if v.rescue_vessel is not None}

    for grounded in vessels:
        if not grounded.distress or grounded.rescue_vessel is not None:
            continue
        best, best_d = None, float("inf")
        for v in vessels:
            if v is grounded:
                continue
            if v.status not in ("underway", "avoiding"):
                continue
            if v.player_commanded:
                continue
            if id(v) in active_rescuer_ids:
                continue
            d = v.distance_to(grounded.position)
            if d < best_d and d <= range_wu:
                best, best_d = v, d
        if best is not None:
            if world is not None:
                waypoints = find_safe_path(best.position, grounded.position, world)
            else:
                waypoints = [grounded.position]
            best.destination = waypoints[0]
            best.player_commanded = True
            grounded.rescue_vessel = best
            active_rescuer_ids.add(id(best))
            if player_paths is not None and len(waypoints) > 1:
                player_paths[id(best)] = waypoints[1:]
            if event_log is not None:
                event_log.add(sim_time,
                              f"RESCUE — {best.name} → {grounded.name}",
                              EVENT_COLOR_RESCUE)


def _trigger_random_event(vessel, world, environment, event_log=None) -> None:
    """Trigger one random emergency event on an underway vessel.

    Three types (equal probability among eligible events):
      0 — Engine failure (powered vessels only; sailboats are ineligible)
      1 — Medical emergency (divert to nearest port)
      2 — Man overboard (stop, turn 180°, slow search for MOB_SEARCH_DURATION_S)
    """
    t = _sim_time_str(environment)

    # Sailboats have no engine — they can only get medical or MOB.
    eligible = [1, 2] if vessel.fuel is None else [0, 1, 2]
    event_type = random.choice(eligible)

    if event_type == 0:  # Engine failure
        vessel.status = "adrift"
        vessel.engine_failure = True
        vessel.distress = True
        if event_log is not None:
            event_log.add(t, f"ENGINE FAILURE — {vessel.name}", EVENT_COLOR_MAYDAY)

    elif event_type == 1:  # Medical emergency — head to nearest port
        nearest = min(world.ports, key=lambda p: vessel.distance_to(p.position))
        vessel.destination = nearest.position
        vessel.player_commanded = True
        if event_log is not None:
            event_log.add(t, f"MEDICAL EMERGENCY — {vessel.name} → {nearest.name}",
                          EVENT_COLOR_MEDICAL)

    else:  # Man overboard
        vessel.mob_position = vessel.position
        vessel.mob_timer = MOB_SEARCH_DURATION_S
        vessel.target_speed = 0.0
        vessel.heading = (vessel.heading + 180.0) % 360.0
        if event_log is not None:
            event_log.add(t, f"MAN OVERBOARD — {vessel.name}", EVENT_COLOR_MAYDAY)


# ---------------------------------------------------------------------------
# Mission helpers
# ---------------------------------------------------------------------------

def _set_port_mission_status(vessel) -> None:
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


def _set_underway_mission_status(vessel) -> None:
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


def _start_waypoint_pause(vessel) -> None:
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
_VIP_MESSAGES = [
    "Guests enjoying the crossing",
    "Favorable winds — making good progress",
    "Guests requesting refreshments",
    "Perfect sailing conditions",
]


def _apply_smart_decisions(vessel, world, environment, sim_time: str, state: dict) -> None:
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
                vessel.log_decision(sim_time, _VIP_MESSAGES[idx])
                state["vip_msg_idx"] = (idx + 1) % len(_VIP_MESSAGES)

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


# Known-safe open-water fallback positions — used when all route-relative
# jitter attempts fail to find an 80 wu gap from existing spawns.
_FALLBACK_POSITIONS = [
    (200, 350), (400, 300), (600, 350), (800, 300),
    (200, 500), (400, 500), (600, 500), (800, 500),
    (200, 650), (400, 650), (600, 650), (300, 400),
]


def _spawn_ok(pos, world, draft, existing_positions, sep):
    """Return True when pos passes depth, coast, and separation checks."""
    if world.point_in_island(pos):
        return False
    if world.water_depth_at(pos, 0.0) < draft + 2.0:
        return False
    if world._min_dist_to_coast(pos) < 15.0:
        return False
    if existing_positions and any(
        math.hypot(pos[0] - ep[0], pos[1] - ep[1]) < sep
        for ep in existing_positions
    ):
        return False
    return True


def _random_spawn(route: list, world, draft: float,
                  existing_positions: list = None) -> tuple:
    """Pick a random waypoint as the spawn position so each session looks different.

    Phase 1 — 20 jittered attempts around the chosen waypoint, requiring 80 wu
               separation from every already-spawned vessel.
    Phase 2 — shuffled fallback grid tried when Phase 1 finds nothing.
    Fallback  — bare waypoint (always route-safe) if both phases fail.

    Returns (position, route_index, destination, heading).
    """
    i = random.randrange(len(route))
    dest_i = (i + 1) % len(route)
    pos = route[i]   # ultimate fallback — bare waypoint is always route-verified safe

    # Phase 1: jitter around the chosen waypoint
    for _ in range(20):
        candidate = (route[i][0] + random.uniform(-25, 25),
                     route[i][1] + random.uniform(-25, 25))
        if _spawn_ok(candidate, world, draft, existing_positions, sep=80):
            pos = candidate
            break
    else:
        # Phase 2: try shuffled fallback grid
        fallbacks = list(_FALLBACK_POSITIONS)
        random.shuffle(fallbacks)
        for fb in fallbacks:
            if _spawn_ok(fb, world, draft, existing_positions, sep=80):
                pos = fb
                break

    dest = route[dest_i]
    dx = dest[0] - pos[0]
    dy = dest[1] - pos[1]
    hdg = math.degrees(math.atan2(dy, dx)) % 360
    return pos, dest_i, dest, hdg


class FrameProfiler:
    """Cheap per-phase frame timing for the web build (config.WEB_PROFILE).

    Accumulates elapsed seconds into plain CUMULATIVE float slots — no per-frame
    allocation.  Two consumers read windowed averages off their own baselines:

    - ``maybe_report()`` prints ONE line to stdout every REPORT_S seconds.
      pygbag pipes stdout to the browser console, so this line is how we see
      where WASM time actually goes and prove each perf fix.
    - ``hud_line()`` returns a short bucket string for the on-screen overlay,
      averaged since its previous call (the overlay calls it once per second).

    ``idle`` is frame wall time minus the measured buckets — the time between
    rendered frames: skipped rAF ticks under the 30 fps cap, plus event
    handling and loop overhead.  At the cap, idle ~= 33.3ms - work by design;
    an UNEXPECTEDLY large idle with the cap off would mean pacing, not work.
    Only instantiated when WEB_PROFILE is True, so fully inert on desktop.
    fps counts RENDERED frames only (skip iterations never touch n).

    The console line::

        [WEBPROF] fps=30.0 frame= 33.3ms | sim= 0.40 chart= 2.10 panels= 0.80 flip= 1.20 idle=28.0 ms/f | steps/f=1.00
    """
    REPORT_S = 5.0
    __slots__ = ("n", "sim", "chart", "panels", "flip", "steps",
                 "_rep_t", "_rep_n", "_rep_sim", "_rep_chart", "_rep_panels",
                 "_rep_flip", "_rep_steps",
                 "_hud_t", "_hud_n", "_hud_sim", "_hud_chart", "_hud_panels",
                 "_hud_flip")

    def __init__(self) -> None:
        self.n = 0
        self.sim = self.chart = self.panels = self.flip = 0.0
        self.steps = 0
        t = time.perf_counter()
        self._rep_t = t
        self._rep_n = 0
        self._rep_sim = self._rep_chart = self._rep_panels = self._rep_flip = 0.0
        self._rep_steps = 0
        self._hud_t = t
        self._hud_n = 0
        self._hud_sim = self._hud_chart = self._hud_panels = self._hud_flip = 0.0

    def maybe_report(self) -> None:
        """Print one [WEBPROF] line + rebase once REPORT_S of wall time passed."""
        now = time.perf_counter()
        wall = now - self._rep_t
        dn = self.n - self._rep_n
        if wall < self.REPORT_S or dn == 0:
            return
        work = ((self.sim - self._rep_sim) + (self.chart - self._rep_chart)
                + (self.panels - self._rep_panels) + (self.flip - self._rep_flip))
        fps = dn / wall
        # %-format (not f-string) and one print/5 s: negligible per-report cost.
        print("[WEBPROF] fps=%4.1f frame=%5.1fms | sim=%5.2f chart=%5.2f "
              "panels=%5.2f flip=%5.2f idle=%5.2f ms/f | steps/f=%.2f" % (
                  fps, 1000.0 / fps,
                  (self.sim - self._rep_sim) / dn * 1e3,
                  (self.chart - self._rep_chart) / dn * 1e3,
                  (self.panels - self._rep_panels) / dn * 1e3,
                  (self.flip - self._rep_flip) / dn * 1e3,
                  max(0.0, wall - work) / dn * 1e3,
                  (self.steps - self._rep_steps) / dn))
        self._rep_t = now
        self._rep_n = self.n
        self._rep_sim, self._rep_chart = self.sim, self.chart
        self._rep_panels, self._rep_flip = self.panels, self.flip
        self._rep_steps = self.steps

    def hud_line(self) -> str:
        """Bucket averages since the previous call, formatted for the overlay.

        Returns "" until at least one frame has elapsed in the window.
        """
        now = time.perf_counter()
        wall = now - self._hud_t
        dn = self.n - self._hud_n
        if dn <= 0:
            return ""
        sim = (self.sim - self._hud_sim) / dn * 1e3
        chart = (self.chart - self._hud_chart) / dn * 1e3
        ui = (self.panels - self._hud_panels) / dn * 1e3
        flip = (self.flip - self._hud_flip) / dn * 1e3
        idle = max(0.0, wall / dn * 1e3 - sim - chart - ui - flip)
        self._hud_t = now
        self._hud_n = self.n
        self._hud_sim, self._hud_chart = self.sim, self.chart
        self._hud_panels, self._hud_flip = self.panels, self.flip
        return (f"sim {sim:.1f} · chart {chart:.1f} · ui {ui:.1f}"
                f" · flip {flip:.1f} · idle {idle:.1f}")


class Game:
    """Manages the main game loop and ties together input, simulation, and rendering."""

    def __init__(self):
        """Initialize Pygame and the game state."""
        pygame.init()
        # Persisted preferences (audio/display/keybinds/gameplay).  Defaults match
        # the old hardcoded behaviour, so an absent settings.json changes nothing.
        self.settings = Settings.load()
        self.display, display_width, display_height = self._create_display()
        # Resolution-aware UI scale (web only): the layout/font pixel values are
        # tuned for a ~720p canvas, but the web framebuffer now renders at true
        # device-pixel size (Phase 2 step 3) — without this, all text is
        # microscopic at 1080p+.  Must be set BEFORE Chart/panels are built
        # (fonts and dimensions are computed in their __init__).  Never set on
        # desktop: scale stays 1.0 there and every ui_px(v) == v.
        if IS_WEB:
            from render.fonts import set_ui_scale
            set_ui_scale(min(2.0, max(1.0, display_height / 720.0)))
        pygame.display.set_caption(WINDOW_TITLE)
        self.clock = pygame.time.Clock()
        # Sim-step cap is lower on web to keep the tab responsive; on desktop it
        # resolves to the original constant (IS_WEB is False).  Web frame RATE
        # is paced by the browser's requestAnimationFrame (see run()), so there
        # is no web fps target anymore.
        self._max_sim_steps = WEB_MAX_SIM_STEPS_PER_FRAME if IS_WEB else MAX_SIM_STEPS_PER_FRAME
        self._collision_frame = 0   # web-only: runs collision avoidance every 2nd frame
        # In-browser frame profiler (None on desktop, so fully inert there).
        self._prof = FrameProfiler() if WEB_PROFILE else None
        # On-screen perf overlay (web): "31 fps · 32 ms" plus a second bucket-
        # breakdown line, top-right, re-rendered once per second.  The *_surf
        # attrs cache the text surfaces; only cheap blits happen per frame.
        self._hud_perf_surf: Optional[pygame.Surface] = None
        self._hud_prof_surf: Optional[pygame.Surface] = None
        self._hud_perf_frames = 0
        self._hud_perf_t0 = time.perf_counter()
        self._hud_perf_font = (safe_sysfont(FONT_DATA_NAME, FONT_SIZE_SMALL)
                               if WEB_HUD_PERF else None)
        # Web display watchdog: at boot pygbag's canvas may still be the
        # template's 1280x720 (its own window_resize settles AFTER our first
        # set_mode), so SDL clamps us to a smaller surface than the real canvas
        # and the whole boot sizing (fit zoom, UI scale) is computed for the
        # wrong resolution.  Once per second we compare our surface against the
        # canvas's true device-pixel size and heal when they disagree.
        self._web_size_check_ms = 0      # next watchdog tick (pygame ms)
        self._web_heal_attempts = 0      # bounded retries; reset on success
        # Web zoom easing: the wheel sets a target; _ease_zoom() glides the
        # camera toward it each frame, anchored at the cursor.  None = settled.
        self._zoom_target: Optional[float] = None
        self._zoom_anchor: tuple = (0, 0)
        self.running = True
        self.is_paused = False
        self._prepause_speed = 1.0   # speed to restore when un-pausing

        # Rebindable input: action -> keycode maps built from the keybind settings.
        self._rebuild_keybinds()

        # Camera and rendering
        self.camera = Camera(display_width, display_height)
        self.camera.zoom = self._calculate_default_zoom(display_width, display_height)
        # Open framed on the middle of the port cluster, not the player's
        # far-western start; follow-cam engages in run() once the title clears.
        self.camera.set_center(CAMERA_START_CENTER)
        # Web spectator boot: there is no player ship to follow, so frame the
        # entire Meridian Sea (both axes) and centre on the world, rather than the
        # port-cluster width the desktop follow-cam default assumes.
        if IS_WEB:
            self.camera.zoom = self._calculate_overview_zoom(display_width, display_height)
            self.camera.set_center((WORLD_WIDTH / 2.0, WORLD_HEIGHT / 2.0))
        self.chart = Chart(self.display, self.camera)

        # UI Panels
        self.vessel_info_panel = VesselInfoPanel(self.display)
        self.tech_systems_panel = TechnicalSystemsPanel(self.display)
        self.settings_panel = SettingsPanel(self.display)
        self.event_log = EventLog(self.display)
        self.fleet_panel = FleetStatusPanel(self.display)
        self.mission_panel = MissionPanel(self.display)
        self.mission_manager = MissionManager()
        self.player_hud = PlayerHUDPanel(self.display)
        self.career = PlayerCareer()
        self.job_board = JobBoard()
        self.career_panel = CareerPanel(self.display)
        self.docking_menu = DockingMenuPanel(self.display)
        self.minimap = MinimapPanel(self.display)
        self.tutorial_overlay = TutorialOverlayPanel(self.display)
        self.reward_banner = RewardBannerPanel(self.display)
        # Active celebratory banners: list of {label, big, color, start_ms}.
        self._banners: list = []

        # Audio — constructed after pygame.init(); falls back to silence on
        # any mixer failure.  Ambient sea bed starts immediately.
        self.sound = SoundManager()
        self.sound.set_volumes(self.settings.master_volume,
                               self.settings.sfx_volume,
                               self.settings.music_volume)
        self.sound.start_ambient()

        # Game-over state
        self.game_over = False
        self.game_over_reason = ""
        self._restart_requested = False
        self._session_start_time = time.time()
        self._game_over_screen = GameOverScreen(self.display)

        # Hull-damage feedback: track how much integrity each source has cost so the
        # game-over screen can name the dominant cause in plain English, plus the tick
        # (ms) until which the red screen flash lingers after the most recent hit.
        self._hull_damage_by_source = {"grounding": 0.0, "storm": 0.0}
        self._hull_damage_flash_until: int = 0
        self._hull_warn_font = safe_sysfont(
            FONT_UI_NAME, FONT_SIZE_TITLE, bold=True)
        self._hull_warn_sub_font = safe_sysfont(
            FONT_UI_NAME, FONT_SIZE_SECTION, bold=True)

        # Port the player just departed from — proximity docking is suppressed
        # until the vessel clears that port's radius, else DEPART would re-dock
        # on the very next sim step.
        self._departed_port: Optional[str] = None

        # Player consequence trackers (Game-level; engine stays pure)
        self._zone_timer: float = 0.0          # cumulative seconds inside violation zone
        self._zone_fine_cooldown: float = 0.0  # seconds until next fine can fire
        self._zone_warning_sent: bool = False  # one-time entry-warning flag
        self._storm_speed_warning_sent: bool = False

        # Onboarding state — Game owns step progression, career owns the
        # persistent tutorial_complete flag.  Activated in _begin_tutorial().
        self._tutorial_active: bool = False
        self._tutorial_step: int = 0
        self._tutorial_route: list = []
        self._tutorial_wp_index: int = 0

        # SPD-label flash: ticks (ms) until which the HUD throttle label stays lit.
        self._throttle_flash_until: int = 0

        # Voyage flavour: cosmetic log lines, throttled by sim-time, de-duped per
        # voyage.  Reset on departure / tutorial start (see _reset_voyage_flavor).
        self._flavor_seen: set = set()
        self._flavor_last_s: float = 0.0

        # Simulation state
        self.world = World()
        populate_world(self.world)  # Load the Meridian Sea map

        self.environment = Environment()
        self.selected_vessel: Optional[Vessel] = None
        self.hover_vessel: Optional[Vessel] = None
        self.player_vessel: Optional[Vessel] = None
        self._dragging = False
        self._drag_last_pos = None
        self._drag_start_pos = None
        # Keyed by id(vessel): remaining waypoints after a multi-hop player command
        self._pending_player_paths: dict = {}
        # Keyed by id(vessel): persistent smart-decision state for each vessel.
        self._vessel_smart_state: dict = {}
        # Party yacht system: keyed by id(yacht); value = id of yacht being served.
        self._party_state: dict = {}

        # Create initial vessels
        self._create_initial_vessels()

        # Follow-cam is engaged in run() (after the title overview) so the
        # opening chart stays centred on the cluster set above, not snapped
        # straight to the player at the far-western edge.

        # Time tracking for fixed timesteps
        self.accumulator = 0.0  # accumulated time for simulation
        self.last_sim_steps = 0  # steps executed last frame (exposed for diagnostics)

    def _create_display(self):
        """Create the window surface from settings (resolution + fullscreen),
        falling back to the desktop-scaled default.  Returns (surface, w, h).

        resolution=None + windowed reproduces the original behaviour exactly.
        Used at startup and re-used when the player changes display settings.
        """
        if IS_WEB:
            # Web: render at the canvas's true device-pixel size so text is crisp,
            # instead of pygbag's blurry CSS-stretched 1280x720 default.  Its own
            # method keeps the desktop path below byte-for-byte unchanged.
            w, h = self._web_framebuffer_size()
            surface = pygame.display.set_mode((w, h))
            w, h = surface.get_size()
            return surface, w, h

        # True desktop size.  pygame.display.Info().current_* returns the CURRENT
        # mode after the first set_mode (NOT the desktop), so it can't be trusted
        # at runtime — a runtime fullscreen toggle would size off the current
        # window, not the screen.  get_desktop_sizes() is mode-independent.
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
        except (pygame.error, IndexError, AttributeError):
            info = pygame.display.Info()
            dw, dh = info.current_w, info.current_h

        if self.settings.fullscreen:
            if self.settings.resolution:
                w = min(self.settings.resolution[0], dw)
                h = min(self.settings.resolution[1], dh)
            else:
                w, h = dw, dh                      # native desktop resolution
            surface = pygame.display.set_mode((w, h), pygame.FULLSCREEN)
        else:
            if self.settings.resolution:
                w = min(self.settings.resolution[0], dw)
                h = min(self.settings.resolution[1], dh)
            else:
                w = min(max(WINDOW_MIN_WIDTH, int(dw * WINDOW_SCALE_FACTOR)), dw)
                h = min(max(WINDOW_MIN_HEIGHT, int(dh * WINDOW_SCALE_FACTOR)), dh)
            surface = pygame.display.set_mode((w, h))

        # Read back the REAL size SDL gave us (authoritative for camera/panels).
        w, h = surface.get_size()
        return surface, w, h

    def _web_framebuffer_size(self):
        """Choose the web framebuffer (set_mode) size.

        pygbag's default canvas is a fixed 1280x720 backing store CSS-stretched to
        fill the page, so on a larger or HiDPI display it upscales blurry and text
        goes fuzzy.  Query the canvas's real DEVICE-pixel size via the pygbag JS
        bridge (window inner size * devicePixelRatio) and render at that, so the
        framebuffer maps 1:1 to physical pixels — crisp.  The size is capped
        aspect-preserving to WEB_FB_MAX so fill-rate and fixed-px UI fonts stay
        sane on 4K/HiDPI.  If the bridge is unavailable (older pygbag, headless),
        fall back to a fixed higher-than-default size that still beats 1280x720.
        """
        fallback = (WEB_FB_FALLBACK_W, WEB_FB_FALLBACK_H)
        try:
            import platform as _platform          # pygbag shim: .window is the JS window
            win = _platform.window
            dpr = float(win.devicePixelRatio) or 1.0
            cw = int(win.innerWidth)
            ch = int(win.innerHeight)
        except Exception:
            return fallback
        if cw < 320 or ch < 240:                  # nonsense / not ready -> safe default
            return fallback
        # WEB_RENDER_SCALE: render fewer pixels than the canvas has; the
        # browser's GPU upscale (canvas CSS is 100%) stretches for free.  The
        # per-frame canvas upload is the real-browser bottleneck, so this is
        # the lever that actually moves fps (see config.py).
        dw = int(cw * dpr * WEB_RENDER_SCALE)
        dh = int(ch * dpr * WEB_RENDER_SCALE)
        # Cap while preserving the window's aspect ratio (no CSS-stretch distortion).
        scale = min(1.0, WEB_FB_MAX_W / dw, WEB_FB_MAX_H / dh)
        return max(1, int(dw * scale)), max(1, int(dh * scale))

    def _web_watch_display(self) -> None:
        """Once-per-second sanity check: does our surface match the real canvas?

        The Phase 4 root cause of the letterboxed world: our boot set_mode runs
        BEFORE pygbag's own window_resize() has grown the canvas past the
        template's 1280x720, so SDL clamps the surface and every boot-time size
        decision (overview fit, UI scale) is computed for a resolution the
        canvas stops having moments later.  A single boot-time measurement can
        never win that race — so we re-measure and heal until stable.
        Bounded retries: if the environment simply refuses the size (surface
        never changes after a heal), stop asking rather than loop forever.
        """
        now = pygame.time.get_ticks()
        if now < self._web_size_check_ms:
            return
        self._web_size_check_ms = now + 1000
        if self._web_heal_attempts >= 5:
            return
        desired = self._web_framebuffer_size()
        cur = self.display.get_size()
        if abs(desired[0] - cur[0]) <= 8 and abs(desired[1] - cur[1]) <= 8:
            self._web_heal_attempts = 0
            return
        self._web_heal_display(desired)
        # Success resets the budget; a refused size burns one attempt.
        if self.display.get_size() == desired:
            self._web_heal_attempts = 0
        else:
            self._web_heal_attempts += 1

    def _web_heal_display(self, size) -> None:
        """Recreate the display at the canvas's true size and rebuild the UI.

        Unlike _apply_display_settings (which only repoints surfaces), this
        also recomputes UI_SCALE and RECONSTRUCTS the chart + panels so their
        fonts and scaled dimensions pick up the new resolution — fonts are
        built in each panel's __init__, so repointing alone can't resize text.
        Game state (world, vessels, camera position, event log) is preserved.
        """
        from render.fonts import set_ui_scale, get_ui_scale
        self.display = pygame.display.set_mode(size)
        w, h = self.display.get_size()
        set_ui_scale(min(2.0, max(1.0, h / 720.0)))
        self.camera.viewport_width = w
        self.camera.viewport_height = h
        # Rebuild chart + panels (fonts/dimensions bake the scale in __init__).
        _entries = self.event_log._entries       # keep the spectator's feed
        self.chart = Chart(self.display, self.camera)
        self.vessel_info_panel = VesselInfoPanel(self.display)
        self.tech_systems_panel = TechnicalSystemsPanel(self.display)
        self.settings_panel = SettingsPanel(self.display)
        self.event_log = EventLog(self.display)
        self.event_log._entries = _entries
        self.fleet_panel = FleetStatusPanel(self.display)
        self.mission_panel = MissionPanel(self.display)
        self.player_hud = PlayerHUDPanel(self.display)
        self.career_panel = CareerPanel(self.display)
        self.docking_menu = DockingMenuPanel(self.display)
        self.minimap = MinimapPanel(self.display)
        self.tutorial_overlay = TutorialOverlayPanel(self.display)
        self.reward_banner = RewardBannerPanel(self.display)
        self._game_over_screen = GameOverScreen(self.display)
        self._hud_perf_font = safe_sysfont(FONT_DATA_NAME, FONT_SIZE_SMALL)
        self._hud_perf_surf = None
        # Re-fit the overview when nothing is followed (the spectator default).
        self._zoom_target = None   # cancel any in-flight wheel ease
        if self.camera.follow_target is None:
            self.camera.zoom = self._calculate_overview_zoom(w, h)
            self.camera.set_center((WORLD_WIDTH / 2.0, WORLD_HEIGHT / 2.0))
        print(f"[WEBDISPLAY] healed display to {w}x{h} "
              f"(ui_scale={get_ui_scale():.3f}, zoom={self.camera.zoom:.3f})")

    def _nudge_zoom_target(self, cursor_pos, factor: float) -> None:
        """Accumulate a wheel notch into the eased zoom target (web only)."""
        base = self._zoom_target if self._zoom_target is not None else self.camera.zoom
        self._zoom_target = max(ZOOM_MIN, min(ZOOM_MAX, base * factor))
        self._zoom_anchor = cursor_pos

    def _ease_zoom(self) -> None:
        """Glide camera.zoom toward the wheel target, anchored at the cursor.

        Exponential ease (~0.3s settle at 30fps); snaps and clears the target
        once within 0.2% so the static chunk gets a stable final zoom to build
        against.  Web only — desktop zoom stays immediate.
        """
        if self._zoom_target is None:
            return
        z = self.camera.zoom
        if abs(self._zoom_target - z) / max(z, 1e-6) > 0.002:
            step = (self._zoom_target / z) ** 0.30
            self.camera.zoom_at(self._zoom_anchor, step)
            self.camera.clamp_zoom(ZOOM_MIN, ZOOM_MAX)
        else:
            self.camera.zoom_at(self._zoom_anchor, self._zoom_target / z)
            self.camera.clamp_zoom(ZOOM_MIN, ZOOM_MAX)
            self._zoom_target = None

    def _rebuild_keybinds(self) -> None:
        """(Re)build the action<->keycode maps from settings.keybinds (key names).

        Keeps engine/settings.py pygame-free: it stores key NAMES, and the
        conversion to keycodes happens here.  Call after any keybind change.
        """
        self.keys: dict = {}            # action -> keycode
        self._action_by_key: dict = {}  # keycode -> action
        for action, name in self.settings.keybinds.items():
            try:
                code = pygame.key.key_code(name)
            except (ValueError, TypeError):
                code = pygame.key.key_code(DEFAULT_KEYBINDS.get(action, "a"))
            self.keys[action] = code
            self._action_by_key[code] = action

    def _calculate_default_zoom(self, width: int, height: int) -> float:
        # Frame the main port cluster across the screen width, not the whole
        # world — the follow cam keeps the player centred, so fitting the full
        # 1400-wu sea just shrank everything into the middle of a void.
        return max(ZOOM_MIN, min(width / DEFAULT_VIEW_SPAN_WU, ZOOM_MAX))

    def _calculate_overview_zoom(self, width: int, height: int) -> float:
        """Zoom that frames the WHOLE Meridian Sea (both axes) with a little
        breathing room around the coast — the ambient spectator overview used on
        the web boot, where nothing is followed so the full sea must be visible.

        The margin is deliberately tight (2%): on a viewport wider than the
        world's aspect the leftover side bands are unavoidable, so they're kept
        minimal and styled as open sea (water fill + world frame + matching page
        background) rather than dead space.
        """
        margin = 1.02  # ~2% padding so the coastline isn't flush to the edges
        fit = min(width / (WORLD_WIDTH * margin), height / (WORLD_HEIGHT * margin))
        return max(ZOOM_MIN, min(fit, ZOOM_MAX))

    def _find_next_port_in_route(self, vessel):
        """Return the next Port in vessel.route from route_index, or None."""
        if not vessel.route:
            return None
        n = len(vessel.route)
        for offset in range(n):
            wp = vessel.route[(vessel.route_index + offset) % n]
            for port in self.world.ports:
                if abs(wp[0] - port.position[0]) < 2 and abs(wp[1] - port.position[1]) < 2:
                    return port
        return None

    def _create_initial_vessels(self) -> None:
        """Create all vessels with randomised but well-separated spawn positions."""
        # Each spawn appends to _spawns so subsequent vessels stay >= 30 wu apart.
        _spawns: list = []
        # Cargo vessel — 150 m LOA, deep-sea freighter.
        # Runs the deep north-channel route (avoids Skerry Bank with 8 m draft).
        _pos, _ridx, _dest, _hdg = _random_spawn(VESSEL_ROUTE_CARGO, self.world, 8.0, _spawns); _spawns.append(_pos)
        cargo = Vessel(
            name="MV Meridian",
            vessel_type="cargo",
            position=_pos,
            heading=_hdg,
            target_speed=8.0,
            current_speed=0.0,
            max_speed=12.0,
            acceleration=0.008,
            deceleration=0.006,
            turn_rate=0.5,
            length_m=150.0,
            beam_m=25.0,
            draft_m=8.0,
            fuel=100.0,
            fuel_capacity=100.0,
            fuel_consumption_rate=3.5,
            route=VESSEL_ROUTE_CARGO,
            route_index=_ridx,
            port_stay_duration=PORT_STAY_CARGO_S,
            destination=_dest,
        )
        self.world.add_vessel(cargo)

        # Fishing vessel — 40 m, twin-screw.
        # Home: Saltgate Harbour; fishes the open grounds south of Skerry Bank.
        _pos, _ridx, _dest, _hdg = _random_spawn(VESSEL_ROUTE_FISHING, self.world, 3.0, _spawns); _spawns.append(_pos)
        fishing = Vessel(
            name="FV Horizon",
            vessel_type="fishing",
            position=_pos,
            heading=_hdg,
            target_speed=6.0,
            current_speed=0.0,
            max_speed=10.0,
            acceleration=0.050,
            deceleration=0.030,
            turn_rate=2.0,
            length_m=40.0,
            beam_m=8.0,
            draft_m=3.0,
            fuel=50.0,
            fuel_capacity=50.0,
            fuel_consumption_rate=2.8,
            route=VESSEL_ROUTE_FISHING,
            route_index=_ridx,
            port_stay_duration=PORT_STAY_FISHING_S,
            destination=_dest,
        )
        self.world.add_vessel(fishing)

        # Sailing yacht — 35 m, wind-powered.
        # Clockwise south-corridor circuit: Vesper Cove → NE mark → SE reach → S reach.
        _pos, _ridx, _dest, _hdg = _random_spawn(VESSEL_ROUTE_SAILBOAT, self.world, 2.5, _spawns); _spawns.append(_pos)
        sailboat = Vessel(
            name="SY Windward",
            vessel_type="sailboat",
            position=_pos,
            heading=_hdg,
            target_speed=5.0,
            current_speed=0.0,
            max_speed=10.0,
            acceleration=0.020,
            deceleration=0.010,
            turn_rate=1.0,
            length_m=35.0,
            beam_m=7.0,
            draft_m=2.5,
            fuel=None,
            fuel_capacity=None,
            fuel_consumption_rate=0.0,
            route=VESSEL_ROUTE_SAILBOAT,
            route_index=_ridx,
            port_stay_duration=PORT_STAY_SAILBOAT_S,
            destination=_dest,
        )
        self.world.add_vessel(sailboat)

        # Ferry — 80 m, designed for port manoeuvring.
        # 4-port loop: Maren → Ardent → Brattlin → Vesper → Maren via south corridor.
        _pos, _ridx, _dest, _hdg = _random_spawn(VESSEL_ROUTE_FERRY, self.world, 4.0, _spawns); _spawns.append(_pos)
        ferry = Vessel(
            name="MS Coastal Express",
            vessel_type="ferry",
            position=_pos,
            heading=_hdg,
            target_speed=10.0,
            current_speed=0.0,
            max_speed=14.0,
            acceleration=0.040,
            deceleration=0.020,
            turn_rate=1.5,
            length_m=80.0,
            beam_m=15.0,
            draft_m=4.0,
            fuel=80.0,
            fuel_capacity=80.0,
            port_stay_duration=PORT_STAY_FERRY_S,
            fuel_consumption_rate=5.0,
            route=VESSEL_ROUTE_FERRY,
            route_index=_ridx,
            destination=_dest,
        )
        self.world.add_vessel(ferry)

        # ── 4 additional vessels ─────────────────────────────────────────────

        # MV Carrick Star — second cargo, 130 m, draft 6.5 m.
        # Route: Port Maren ↔ Brattlin Light Quay via south corridor.
        _pos, _ridx, _dest, _hdg = _random_spawn(VESSEL_ROUTE_CARGO2, self.world, 6.5, _spawns); _spawns.append(_pos)
        cargo2 = Vessel(
            name="MV Carrick Star",
            vessel_type="cargo",
            position=_pos,
            heading=_hdg,
            target_speed=8.0,
            current_speed=0.0,
            max_speed=11.0,
            acceleration=0.008,
            deceleration=0.006,
            turn_rate=0.5,
            length_m=130.0,
            beam_m=22.0,
            draft_m=6.5,
            fuel=80.0,
            fuel_capacity=80.0,
            fuel_consumption_rate=3.0,
            route=VESSEL_ROUTE_CARGO2,
            route_index=_ridx,
            port_stay_duration=PORT_STAY_CARGO_S,
            destination=_dest,
        )
        self.world.add_vessel(cargo2)

        # FV Skerrywatch — second fishing vessel, 32 m.
        # Route: Saltgate Harbour → western fishing ground → return.
        _pos, _ridx, _dest, _hdg = _random_spawn(VESSEL_ROUTE_FISHING2, self.world, 2.5, _spawns); _spawns.append(_pos)
        fishing2 = Vessel(
            name="FV Skerrywatch",
            vessel_type="fishing",
            position=_pos,
            heading=_hdg,
            target_speed=6.0,
            current_speed=0.0,
            max_speed=9.0,
            acceleration=0.050,
            deceleration=0.030,
            turn_rate=2.0,
            length_m=32.0,
            beam_m=7.0,
            draft_m=2.5,
            fuel=40.0,
            fuel_capacity=40.0,
            fuel_consumption_rate=2.5,
            route=VESSEL_ROUTE_FISHING2,
            route_index=_ridx,
            port_stay_duration=PORT_STAY_FISHING_S,
            destination=_dest,
        )
        self.world.add_vessel(fishing2)

        # Ardent Pilot — harbour tug / pilot boat, 25 m.
        # Short, frequent shuttle Port Ardent ↔ Brattlin Light Quay.
        # Refuels only at Ardent (Brattlin has no fuel). Quick turnaround.
        _pos, _ridx, _dest, _hdg = _random_spawn(VESSEL_ROUTE_TUG, self.world, 2.0, _spawns); _spawns.append(_pos)
        tug = Vessel(
            name="Ardent Pilot",
            vessel_type="tug",
            position=_pos,
            heading=_hdg,
            target_speed=10.0,
            current_speed=0.0,
            max_speed=12.0,
            acceleration=0.040,
            deceleration=0.025,
            turn_rate=2.5,
            length_m=25.0,
            beam_m=8.0,
            draft_m=2.0,
            fuel=25.0,
            fuel_capacity=25.0,
            fuel_consumption_rate=4.0,
            route=VESSEL_ROUTE_TUG,
            route_index=_ridx,
            port_stay_duration=PORT_STAY_FERRY_S,
            destination=_dest,
        )
        self.world.add_vessel(tug)

        # SY Meridian Breeze — second sailboat, 28 m.
        # Western back-and-forth: Saltgate ↔ WP_SAIL2_WEST (52,473).
        _pos, _ridx, _dest, _hdg = _random_spawn(VESSEL_ROUTE_SAILBOAT2, self.world, 2.0, _spawns); _spawns.append(_pos)
        sail2 = Vessel(
            name="SY Meridian Breeze",
            vessel_type="sailboat",
            position=_pos,
            heading=_hdg,
            target_speed=5.0,
            current_speed=0.0,
            max_speed=8.0,
            acceleration=0.020,
            deceleration=0.010,
            turn_rate=1.0,
            length_m=28.0,
            beam_m=6.0,
            draft_m=2.0,
            fuel=None,
            fuel_capacity=None,
            fuel_consumption_rate=0.0,
            route=VESSEL_ROUTE_SAILBOAT2,
            route_index=_ridx,
            port_stay_duration=PORT_STAY_SAILBOAT_S,
            destination=_dest,
        )
        self.world.add_vessel(sail2)

        # MT Meridian Star — large tanker, 200 m, deep-draft 12 m.
        # Slow deep-sea loop: Port Maren → NE open ocean → back.
        _pos, _ridx, _dest, _hdg = _random_spawn(VESSEL_ROUTE_TANKER, self.world, 12.0, _spawns); _spawns.append(_pos)
        tanker = Vessel(
            name="MT Meridian Star",
            vessel_type="tanker",
            position=_pos,
            heading=_hdg,
            target_speed=7.0,
            current_speed=0.0,
            max_speed=10.0,
            acceleration=0.005,
            deceleration=0.004,
            turn_rate=0.3,
            length_m=200.0,
            beam_m=32.0,
            draft_m=12.0,
            fuel=150.0,
            fuel_capacity=150.0,
            fuel_consumption_rate=4.5,
            route=VESSEL_ROUTE_TANKER,
            route_index=_ridx,
            port_stay_duration=PORT_STAY_CARGO_S,
            destination=_dest,
        )
        self.world.add_vessel(tanker)

        # CG Sentinel — coast guard patrol vessel, 45 m, draft 2 m.
        # Fast patrol loop visiting all five ports in sequence.
        _pos, _ridx, _dest, _hdg = _random_spawn(VESSEL_ROUTE_COAST_GUARD, self.world, 2.0, _spawns); _spawns.append(_pos)
        coast_guard = Vessel(
            name="CG Sentinel",
            vessel_type="coast_guard",
            position=_pos,
            heading=_hdg,
            target_speed=18.0,
            current_speed=0.0,
            max_speed=25.0,
            acceleration=0.15,
            deceleration=0.10,
            turn_rate=4.0,
            length_m=45.0,
            beam_m=8.0,
            draft_m=2.0,
            fuel=60.0,
            fuel_capacity=60.0,
            fuel_consumption_rate=6.0,
            route=VESSEL_ROUTE_COAST_GUARD,
            route_index=_ridx,
            port_stay_duration=PORT_STAY_PATROL_S,
            destination=_dest,
        )
        self.world.add_vessel(coast_guard)

        # MV Thornwick — deep-sea cargo, Port Maren ↔ Thornwick Roads.
        # Pale green distinguishes it from the standard bright-green cargo vessels.
        _pos, _ridx, _dest, _hdg = _random_spawn(VESSEL_ROUTE_THORNWICK, self.world, 8.0, _spawns); _spawns.append(_pos)
        thornwick = Vessel(
            name="MV Thornwick",
            vessel_type="cargo",
            position=_pos,
            heading=_hdg,
            target_speed=9.0,
            current_speed=0.0,
            max_speed=11.0,
            acceleration=0.007,
            deceleration=0.005,
            turn_rate=0.5,
            length_m=140.0,
            beam_m=23.0,
            draft_m=8.0,
            fuel=120.0,
            fuel_capacity=120.0,
            fuel_consumption_rate=3.8,
            route=VESSEL_ROUTE_THORNWICK,
            route_index=_ridx,
            port_stay_duration=PORT_STAY_CARGO_S,
            destination=_dest,
            color_override=(140, 210, 140),   # pale green — long-haul deep-sea freighter
        )
        self.world.add_vessel(thornwick)

        # SY Blue Horizon — luxury sailing yacht, Vesper Cove → Cape Durran → Merin Bay.
        # Pale cyan distinguishes it from SY Windward's standard bright cyan.
        _pos, _ridx, _dest, _hdg = _random_spawn(VESSEL_ROUTE_BLUE_HORIZON, self.world, 2.5, _spawns); _spawns.append(_pos)
        blue_horizon = Vessel(
            name="SY Blue Horizon",
            vessel_type="sailboat",
            position=_pos,
            heading=_hdg,
            target_speed=6.0,
            current_speed=0.0,
            max_speed=9.0,
            acceleration=0.018,
            deceleration=0.010,
            turn_rate=1.0,
            length_m=38.0,
            beam_m=7.5,
            draft_m=2.5,
            fuel=None,
            fuel_capacity=None,
            fuel_consumption_rate=0.0,
            route=VESSEL_ROUTE_BLUE_HORIZON,
            route_index=_ridx,
            port_stay_duration=PORT_STAY_SAILBOAT_S,
            destination=_dest,
            color_override=(120, 210, 210),   # pale cyan — leisure sailing cruise
        )
        self.world.add_vessel(blue_horizon)

        # ── 3 new vessels: Eastern Star, North Fisher, Tender I ─────────────

        # MV Eastern Star — inter-port cargo, Cape Durran ↔ Thornwick Roads.
        _pos, _ridx, _dest, _hdg = _random_spawn(VESSEL_ROUTE_EASTERN_STAR, self.world, 6.0, _spawns); _spawns.append(_pos)
        eastern_star = Vessel(
            name="MV Eastern Star",
            vessel_type="cargo",
            position=_pos,
            heading=_hdg,
            target_speed=9.0,
            current_speed=0.0,
            max_speed=13.0,
            acceleration=0.010,
            deceleration=0.007,
            turn_rate=0.8,
            length_m=120.0,
            beam_m=20.0,
            draft_m=6.0,
            fuel=90.0,
            fuel_capacity=90.0,
            fuel_consumption_rate=3.2,
            route=VESSEL_ROUTE_EASTERN_STAR,
            route_index=_ridx,
            port_stay_duration=PORT_STAY_CARGO_S,
            destination=_dest,
            personality="aggressive",
            color_override=(80, 200, 90),   # vivid green — eastern corridor cargo
        )
        self.world.add_vessel(eastern_star)

        # FV North Fisher — Thornwick-based trawler, northern fishing grounds.
        _pos, _ridx, _dest, _hdg = _random_spawn(VESSEL_ROUTE_NORTH_FISHER, self.world, 2.5, _spawns); _spawns.append(_pos)
        north_fisher = Vessel(
            name="FV North Fisher",
            vessel_type="fishing",
            position=_pos,
            heading=_hdg,
            target_speed=6.0,
            current_speed=0.0,
            max_speed=9.0,
            acceleration=0.050,
            deceleration=0.030,
            turn_rate=2.0,
            length_m=36.0,
            beam_m=8.0,
            draft_m=2.5,
            fuel=45.0,
            fuel_capacity=45.0,
            fuel_consumption_rate=2.6,
            route=VESSEL_ROUTE_NORTH_FISHER,
            route_index=_ridx,
            port_stay_duration=PORT_STAY_FISHING_S,
            destination=_dest,
            personality="cautious",
        )
        self.world.add_vessel(north_fisher)

        # MV Tender I — service tender, Vesper Cove ↔ Merin Bay.
        # Small, fast white vessel; also used by the party yacht system.
        _pos, _ridx, _dest, _hdg = _random_spawn(VESSEL_ROUTE_TENDER, self.world, 1.5, _spawns); _spawns.append(_pos)
        tender_vessel = Vessel(
            name="MV Tender I",
            vessel_type="tender",
            position=_pos,
            heading=_hdg,
            target_speed=12.0,
            current_speed=0.0,
            max_speed=18.0,
            acceleration=0.080,
            deceleration=0.050,
            turn_rate=4.0,
            length_m=18.0,
            beam_m=4.5,
            draft_m=1.5,
            fuel=20.0,
            fuel_capacity=20.0,
            fuel_consumption_rate=4.0,
            route=VESSEL_ROUTE_TENDER,
            route_index=_ridx,
            port_stay_duration=PORT_STAY_TENDER_S,
            destination=_dest,
            personality="efficient",
            color_override=(240, 240, 240),   # white — service tender
        )
        self.world.add_vessel(tender_vessel)

        # Assign mission types and mission-appropriate port stay durations.
        # Done after all vessels are added so we can iterate world.vessels cleanly.
        _MISSION_MAP = {
            "MV Meridian":       ("cargo_run",     PORT_STAY_CARGO_LOAD_S,     None),
            "MV Carrick Star":   ("cargo_run",     PORT_STAY_CARGO_LOAD_S,     None),
            "MS Coastal Express":("ferry_run",     PORT_STAY_FERRY_BOARD_S,    None),
            "FV Horizon":        ("fishing_trip",  PORT_STAY_FISHING_UNLOAD_S, None),
            "FV Skerrywatch":    ("fishing_trip",  PORT_STAY_FISHING_UNLOAD_S, None),
            "SY Windward":       ("sailing_cruise",None,                        None),
            "SY Meridian Breeze":("sailing_cruise",None,                        None),
            "Ardent Pilot":      ("tug_duty",      PORT_STAY_TUG_S,            None),
            "MT Meridian Star":  ("cargo_run",     PORT_STAY_CARGO_LOAD_S,     None),
            "CG Sentinel":       ("patrol",        PORT_STAY_PATROL_S,         None),
            "MV Thornwick":      ("cargo_run",     PORT_STAY_CARGO_LOAD_S,     None),
            "SY Blue Horizon":   ("sailing_cruise",None,                        None),
            "MV Eastern Star":   ("cargo_run",     PORT_STAY_CARGO_LOAD_S,     None),
            "FV North Fisher":   ("fishing_trip",  PORT_STAY_FISHING_UNLOAD_S, None),
            "MV Tender I":       ("tug_duty",      PORT_STAY_TENDER_S,         None),
        }
        for v in self.world.vessels:
            if v.name in _MISSION_MAP:
                m_type, m_stay, _ = _MISSION_MAP[v.name]
                v.mission_type = m_type
                if m_stay is not None:
                    v.port_stay_duration = m_stay
                _set_underway_mission_status(v)

        # Assign personalities to all vessels that don't already have one set
        # in their constructor.  New vessels have personality set directly; the
        # original 12 are patched here so the constructor signatures stay clean.
        _PERSONALITY_MAP = {
            "MV Meridian":        "efficient",
            "FV Horizon":         "cautious",
            "SY Windward":        "leisure",
            "MS Coastal Express": "aggressive",
            "MV Carrick Star":    "efficient",
            "FV Skerrywatch":     "cautious",
            "Ardent Pilot":       "aggressive",
            "SY Meridian Breeze": "leisure",
            "MT Meridian Star":   "efficient",
            "CG Sentinel":        "aggressive",
            "MV Thornwick":       "cautious",
            "SY Blue Horizon":    "leisure",
        }
        for v in self.world.vessels:
            if v.name in _PERSONALITY_MAP:
                v.personality = _PERSONALITY_MAP[v.name]

        # Player vessel — human-controlled cargo ship near Port Maren.
        # No route, no mission: heading and throttle are set by keyboard.
        #
        # Skipped on web: the browser build boots as a pure ambient spectator —
        # no player ship, no career, no tutorial (see IS_WEB in run()).  Leaving
        # self.player_vessel = None makes every player-centric branch a no-op.
        if not IS_WEB:
            player = Vessel(
                name="MV Velawind",
                vessel_type="cargo",
                position=(130.0, 320.0),
                heading=90.0,
                target_speed=0.0,
                current_speed=0.0,
                max_speed=14.0,
                acceleration=2.0,
                deceleration=1.0,
                turn_rate=10.0,
                length_m=85.0,
                beam_m=14.0,
                draft_m=5.0,
                fuel=100.0,
                fuel_capacity=100.0,
                fuel_consumption_rate=1.0,   # ~5% of tank per typical run — a minor
                                             # cost; mistakes, not fuel, are the sink
                is_player=True,
                status="underway",
            )
            self.world.add_vessel(player)
            self.player_vessel = player

    def handle_events(self) -> None:
        """Process keyboard and mouse input."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif IS_WEB and event.type == pygame.VIDEORESIZE:
                # Browser window resized (if pygbag delivers it): heal through
                # the same path as the watchdog — recreate the framebuffer at
                # the true canvas size, recompute UI_SCALE, rebuild fonts and
                # panels, and re-fit the overview when nothing is followed.
                self._web_heal_display(self._web_framebuffer_size())

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.game_over:
                        self.running = False     # game over: Esc exits
                    elif IS_WEB:
                        # Web spectator: never open the blocking pause menu.
                        # Esc simply clears the current selection / follow-cam.
                        self.selected_vessel = None
                        self.camera.set_follow_target(None)
                    else:
                        self._run_pause_menu()    # in-game: Esc opens pause menu
                elif event.key == pygame.K_r and self.game_over:
                    self._restart_requested = True
                    self.running = False

                # Docking menu captures its keys while the player is in port —
                # SPACE departs instead of pausing, W departs and throttles up.
                elif (self.docking_menu.visible
                        and not self.settings_panel.is_visible
                        and event.key in (pygame.K_UP, pygame.K_DOWN,
                                          pygame.K_RETURN, pygame.K_KP_ENTER,
                                          pygame.K_SPACE, pygame.K_w)):
                    self._handle_docking_key(event.key)

                elif event.key == self.keys["pause"]:
                    if self.is_paused:
                        self.is_paused = False
                        self.environment.time_speed_multiplier = self._prepause_speed
                    else:
                        # Remember the speed so unpausing restores a 2x/3x choice.
                        self._prepause_speed = self.environment.time_speed_multiplier or 1.0
                        self.is_paused = True
                        self.environment.time_speed_multiplier = 0.0

                # Player throttle — bound throttle keys / UP-DOWN when player active
                elif event.key in (self.keys["throttle_up"], pygame.K_UP,
                                   self.keys["throttle_down"], pygame.K_DOWN):
                    _pv_active = (self.player_vessel is not None
                                  and not self.settings_panel.is_visible)
                    if _pv_active:
                        pv = self.player_vessel
                        if event.key in (self.keys["throttle_up"], pygame.K_UP):
                            pv.target_speed = min(pv.max_speed,
                                                  pv.target_speed + PLAYER_THROTTLE_STEP)
                        else:
                            pv.target_speed = max(0.0,
                                                  pv.target_speed - PLAYER_THROTTLE_STEP)
                        # Tactile feedback: soft click + a brief SPD-label flash
                        # so each throttle press audibly and visibly registers.
                        self.sound.play("throttle_click")
                        self._throttle_flash_until = (
                            pygame.time.get_ticks() + THROTTLE_FLASH_MS)
                    else:
                        # No player vessel — arrows pan map; throttle-down opens settings
                        if event.key == pygame.K_UP:
                            self.camera.pan(0, PAN_SPEED * (1.0 / TARGET_FPS))
                        elif event.key == pygame.K_DOWN:
                            self.camera.pan(0, -PAN_SPEED * (1.0 / TARGET_FPS))
                        elif event.key == self.keys["throttle_down"]:
                            self.settings_panel.toggle_visibility()
                            self.environment.weather_drift_enabled = not self.settings_panel.is_visible

                # Arrow pan — LEFT/RIGHT only pan when player vessel not active
                elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    _pv_active = (self.player_vessel is not None
                                  and not self.settings_panel.is_visible)
                    if not _pv_active:
                        if event.key == pygame.K_LEFT:
                            self.camera.pan(PAN_SPEED * (1.0 / TARGET_FPS), 0)
                        else:
                            self.camera.pan(-PAN_SPEED * (1.0 / TARGET_FPS), 0)
                    # A/D turning is handled continuously in update_simulation

                # Reset zoom — keep following player vessel if one exists
                elif event.key == pygame.K_z:
                    self._zoom_target = None   # cancel any in-flight wheel ease
                    self.camera.zoom = self._calculate_default_zoom(self.display.get_width(), self.display.get_height())
                    if self.player_vessel is None:
                        self.camera.set_follow_target(None)

                # Select next vessel (for testing)
                elif event.key == pygame.K_TAB:
                    self._cycle_vessel_selection()

                # Toggle technical systems panel
                elif event.key == self.keys["tech"]:
                    self.tech_systems_panel.toggle_visibility()

                # Toggle follow cam on/off for player vessel
                elif event.key == self.keys["follow_cam"] and self.player_vessel is not None:
                    if self.camera.follow_target is self.player_vessel:
                        self.camera.set_follow_target(None)
                    else:
                        self.camera.set_follow_target(self.player_vessel)

                # Toggle career panel
                elif event.key == self.keys["career"] and self.player_vessel is not None:
                    self.career_panel.toggle_visibility()

                # Toggle minimap
                elif event.key == self.keys["minimap"]:
                    self.minimap.is_visible = not self.minimap.is_visible

                # Skip onboarding — persisted so it never returns this save.
                elif event.key == self.keys["skip_tutorial"] and self._tutorial_active:
                    self._tutorial_active = False
                    self.career.tutorial_complete = True
                    self._tutorial_step = len(TUTORIAL_STEPS)
                    # Drop any transit time-bump back to normal speed on skip.
                    self.environment.time_speed_multiplier = 1.0
                    self.is_paused = False
                    if self.player_vessel is not None:
                        save_career(self.career,
                                    hull_integrity=self.player_vessel.hull_integrity)
                    self.event_log.add(_sim_time_str(self.environment),
                                       "Tutorial skipped", EVENT_COLOR_WEATHER)

                # Toggle settings panel — bound settings key always
                elif event.key == self.keys["settings"]:
                    self.settings_panel.toggle_visibility()
                    self.environment.weather_drift_enabled = not self.settings_panel.is_visible

                # Time controls
                elif event.key == pygame.K_1:
                    self.environment.time_speed_multiplier = 0.0  # pause
                    self.is_paused = True
                elif event.key == pygame.K_2:
                    self.environment.time_speed_multiplier = 1.0  # normal
                    self.is_paused = False
                elif event.key == pygame.K_3:
                    self.environment.time_speed_multiplier = 2.0  # 2x
                    self.is_paused = False
                elif event.key == pygame.K_4:
                    self.environment.time_speed_multiplier = 3.0  # 3x (max)
                    self.is_paused = False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 4:  # scroll wheel up
                    cursor_pos = pygame.mouse.get_pos()
                    zoom_factor = 1.0 + ZOOM_SCROLL_SPEED
                    if IS_WEB:
                        self._nudge_zoom_target(cursor_pos, zoom_factor)
                    else:
                        self.camera.zoom_at(cursor_pos, zoom_factor)
                        self.camera.clamp_zoom(ZOOM_MIN, ZOOM_MAX)

                elif event.button == 5:  # scroll wheel down
                    cursor_pos = pygame.mouse.get_pos()
                    zoom_factor = 1.0 - ZOOM_SCROLL_SPEED
                    if IS_WEB:
                        self._nudge_zoom_target(cursor_pos, zoom_factor)
                    else:
                        self.camera.zoom_at(cursor_pos, zoom_factor)
                        self.camera.clamp_zoom(ZOOM_MIN, ZOOM_MAX)

                elif event.button == 1:  # begin drag / click
                    self._dragging = True
                    self._drag_last_pos = event.pos
                    self._drag_start_pos = event.pos

                elif event.button == 3:  # right click
                    self._handle_right_click(pygame.mouse.get_pos())

            elif event.type == pygame.MOUSEMOTION:
                if self._dragging and self._drag_last_pos is not None:
                    dx = event.pos[0] - self._drag_last_pos[0]
                    dy = event.pos[1] - self._drag_last_pos[1]
                    # Release camera follow the first time the drag moves > 3 px
                    if self.camera.follow_target is not None and self._drag_start_pos:
                        sdx = event.pos[0] - self._drag_start_pos[0]
                        sdy = event.pos[1] - self._drag_start_pos[1]
                        if sdx * sdx + sdy * sdy > 9:
                            self.camera.set_follow_target(None)
                    cx, cy = self.camera.position
                    self.camera.position = (cx - dx / self.camera.zoom,
                                            cy - dy / self.camera.zoom)
                    self.camera.clamp_position()
                    self._drag_last_pos = event.pos

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    # Treat as a click only when the mouse barely moved (< 3 px)
                    if self._drag_start_pos is not None:
                        sdx = event.pos[0] - self._drag_start_pos[0]
                        sdy = event.pos[1] - self._drag_start_pos[1]
                        if sdx * sdx + sdy * sdy <= 9:
                            self._handle_left_click(event.pos)
                    self._dragging = False
                    self._drag_last_pos = None
                    self._drag_start_pos = None

    def _handle_right_click(self, screen_pos) -> None:
        """Right-click: set the player's autopilot waypoint, or command an AI vessel.

        With a non-player vessel selected, the click commands that vessel to
        the position (legacy dispatcher behaviour).  Otherwise the click sets
        the player's autopilot destination — snapping to a port if the click
        landed on its symbol, ignored entirely when the click is on land.
        """
        if (self.selected_vessel is None
                or getattr(self.selected_vessel, 'is_player', False)):
            self._set_player_autopilot(screen_pos)
            return
        v = self.selected_vessel
        world_pos = self.camera.screen_to_world(screen_pos)
        # Force-depart if currently in port so the command takes effect immediately.
        if v.status == "in_port" and v._docked_port_name:
            port = self.world.find_port(v._docked_port_name)
            if port is not None:
                port.release_berth(v.name)
            v._docked_port_name = None
            v.port_stay_timer = 0.0
        waypoints = find_safe_path(v.position, world_pos, self.world)
        v.destination = waypoints[0]
        v.player_commanded = True
        if len(waypoints) > 1:
            self._pending_player_paths[id(v)] = waypoints[1:]
        elif id(v) in self._pending_player_paths:
            del self._pending_player_paths[id(v)]
        if v.status in ("in_port", "docked"):
            v.status = "underway"

    def _set_player_autopilot(self, screen_pos) -> None:
        """Point the player's autopilot at the clicked water position or port."""
        pv = self.player_vessel
        if pv is None:
            return
        world_pos = self.camera.screen_to_world(screen_pos)

        # Clicking a port symbol snaps the waypoint to the port itself.
        target = None
        for port in self.world.ports:
            psx, psy = self.camera.world_to_screen(port.position)
            if math.hypot(psx - screen_pos[0], psy - screen_pos[1]) <= PORT_CLICK_RADIUS_PX:
                target = port.position
                break
        if target is None:
            if self.world.point_in_island(world_pos):
                return  # can't sail onto land
            target = world_pos

        # Setting a course while berthed implies departure.
        if pv.status == "in_port":
            self._player_depart()
        pv.autopilot_destination = target
        self.event_log.add(_sim_time_str(self.environment),
                           "Autopilot — course set", EVENT_COLOR_WEATHER)

    def _cycle_vessel_selection(self) -> None:
        """Cycle to the next vessel for testing."""
        if not self.world.vessels:
            return
        if self.selected_vessel is None:
            self.selected_vessel = self.world.vessels[0]
        else:
            idx = self.world.vessels.index(self.selected_vessel)
            idx = (idx + 1) % len(self.world.vessels)
            self.selected_vessel = self.world.vessels[idx]
        self.camera.set_follow_target(self.selected_vessel)

    def _handle_left_click(self, screen_pos) -> None:
        """Handle a left-click: select a vessel or adjust sliders."""
        # Settings panel sliders have priority
        if self.settings_panel.is_visible:
            self.settings_panel.handle_mouse_click(self.environment, screen_pos,
                                                   self.sound)
            return

        # Docking menu — clicks on its rows take priority while in port.
        if self.docking_menu.visible:
            action = self.docking_menu.handle_click(
                screen_pos, self.player_vessel, self.career)
            if action is not None:
                self._apply_docking_action(action)
                return
            # Swallow clicks inside the panel so they don't select vessels.
            if (self.docking_menu.panel_rect is not None
                    and self.docking_menu.panel_rect.collidepoint(screen_pos)):
                return

        # Career panel — accept contract clicks
        if self.career_panel.is_visible:
            if self.career_panel.handle_click(
                    screen_pos, self.job_board, self.career,
                    self.mission_manager.sim_elapsed_s) is not None:
                return

        # Fleet status panel click — check before chart click
        clicked = self.fleet_panel.handle_click(screen_pos)
        if clicked is not None:
            self.selected_vessel = clicked
            self.camera.set_follow_target(clicked)
            return

        # Otherwise, try to select a vessel
        from config import SHIP_SELECT_RADIUS
        world_pos = self.camera.screen_to_world(screen_pos)
        
        closest_vessel = None
        closest_dist = SHIP_SELECT_RADIUS / self.camera.zoom
        
        for vessel in self.world.vessels:
            dist = vessel.distance_to(world_pos)
            if dist < closest_dist:
                closest_dist = dist
                closest_vessel = vessel
        
        if closest_vessel:
            self.selected_vessel = closest_vessel
            self.camera.set_follow_target(closest_vessel)
        else:
            self.selected_vessel = None
            self.camera.set_follow_target(None)

    def _update_party_system(self, sim_dt: float) -> None:
        """Check for yacht party triggers and manage tender dispatch/return.

        When a yacht is at anchor, there is a small per-step chance it triggers
        a party.  MV Tender I is redirected to the yacht; after the party timer
        expires the tender returns to its normal route.
        """
        tender = next(
            (v for v in self.world.vessels if v.name == PARTY_TENDER_NAME), None
        )
        if tender is None:
            return

        _t = _sim_time_str(self.environment)

        for vessel in self.world.vessels:
            if vessel.vessel_type != "sailboat":
                continue
            vid = id(vessel)

            if vessel.party_active:
                vessel.party_timer -= sim_dt
                if vessel.party_timer <= 0:
                    vessel.party_active = False
                    vessel.party_timer = 0.0
                    # Return tender to its scheduled route
                    if (tender.player_commanded
                            and self._party_state.get("tender_for") == vid):
                        tender.player_commanded = False
                        if tender.route:
                            tender.destination = tender.route[tender.route_index]
                        vessel.log_decision(_t, "Party over — tender returning to service")
                    self._party_state.pop("tender_for", None)
                continue

            # Trigger: yacht anchored, tender free, no party already running
            is_anchored = (vessel.trawling_timer > 0
                           and getattr(vessel, "mission_status", "") == "ANCHORED")
            if not is_anchored:
                continue
            if tender.player_commanded:
                continue
            if self._party_state.get("tender_for") is not None:
                continue
            if vessel.player_commanded:
                continue

            # ~0.00015 per sim-second ≈ once per ~110 sim-min per anchored yacht
            if random.random() < 0.00015 * sim_dt:
                vessel.party_active = True
                vessel.party_timer = random.uniform(PARTY_DURATION_MIN_S, PARTY_DURATION_MAX_S)
                tender.destination = vessel.position
                tender.player_commanded = True
                self._party_state["tender_for"] = vid
                vessel.log_decision(_t, "Party on deck — tender dispatched")
                self.event_log.add(
                    _t, f"PARTY — tender dispatched to {vessel.name}", EVENT_COLOR_WEATHER
                )

    def _handle_docking_key(self, key: int) -> None:
        """Translate a KEYDOWN into a docking-menu action while in port."""
        pv = self.player_vessel
        if key == pygame.K_UP:
            self.docking_menu.move_selection(-1)
        elif key == pygame.K_DOWN:
            self.docking_menu.move_selection(1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._apply_docking_action(
                self.docking_menu.selected_action(pv, self.career))
        elif key == pygame.K_SPACE:
            self._apply_docking_action("depart")
        elif key == pygame.K_w:
            # Throttling up while berthed is the natural "cast off" gesture.
            self._apply_docking_action("depart")
            if pv is not None:
                pv.target_speed = min(pv.max_speed,
                                      pv.target_speed + PLAYER_THROTTLE_STEP)

    def _apply_docking_action(self, action: Optional[str]) -> None:
        """Apply a docking-menu purchase or departure to the game state."""
        pv = self.player_vessel
        if action is None or pv is None:
            return
        _t = _sim_time_str(self.environment)

        if action == "fuel":
            cost = DockingMenuPanel.fuel_cost(pv)
            if cost > 0 and self.career.spend(cost, "Refuel"):
                pv.fuel = pv.fuel_capacity
                self.event_log.add(_t, f"Refueled — -\xa3{cost:.0f}",
                                   EVENT_COLOR_WEATHER)
                save_career(self.career, hull_integrity=pv.hull_integrity)

        elif action == "repair":
            cost = DockingMenuPanel.repair_cost(pv)
            if cost > 0 and self.career.spend(cost, "Hull repair"):
                pv.hull_integrity = 1.0
                self.career.hull_repairs_paid += cost
                self.event_log.add(_t, f"Hull repaired — -\xa3{cost:.0f}",
                                   EVENT_COLOR_WEATHER)
                save_career(self.career, hull_integrity=pv.hull_integrity)

        elif action == "jobs":
            self.career_panel.is_visible = True

        elif action == "depart":
            self._player_depart()

    def _player_depart(self) -> None:
        """Cast the player off: release the berth and set the vessel underway."""
        pv = self.player_vessel
        if pv is None or pv.status != "in_port":
            return
        if pv._docked_port_name:
            port = self.world.find_port(pv._docked_port_name)
            if port is not None:
                port.release_berth(pv.name)
        self._departed_port = pv._docked_port_name
        pv._docked_port_name = None
        pv.port_stay_timer = 0.0
        pv.status = "underway"
        self.docking_menu.visible = False
        self._reset_voyage_flavor()   # fresh flavour log for the new voyage
        save_career(self.career, hull_integrity=pv.hull_integrity)

    def _on_player_docked(self, vessel) -> None:
        """Career hooks fired once when the player vessel berths at a port.

        Completes a matching contract, refreshes the job board, and writes the
        auto-save checkpoint.  Fuel and hull repair are bought explicitly via
        the docking menu, never applied automatically.
        """
        _t = _sim_time_str(self.environment)
        _docked_at = getattr(vessel, '_docked_port_name', '')
        if not _docked_at:
            return
        self.sound.play("docking")
        _tier_before = self.career.tier_name
        _done = self.job_board.complete_job(_docked_at, self.career)
        if _done:
            self.event_log.add(
                _t,
                f"Contract complete — \xa3{_done.payout:.0f} earned",
                EVENT_COLOR_REFLOAT)
            # Reward moment: chime + a centered celebratory banner with the
            # payout — the payoff of the whole loop, not just a log line.
            self.sound.play("success_chime")
            self._add_banner("CONTRACT COMPLETE",
                             f"+\xa3{_done.payout:,.0f}", COLOR_OBJECTIVE)
            # Promotion banner when the +5 rep crossed into a new tier.
            if self.career.tier_name != _tier_before:
                self._add_banner("PROMOTED", self.career.tier_name,
                                 BANNER_PROMOTE_COLOR)
            # Achievement checks tied to contract completion.
            if self.career.total_deliveries >= 1:
                self._award_achievement("First Delivery")
            if (self.environment.active_event_name() == "storm"
                    or self.environment.wave_height > STORM_WAVE_THRESHOLD):
                self._award_achievement("Storm Sailor")
            if (self.career.total_deliveries >= 5
                    and self.career.fines_paid == 0):
                self._award_achievement("Clean Record")
            # Onboarding: completing the guided first delivery retires the
            # tutorial for good (persisted in the auto-save below).
            if getattr(_done, "is_tutorial", False):
                self.career.tutorial_complete = True
                self._tutorial_active = False
                self._tutorial_step = len(TUTORIAL_STEPS)
        self.job_board.refresh_jobs(self.world, self.career)
        # Auto-save: docking is the natural checkpoint — the contract payout
        # above is included; menu purchases re-save when they happen.
        save_career(self.career, hull_integrity=vessel.hull_integrity)

    def _add_banner(self, label: str, big: str, color: tuple) -> None:
        """Queue a centered celebratory banner (fades out; rendered each frame)."""
        self._banners.append({
            "label": label, "big": big, "color": color,
            "start_ms": pygame.time.get_ticks(),
        })

    def _award_achievement(self, name: str) -> None:
        """Unlock an achievement once; log the moment it happens."""
        if name in self.career.achievements:
            return
        self.career.achievements.add(name)
        self.event_log.add(_sim_time_str(self.environment),
                           f"ACHIEVEMENT — {name}", EVENT_COLOR_REFLOAT)

    def _apply_hull_damage(self, vessel, amount: float, source: str) -> None:
        """Subtract hull integrity from a named source, record the amount for the
        game-over cause line, and arm the red on-screen flash.  Triggers game-over
        (attributed to the dominant source) when the hull reaches zero.

        Centralising both damage sites here keeps the on-screen feedback and the
        loss attribution in one place — call sites just say how much and why.
        """
        if amount <= 0.0 or self.game_over:
            return
        before = vessel.hull_integrity
        vessel.hull_integrity = max(0.0, before - amount)
        dealt = before - vessel.hull_integrity
        if dealt <= 0.0:
            return
        self._hull_damage_by_source[source] = (
            self._hull_damage_by_source.get(source, 0.0) + dealt)
        self._hull_damage_flash_until = (
            pygame.time.get_ticks() + HULL_DAMAGE_FLASH_MS)
        if vessel.hull_integrity <= 0.0:
            self._trigger_game_over(self._hull_failure_cause())

    def _hull_failure_cause(self) -> str:
        """Plain-English game-over line naming the dominant hull-damage source.

        Reads the per-source damage tally so the player learns *why* the run
        ended (\"ran aground once too often\" vs \"caught out in heavy seas\")
        instead of a bare \"Hull failure\".
        """
        g = self._hull_damage_by_source.get("grounding", 0.0)
        s = self._hull_damage_by_source.get("storm", 0.0)
        if g <= 0.0 and s <= 0.0:
            return "Hull failure — the sea finally won."
        # Co-causes when neither dominates (within 1.5x of each other).
        if g > 0.0 and s > 0.0 and max(g, s) < 1.5 * min(g, s):
            return "Hull lost — groundings and heavy seas together broke her open."
        if g >= s:
            return "Hull holed — you ran aground once too often."
        return "Hull battered apart — caught out in heavy seas."

    def _trigger_game_over(self, reason: str) -> None:
        """Freeze the sim and show the game-over overlay."""
        if self.game_over:
            return
        self.game_over = True
        self.game_over_reason = reason
        self.sound.play("mayday")
        # A lost run cannot be continued: remove the save so the title
        # screen greys out "Continue" on the next launch.
        delete_save()

    def update_simulation(self, dt: float) -> None:
        """Update the simulation by dt seconds using fixed timesteps.

        Args:
            dt: elapsed time since last frame (variable)
        """
        # Scale real dt into simulated seconds controlled by a single multiplier.
        # `sim_speed` is 0 when paused; otherwise it is the environment multiplier.
        sim_speed = 0.0 if self.is_paused else self.environment.time_speed_multiplier
        scaled_dt = dt * sim_speed * TIME_COMPRESSION

        # If sim_speed == 0, we advance nothing (full freeze).
        if scaled_dt <= 0.0:
            return

        # Accumulate simulated seconds and step the simulation in fixed chunks.
        # The step count is capped at MAX_SIM_STEPS_PER_FRAME: without the cap a
        # single slow frame grows the accumulator, causing the next frame to take
        # even longer — a feedback loop that exhausts the CPU and kills the process.
        self.accumulator += scaled_dt
        steps = 0

        while self.accumulator >= SIM_TIMESTEP and steps < self._max_sim_steps:
            # Weather event detection: snapshot before update, compare after.
            _prev_event = self.environment.active_event_name()
            self.environment.update(SIM_TIMESTEP)
            self.mission_manager.update(SIM_TIMESTEP)
            _new_event  = self.environment.active_event_name()
            if _prev_event != _new_event:
                _t = _sim_time_str(self.environment)
                if _new_event == "squall":
                    self.event_log.add(_t, "SQUALL WARNING — sudden wind and rain",
                                       EVENT_COLOR_WEATHER)
                elif _new_event:
                    self.event_log.add(_t, f"WEATHER — {_new_event.upper()}", EVENT_COLOR_WEATHER)
                else:
                    self.event_log.add(_t, f"Weather event cleared: {_prev_event}",
                                       EVENT_COLOR_WEATHER)

            # Update each vessel using the same simulated timestep.
            for vessel in self.world.vessels:
                # Port stay: count down timer; depart when ready.  The player
                # has no schedule — they stay berthed until the docking menu's
                # DEPART (or W/SPACE), so the timer countdown is skipped.
                _was_in_port = vessel.status == "in_port"
                if vessel.status == "in_port" and not getattr(vessel, 'is_player', False):
                    vessel.update_route(SIM_TIMESTEP, self.world)
                # Departure detected → generate mission for relevant vessel types.
                if _was_in_port and vessel.status == "underway":
                    if vessel.vessel_type in ("cargo", "tanker"):
                        next_port = self._find_next_port_in_route(vessel)
                        if next_port:
                            if random.random() < 0.30:
                                self.mission_manager.generate_mission(
                                    "cargo_deadline", vessel,
                                    next_port.position, next_port.name)
                            else:
                                self.mission_manager.generate_mission(
                                    "delivery", vessel,
                                    next_port.position, next_port.name)
                    elif vessel.vessel_type == "ferry":
                        next_port = self._find_next_port_in_route(vessel)
                        if next_port:
                            self.mission_manager.generate_mission(
                                "passenger_pickup", vessel,
                                next_port.position, next_port.name)
                    elif vessel.name == "CG Sentinel":
                        next_port = self._find_next_port_in_route(vessel)
                        if next_port:
                            self.mission_manager.generate_mission(
                                "patrol", vessel, next_port.position, next_port.name)
                    elif (vessel.vessel_type == "sailboat"
                            and vessel.name in ("SY Blue Horizon", "SY Windward")):
                        target = vessel.destination
                        if target:
                            port_name = "next anchorage"
                            for _p in self.world.ports:
                                if (abs(target[0] - _p.position[0]) < 2
                                        and abs(target[1] - _p.position[1]) < 2):
                                    port_name = _p.name
                                    break
                            self.mission_manager.generate_mission(
                                "vip_cruise", vessel, target, port_name)

                _is_player = getattr(vessel, 'is_player', False)

                if _is_player:
                    # Player vessel: heading controlled by held turn keys each sim step.
                    if not self.settings_panel.is_visible:
                        _keys = pygame.key.get_pressed()
                        _turn = 0.0
                        if _keys[self.keys["helm_left"]] or _keys[pygame.K_LEFT]:
                            _turn -= PLAYER_TURN_RATE
                        if _keys[self.keys["helm_right"]] or _keys[pygame.K_RIGHT]:
                            _turn += PLAYER_TURN_RATE
                        if _turn:
                            # Manual helm always wins: reclaim control from any AI
                            # avoidance state, cancel the autopilot, then steer.
                            if vessel.status == "avoiding":
                                vessel.status = "underway"
                            if vessel.status == "underway":
                                vessel.autopilot_destination = None
                                vessel.heading = (vessel.heading + _turn * SIM_TIMESTEP) % 360.0

                    _pt = _sim_time_str(self.environment)

                    # Autopilot: steer toward the right-click waypoint using the
                    # vessel's real rudder model; clear on arrival.
                    if (vessel.autopilot_destination is not None
                            and vessel.status == "underway"):
                        _ap = vessel.autopilot_destination
                        vessel.turn_toward(vessel.bearing_to(_ap), SIM_TIMESTEP)
                        if vessel.distance_to(_ap) <= ARRIVAL_DISTANCE:
                            vessel.autopilot_destination = None
                            self.event_log.add(_pt, "Waypoint reached",
                                               EVENT_COLOR_WEATHER)

                    # Charter clause: passenger comfort caps speed at 10 kn
                    # everywhere for the duration of the contract.
                    _charter_c = self.job_board.active
                    if (_charter_c is not None
                            and _charter_c.job_type == "charter"
                            and vessel.target_speed > CHARTER_MAX_SPEED_KN):
                        vessel.target_speed = CHARTER_MAX_SPEED_KN

                    # Departure grace: re-enable proximity docking only after
                    # the player has cleared the port they just cast off from.
                    if self._departed_port is not None:
                        _near = vessel._port_at(vessel.position, self.world)
                        if _near is None or _near.name != self._departed_port:
                            self._departed_port = None

                    # Proximity docking: drifting into a port radius at low
                    # speed berths the ship — no destination click required.
                    # "avoiding" counts too: collision-avoidance near a busy port
                    # must not lock a slow, careful approach out of docking.
                    if (vessel.status in ("underway", "avoiding")
                            and vessel.current_speed <= PLAYER_DOCKING_MAX_SPEED_KN
                            and vessel.target_speed <= PLAYER_DOCKING_MAX_SPEED_KN):
                        _dock_port = vessel._port_at(vessel.position, self.world)
                        # Draft restriction: shallow anchorages refuse deep hulls.
                        # Tier 3 (Captain) reputation earns special clearance.
                        if (_dock_port is not None
                                and _dock_port.max_draft_m is not None
                                and vessel.draft_m >= _dock_port.max_draft_m
                                and self.career.reputation < REP_TIER_3):
                            if _dock_port.name != self._departed_port:
                                self.event_log.add(
                                    _pt,
                                    f"REFUSED — draft too deep for {_dock_port.name}",
                                    EVENT_COLOR_MAYDAY)
                                # Reuse the departure grace so the refusal
                                # doesn't repeat every sim step in the radius.
                                self._departed_port = _dock_port.name
                            _dock_port = None
                        if (_dock_port is not None
                                and _dock_port.name != self._departed_port):
                            vessel.status = "in_port"
                            vessel.current_speed = 0.0
                            vessel.target_speed = 0.0
                            vessel._docked_port_name = _dock_port.name
                            vessel.position = _dock_port.claim_berth(
                                vessel.name, vessel.position)
                            self.event_log.add(
                                _pt, f"Docked at {_dock_port.name}",
                                EVENT_COLOR_WEATHER)
                            self._on_player_docked(vessel)

                    # Storm: cap speed and apply hull damage each step.
                    if vessel.status == "underway":
                        if self.environment.wave_height > STORM_WAVE_THRESHOLD:
                            if vessel.target_speed > STORM_MAX_SPEED_KN:
                                vessel.target_speed = STORM_MAX_SPEED_KN
                            if not self._storm_speed_warning_sent:
                                self._storm_speed_warning_sent = True
                                self.event_log.add(
                                    _pt,
                                    "WARNING — heavy seas, speed capped to 6 kn",
                                    EVENT_COLOR_WEATHER)
                            self._apply_hull_damage(
                                vessel, STORM_HULL_DAMAGE_RATE * SIM_TIMESTEP,
                                "storm")
                        else:
                            self._storm_speed_warning_sent = False

                    # Zone violation: warn once on entry, fine every 30 s after 10 s grace.
                    if vessel.status in ("underway", "avoiding"):
                        _viol_zone = None
                        for _z in self.world.get_zones_containing(vessel.position):
                            if _z.kind == "no_entry":
                                _viol_zone = _z
                                break
                            if (_z.speed_limit is not None
                                    and vessel.current_speed > _z.speed_limit):
                                _viol_zone = _z
                        if _viol_zone is not None:
                            self._zone_timer += SIM_TIMESTEP
                            self._zone_fine_cooldown = max(
                                0.0, self._zone_fine_cooldown - SIM_TIMESTEP)
                            if not self._zone_warning_sent:
                                self._zone_warning_sent = True
                                self.sound.play("warning")
                                self.event_log.add(
                                    _pt,
                                    f"WARNING — entering restricted zone: {_viol_zone.name}",
                                    EVENT_COLOR_MAYDAY)
                            # Training wheels: the onboarding tutorial warns but
                            # never fines — a learning captain isn't bankrupted
                            # by the Maren approach speed limit on their first run.
                            if (self._zone_timer >= 10.0
                                    and self._zone_fine_cooldown <= 0.0
                                    and not self._tutorial_active):
                                _fine = (ZONE_FINE_NO_ENTRY
                                         if _viol_zone.kind == "no_entry"
                                         else ZONE_FINE_SPEED)
                                # Hazmat clause: dangerous cargo doubles every
                                # zone fine for the duration of the contract.
                                _active_c = self.job_board.active
                                if (_active_c is not None
                                        and _active_c.job_type == "hazmat"):
                                    _fine *= HAZMAT_FINE_MULT
                                # Difficulty preset scales fines (Easy 0.5x / Hard 1.5x).
                                _fine *= self.settings.fine_multiplier()
                                self.career.force_spend(
                                    _fine, f"Zone fine: {_viol_zone.name}")
                                self.career.fines_paid += _fine
                                self.event_log.add(
                                    _pt,
                                    f"FINE — \xa3{_fine:.0f} zone violation",
                                    EVENT_COLOR_MAYDAY)
                                self._zone_fine_cooldown = ZONE_FINE_INTERVAL_S
                        else:
                            self._zone_timer = 0.0
                            self._zone_warning_sent = False
                else:
                    # Navigation priority: MOB > trawling/anchoring > avoidance > normal.
                    if vessel.mob_timer > 0:
                        vessel.mob_timer = max(0.0, vessel.mob_timer - SIM_TIMESTEP)
                        if vessel.mob_timer > 0:
                            vessel.target_speed = MOB_SEARCH_SPEED_KN
                            vessel.turn_toward(vessel.bearing_to(vessel.mob_position), SIM_TIMESTEP)
                        else:
                            # Search complete — restore speed and hand back to schedule.
                            vessel.mob_position = None
                            vessel.target_speed = vessel.max_speed
                            if vessel.route:
                                vessel.destination = vessel.route[vessel.route_index]
                    elif vessel.trawling_timer > 0:
                        # Trawling (fishing) or anchoring (sailboat) pause at open-sea WP.
                        vessel.trawling_timer = max(0.0, vessel.trawling_timer - SIM_TIMESTEP)
                        if vessel.trawling_timer > 0:
                            if vessel.mission_type == "fishing_trip":
                                vessel.target_speed = TRAWL_SPEED_KN
                                vessel.trawling_heading_timer -= SIM_TIMESTEP
                                if vessel.trawling_heading_timer <= 0:
                                    vessel.heading = (vessel.heading + random.uniform(-40, 40)) % 360
                                    vessel.trawling_heading_timer = TRAWL_WANDER_INTERVAL_S
                            else:  # sailing_cruise anchor stop
                                vessel.target_speed = 0.0
                        else:
                            # Pause complete — restore speed and resume route.
                            vessel.trawling_heading_timer = 0.0
                            vessel.target_speed = vessel.max_speed
                            _set_underway_mission_status(vessel)
                            if vessel.route:
                                vessel.destination = vessel.route[vessel.route_index]
                    elif vessel.status == "avoiding":
                        vessel.turn_toward(vessel.avoid_heading, SIM_TIMESTEP)
                    elif vessel.destination and vessel.status == "underway":
                        target_bearing = vessel.bearing_to(vessel.destination)
                        vessel.turn_toward(target_bearing, SIM_TIMESTEP)
                        # Approach slowdown: bleed speed within 3 wu of destination.
                        # The else branch restores cruise speed once outside the zone
                        # so target_speed never stays pinned at 2 kn after a waypoint pass.
                        dist_to_dest = vessel.distance_to(vessel.destination)
                        if dist_to_dest < ARRIVAL_DISTANCE * 3:
                            vessel.target_speed = max(2.0, vessel.current_speed * 0.3)
                        elif vessel.target_speed < vessel.max_speed:
                            vessel.target_speed = vessel.max_speed

                    # Smart captain decisions: weather, fuel efficiency, traffic, port congestion.
                    _apply_smart_decisions(
                        vessel, self.world, self.environment,
                        _sim_time_str(self.environment),
                        self._vessel_smart_state.setdefault(id(vessel), {}),
                    )

                    # Zone speed enforcement — hard cap applied after AI decisions.
                    # Finds the most restrictive speed limit among all zones the vessel
                    # is currently inside; overrides any higher target_speed.
                    if vessel.status in ("underway", "avoiding"):
                        _zone_limit = None
                        for _zone in self.world.zones:
                            if (_zone.speed_limit is not None
                                    and _zone.contains(vessel.position)):
                                if _zone_limit is None or _zone.speed_limit < _zone_limit:
                                    _zone_limit = _zone.speed_limit
                        if _zone_limit is not None and vessel.target_speed > _zone_limit:
                            vessel.target_speed = _zone_limit

                # Mood timer advance — once per sim step per vessel.
                _mt = _sim_time_str(self.environment)
                if vessel.status in ("underway", "avoiding"):
                    vessel._underway_timer += SIM_TIMESTEP
                    vessel._port_rest_timer = 0.0
                    if (vessel._underway_timer >= MOOD_TIRED_AFTER_S
                            and vessel.mood not in ("tired", "stressed")):
                        vessel.mood = "tired"
                        vessel.log_decision(_mt, "Long watch — fatigue setting in")
                    elif (vessel._underway_timer >= MOOD_CONFIDENT_AFTER_S
                            and vessel.mood == "normal"):
                        vessel.mood = "confident"
                        vessel.log_decision(_mt, "Smooth passage — running with confidence")
                elif vessel.status == "in_port":
                    vessel._port_rest_timer += SIM_TIMESTEP
                    vessel._underway_timer = 0.0
                    if (vessel._port_rest_timer >= MOOD_RESTED_AFTER_S
                            and vessel.mood in ("tired", "stressed")):
                        vessel.mood = "normal"
                        vessel.log_decision(_mt, "Rested — crew refreshed")

                # Speed and movement (both methods respect status internally).
                _was_adrift = vessel.status == "adrift"
                vessel.update_speed(SIM_TIMESTEP, self.environment)
                _t = _sim_time_str(self.environment)
                vessel.move(SIM_TIMESTEP, self.environment,
                            world=self.world, sim_time=_t)
                # Fuel-exhaustion distress: ship.py sets distress=True when fuel
                # hits zero away from a port.  Fire event_log and mission_manager
                # here (ship.py cannot access them) on the first tick only.
                if (not _was_adrift
                        and vessel.status == "adrift"
                        and vessel.distress
                        and vessel.fuel is not None and vessel.fuel == 0.0):
                    self.event_log.add(
                        _t, f"MAYDAY — {vessel.name} FUEL EXHAUSTED",
                        EVENT_COLOR_MAYDAY)
                    if _is_player:
                        self.sound.play("mayday")
                    self.mission_manager.generate_mission(
                        "rescue", vessel, vessel.position)

                # Arrival check: fire for "underway" and "avoiding" so a vessel that
                # reaches a port during avoidance still docks correctly.
                if (vessel.status in ("underway", "avoiding")
                        and vessel.destination
                        and vessel.at_destination(vessel.destination, tolerance=PORT_DETECT_RADIUS)):
                    # SAR rescue completion: if this vessel was dispatched as a rescuer,
                    # refloat the grounded vessel before resuming its own route.
                    if vessel.player_commanded:
                        for grounded in self.world.vessels:
                            if (grounded is not vessel
                                    and grounded.distress
                                    and grounded.rescue_vessel is vessel
                                    and grounded.status in ("aground", "adrift")):
                                _sar_refloat(grounded, self.event_log,
                                             _sim_time_str(self.environment))
                                break
                    _was_player_cmd = vessel.player_commanded
                    vessel.arrive(self.world)
                    # Career hook: player docked at a port.
                    if _is_player and vessel.status == "in_port":
                        self._on_player_docked(vessel)
                    # Advance any pending multi-hop player path (from find_safe_path).
                    _vid = id(vessel)
                    if _was_player_cmd and _vid in self._pending_player_paths:
                        _remaining = self._pending_player_paths[_vid]
                        vessel.destination = _remaining[0]
                        vessel.player_commanded = True  # keep commanding
                        if len(_remaining) > 1:
                            self._pending_player_paths[_vid] = _remaining[1:]
                        else:
                            del self._pending_player_paths[_vid]
                    # Mission hooks on arrival
                    if vessel.mission_type:
                        if vessel.status == "in_port":
                            vessel.port_visit_count += 1
                            _set_port_mission_status(vessel)
                        elif vessel.status == "underway" and not _was_player_cmd:
                            _start_waypoint_pause(vessel)
                    # Restore cruise speed after passing through a non-port waypoint.
                    # trawling_timer > 0 means a fishing/sailing pause was just started;
                    # don't override that.  mob_timer guard is a safety belt.
                    if (vessel.status == "underway"
                            and vessel.trawling_timer <= 0
                            and vessel.mob_timer <= 0):
                        vessel.target_speed = vessel.max_speed

                # Grounding check — skip in_port and docked vessels.
                # For aground vessels: check tide refloating before skipping.
                if vessel.status in ("in_port", "docked"):
                    continue
                if vessel.status == "aground":
                    # SAR distress timer
                    if vessel.distress:
                        vessel.distress_timer += SIM_TIMESTEP
                    # Tide refloating: depth now exceeds required UKC
                    depth = self.world.water_depth_at(
                        vessel.position, self.environment.tide_level
                    )
                    if depth >= vessel.draft_m + DRAFT_SAFETY_MARGIN_M:
                        _sar_refloat(vessel, self.event_log,
                                     _sim_time_str(self.environment))
                    continue
                # Skip vessels inside a port approach zone (no false groundings).
                if vessel._port_at(vessel.position, self.world) is not None:
                    continue
                depth = self.world.water_depth_at(
                    vessel.position, self.environment.tide_level
                )
                # Training wheels: the player can't run aground during the
                # guided tutorial — the green route already keeps them in deep
                # water; this just forgives a stray first-timer.
                if (depth < vessel.draft_m + DRAFT_SAFETY_MARGIN_M
                        and not (_is_player and self._tutorial_active)):
                    vessel.status = "aground"
                    vessel.current_speed = 0.0
                    vessel.distress = True   # triggers SAR dispatch next step
                    vessel.mood = "stressed"
                    # Keep only the most recent groundings — this list is scanned
                    # every smart-decision tick, so it must not grow unbounded over
                    # a long session of repeated AI groundings.
                    _gp = vessel.memory["grounded_positions"]
                    _gp.append(vessel.position)
                    if len(_gp) > 12:
                        del _gp[:-12]
                    _t = _sim_time_str(self.environment)
                    self.event_log.add(_t, f"MAYDAY — {vessel.name} AGROUND", EVENT_COLOR_MAYDAY)
                    if _is_player:
                        self.sound.play("mayday")
                    vessel.log_decision(_t, "AGROUND — sending distress signal")
                    self.mission_manager.generate_mission(
                        "rescue", vessel, vessel.position)
                    # Player hull damage on grounding.
                    if _is_player:
                        self._apply_hull_damage(
                            vessel,
                            GROUNDING_HULL_DAMAGE * self.settings.damage_multiplier(),
                            "grounding")
                        self.event_log.add(
                            _t,
                            f"HULL DAMAGE — integrity {vessel.hull_integrity * 100:.0f}%",
                            EVENT_COLOR_MAYDAY)
                        if (not self.game_over
                                and vessel.hull_integrity > LUCKY_ESCAPE_HULL_MIN):
                            self._award_achievement("Lucky Escape")

            # Career deadline check — once per sim step for the player vessel only.
            if self.player_vessel is not None:
                _expired = self.job_board.check_deadline(self.mission_manager.sim_elapsed_s)
                if _expired is not None:
                    self.job_board.fail_active(self.career)
                    self.event_log.add(
                        _sim_time_str(self.environment),
                        f"Contract DEADLINE MISSED — {_expired.contract_id}",
                        EVENT_COLOR_MAYDAY)

            # Game-over checks — player only.
            if self.player_vessel is not None and not self.game_over:
                if self.career.money < -500.0:
                    self._trigger_game_over(
                        "Bankrupt — the company repossessed MV Velawind.")

            # Random sudden events: each underway vessel has a small per-step chance.
            for vessel in self.world.vessels:
                if vessel.status != "underway":
                    continue
                if vessel.distress or vessel.engine_failure or vessel.mob_timer > 0:
                    continue
                if random.random() < RANDOM_EVENT_PROBABILITY * SIM_TIMESTEP:
                    _trigger_random_event(vessel, self.world, self.environment, self.event_log)
                    if vessel.distress:
                        self.mission_manager.generate_mission(
                            "rescue", vessel, vessel.position)

            # SAR dispatch: assign nearest eligible vessel to each unrescued casualty.
            _t = _sim_time_str(self.environment)
            _sar_dispatch(
                self.world.vessels,
                SAR_DISPATCH_RANGE_NM * KNOTS_TO_UNITS_PER_HOUR,
                self.event_log, _t,
                player_paths=self._pending_player_paths,
                world=self.world,
            )

            # Mission completion check (once per sim step, not per vessel loop).
            self.mission_manager.check_completion(self.world, PORT_DETECT_RADIUS)

            # Party yacht system — runs once per sim step.
            self._update_party_system(SIM_TIMESTEP)

            self.accumulator -= SIM_TIMESTEP
            steps += 1

        # Discard any excess accumulated time after the cap to prevent it from
        # carrying over and demanding even more steps next frame.
        if steps >= self._max_sim_steps:
            self.accumulator = 0.0

        self.last_sim_steps = steps

        # Docking menu visibility mirrors the player's port status — updated
        # after the sim steps so it's consistent the moment the player docks.
        if self.player_vessel is not None:
            self.docking_menu.visible = (
                self.player_vessel.status == "in_port" and not self.game_over)

        # Collision avoidance runs once per real frame (not per sim step).
        # Running it inside the loop at 375× per frame was the crash cause at 3×
        # speed — the O(n²) pair scan repeated hundreds of times per frame.
        # One call per frame is sufficient: positions update smoothly at 60 FPS.
        if IS_WEB:
            # Halve the O(n²) pair scan on web: 15 Hz avoidance at 30 fps is ample
            # for ambient traffic and leaves more of the frame budget for rendering.
            self._collision_frame ^= 1
            if self._collision_frame == 0:
                update_collision_avoidance(self.world.vessels)
        else:
            update_collision_avoidance(self.world.vessels)

        # Onboarding step progression (once per frame, reads live player state).
        self._update_tutorial()
        # Cosmetic voyage flavour in the event log (throttled, de-duped).
        self._update_voyage_flavor()

        # Update the camera follow target (if any)
        self.camera.update_follow()

    def render(self) -> None:
        """Render the current frame."""
        # Engine hum tracks the player's actual way through the water.
        if self.player_vessel is not None:
            _eng_spd = (self.player_vessel.current_speed
                        if self.player_vessel.status == "underway" else 0.0)
            self.sound.update_engine(_eng_spd)

        # Hover detection: nearest vessel within click radius, excluding selected.
        mouse_pos = pygame.mouse.get_pos()
        world_pos = self.camera.screen_to_world(mouse_pos)
        threshold = SHIP_SELECT_RADIUS / self.camera.zoom
        self.hover_vessel = None
        for vessel in self.world.vessels:
            if vessel is self.selected_vessel:
                continue
            if vessel.distance_to(world_pos) < threshold:
                self.hover_vessel = vessel
                break
        # Fog disables the AIS hover aid — can't identify what you can't see.
        if self.environment.visibility < FOG_LOW_VIS_THRESHOLD_M:
            self.hover_vessel = None

        # Inset the Y-axis grid labels past the fleet panel (left edge, x=20,
        # WIDTH wide) when it's showing, so the panel can't clip them; else hug
        # the left edge.  The fleet panel is drawn whenever settings is hidden.
        _fleet_visible = not self.settings_panel.is_visible
        _y_label_x = (20 + self.fleet_panel.WIDTH + 8) if _fleet_visible else 4
        # Web: keep chart labels out from under the vessel-info column so they
        # can't ghost through its translucent card (see chart.label_occluders).
        if IS_WEB:
            if self.selected_vessel is not None:
                _vw, _vh = self.display.get_size()
                _pw = min(ui_px(360), max(ui_px(280), _vw - ui_px(40)))
                self.chart.label_occluders = [pygame.Rect(
                    _vw - _pw - ui_px(40), 0, _pw + ui_px(40), _vh)]
            else:
                self.chart.label_occluders = []
        _prof = self._prof   # None on desktop -> all timing branches skipped
        _c = time.perf_counter() if _prof is not None else 0.0
        self.chart.draw_all(world=self.world, environment=self.environment,
                            selected_vessel=self.selected_vessel,
                            hover_vessel=self.hover_vessel,
                            y_label_x=_y_label_x)
        if _prof is not None:
            _ce = time.perf_counter()      # chart end / panels start
            _prof.chart += _ce - _c

        # Hull-damage feedback sits over the chart but under the panels, so the
        # red flash never obscures the HUD's own (crisp) hull bar.
        self._draw_hull_feedback()

        # Always-on objective marker pointing at the active contract's
        # destination — the single clear "go here" cue (on-screen marker +
        # dashed line, or an edge arrow when the port is off-screen).
        _ac = self.job_board.active
        if _ac is not None and self.player_vessel is not None:
            _dest = self.world.find_port(_ac.to_port)
            if _dest is not None:
                # Focus dim first so the green destination + route (drawn next)
                # are the brightest things on screen and the traffic recedes.
                self.chart.draw_focus_dim()
                _dist_nm = (self.player_vessel.distance_to(_dest.position)
                            * NM_PER_WORLD_UNIT)
                # During the tutorial the guide line follows the safe waypoint
                # route (remaining legs); otherwise it points straight at the port.
                _route = (self._tutorial_route[self._tutorial_wp_index:]
                          if self._tutorial_active and self._tutorial_route
                          else None)
                _obj_label = f"{_ac.to_port} — \xa3{_ac.payout:,.0f}"
                self.chart.draw_objective(self.player_vessel.position,
                                          _dest.position, _obj_label, _dist_nm,
                                          route=_route)

        # Draw UI panels
        self.vessel_info_panel.draw(self.selected_vessel, self.environment, self.world)  # Phase 2
        self.tech_systems_panel.draw(self.world, self.environment, self.selected_vessel)  # Phase 3
        self.settings_panel.draw(self.environment, self.sound)  # Phase 4
        self.event_log.draw()
        if not self.settings_panel.is_visible:
            self.fleet_panel.draw(self.world, self.selected_vessel)
        # Mission panel lifts above the minimap when both occupy bottom-right.
        _mm_offset = (MINIMAP_HEIGHT_PX + MINIMAP_MARGIN_PX
                      if self.minimap.is_visible else 0)
        self.mission_panel.draw(self.mission_manager,
                                self.mission_manager.sim_elapsed_s,
                                bottom_offset=_mm_offset)
        self.mission_manager.clear_if_expired()
        # Web: the minimap and the vessel-info card contend for the bottom-right
        # corner (the map clipped the card's log text — caught in the preview
        # harness), so the minimap yields while a detail card is open.
        _minimap_hidden = IS_WEB and self.selected_vessel is not None
        if not self.settings_panel.is_visible and not _minimap_hidden:
            self.minimap.draw(self.world, self.player_vessel)
        self.player_hud.draw(
            self.player_vessel,
            career=self.career,
            zone_violation=self._zone_warning_sent,
            frame_count=pygame.time.get_ticks() // 250,
            low_visibility=self.environment.visibility < FOG_LOW_VIS_THRESHOLD_M,
            active_contract=self.job_board.active,
            world=self.world,
            throttle_flash=pygame.time.get_ticks() < self._throttle_flash_until,
        )
        if not self.settings_panel.is_visible:
            self.career_panel.draw(self.career, self.job_board,
                                   self.mission_manager.sim_elapsed_s)
            if self.player_vessel is not None:
                self.docking_menu.draw(
                    self.player_vessel,
                    self.player_vessel._docked_port_name or "IN PORT",
                    self.career, job_board=self.job_board)

        # Onboarding card — drawn above the chart/HUD so the next step is always
        # readable, but hidden behind the settings panel.
        if (self._tutorial_active and not self.career.tutorial_complete
                and not self.settings_panel.is_visible):
            self.tutorial_overlay.draw(self._tutorial_step)

        # Reward banners — fade out, pruned once past their lifetime.  Drawn on
        # top of everything except the game-over overlay.
        if self._banners:
            _now = pygame.time.get_ticks()
            self._banners = [b for b in self._banners
                             if _now - b["start_ms"] <= BANNER_DURATION_MS]
            self.reward_banner.draw(self._banners, _now)

        if self.game_over:
            self._game_over_screen.draw(
                self.game_over_reason, self.career,
                time.time() - self._session_start_time)

        # On-screen perf overlay (web only): tiny fps/ms readout top-right, just
        # below the status bar, plus a second line with the per-frame bucket
        # breakdown "sim · chart · ui · flip · idle" averaged over the same ~1 s
        # window.  fps counts RENDERED frames (the 30 fps cap skips rAF ticks
        # without touching these counters); 'idle' = wall time between rendered
        # frames minus measured work — under the cap it reads ~budget-work by
        # design.  Text re-rendered once per second (through the text cache);
        # per-frame cost is two small blits.  Screenshots carry it all.
        if WEB_HUD_PERF and self._hud_perf_font is not None:
            self._hud_perf_frames += 1
            _now_s = time.perf_counter()
            _elapsed = _now_s - self._hud_perf_t0
            if _elapsed >= 1.0:
                _fps = self._hud_perf_frames / _elapsed
                _txt = f"{_fps:.0f} fps · {1000.0 / _fps:.0f} ms" if _fps > 0 else "-- fps"
                from render import theme
                self._hud_perf_surf = self._hud_perf_font.render(
                    _txt, True, theme.FPS_COLOR)
                if self._prof is not None:
                    _line = self._prof.hud_line()
                    self._hud_prof_surf = (self._hud_perf_font.render(
                        _line, True, theme.FPS_COLOR) if _line else None)
                self._hud_perf_frames = 0
                self._hud_perf_t0 = _now_s
            if self._hud_perf_surf is not None:
                _pw = self.display.get_width()
                _py = ui_px(46)
                self.display.blit(
                    self._hud_perf_surf,
                    (_pw - self._hud_perf_surf.get_width() - ui_px(10), _py))
                if self._hud_prof_surf is not None:
                    self.display.blit(
                        self._hud_prof_surf,
                        (_pw - self._hud_prof_surf.get_width() - ui_px(10),
                         _py + self._hud_perf_surf.get_height() + ui_px(2)))

        if _prof is not None:
            _pe = time.perf_counter()      # panels end / flip start
            _prof.panels += _pe - _ce
        pygame.display.flip()
        if _prof is not None:
            _prof.flip += time.perf_counter() - _pe

    def _draw_hull_feedback(self) -> None:
        """In-play hull-damage legibility: a brief red screen flash on a fresh
        hit, plus a persistent pulsing HULL CRITICAL banner while integrity sits
        in the danger band.  Reads vessel state only — pure feedback, no mutation.
        """
        pv = self.player_vessel
        if pv is None or self.game_over:
            return
        now = pygame.time.get_ticks()
        vw, vh = self.display.get_size()

        # Red flash: alpha decays linearly to zero over HULL_DAMAGE_FLASH_MS.
        if now < self._hull_damage_flash_until:
            frac = (self._hull_damage_flash_until - now) / HULL_DAMAGE_FLASH_MS
            alpha = int(HULL_DAMAGE_FLASH_MAX_ALPHA * max(0.0, min(1.0, frac)))
            if alpha > 0:
                s = pygame.Surface((vw, vh), pygame.SRCALPHA)
                s.fill((*HULL_DAMAGE_FLASH_COLOR, alpha))
                self.display.blit(s, (0, 0))

        # Persistent banner once the hull is at/below the critical threshold.
        hull = getattr(pv, "hull_integrity", 1.0)
        if hull <= HULL_CRITICAL_THRESHOLD:
            pulse = (now // 400) % 2 == 0      # ~1.25 Hz blink — impossible to miss
            col = COLOR_WARNING if pulse else (120, 30, 30)
            line = self._hull_warn_font.render("HULL CRITICAL", True, col)
            sub = self._hull_warn_sub_font.render(
                f"integrity {hull * 100:.0f}% — make port and repair",
                True, (230, 200, 200))
            by = int(vh * 0.16)
            self.display.blit(line, (vw // 2 - line.get_width() // 2, by))
            self.display.blit(sub, (vw // 2 - sub.get_width() // 2,
                                    by + line.get_height() + 4))

    def _title_loop(self) -> str:
        """Run the title menu until the player confirms an action.

        The simulation keeps ticking underneath so the chart background is
        alive (AI vessels sail their routes).  Returns "new", "continue",
        or "quit".
        """
        # Never run this blocking loop under WebAssembly — it would freeze the
        # browser tab.  The web path skips the call site too; this is a backstop.
        if IS_WEB:
            return "new"
        title = TitleScreen(self.display)
        while True:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            has_save = os.path.exists(SAVE_FILEPATH)
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "quit"
                elif event.type == pygame.KEYDOWN:
                    action = title.handle_key(event.key, has_save)
                    if action == "settings":
                        self._run_settings_screen()
                    elif action is not None:
                        return action
                elif event.type == pygame.MOUSEMOTION:
                    title.handle_motion(event.pos)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    action = title.handle_click(event.pos, has_save)
                    if action == "settings":
                        self._run_settings_screen()
                    elif action is not None:
                        return action

            # A window-close inside the Settings sub-screen sets self.running
            # False; honour it here so the title doesn't keep looping.
            if not self.running:
                return "quit"

            self.update_simulation(dt)
            self.chart.draw_all(world=self.world, environment=self.environment)
            title.surface = self.display   # follow any display re-init from settings
            title.draw(has_save, mouse_pos)
            pygame.display.flip()

    def _run_settings_screen(self) -> None:
        """Run the settings screen modally until Back, then persist settings.json.

        Reused by the title menu and the in-game pause menu.  Volume changes
        apply live (Stage 3); the chart stays drawn underneath, but the sim does
        not advance — settings is a modal sub-screen.
        """
        # Blocking modal loop — never reachable on web (title/pause are skipped),
        # but guarded so it can never freeze a browser tab.
        if IS_WEB:
            return
        screen = SettingsScreen(self.display)
        while True:
            self.clock.tick(TARGET_FPS)
            mouse_pos = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    return
                elif event.type == pygame.KEYDOWN:
                    result = screen.handle_key(event.key, self.settings)
                    if result == "rebind":
                        self._rebuild_keybinds()   # remap drives input immediately
                    elif result == "back":
                        self._exit_settings(screen)
                        return
                elif event.type == pygame.MOUSEMOTION:
                    screen.handle_motion(event.pos)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    screen.end_drag()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if screen.handle_click(event.pos, self.settings) == "back":
                        self._exit_settings(screen)
                        return
            # Live-apply audio volumes each frame (cheap, idempotent).
            self.sound.set_volumes(self.settings.master_volume,
                                   self.settings.sfx_volume,
                                   self.settings.music_volume)
            # Keep this screen pointed at the live surface (display may have just
            # been re-created by an earlier display change).
            screen.surface = self.display
            self.chart.draw_all(world=self.world, environment=self.environment)
            screen.draw(self.settings, mouse_pos)
            pygame.display.flip()

    def _exit_settings(self, screen) -> None:
        """Persist settings on leaving; re-init the display if resolution or
        fullscreen changed (camera + panels rebuilt without losing game state)."""
        self.settings.save()
        if getattr(screen, "_display_dirty", False):
            self._apply_display_settings()

    def _apply_display_settings(self) -> None:
        """Re-create the window from the current display settings and re-point the
        camera viewport + every panel + the chart at the new surface, WITHOUT
        losing game state.  Size-keyed caches (chart depth layer, etc.) rebuild
        on the new dimensions."""
        self.display, w, h = self._create_display()
        self.camera.viewport_width = w
        self.camera.viewport_height = h
        self.chart.surface = self.display
        for panel in (self.vessel_info_panel, self.tech_systems_panel,
                      self.settings_panel, self.event_log, self.fleet_panel,
                      self.mission_panel, self.player_hud, self.career_panel,
                      self.docking_menu, self.minimap, self.tutorial_overlay,
                      self.reward_banner, self._game_over_screen):
            panel.surface = self.display

    def _run_pause_menu(self) -> None:
        """Modal in-game pause menu (Esc): Resume / Settings / Save & Quit to
        Title.  Freezes the sim (it never ticks update_simulation here); Settings
        reuses the settings screen; Save & Quit persists the career and returns
        to the title with the save intact (Continue then loads it)."""
        # Blocking modal loop — on web Esc deselects instead (see handle_events);
        # this backstop guarantees the browser tab can never freeze here.
        if IS_WEB:
            return
        menu = PauseMenu(self.display)
        # Remember the speed so Resume restores it (a 2x/3x selection isn't lost).
        prev_speed = self.environment.time_speed_multiplier
        self.is_paused = True
        self.environment.time_speed_multiplier = 0.0
        while True:
            self.clock.tick(TARGET_FPS)
            mouse_pos = pygame.mouse.get_pos()
            chosen = None
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    return
                elif event.type == pygame.KEYDOWN:
                    chosen = menu.handle_key(event.key)
                elif event.type == pygame.MOUSEMOTION:
                    menu.handle_motion(event.pos)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    chosen = menu.handle_click(event.pos)
                if chosen:
                    break

            if chosen == "resume":
                self.is_paused = False
                # Restore the pre-pause speed (preserve 2x/3x); fall back to 1x
                # if the player had manually paused before opening the menu.
                self.environment.time_speed_multiplier = prev_speed if prev_speed > 0 else 1.0
                return
            if chosen == "settings":
                self._run_settings_screen()        # may re-init the display
                menu.surface = self.display
            elif chosen == "quit_title":
                if self.player_vessel is not None:
                    save_career(self.career,
                                hull_integrity=self.player_vessel.hull_integrity)
                self._restart_requested = True     # main() builds a fresh Game -> title
                self.running = False
                return

            self.chart.draw_all(world=self.world, environment=self.environment)
            menu.surface = self.display
            menu.draw(mouse_pos)
            pygame.display.flip()

    def _load_save(self) -> None:
        """Restore career state and player hull from save.json.

        A None result (missing/corrupt/wrong-version file) leaves the fresh
        default career untouched — equivalent to starting a new career.
        """
        data = load_career()
        if data is None:
            return
        self.career.money             = data["money"]
        self.career.reputation        = data["reputation"]
        self.career.total_deliveries  = data["total_deliveries"]
        self.career.total_distance_nm = data["total_distance_nm"]
        self.career.fines_paid        = data["fines_paid"]
        self.career.hull_repairs_paid = data["hull_repairs_paid"]
        self.career.achievements      = set(data.get("achievements", []))
        # .get() so saves written before the flag existed still load cleanly.
        self.career.tutorial_complete = bool(data.get("tutorial_complete", False))
        if self.player_vessel is not None:
            self.player_vessel.hull_integrity = data["hull_integrity"]

    def _begin_tutorial(self) -> None:
        """Open the guided first-five-minutes onboarding for a new captain.

        Zooms in close on the player, follows them, and boards a guaranteed,
        pre-accepted Maren→Saltgate delivery (the nearest port, ~29 nm) so the
        first payout lands fast.  Step progression is tracked per frame in
        _update_tutorial(); the persistent flag is set on completion.
        """
        pv = self.player_vessel
        if pv is None:
            return
        self._tutorial_active = True
        self._tutorial_step = 0
        # Close, ship-filling framing so the player ship reads as "you".
        self.camera.zoom = max(ZOOM_MIN, min(ZOOM_MAX, TUTORIAL_START_ZOOM))
        self.camera.set_follow_target(pv)
        # Guaranteed, pre-accepted first delivery.
        self.job_board.refresh_jobs(self.world, self.career)
        self.job_board.create_tutorial_contract(
            TUTORIAL_CONTRACT_FROM, TUTORIAL_CONTRACT_TO,
            TUTORIAL_CONTRACT_PAYOUT, self.mission_manager.sim_elapsed_s)
        # Verified safe waypoint route Maren→Saltgate (deep south-of-Saltgate
        # corridor); the green guide line follows it so the player never has to
        # plot a course on their first run.  Final waypoint is the berth.
        self._tutorial_route = [tuple(map(float, wp)) for wp in TUTORIAL_ROUTE]
        self._tutorial_wp_index = 0
        self._reset_voyage_flavor()
        self.event_log.add(_sim_time_str(self.environment),
                           f"New contract — deliver to {TUTORIAL_CONTRACT_TO}",
                           EVENT_COLOR_WEATHER)

    def _update_tutorial(self) -> None:
        """Advance the onboarding step/waypoint as the player acts, and manage
        the transit time-compression handoff.

        Steps: throttle up (0→1), steer toward the marker (1→2), the time-speed
        hint clears once real progress is made (2→3), then the player follows the
        line until the final leg (3→4).  On entering step 2 the sim auto-bumps to
        3× so the sail isn't dead time; on entering step 4 it drops back to 1× so
        the docking approach is controllable.  Step 4 completes on docking."""
        if not self._tutorial_active:
            return
        pv = self.player_vessel
        if pv is None or not self._tutorial_route:
            return

        route = self._tutorial_route
        last = len(route) - 1
        # Advance to the next waypoint once the current one is reached.
        target = route[self._tutorial_wp_index]
        if (self._tutorial_wp_index < last
                and pv.distance_to(target) < TUTORIAL_WAYPOINT_RADIUS):
            self._tutorial_wp_index += 1
            target = route[self._tutorial_wp_index]

        prev_step = self._tutorial_step
        if self._tutorial_step == 0:
            if pv.current_speed > TUTORIAL_THROTTLE_SPEED_KN:
                self._tutorial_step = 1
        elif self._tutorial_step == 1:
            bearing = pv.bearing_to(target)
            diff = abs((pv.heading - bearing + 180.0) % 360.0 - 180.0)
            if diff <= TUTORIAL_HEADING_TOLERANCE:
                self._tutorial_step = 2
        elif self._tutorial_step == 2:
            # "Speed up time" — clears once the player has made real progress
            # (passed the first waypoint); the auto-bump below does the work.
            if self._tutorial_wp_index >= 1:
                self._tutorial_step = 3
        elif self._tutorial_step == 3:
            if self._tutorial_wp_index >= last:
                self._tutorial_step = 4

        # Time-compression handoff on step transitions.
        if self._tutorial_step != prev_step:
            if self._tutorial_step == 2:
                # Entering the sail — fast-forward so transit isn't dead time.
                self.environment.time_speed_multiplier = TUTORIAL_TRANSIT_TIME_SPEED
                self.is_paused = False
            elif self._tutorial_step == 4:
                # Final approach — hand control back at normal speed to dock.
                self.environment.time_speed_multiplier = 1.0
                self.is_paused = False
        # Step 4 (the final "dock" step) completes in _on_player_docked().

    def _reset_voyage_flavor(self) -> None:
        """Start a fresh voyage's flavour log (clear de-dup, restart cooldown)."""
        self._flavor_seen = set()
        self._flavor_last_s = self.mission_manager.sim_elapsed_s

    def _update_voyage_flavor(self) -> None:
        """Occasionally drop a cosmetic log line during a sail — passing a
        vessel, nearing a port, or open water — so transit isn't dead air.
        Throttled by FLAVOR_COOLDOWN_S of sim-time and de-duped per voyage."""
        if not self.settings.voyage_flavour:   # gameplay toggle
            return
        pv = self.player_vessel
        if pv is None or pv.status not in ("underway", "avoiding"):
            return
        now_s = self.mission_manager.sim_elapsed_s
        if now_s - self._flavor_last_s < FLAVOR_COOLDOWN_S:
            return

        msg = None
        # 1) Nearest un-announced vessel within range → "Passing X to <side>".
        best_v, best_d = None, FLAVOR_VESSEL_RANGE_WU
        for v in self.world.vessels:
            if v is pv or f"v:{v.name}" in self._flavor_seen:
                continue
            d = pv.distance_to(v.position)
            if d < best_d:
                best_v, best_d = v, d
        if best_v is not None:
            rel = (pv.bearing_to(best_v.position) - pv.heading + 180.0) % 360.0 - 180.0
            side = "starboard" if rel > 0 else "port"
            msg = f"Passing {best_v.name} to {side}"
            self._flavor_seen.add(f"v:{best_v.name}")
        else:
            # 2) Nearest un-announced port within range → "approaching X".
            best_p, best_pd = None, FLAVOR_PORT_RANGE_WU
            for p in self.world.ports:
                if f"p:{p.name}" in self._flavor_seen or p.name == self._departed_port:
                    continue
                d = pv.distance_to(p.position)
                if d < best_pd:
                    best_p, best_pd = p, d
            if best_p is not None:
                _ac = self.job_board.active
                if _ac is not None and _ac.to_port == best_p.name:
                    msg = f"Entering {best_p.name} approach"
                else:
                    msg = f"Passing {best_p.name} off the bow"
                self._flavor_seen.add(f"p:{best_p.name}")
            elif "open_water" not in self._flavor_seen:
                nearest = min((pv.distance_to(p.position) for p in self.world.ports),
                              default=0.0)
                if nearest > FLAVOR_OPEN_WATER_WU:
                    msg = "Open water — steady as she goes"
                    self._flavor_seen.add("open_water")

        if msg is not None:
            self.event_log.add(_sim_time_str(self.environment), msg,
                               EVENT_COLOR_WEATHER)
            self._flavor_last_s = now_s

    async def run(self, skip_title: bool = False) -> None:
        """Run the title menu, then the main game loop until quit.

        Async so the frame loop can `await asyncio.sleep(0)` once per frame — the
        yield pygbag needs to hand control back to the browser's event loop each
        frame under WebAssembly.  On desktop the sleep(0) is a no-op round-trip
        through the event loop, so behavior is identical.
        """
        # Web boots straight into the living sea — no title screen (its blocking
        # while-loop would freeze the browser tab).  On desktop the title runs
        # exactly as before.
        if not skip_title and not IS_WEB:
            action = self._title_loop()
            if action == "quit":
                self.running = False
            elif action == "continue":
                self._load_save()
        # A brand-new career (tutorial not yet finished) opens zoomed in on the
        # player with a guided first contract; a returning captain skips it.
        if self.player_vessel is not None and not self.career.tutorial_complete:
            self._begin_tutorial()
        # Engage follow-cam now the title overview is done: gameplay tracks the
        # player ship, while the title screen kept the port cluster framed.
        if self.player_vessel is not None and PLAYER_FOLLOW_CAM:
            self.camera.set_follow_target(self.player_vessel)
        # Web frame cap (skip, don't sleep): rAF paces the loop at display rate
        # (60+ Hz), but an ambient tab must not render that often — cap at
        # WEB_TARGET_FPS by SKIPPING ticks until the budget elapses.  The grid
        # is a perf_counter deadline advanced by exactly one budget per rendered
        # frame: render on the first rAF tick past each deadline, and the grid
        # self-corrects to a true 30.0 average.  (Deliberately NOT accumulated
        # from clock.tick(): it returns integer ms, and floor-bias against a
        # 33.33 ms threshold lands 16+16=32 < budget -> render every THIRD tick
        # -> 20 fps — the same boundary bug the pacing audit killed.)
        _web_budget = 1.0 / WEB_TARGET_FPS
        _web_last = _web_next = time.perf_counter()
        while self.running:
            if IS_WEB:
                _now = time.perf_counter()
                if _now < _web_next:
                    # Skip path — near-zero work: one clock read, one compare,
                    # straight back to the browser until the next rAF tick.  No
                    # events, no sim, no render, no overlay.
                    await asyncio.sleep(0)
                    continue
                # Rendered frame: sim consumes the real time since the last
                # rendered frame, clamped so returning to a throttled/hidden
                # tab (rAF suspended -> huge gap) can't trigger a giant
                # catch-up burst (the step cap below bounds it further).
                dt = min(_now - _web_last, WEB_FRAME_DT_CLAMP_S)
                _web_last = _now
                _web_next += _web_budget
                if _web_next < _now:
                    # Fell behind by a whole budget (slow frame / hidden tab):
                    # restart the grid instead of racing to catch up.
                    _web_next = _now + _web_budget
                # Heal the display if the real canvas size disagrees with our
                # surface (boot race against pygbag's window_resize; ~1/s check).
                self._web_watch_display()
                # Glide toward the wheel's zoom target (no-op when settled).
                self._ease_zoom()
            else:
                dt = self.clock.tick(TARGET_FPS) / 1000.0  # convert ms to seconds

            self.handle_events()
            _prof = self._prof   # None on desktop -> every timing branch is skipped
            _s = time.perf_counter() if _prof is not None else 0.0
            if not self.game_over:
                self.update_simulation(dt)
            if _prof is not None:
                _prof.sim += time.perf_counter() - _s
            self.render()
            if _prof is not None:
                _prof.n += 1
                _prof.steps += self.last_sim_steps
                _prof.maybe_report()

            # Yield to the event loop once per frame.  Required by pygbag under
            # WebAssembly (lets the browser paint + deliver input); a harmless
            # no-op on desktop, where clock.tick(TARGET_FPS) above paces.
            #
            # PACING AUDIT (why sleep(0), never sleep(budget-spent)): pygbag
            # steps the asyncio loop only on requestAnimationFrame ticks, so a
            # sleep can only wake ON a tick.  Sleeping "the rest of the 33.3ms
            # budget" set the deadline exactly on a tick boundary; browser
            # jitter then landed the wake on the 33.3ms tick OR slid to the
            # 50ms one, alternating 33/50ms frames -> the observed hardware-
            # independent 25 fps / 40 ms wall that no work optimization could
            # move (the smaller the work, the longer the sleep — same tick).
            # sleep(0) parks the task until the NEXT rAF tick only; the frame
            # CAP is enforced by the skip path at the top of the loop, never
            # by a longer sleep.
            await asyncio.sleep(0)

        # Silence loops so a restart doesn't stack a second ambient track.
        self.sound.stop_all()

        if not self._restart_requested:
            pygame.quit()
            sys.exit()


async def main():
    """Entry point.

    Async + launched via asyncio.run() so the same file runs under pygbag
    (WebAssembly) and on desktop without a fork — pygbag reroutes asyncio.run()
    onto the browser's event loop, while CPython runs it normally.

    The whole run is wrapped so any startup/runtime crash prints its FULL
    traceback to stdout.  pygbag pipes stdout to the browser console, so a web
    failure shows the real error instead of a silent gray screen; on desktop the
    happy path is unchanged and a genuine crash still surfaces + exits non-zero.
    """
    try:
        skip_title = "--skip-title" in sys.argv
        while True:
            game = Game()
            await game.run(skip_title=skip_title)
            if not getattr(game, '_restart_requested', False):
                break
        pygame.quit()
        sys.exit()
    except SystemExit:
        raise                       # normal shutdown via sys.exit() — not a crash
    except BaseException:
        print("=== Meridian Sea: unhandled startup/runtime error ===",
              file=sys.stdout)
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        raise


if __name__ == "__main__":
    asyncio.run(main())
