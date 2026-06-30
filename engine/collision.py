"""COLREGS-simplified collision avoidance: CPA/TCPA computation and give-way logic.

All math is pure Python with no Pygame imports (engine/ rule).
World positions are in world units (wu); speeds are in knots.
Time values are in simulated seconds.

COLREGS rules implemented (simplified):
  Rule 15 — Crossing: the vessel that has the other on its starboard side gives way.
  Rule 14 — Head-on: both should alter to starboard; we use an index tie-break so
             exactly one vessel gives way, avoiding simultaneous mirrored turns.
  Rule 17 — Stand-on: the stand-on vessel keeps course and speed.

Only "underway" and "avoiding" vessels participate; docked, in_port, aground,
adrift, and anchored vessels are invisible to the avoidance system.
"""

from math import atan2, cos, degrees, hypot, radians, sin
from typing import List, Optional, Tuple

from config import (
    KNOTS_TO_UNITS_PER_HOUR,
    NM_PER_WORLD_UNIT,
    COLLISION_DETECTION_RANGE_NM,
    COLLISION_SAFE_CPA_NM,
    COLLISION_SAFE_TCPA_S,
    COLLISION_MAX_AVOID_DEG,
    COLLISION_CLEAR_HYSTERESIS,
    COLLISION_EMERGENCY_CPA_FRAC,
    COLLISION_EMERGENCY_AVOID_DEG,
)

# Convert detection range to world units once at module load (cheap pre-filter).
_DETECT_WU = COLLISION_DETECTION_RANGE_NM / NM_PER_WORLD_UNIT
# Clear threshold (with hysteresis) in nm — wider than trigger to prevent oscillation.
_CLEAR_CPA_NM = COLLISION_SAFE_CPA_NM * COLLISION_CLEAR_HYSTERESIS


def _velocity_wu_per_s(vessel) -> Tuple[float, float]:
    """Return vessel velocity in world-units per sim-second from heading and speed (kn)."""
    spd_wu_hr = vessel.current_speed * KNOTS_TO_UNITS_PER_HOUR
    h = radians(vessel.heading)
    return cos(h) * spd_wu_hr / 3600.0, sin(h) * spd_wu_hr / 3600.0


def find_safe_path(start: Tuple[float, float],
                   end: Tuple[float, float],
                   world,
                   n_samples: int = 20) -> List[Tuple[float, float]]:
    """Return a list of waypoints from start to end that avoids island polygons.

    Checks the direct leg by sampling n_samples points.  If any point is inside
    an island, tries routing via a pre-verified safe intermediate waypoint that
    (a) has a clear leg from start and (b) is closer to end than start is.
    Returns [end] when the direct path is clear, or [intermediate, end] for a
    single-hop detour.  Falls back to [end] (direct) when no clear via-point
    can be found — this is intentionally simple, not A*.
    """
    sx, sy = start
    ex, ey = end

    def _leg_clear(a_pos, b_pos):
        """True when all sampled points along the leg are outside every island."""
        ax, ay = a_pos
        bx, by = b_pos
        for i in range(n_samples + 1):
            t = i / n_samples
            if world.point_in_island((ax + (bx - ax) * t,
                                      ay + (by - ay) * t)):
                return False
        return True

    if _leg_clear(start, end):
        return [end]

    # ── Try a single intermediate from the verified open-sea waypoint network ──
    # Imported here (not at module level) to keep engine/ free of data/ at import
    # time while still reusing the already-verified safe positions.
    try:
        from data.world_data import (   # noqa: PLC0415
            _WP_SE_OPEN, _WP_S_ISLANDS, _WP_ARDENT_APP, _WP_S_BRAT,
            _WP_S_CARROW, _WP_WEST_SEA, _WP_FISH_OUT, _WP_FISH_GND,
            _WP_W_APPROACH, _WP_W_FISH_GND, _WP_SAIL2_WEST,
        )
        _SAFE_HUB_WPS: List[Tuple[float, float]] = [
            _WP_SE_OPEN, _WP_S_ISLANDS, _WP_ARDENT_APP, _WP_S_BRAT,
            _WP_S_CARROW, _WP_WEST_SEA, _WP_FISH_OUT, _WP_FISH_GND,
            _WP_W_APPROACH, _WP_W_FISH_GND, _WP_SAIL2_WEST,
        ]
    except ImportError:
        _SAFE_HUB_WPS = []

    d_start_end = hypot(ex - sx, ey - sy)
    best_wp: Optional[Tuple[float, float]] = None
    best_score = float("inf")

    for wp in _SAFE_HUB_WPS:
        wx, wy = wp
        # Only consider waypoints that are closer to end than start is
        # (ensures we make forward progress, not a longer detour).
        if hypot(ex - wx, ey - wy) >= d_start_end:
            continue
        if not _leg_clear(start, wp):
            continue
        # Score by distance from start — choose the nearest viable intermediate.
        score = hypot(wx - sx, wy - sy)
        if score < best_score:
            best_score = score
            best_wp = wp

    if best_wp is not None:
        return [best_wp, end]
    return [end]  # fallback: direct even if it crosses land


def compute_cpa_tcpa(a, b) -> Tuple[float, float]:
    """Compute (cpa_nm, tcpa_s) for the vessel pair (a, b).

    Returns:
        cpa_nm  — minimum separation distance at closest approach, in nautical miles.
        tcpa_s  — simulated seconds until that closest point.
                  Negative means vessels are already past CPA (diverging).
    """
    drx = b.position[0] - a.position[0]
    dry = b.position[1] - a.position[1]

    avx, avy = _velocity_wu_per_s(a)
    bvx, bvy = _velocity_wu_per_s(b)
    dvx = bvx - avx
    dvy = bvy - avy

    dv_sq = dvx * dvx + dvy * dvy
    if dv_sq < 1e-12:
        # Identical velocities — vessels never converge; CPA equals current distance.
        return hypot(drx, dry) * NM_PER_WORLD_UNIT, float("inf")

    tcpa_s = -(drx * dvx + dry * dvy) / dv_sq

    # Position of b relative to a at TCPA
    cpa_dx = drx + dvx * tcpa_s
    cpa_dy = dry + dvy * tcpa_s
    cpa_nm = hypot(cpa_dx, cpa_dy) * NM_PER_WORLD_UNIT

    return cpa_nm, tcpa_s


def _bearing_deg(a, b) -> float:
    """Bearing from vessel a to vessel b (degrees, 0° = east in this coordinate system)."""
    dx = b.position[0] - a.position[0]
    dy = b.position[1] - a.position[1]
    return degrees(atan2(dy, dx)) % 360.0


def _is_on_starboard(own_heading: float, bearing_to_other: float) -> bool:
    """Return True if 'other' lies on own vessel's starboard (right) side.

    Starboard is the arc (0°, 180°) measured clockwise from own heading.
    Dead ahead (0°) and dead astern (180°) are edge cases; we return False for both
    so they fall through to the head-on tie-break path.
    """
    rel = (bearing_to_other - own_heading) % 360.0
    return 0.0 < rel < 180.0


def _compute_avoid_heading(give_way, severity: float, emergency: bool) -> float:
    """Return the avoidance heading for the give-way vessel.

    Turns to starboard (clockwise) from the vessel's current destination bearing
    by an amount proportional to risk severity (0–1).

    In emergency mode (CPA below the emergency threshold) the maximum turn angle
    doubles to COLLISION_EMERGENCY_AVOID_DEG so the manoeuvre is obvious and fast
    enough to separate vessels that are already critically close.
    """
    if give_way.destination is not None:
        ref = give_way.bearing_to(give_way.destination)
    else:
        ref = give_way.heading

    max_deg = COLLISION_EMERGENCY_AVOID_DEG if emergency else COLLISION_MAX_AVOID_DEG
    avoid_deg = severity * max_deg
    return (ref + avoid_deg) % 360.0


def update_collision_avoidance(vessels) -> None:
    """Run one collision avoidance tick for all vessel pairs.

    Algorithm:
      1. Collect active vessels (underway + avoiding).
      2. For every pair, compute CPA/TCPA.  If within danger thresholds, determine
         the give-way vessel and record the required avoidance heading.
      3. Apply: give-way vessels enter/stay "avoiding"; all others that were
         "avoiding" but had no risk this tick are cleared back to "underway"
         (with a CPA hysteresis margin to prevent oscillation).

    With 8 vessels → 28 pairs; each pair costs ~20 float ops.  Well under 0.1 ms.
    """
    active = [v for v in vessels if v.status in ("underway", "avoiding")]
    n = len(active)

    # needs_avoid maps id(vessel) → (vessel_ref, avoidance_heading, avoid_deg).
    # We key by id() because Vessel is a mutable dataclass and not hashable.
    needs_avoid: dict = {}

    if n >= 2:
        for i in range(n):
            for j in range(i + 1, n):
                a, b = active[i], active[j]

                # Cheap bounding-box pre-filter before the sqrt
                drx = b.position[0] - a.position[0]
                dry = b.position[1] - a.position[1]
                if abs(drx) > _DETECT_WU or abs(dry) > _DETECT_WU:
                    continue
                if hypot(drx, dry) > _DETECT_WU:
                    continue

                cpa_nm, tcpa_s = compute_cpa_tcpa(a, b)

                # Skip if diverging, too far in the future, or already passing safely
                if tcpa_s <= 0.0 or tcpa_s > COLLISION_SAFE_TCPA_S:
                    continue
                if cpa_nm >= COLLISION_SAFE_CPA_NM:
                    continue

                # --- Determine give-way vessel (COLREGS Rules 14–15) ---
                brg_ab = _bearing_deg(a, b)
                brg_ba = _bearing_deg(b, a)
                a_sb = _is_on_starboard(a.heading, brg_ab)
                b_sb = _is_on_starboard(b.heading, brg_ba)

                if a_sb and not b_sb:
                    give_way = a   # b is on a's starboard → a gives way
                elif b_sb and not a_sb:
                    give_way = b   # a is on b's starboard → b gives way
                else:
                    give_way = a   # head-on / ambiguous: index-i vessel gives way

                # The human player is never auto-steered: if COLREGS would make the
                # player the give-way vessel, the AI vessel takes the evasive action
                # instead.  The player stays a stand-on obstacle others avoid, and
                # keeps full manual helm (it never enters "avoiding").
                if getattr(give_way, "is_player", False):
                    give_way = b if give_way is a else a

                # Severity scales 0→1 as CPA shrinks from threshold toward zero.
                # Emergency: below the emergency fraction of SAFE_CPA, snap to max
                # severity so the turn is immediate and large regardless of CPA value.
                # This catches the "almost but not quite zero CPA" cases where a gentle
                # proportional turn was too slow to create real separation.
                emergency = cpa_nm < COLLISION_SAFE_CPA_NM * COLLISION_EMERGENCY_CPA_FRAC
                severity = 1.0 if emergency else max(0.0, min(1.0, 1.0 - cpa_nm / COLLISION_SAFE_CPA_NM))
                avoid_heading = _compute_avoid_heading(give_way, severity, emergency)
                max_deg = COLLISION_EMERGENCY_AVOID_DEG if emergency else COLLISION_MAX_AVOID_DEG
                avoid_deg = severity * max_deg

                # Keep the worst (largest) avoidance request across all pairs
                vid = id(give_way)
                if vid not in needs_avoid or avoid_deg > needs_avoid[vid][2]:
                    needs_avoid[vid] = (give_way, avoid_heading, avoid_deg)

    # --- Apply state changes ---
    for vessel in active:
        vid = id(vessel)
        if vid in needs_avoid:
            vessel.status = "avoiding"
            vessel.avoid_heading = needs_avoid[vid][1]
        elif vessel.status == "avoiding":
            # Hysteresis: keep "avoiding" until the situation is genuinely clear.
            # Re-check all pairs for this vessel using the wider _CLEAR_CPA_NM threshold.
            still_at_risk = False
            for other in active:
                if other is vessel:
                    continue
                drx = other.position[0] - vessel.position[0]
                dry = other.position[1] - vessel.position[1]
                if abs(drx) > _DETECT_WU or abs(dry) > _DETECT_WU:
                    continue
                cpa_nm, tcpa_s = compute_cpa_tcpa(vessel, other)
                if 0.0 < tcpa_s <= COLLISION_SAFE_TCPA_S and cpa_nm < _CLEAR_CPA_NM:
                    still_at_risk = True
                    break

            if not still_at_risk:
                vessel.status = "underway"
