"""Mission system — player objectives generated from live simulation events.

MissionManager holds one active mission at a time.  Missions are generated
automatically (cargo departure → delivery, distress → rescue, CG departure →
patrol) and completed when the relevant vessel reaches the target position.
The engine layer is pure Python; time.time() is the only non-dataclass import.
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Tuple

from config import RESCUE_MISSION_COOLDOWN_S, RESCUE_MISSION_TTL_S

Position = Tuple[float, float]

# How long the completion banner stays visible before the mission is cleared.
MISSION_COMPLETE_DISPLAY_S = 5.0


@dataclass
class Mission:
    """One player objective."""
    mission_type: str       # "delivery"|"rescue"|"patrol"|"passenger_pickup"|"cargo_deadline"|"vip_cruise"
    description: str        # bold header line shown in the panel
    objective: str          # action line ("Command X to Y")
    target_vessel_name: str # vessel the player needs to command ("" = any)
    target_position: Position
    reward_text: str
    complete: bool = False
    complete_time: float = field(default=0.0, repr=False)
    # Deadline: deadline_sim_time > 0 means mission fails if not completed by then.
    # Elapsed sim-seconds are tracked by MissionManager.sim_elapsed_s.
    deadline_sim_time: float = 0.0
    failed: bool = False
    # Slot TTL: expire_sim_time > 0 means the mission releases the single
    # mission slot at that sim time even if never completed.  Without it an
    # unresolvable rescue mission is immortal (generate_mission refuses to
    # replace an incomplete mission, and clear_if_expired only drops completed
    # ones), so the first mayday of a session is the only one ever shown.
    expire_sim_time: float = 0.0


class MissionManager:
    """Generates and tracks one player mission at a time."""

    def __init__(self) -> None:
        self.active_mission: Optional[Mission] = None
        # Accumulated simulated seconds since game start — used for deadline math.
        self.sim_elapsed_s: float = 0.0
        # vessel name -> sim time its last rescue mission left the slot.  Keyed by
        # name rather than id() so it survives any future vessel rebuild.
        self._rescue_cooldown: dict = {}

    def update(self, dt: float) -> None:
        """Advance the internal sim clock by dt simulated seconds."""
        self.sim_elapsed_s += dt
        # Release the slot when an incomplete rescue mission outlives its TTL.
        m = self.active_mission
        if (m is not None and not m.complete
                and m.expire_sim_time > 0.0
                and self.sim_elapsed_s > m.expire_sim_time):
            # Stamp the cooldown too: the casualty is usually still in distress,
            # and without the stamp it would re-raise and re-lock immediately.
            if m.target_vessel_name:
                self._rescue_cooldown[m.target_vessel_name] = self.sim_elapsed_s
            self.active_mission = None

    # ------------------------------------------------------------------ generate

    def generate_mission(self, mission_type: str, vessel,
                         target_pos: Position, port_name: str = "") -> None:
        """Create a new mission, replacing any completed one.

        Silently ignored when a live (incomplete) mission is already active so
        the player is not interrupted mid-task.
        """
        if (self.active_mission is not None
                and not self.active_mission.complete):
            return

        # Per-vessel rescue cooldown.  A refloated vessel re-grounds in a median
        # 1.2 sim-seconds, so the same hull would otherwise raise a fresh mayday
        # (and a fresh toast) several times a sim-minute.
        if mission_type == "rescue":
            _last = self._rescue_cooldown.get(vessel.name)
            if (_last is not None
                    and self.sim_elapsed_s - _last < RESCUE_MISSION_COOLDOWN_S):
                return

        if mission_type == "delivery":
            m = Mission(
                mission_type="delivery",
                description=f"Delivery — {vessel.name}",
                objective=f"Command to {port_name}",
                target_vessel_name=vessel.name,
                target_position=target_pos,
                reward_text=f"Cargo delivered to {port_name}",
            )
        elif mission_type == "rescue":
            m = Mission(
                mission_type="rescue",
                description=f"MAYDAY — {vessel.name}",
                # Observational, not imperative: the web build is a spectator
                # view with no vessel commands, and an order ("dispatch...")
                # reads as an offer of control the viewer doesn't have — the
                # first cold viewer asked "can I control ships?" off this line.
                objective="Nearest vessel diverting to assist",
                # The casualty, not the rescuer: resolution is "this vessel is
                # no longer in distress", which is the only test the vessel that
                # actually performs the rescue can pass.  See check_completion.
                target_vessel_name=vessel.name,
                target_position=target_pos,
                reward_text=f"{vessel.name} has been assisted",
                expire_sim_time=self.sim_elapsed_s + RESCUE_MISSION_TTL_S,
            )
        elif mission_type == "patrol":
            m = Mission(
                mission_type="patrol",
                description="Patrol — CG Sentinel",
                objective=f"Escort to {port_name}",
                target_vessel_name="CG Sentinel",
                target_position=target_pos,
                reward_text=f"Sector secured at {port_name}",
            )
        elif mission_type == "passenger_pickup":
            m = Mission(
                mission_type="passenger_pickup",
                description=f"Passenger Service — {vessel.name}",
                objective=f"Transport passengers to {port_name}",
                target_vessel_name=vessel.name,
                target_position=target_pos,
                reward_text=f"Passengers delivered to {port_name}",
            )
        elif mission_type == "cargo_deadline":
            # Deadline = 4 sim-hours (14 400 sim-s) from now.
            deadline = self.sim_elapsed_s + 14400.0
            m = Mission(
                mission_type="cargo_deadline",
                description=f"Urgent Delivery — {vessel.name}",
                objective=f"Deliver to {port_name} before deadline",
                target_vessel_name=vessel.name,
                target_position=target_pos,
                reward_text=f"Cargo on time to {port_name}",
                deadline_sim_time=deadline,
            )
        elif mission_type == "vip_cruise":
            m = Mission(
                mission_type="vip_cruise",
                description=f"VIP Charter — {vessel.name}",
                objective=f"Complete scenic cruise to {port_name}",
                target_vessel_name=vessel.name,
                target_position=target_pos,
                reward_text=f"VIP guests satisfied — cruise complete",
            )
        else:
            return

        self.active_mission = m

    # ------------------------------------------------------------------ check

    def check_completion(self, world, port_detect_radius: float) -> None:
        """Check whether the active mission objective has been met."""
        m = self.active_mission
        if m is None or m.complete:
            return

        tol = port_detect_radius

        if m.mission_type in ("delivery", "passenger_pickup"):
            for v in world.vessels:
                if v.name != m.target_vessel_name:
                    continue
                if (v.status == "in_port"
                        and v.distance_to(m.target_position) <= tol * 3):
                    self._mark_complete(m)
                break

        elif m.mission_type == "cargo_deadline":
            for v in world.vessels:
                if v.name != m.target_vessel_name:
                    continue
                if (v.status == "in_port"
                        and v.distance_to(m.target_position) <= tol * 3):
                    if self.sim_elapsed_s > m.deadline_sim_time:
                        m.failed = True
                        m.reward_text = "DEADLINE MISSED"
                    self._mark_complete(m)
                break

        elif m.mission_type == "rescue":
            # Completion is the CASUALTY being freed — not a commanded vessel
            # touching its last known position.  The old test could never fire
            # for the vessel that actually performed the rescue: a rescuer is
            # aimed at a standoff at least STANDOFF_STEP_WU (2.0 wu) clear of the
            # casualty against a PORT_DETECT_RADIUS (2.0 wu) tolerance, and by
            # the time check_completion runs, both _sar_refloat and arrive() have
            # already cleared its player_commanded flag.  Measured closest
            # approach was 2.03 wu against the 2.00 wu tolerance.
            for v in world.vessels:
                if v.name != m.target_vessel_name:
                    continue
                if not v.distress and not v.engine_failure:
                    self._rescue_cooldown[v.name] = self.sim_elapsed_s
                    self._mark_complete(m)
                break

        elif m.mission_type == "patrol":
            for v in world.vessels:
                if v.name != "CG Sentinel":
                    continue
                if (v.status == "in_port"
                        and v.distance_to(m.target_position) <= tol * 3):
                    self._mark_complete(m)
                break

        elif m.mission_type == "vip_cruise":
            for v in world.vessels:
                if v.name != m.target_vessel_name:
                    continue
                # Complete when the yacht anchors (trawling_timer active) or docks
                # at/near the target position.
                is_anchored = (getattr(v, "trawling_timer", 0) > 0
                               and getattr(v, "mission_status", "") == "ANCHORED")
                is_in_port = v.status == "in_port"
                if (is_anchored or is_in_port) and v.distance_to(m.target_position) <= tol * 5:
                    self._mark_complete(m)
                break

    def _mark_complete(self, m: Mission) -> None:
        m.complete = True
        m.complete_time = time.time()

    # ------------------------------------------------------------------ expire

    def clear_if_expired(self) -> None:
        """Drop completed missions after the display window closes."""
        if (self.active_mission is not None
                and self.active_mission.complete
                and time.time() - self.active_mission.complete_time
                    > MISSION_COMPLETE_DISPLAY_S):
            self.active_mission = None
