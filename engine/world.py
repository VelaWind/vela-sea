"""World model for the maritime simulation: landmasses, ports, zones, navigation marks."""

from dataclasses import dataclass, field
from math import sqrt
from typing import List, Optional, Tuple

Position = Tuple[float, float]
Polygon = List[Position]


def _point_to_segment_dist(p: Position, a: Position, b: Position) -> float:
    """Distance from point p to the nearest point on segment a-b."""
    ax, ay = a;  bx, by = b;  px, py = p
    abx, aby = bx - ax, by - ay
    ab_sq = abx * abx + aby * aby
    if ab_sq < 1e-12:
        return sqrt((px - ax) ** 2 + (py - ay) ** 2)
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / ab_sq))
    cx, cy = ax + t * abx, ay + t * aby
    return sqrt((px - cx) ** 2 + (py - cy) ** 2)


@dataclass
class Island:
    """A landmass (island or mainland). Vessels cannot sail over it."""
    name: str
    polygon: Polygon  # closed list of (x, y) points defining the shape
    is_mainland: bool = False
    # Rendering hint; renderer maps to fill/coast colours in config.py.
    # Values: "mainland" | "island" | "rocky" | "shallow_bank"
    land_type: str = "island"


@dataclass
class Port:
    """A port: a named destination where vessels can dock."""
    name: str
    position: Position
    port_type: str  # "commercial", "fishing", "marina", "quay"
    size: str  # "large", "medium", "small"
    refuel: bool  # whether powered vessels can take on fuel
    speed_limit: Optional[float]  # harbour approach speed limit (knots), or None
    # Maximum vessel draft (m) the port can berth; None = no restriction.
    # Vessels at or above this draft are refused on the docking check.
    max_draft_m: Optional[float] = None
    # 4 berths at cardinal offsets around the port centre, initialised by World.add_port().
    # Keyed by index 0-3 (E, W, S, N).  Occupant is the vessel name string or None.
    _berth_positions: List[Position] = field(default_factory=list, repr=False)
    _berth_occupants: List[Optional[str]] = field(default_factory=list, repr=False)

    def _init_berths(self, offset: float) -> None:
        """Place 4 berths at cardinal offsets from the port centre."""
        x, y = self.position
        self._berth_positions = [
            (x + offset, y),  # E
            (x - offset, y),  # W
            (x, y + offset),  # S
            (x, y - offset),  # N
        ]
        self._berth_occupants = [None, None, None, None]

    def claim_berth(self, vessel_name: str, from_pos: Position) -> Position:
        """Assign the nearest free berth to a vessel; fall back to port centre if all occupied."""
        best_i, best_d2 = -1, float("inf")
        for i, bp in enumerate(self._berth_positions):
            if self._berth_occupants[i] is not None:
                continue
            d2 = (from_pos[0] - bp[0]) ** 2 + (from_pos[1] - bp[1]) ** 2
            if d2 < best_d2:
                best_d2, best_i = d2, i
        if best_i >= 0:
            self._berth_occupants[best_i] = vessel_name
            return self._berth_positions[best_i]
        return self.position  # all 4 berths occupied; park at centre

    def release_berth(self, vessel_name: str) -> None:
        """Free the berth held by vessel_name when it departs."""
        for i, occ in enumerate(self._berth_occupants):
            if occ == vessel_name:
                self._berth_occupants[i] = None
                return


@dataclass
class Zone:
    """A circular zone with a rule kind (speed limit, no entry, protected, etc.)."""
    name: str
    center: Position  # (x, y) center of the circular zone
    radius: float  # world units
    kind: str  # "no_entry", "speed_limit", "protected", "anchorage", "tss", "shallow"
    speed_limit: Optional[float]  # if applicable (knots), or None

    def contains(self, position: Position) -> bool:
        """Return True when a position lies inside this zone."""
        dx = position[0] - self.center[0]
        dy = position[1] - self.center[1]
        return dx * dx + dy * dy <= self.radius * self.radius


@dataclass
class NavMark:
    """A navigation mark (buoy, beacon) to help sailors navigate safely."""
    name: str
    position: Position
    kind: str  # "lateral_port", "lateral_stbd", "cardinal_n/e/s/w", "safe_water"


@dataclass
class World:
    """The simulated maritime world: islands, ports, zones, and vessels."""
    width: float = 1000.0
    height: float = 1000.0
    islands: List[Island] = field(default_factory=list)
    ports: List[Port] = field(default_factory=list)
    zones: List[Zone] = field(default_factory=list)
    nav_marks: List[NavMark] = field(default_factory=list)
    vessels: List[object] = field(default_factory=list)
    # Distance-to-coast cache keyed by integer (x, y) cell (1 wu resolution).
    # Computed once per unique cell; avoids per-tick polygon sweeps in hot path.
    _dist_cache: dict = field(default_factory=dict, init=False, repr=False)

    def add_island(self, name: str, polygon: Polygon, is_mainland: bool = False,
                   land_type: str = "island") -> None:
        """Add an island or mainland to the world."""
        self.islands.append(Island(name=name, polygon=polygon, is_mainland=is_mainland,
                                   land_type=land_type))

    def add_port(self, name: str, x: float, y: float, port_type: str, size: str,
                 refuel: bool, speed_limit: Optional[float] = None,
                 max_draft_m: Optional[float] = None) -> None:
        """Add a port to the world and initialise its berths."""
        from config import PORT_BERTH_OFFSET
        port = Port(
            name=name,
            position=(x, y),
            port_type=port_type,
            size=size,
            refuel=refuel,
            speed_limit=speed_limit,
            max_draft_m=max_draft_m,
        )
        port._init_berths(PORT_BERTH_OFFSET)
        self.ports.append(port)

    def add_zone(self, name: str, x: float, y: float, radius: float,
                 kind: str, speed_limit: Optional[float] = None) -> None:
        """Add a restriction zone to the world."""
        self.zones.append(Zone(
            name=name,
            center=(x, y),
            radius=radius,
            kind=kind,
            speed_limit=speed_limit,
        ))

    def add_nav_mark(self, name: str, x: float, y: float, kind: str) -> None:
        """Add a navigation mark (buoy/beacon) to the world."""
        self.nav_marks.append(NavMark(name=name, position=(x, y), kind=kind))

    def add_vessel(self, vessel: object) -> None:
        """Register a vessel in the world."""
        self.vessels.append(vessel)

    def find_port(self, name: str) -> Optional[Port]:
        """Return a port by name, or None if not found."""
        for port in self.ports:
            if port.name == name:
                return port
        return None

    def get_zones_containing(self, position: Position) -> List[Zone]:
        """Return all zones that currently contain the given position."""
        return [zone for zone in self.zones if zone.contains(position)]

    def point_in_island(self, position: Position) -> bool:
        """Return True if the position is inside any island (grounding check)."""
        for island in self.islands:
            if self._point_in_polygon(position, island.polygon):
                return True
        return False

    def water_depth_at(self, position: Position, tide_level: float = 0.0) -> float:
        """Return water depth in metres at position, including tidal adjustment.

        Model layers (evaluated in order):
          1. Land polygon  → 0 m  (extreme grounding case)
          2. Shallow zone  → DEPTH_SHOAL_SKERRY (named shoal, e.g. Skerry Bank)
          3. Open water    → min(DEPTH_OFFSHORE, dist_to_coast * DEPTH_COASTAL_SLOPE)
        Tidal adjustment (TIDAL_DEPTH_INFLUENCE * tide_level) applied to layers 2 & 3.
        """
        from config import (DEPTH_OFFSHORE, DEPTH_COASTAL_SLOPE,
                            DEPTH_SHOAL_SKERRY, TIDAL_DEPTH_INFLUENCE)

        if self.point_in_island(position):
            return 0.0

        for zone in self.zones:
            if zone.kind == "shallow" and zone.contains(position):
                return max(0.0, DEPTH_SHOAL_SKERRY + tide_level * TIDAL_DEPTH_INFLUENCE)

        # Depth from coastal proximity — cached at 1 wu integer resolution to
        # avoid re-sweeping all polygon edges on every physics tick.
        ix, iy = int(position[0]), int(position[1])
        dist = self._dist_cache.get((ix, iy))
        if dist is None:
            dist = self._min_dist_to_coast((ix + 0.5, iy + 0.5))
            self._dist_cache[(ix, iy)] = dist

        base = min(DEPTH_OFFSHORE, dist * DEPTH_COASTAL_SLOPE)
        return max(0.0, base + tide_level * TIDAL_DEPTH_INFLUENCE)

    def _min_dist_to_coast(self, position: Position) -> float:
        """Minimum world-unit distance from position to any island polygon edge."""
        min_d = float('inf')
        for island in self.islands:
            poly = island.polygon
            n = len(poly)
            for i in range(n):
                d = _point_to_segment_dist(position, poly[i], poly[(i + 1) % n])
                if d < min_d:
                    min_d = d
        return min_d

    @staticmethod
    def _point_in_polygon(point: Position, polygon: Polygon) -> bool:
        """Ray-casting algorithm to check if a point is inside a polygon."""
        x, y = point
        n = len(polygon)
        inside = False

        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y

        return inside
