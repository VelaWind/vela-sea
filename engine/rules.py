"""Rules engine for checking maritime restrictions each tick."""

from dataclasses import dataclass
from typing import List

from .world import Zone, Position


@dataclass
class RuleViolation:
    """Represents a rule violation detected during simulation."""
    zone: Zone
    message: str


class RulesEngine:
    """Evaluates the ship state against restriction zones."""

    def __init__(self, world):
        self.world = world

    def check(self, position: Position) -> List[RuleViolation]:
        """Return a list of violations for the current position."""
        violations = []
        zones = self.world.get_zones_containing(position)
        for zone in zones:
            violations.append(
                RuleViolation(
                    zone=zone,
                    message=(
                        f"Zone: {zone.name} ({zone.kind})"
                        f"{f', speed limit {zone.speed_limit}kt' if zone.speed_limit else ''}"
                    ),
                )
            )
        return violations
