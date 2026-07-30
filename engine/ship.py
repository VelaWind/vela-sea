"""Ship/Vessel model with types, dimensions, fuel, speed, and navigation."""

import time as _time
from dataclasses import dataclass, field
from math import atan2, cos, degrees, radians, sin, sqrt
from typing import List, Optional, Tuple

from config import (
    KNOTS_TO_UNITS_PER_HOUR,
    FUEL_COAST_DECELERATION,
    TURN_OPTIMAL_SPEED_FRACTION,
    TURN_MIN_EFFECTIVENESS,
    TURN_HIGH_SPEED_EFFECTIVENESS,
    TURN_SPEED_BLEED,
    CURRENT_INFLUENCE,
    WINDAGE_CARGO, WINDAGE_FERRY, WINDAGE_FISHING, WINDAGE_SAILBOAT, WINDAGE_GENERIC,
    SAIL_NO_GO_ANGLE, SAIL_EFFICIENCY, SAIL_RUN_FACTOR,
    REFUEL_FRACTION, PORT_DETECT_RADIUS,
    VESSEL_TRAIL_MAX_POINTS, VESSEL_TRAIL_SAMPLE_STEPS,
)

Position = Tuple[float, float]


@dataclass
class Vessel:
    """A vessel in the simulation: ship, ferry, sailboat, tanker, etc."""
    name: str
    vessel_type: str  # "generic", "sailboat", "fishing", "cargo", "tanker", "ferry"
    position: Position
    heading: float  # degrees (0° = east, 90° = south)
    target_speed: float  # world units/second (desired speed)
    current_speed: float  # actual speed, may differ due to acceleration limits
    max_speed: float     # maximum speed this vessel type can achieve (knots)
    acceleration: float  # knots/simulated-second — how fast the vessel builds speed
    deceleration: float  # knots/simulated-second — how fast it sheds speed (< accel:
                         # ships lose speed much more slowly than they gain it)
    turn_rate: float     # degrees/simulated-second at optimal speed (see turn_toward)
    
    # Dimensions
    length_m: float  # meters (LOA)
    beam_m: float  # meters (width)
    draft_m: float  # meters (depth below waterline)
    
    # Fuel (None for sailboats, which use wind instead)
    fuel: Optional[float]  # current fuel (liters equivalent)
    fuel_capacity: Optional[float]  # max fuel
    fuel_consumption_rate: float  # fuel-units/sim-hour at max speed (scales as speed²)
    
    # Active navigation target — always the next position the vessel heads toward.
    # Set by the route system on departure; cleared only when the route ends.
    destination: Optional[Position] = None

    # Multi-waypoint route (Chunk E)
    # route       — full ordered position list; loops continuously when route_loop=True.
    # route_index — index of the waypoint the vessel is currently heading toward.
    # route_loop  — True: A→B→C→A (circular); False: not yet implemented (reserved).
    route: List[Position] = field(default_factory=list)
    route_index: int = 0
    route_loop: bool = True

    # Port stay timer.  Counts down in sim-seconds while status == "in_port".
    # port_stay_duration is configured per vessel type in main.py via config.py.
    port_stay_timer: float = 0.0
    port_stay_duration: float = 0.0

    status: str = "underway"  # "underway", "avoiding", "in_port", "docked", "anchored", "aground", "adrift"

    # Avoidance heading set by the collision module while status == "avoiding".
    # Ignored in all other states; reset by the collision module each tick.
    avoid_heading: float = 0.0

    # Port name last docked at — used to release the berth on departure.
    # None when underway.
    _docked_port_name: Optional[str] = field(default=None, repr=False)

    # True when the player has issued a direct-nav command overriding the schedule.
    # Cleared automatically by arrive() once the commanded destination is reached;
    # the vessel then resumes its scheduled route at the current route_index.
    player_commanded: bool = False

    # WHY this vessel is commanded: "sar" (dispatched to a casualty), "medical"
    # (diverting to the nearest port with a casualty aboard), "party" (tender
    # running out to an anchored yacht), "player" (direct order), "" (not
    # commanded).  player_commanded alone cannot distinguish these, and the fleet
    # panel labelled all of them "MEDICAL" — so every rescuer the dispatcher
    # drafted appeared on screen as a new medical emergency.  Set at each site
    # that raises the flag and cleared wherever it drops.
    command_reason: str = ""

    # SAR (Search and Rescue) state.
    # distress       — True while the vessel needs outside help: aground, or
    #                  adrift from engine failure or fuel exhaustion.
    # distress_timer — cumulative sim-seconds in distress, any casualty state.
    # rescue_vessel  — reference to the Vessel assigned to rescue this one, or None.
    distress: bool = False
    distress_timer: float = 0.0
    rescue_vessel: Optional[object] = field(default=None, repr=False)

    # Random sudden events.
    # engine_failure — True while engine is dead; cleared by SAR rescue arrival.
    # mob_timer      — seconds remaining in MOB search pattern (0 = none active).
    # mob_position   — world position where MOB occurred; None when not in MOB.
    engine_failure: bool = False
    mob_timer: float = 0.0
    mob_position: Optional[Position] = field(default=None, repr=False)

    # Mission system.
    # mission_type   — "cargo_run", "ferry_run", "fishing_trip", "sailing_cruise", "tug_duty"
    # mission_status — descriptive label shown in the info panel ("TRAWLING", "LOADING", …)
    # trawling_timer        — counts down (s) during trawl/anchor pause; 0 = not paused
    # trawling_heading_timer — counts down to next heading change while trawling
    # port_visit_count — incremented on each port arrival; drives LOADING/UNLOADING alternation
    mission_type:            str   = ""
    mission_status:          str   = ""
    trawling_timer:          float = 0.0
    trawling_heading_timer:  float = 0.0
    port_visit_count:        int   = 0

    # Per-vessel color override (RGB tuple).  When set, replaces the type-based
    # AIS color on the chart so specific vessels can have a distinct hull tint.
    # None → fall through to the normal type-based color logic.
    color_override: Optional[Tuple[int, int, int]] = None

    # Captain's log — last 5 navigational decisions, newest last.
    # Each entry is a pre-formatted "[HH:MM] message" string.
    captain_log: List[str] = field(default_factory=list, repr=False)

    # Trail: sampled position history for the vessel track display.
    # trail          — list of world (x, y) positions, oldest first, newest last.
    # _trail_counter — counts move() calls; appends every VESSEL_TRAIL_SAMPLE_STEPS.
    trail: List[Position] = field(default_factory=list, repr=False)
    _trail_counter: int = field(default=0, repr=False)

    # ── AI personality, mood, and memory ──────────────────────────────────────
    # personality — drives cruise-speed baseline and log commentary
    # mood        — evolves with events (grounding→stressed; long watch→tired; rest→normal)
    # memory      — persistent voyage notes: grounding locations, busy ports, etc.
    personality: str = "efficient"
    mood: str = "normal"
    memory: dict = field(
        default_factory=lambda: {"grounded_positions": [], "congested_ports": []},
        repr=False,
    )

    # Party yacht — yacht-side state; the tender tracks its own assignment
    party_active: bool = False
    party_timer: float = 0.0

    # Mood timers (sim-seconds); reset on status transitions
    _underway_timer: float = field(default=0.0, repr=False)
    _port_rest_timer: float = field(default=0.0, repr=False)

    # Real-time stamp of last log_decision() call; panels.py uses it for the
    # "thinking" indicator that briefly highlights the log section header.
    _last_decision_time: float = field(default=0.0, repr=False)

    # Player vessel flag — True only for the human-controlled ship.
    # Skips all AI navigation logic in the sim loop.
    is_player: bool = False

    # Autopilot waypoint set by right-click (player vessel only).  While set,
    # the sim steers toward it each step; manual A/D steering clears it.
    autopilot_destination: Optional[Position] = None

    # Structural health: 1.0 = fully intact, 0.0 = total loss.
    # Decremented on grounding events; shown in the player HUD.
    hull_integrity: float = 1.0

    # ------------------------------------------------------------------
    # Route / port-stay state machine (Chunk E)
    # ------------------------------------------------------------------

    def display_state(self) -> str:
        """Canonical UI label for this vessel — the single source of truth.

        Four readers used to derive this independently and disagreed on screen at
        the same instant:

          * the fleet list ranked mob_timer > engine_failure > distress >
            player_commanded > mission_status > status, and labelled ANY commanded
            vessel "MEDICAL" — so every rescuer the dispatcher drafted appeared as
            a fresh medical emergency, and a live viewer read the fleet as sicker
            than it was;
          * the info panel's Status row read `mission_status or status` and never
            consulted distress at all, so a tug aground 70 h read "STANDBY";
          * the DISTRESS section was gated on status == "aground", so ENG FAIL and
            fuel-exhaustion casualties showed no rescue information whatsoever;
          * the chart badge keyed off distress alone.

        Precedence is worst-first: an emergency outranks a duty, and a duty
        outranks a schedule label.  Pure Python — render reads it, never
        recomputes it.  Colours stay in the render layer.
        """
        if self.mob_timer > 0:
            return "MOB"
        if self.engine_failure:
            return "ENG FAIL"
        if self.status == "aground":
            return "AGROUND"
        if self.status == "adrift":
            return "ADRIFT"
        if self.player_commanded:
            # WHY it is commanded is the whole point — see command_reason.
            return {"sar": "RESCUING", "medical": "MEDICAL",
                    "party": "PARTY"}.get(self.command_reason, "COMMANDED")
        return self.mission_status or self.status.upper()

    def refloat(self) -> None:
        """Restore underway status after grounding or engine failure resolves.

        Clears all SAR and engine-failure state.  The rescuer's player_commanded
        flag is the orchestrator's responsibility (main.py's _sar_refloat).
        """
        self.status = "underway"
        self.distress = False
        self.distress_timer = 0.0
        self.rescue_vessel = None
        self.engine_failure = False

    def _port_at(self, position: Position, world) -> object:
        """Return the Port whose berth is within PORT_DETECT_RADIUS of position, or None.

        Uses a slightly larger tolerance than ARRIVAL_DISTANCE so port
        detection is robust even with floating-point drift on arrival.
        All open-sea waypoints are > 50 wu from any port, so there is no
        risk of a false positive.
        """
        r2 = PORT_DETECT_RADIUS * PORT_DETECT_RADIUS
        for port in world.ports:
            dx = position[0] - port.position[0]
            dy = position[1] - port.position[1]
            if dx * dx + dy * dy <= r2:
                return port
        return None

    def _advance_route(self) -> None:
        """Advance route_index to the next waypoint and update destination."""
        if not self.route:
            self.destination = None
            return
        self.route_index = (self.route_index + 1) % len(self.route)
        self.destination = self.route[self.route_index]

    def arrive(self, world) -> None:
        """Handle arrival at the current destination waypoint.

        If the waypoint is a port: enter "in_port", start the stay timer,
        and refuel (if the port has fuel and the vessel has a tank).
        If it is an open-sea waypoint: advance the route immediately and
        stay "underway" — the vessel briefly touches the waypoint and
        continues without stopping.

        Player-commanded arrivals: skip all port/route logic and simply
        resume the scheduled route from the current route_index.
        """
        self.current_speed = 0.0

        if self.player_commanded:
            # Commanded destination reached — hand back to the schedule.
            self.player_commanded = False
            self.command_reason = ""
            if self.route:
                self.destination = self.route[self.route_index]
            self.status = "underway"
            return

        current_wp = self.route[self.route_index] if self.route else self.destination
        if current_wp is None:
            return   # nothing to arrive at (no route and no destination)
        port = self._port_at(current_wp, world) if world is not None else None

        if port is not None:
            self.status = "in_port"
            self.port_stay_timer = self.port_stay_duration
            # Snap to a free berth so multiple vessels spread out around the port.
            self._docked_port_name = port.name
            self.position = port.claim_berth(self.name, self.position)
            # Refuel to capacity if this berth has fuel and the vessel has a tank.
            # The player pays for fuel through the docking menu instead, so the
            # free schedule-refuel applies to AI traffic only.
            if (port.refuel and not self.is_player
                    and self.fuel is not None and self.fuel_capacity is not None):
                self.fuel = self.fuel_capacity * REFUEL_FRACTION
        else:
            # Open-sea waypoint: advance and continue without a stay.
            self._advance_route()
            self.status = "underway" if self.destination is not None else "docked"

    def update_route(self, dt: float, world) -> None:
        """Count down the port stay timer and depart when it expires.

        Call every sim tick for vessels with status == "in_port".
        """
        if self.status != "in_port":
            return
        self.port_stay_timer = max(0.0, self.port_stay_timer - dt)
        if self.port_stay_timer <= 0.0:
            # Release the berth before departing so another vessel can claim it.
            if world is not None and self._docked_port_name:
                p = world.find_port(self._docked_port_name)
                if p is not None:
                    p.release_berth(self.name)
            self._docked_port_name = None
            if not self.player_commanded:
                # Normal departure: advance to the next scheduled waypoint.
                self._advance_route()
            # player_commanded: destination already set by the player; just depart.
            self.status = "underway" if self.destination is not None else "docked"

    # ------------------------------------------------------------------
    # Navigation geometry
    # ------------------------------------------------------------------

    def distance_to(self, target: Position) -> float:
        """Compute straight-line distance to a target."""
        dx = target[0] - self.position[0]
        dy = target[1] - self.position[1]
        return sqrt(dx * dx + dy * dy)

    def bearing_to(self, target: Position) -> float:
        """Compute the heading (degrees) needed to move toward a target."""
        dx = target[0] - self.position[0]
        dy = target[1] - self.position[1]
        angle = degrees(atan2(dy, dx))
        return angle % 360

    def at_destination(self, target: Position, tolerance: float = 1.0) -> bool:
        """Return True when the vessel is close enough to a destination."""
        return self.distance_to(target) <= tolerance

    def turn_toward(self, target_heading: float, dt: float) -> None:
        """Turn toward a target heading at a speed-dependent rate.

        Rudder effectiveness peaks at TURN_OPTIMAL_SPEED_FRACTION × max_speed,
        where water-flow over the blade is sufficient for full lateral force.
        Below that fraction the rudder barely bites (vessel nearly stopped).
        Above it, hull momentum widens the turning circle (effectiveness falls).

        Each degree of actual yaw also bleeds a small amount of speed owing to
        increased hydrodynamic drag on the hull in the turn.
        """
        if self.status not in ("underway", "avoiding"):
            return

        # Shortest angular path to target
        delta = target_heading - self.heading
        if delta > 180:
            delta -= 360
        elif delta < -180:
            delta += 360

        if abs(delta) < 0.01:
            return

        # Speed-dependent rudder effectiveness (0 → 1 scale)
        speed_fraction = self.current_speed / max(0.1, self.max_speed)
        if speed_fraction <= TURN_OPTIMAL_SPEED_FRACTION:
            # Linear ramp: TURN_MIN_EFFECTIVENESS at dead-slow → 1.0 at optimal
            effectiveness = (
                TURN_MIN_EFFECTIVENESS
                + (1.0 - TURN_MIN_EFFECTIVENESS)
                * (speed_fraction / TURN_OPTIMAL_SPEED_FRACTION)
            )
        else:
            # Gentle fall-off above optimal: hull momentum widens the circle
            over = (speed_fraction - TURN_OPTIMAL_SPEED_FRACTION) / max(
                0.01, 1.0 - TURN_OPTIMAL_SPEED_FRACTION
            )
            effectiveness = 1.0 - (1.0 - TURN_HIGH_SPEED_EFFECTIVENESS) * over

        max_turn = self.turn_rate * effectiveness * dt
        actual_turn = max(-max_turn, min(max_turn, delta))
        self.heading = (self.heading + actual_turn) % 360

        # Speed bleed: hydrodynamic drag increases with yaw rate.
        # yaw_rate (°/s) × TURN_SPEED_BLEED gives kn lost per simulated second.
        yaw_rate = abs(actual_turn) / max(dt, 1e-9)
        self.current_speed = max(0.0, self.current_speed - TURN_SPEED_BLEED * yaw_rate * dt)

    def update_speed(self, dt: float, environment=None) -> None:
        """Ramp current speed toward target speed using separate accel/decel rates.

        Ships build speed slowly (limited by engine thrust) and shed it even more
        slowly (large displacement, small hydrodynamic braking force).  Using a
        smaller deceleration rate than acceleration reproduces the long stopping
        distances that give large vessels their characteristic "feel".

        For sailboats (fuel is None), wind is the engine: target speed is capped
        by the available drive from the current wind angle.  If in the no-go zone
        the effective limit is 0 kn, so the vessel decelerates via normal drag.
        """
        if self.status == "adrift" or self.engine_failure:
            # No engine (adrift = fuel empty; engine_failure = mechanical breakdown).
            # Coast down on water resistance alone — no reverse thrust available.
            self.current_speed = max(0.0, self.current_speed - FUEL_COAST_DECELERATION * dt)
            return

        # Docked, aground, anchored — hold at zero.  "avoiding" behaves like "underway"
        # for speed: the vessel keeps moving while executing its avoidance turn.
        if self.status not in ("underway", "avoiding"):
            self.current_speed = 0.0
            return

        # For sailboats the wind sets an upper bound on achievable speed.
        in_irons = False
        if self.fuel is None and environment is not None:
            wind_avail = self._effective_wind_speed(environment)
            effective_target = min(self.target_speed, wind_avail)
            # No-go zone: sails can't fill, so there is no drive at all.
            # The hull coasts down on water resistance only — same drag rate as
            # an adrift powered vessel, NOT the vessel's mechanical deceleration
            # (which implies active reverse thrust or engine braking).
            in_irons = wind_avail == 0.0
        else:
            effective_target = self.target_speed

        delta = effective_target - self.current_speed
        # Use acceleration when speeding up, deceleration when slowing.
        # In irons, the only retarding force is hull drag (FUEL_COAST_DECELERATION).
        if delta < 0 and in_irons:
            rate = FUEL_COAST_DECELERATION
        else:
            rate = self.acceleration if delta > 0 else self.deceleration
        max_change = rate * dt
        actual_change = max(-max_change, min(max_change, delta))
        self.current_speed = max(0.0, self.current_speed + actual_change)

    def move(self, dt: float, environment=None, world=None, sim_time: str = "") -> None:
        """Move the vessel by one time step, applying environment forces and consuming fuel.

        Position update is the vector sum of:
          1. Through-water displacement — vessel's own speed along its heading.
          2. Set-and-drift — ocean/tidal current adds a velocity vector to the track,
             so course-over-ground (COG) ≠ heading whenever current ≠ 0.
          3. Wind drift — wind pushes the hull laterally, scaled by a windage factor
             that reflects the vessel's above-waterline profile area.

        Sailboat propulsion is handled in update_speed() (wind caps target speed);
        the same vector additions apply so the wind still drifts a sailing vessel.

        Optional world/sim_time: when supplied, a vessel whose fuel hits zero away
        from any port is declared distress=True so SAR dispatch picks it up.
        """
        # Docked, aground, and anchored vessels are held in place.
        # Underway, avoiding, and adrift vessels can be displaced by any of the three forces below.
        if self.status not in ("underway", "avoiding", "adrift"):
            return

        hours = dt / 3600.0
        new_x, new_y = self.position

        # 1. Through-water motion — only when the vessel has headway.
        #    A stopped underway vessel has no through-water contribution but
        #    still floats on the current and is pushed by wind (forces 2 & 3).
        if self.current_speed > 0:
            distance = self.current_speed * KNOTS_TO_UNITS_PER_HOUR * hours
            heading_rad = radians(self.heading)
            new_x += cos(heading_rad) * distance
            new_y += sin(heading_rad) * distance

        if environment is not None:
            # 2. Set-and-drift: current_direction is the direction the current flows
            #    TOWARD, so a current_direction of 90° pushes vessels southward.
            #    Applies regardless of through-water speed — a vessel stopped in the
            #    water still floats with the tidal stream.
            cur_rad = radians(environment.current_direction)
            cur_dist = environment.current_speed * KNOTS_TO_UNITS_PER_HOUR * hours * CURRENT_INFLUENCE
            new_x += cos(cur_rad) * cur_dist
            new_y += sin(cur_rad) * cur_dist

            # 3. Wind drift: wind_direction is the bearing the wind blows FROM, so
            #    the push on the hull is in the opposite direction (+180°).
            wind_push_kn = environment.wind_speed * self._windage_factor()
            push_rad = radians((environment.wind_direction + 180.0) % 360.0)
            wind_dist = wind_push_kn * KNOTS_TO_UNITS_PER_HOUR * hours
            new_x += cos(push_rad) * wind_dist
            new_y += sin(push_rad) * wind_dist

        self.position = (new_x, new_y)

        # Trail sampling: record one point every VESSEL_TRAIL_SAMPLE_STEPS calls.
        # Using a counter rather than sim-time keeps the trail density proportional
        # to distance covered (faster vessels leave fewer, evenly-spaced dots).
        self._trail_counter += 1
        if self._trail_counter >= VESSEL_TRAIL_SAMPLE_STEPS:
            self._trail_counter = 0
            self.trail.append(self.position)
            if len(self.trail) > VESSEL_TRAIL_MAX_POINTS:
                del self.trail[0]

        # Consume fuel only while under power.  The moment the tank empties,
        # flip to adrift so update_speed starts coasting on the next tick.
        # fuel_consumption_rate is in fuel-units per sim-hour at max speed; use
        # the same hours conversion as distance so the two stay in lock-step.
        if self.fuel is not None and self.fuel > 0:
            speed_ratio = self.current_speed / max(0.1, self.max_speed)
            fuel_used = self.fuel_consumption_rate * speed_ratio * speed_ratio * hours
            self.fuel = max(0.0, self.fuel - fuel_used)
            if self.fuel == 0.0 and self.status == "underway":
                self.status = "adrift"
                # Declare distress unless the vessel is already alongside a port
                # (within PORT_DETECT_RADIUS), where it can drift in unaided.
                near_port = (world is not None
                             and self._port_at(self.position, world) is not None)
                if not near_port:
                    self.distress = True
                    self.log_decision(
                        sim_time,
                        "ENGINE FAILURE — fuel exhausted, requesting assistance")

    def status_line(self) -> str:
        """Return a short status string for display."""
        fuel_str = f"fuel={self.fuel:.1f}" if self.fuel is not None else "wind-powered"
        return (
            f"{self.name}: pos=({self.position[0]:.1f}, {self.position[1]:.1f}) "
            f"heading={self.heading:.0f}° speed={self.current_speed:.1f} "
            f"{fuel_str} status={self.status}"
        )

    def _effective_wind_speed(self, environment) -> float:
        """Return the wind-driven speed available to a sailboat (knots).

        Uses a simplified true-wind polar:
          - No-go zone (< SAIL_NO_GO_ANGLE either side of head-to-wind): 0 kn.
          - Close haul → beam reach (SAIL_NO_GO_ANGLE … 90°): linear ramp 0 → peak.
          - Beam reach → running (90° … 180°): linear taper → SAIL_RUN_FACTOR × peak.
        Peak = wind_speed × SAIL_EFFICIENCY, capped at max_speed.

        Returns 0 for any powered vessel (fuel is not None).
        """
        if self.fuel is not None:
            return 0.0  # not a sailboat

        wind_angle = self._wind_angle_to_heading(environment)
        abs_angle = abs(wind_angle)

        if abs_angle < SAIL_NO_GO_ANGLE:
            return 0.0  # in irons — sail cannot fill

        peak = min(self.max_speed, environment.wind_speed * SAIL_EFFICIENCY)

        if abs_angle <= 90.0:
            # Close haul → beam reach: ramp from 0 at the no-go boundary to peak
            t = (abs_angle - SAIL_NO_GO_ANGLE) / (90.0 - SAIL_NO_GO_ANGLE)
            factor = t
        else:
            # Beam reach → running: taper from peak down to SAIL_RUN_FACTOR × peak
            t = (abs_angle - 90.0) / 90.0
            factor = 1.0 - (1.0 - SAIL_RUN_FACTOR) * t

        return peak * factor

    def _windage_factor(self) -> float:
        """Return fraction of wind speed (kn) that becomes a lateral hull push.

        Keyed on vessel_type; see config.py WINDAGE_* for the real-world basis.
        """
        return {
            "cargo":    WINDAGE_CARGO,
            "ferry":    WINDAGE_FERRY,
            "fishing":  WINDAGE_FISHING,
            "sailboat": WINDAGE_SAILBOAT,
        }.get(self.vessel_type, WINDAGE_GENERIC)

    def _wind_angle_to_heading(self, environment) -> float:
        """Calculate angle between wind direction and vessel heading.

        Returns a value in range (-180, 180] where:
        - 0° = wind directly ahead
        - 90° = wind from the side (starboard)
        - -90° = wind from the side (port)
        - 180° = wind directly astern
        """
        delta = environment.wind_direction - self.heading
        if delta > 180:
            delta -= 360
        elif delta < -180:
            delta += 360
        return delta

    def log_decision(self, sim_time: str, message: str) -> None:
        """Append a decision to the captain's log; keep only the last 5 entries."""
        self.captain_log.append(f"[{sim_time}] {message}")
        if len(self.captain_log) > 5:
            del self.captain_log[0]
        self._last_decision_time = _time.time()


# For backwards compatibility with existing code
Ship = Vessel
