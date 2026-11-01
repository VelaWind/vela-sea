"""Zone rules: the one place the game's restricted-zone rules live.

Pure Python (no Pygame).  main.py asks this module what the rules say and
only performs the side effects itself (sound, event log, charging the fine).

    RulesEngine.speed_cap_kn(position)      AI speed cap from speed-limit zones
    RulesEngine.violated_zone(position, kn) which zone the player is breaking
    RulesEngine.fine_amount(zone, ...)      the fine for one violation
    RulesEngine.step_player(state, ...)     warning, grace period and cooldown

Every number comes from config.py, and the logic is a move of what used to be
inline in Game.update_simulation, kept step for step so fines and caps are
numerically identical (a seeded harness compared every fine before and after).
"""

from dataclasses import dataclass
from typing import Optional

from config import (
    ZONE_FINE_NO_ENTRY, ZONE_FINE_SPEED, ZONE_FINE_INTERVAL_S,
    ZONE_FINE_GRACE_S, HAZMAT_FINE_MULT,
)
from .world import Zone, Position


@dataclass
class ZoneFineState:
    """The player's running zone-violation state, carried between steps.

    timer        seconds spent continuously in violation
    cooldown     seconds until the next fine may be charged
    warning_sent True once the entry warning has fired for this violation
    """
    timer: float = 0.0
    cooldown: float = 0.0
    warning_sent: bool = False


@dataclass
class ZoneStep:
    """What the rules decided for one step.

    zone      the zone being violated, or None
    warn      True on the first step of a violation (play the warning)
    fine_due  True when a fine should be charged this step
    """
    zone: Optional[Zone]
    warn: bool = False
    fine_due: bool = False


class RulesEngine:
    """Evaluates vessel state against the world's restricted zones."""

    def __init__(self, world):
        self.world = world

    def speed_cap_kn(self, position: Position) -> Optional[float]:
        """The lowest speed limit of any zone containing position, or None.

        AI vessels clamp their target speed to this after their own
        decisions, so a zone limit always wins over a captain's choice.
        """
        limit = None
        for zone in self.world.zones:
            if zone.speed_limit is not None and zone.contains(position):
                if limit is None or zone.speed_limit < limit:
                    limit = zone.speed_limit
        return limit

    def violated_zone(self, position: Position, speed_kn: float) -> Optional[Zone]:
        """The zone a vessel at position and speed_kn is breaking, or None.

        A no-entry zone wins outright (being inside is the violation).
        Otherwise the last speed-limit zone, in world order, whose limit is
        exceeded.  The order matters only for the zone name in messages and
        which fine applies, and matches the game's original behaviour.
        """
        violated = None
        for zone in self.world.get_zones_containing(position):
            if zone.kind == "no_entry":
                return zone
            if zone.speed_limit is not None and speed_kn > zone.speed_limit:
                violated = zone
        return violated

    @staticmethod
    def fine_amount(zone: Zone, hazmat: bool, difficulty_mult: float) -> float:
        """The fine for one violation of zone.

        Base fine by zone kind, doubled (HAZMAT_FINE_MULT) while a hazmat
        contract is active, then scaled by the difficulty preset.  The
        multiplications happen in that order, as they always have, so the
        floating-point result is unchanged.
        """
        fine = ZONE_FINE_NO_ENTRY if zone.kind == "no_entry" else ZONE_FINE_SPEED
        if hazmat:
            fine *= HAZMAT_FINE_MULT
        fine *= difficulty_mult
        return fine

    def step_player(self, state: ZoneFineState, position: Position,
                    speed_kn: float, dt: float, fines_allowed: bool) -> ZoneStep:
        """Advance the player's violation state by dt and report what is due.

        Warn once when a violation starts.  Charge the first fine after
        ZONE_FINE_GRACE_S seconds in violation, then at most one per
        ZONE_FINE_INTERVAL_S.  Leaving all violations resets the timer and the
        warning.  fines_allowed is False during the tutorial: it still warns
        but never fines.
        """
        zone = self.violated_zone(position, speed_kn)
        if zone is None:
            state.timer = 0.0
            state.warning_sent = False
            return ZoneStep(zone=None)
        state.timer += dt
        state.cooldown = max(0.0, state.cooldown - dt)
        warn = not state.warning_sent
        if warn:
            state.warning_sent = True
        fine_due = (state.timer >= ZONE_FINE_GRACE_S
                    and state.cooldown <= 0.0
                    and fines_allowed)
        if fine_due:
            state.cooldown = ZONE_FINE_INTERVAL_S
        return ZoneStep(zone=zone, warn=warn, fine_due=fine_due)
