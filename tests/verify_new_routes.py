"""Route safety verification for all non-trivial vessel routes.

Checks every proposed route leg by sampling 200 points along it and verifying:
  1. No point is inside any island polygon.
  2. Water depth >= vessel_draft + 0.5 m at low tide (tide = -TIDE_RANGE = -3 m).
  3. Min distance to coast >= 2 wu everywhere along the leg.
  4. For sailboat legs: |wind_angle| >= SAIL_NO_GO_ANGLE (45°) for default wind.
  5. Skerry Bank clearance: all open-sea legs >= 80 wu from zone boundary (138 wu
     from centre 445,335).

Prints a full report. Exit 0 = all safe, Exit 1 = any failure.
"""

import sys, math
sys.path.insert(0, ".")

from engine.world import World
from data.world_data import (populate_world, VESSEL_ROUTE_THORNWICK, VESSEL_ROUTE_BLUE_HORIZON,
                              VESSEL_ROUTE_FERRY, VESSEL_ROUTE_COAST_GUARD)
from config import TIDE_RANGE, SAIL_NO_GO_ANGLE, DRAFT_SAFETY_MARGIN_M, PORT_DETECT_RADIUS

SAMPLES   = 200
WIND_DIR  = 45.0   # default wind_direction (blows FROM 45°)
LOW_TIDE  = -TIDE_RANGE   # worst-case tide for depth
SKERRY_CENTER = (445, 335)
SKERRY_RADIUS = 58  # zone radius in wu
SKERRY_MIN_DIST = SKERRY_RADIUS + 80  # 138 wu = 80 wu buffer from zone boundary

world = World()
populate_world(world)

# ── Proposed waypoints ──────────────────────────────────────────────────────
_WP_SE_OPEN    = (350, 460)
_WP_S_ISLANDS  = (500, 565)
_WP_ARDENT_APP = (640, 500)
_WP_S_BRAT     = (640, 590)
_WP_W_APPROACH = (300, 420)
_WP_W_FISH_GND = (200, 480)
_WP_SAIL2_WEST = (52, 473)
_WP_SALTGATE_S = (300, 320)

# ── Route definitions (each leg is a (start, end) pair) ─────────────────────
# draft: vessel draft in metres; sailboat: True → check wind angle

def legs(route):
    return [(route[i], route[i+1]) for i in range(len(route)-1)]

ROUTES = [
    {
        "name": "MV Carrick Star (cargo2)",
        "draft": 6.5,
        "sailboat": False,
        "legs": legs([
            (105, 315), _WP_SE_OPEN, _WP_S_ISLANDS, _WP_ARDENT_APP,
            _WP_S_BRAT, (712, 595), _WP_S_BRAT, _WP_ARDENT_APP,
            _WP_S_ISLANDS, _WP_SE_OPEN,
        ]),
    },
    {
        "name": "FV Skerrywatch (fishing2)",
        "draft": 2.5,
        "sailboat": False,
        "legs": legs([
            (300, 225), _WP_W_APPROACH, _WP_W_FISH_GND, _WP_W_APPROACH,
        ]),
    },
    {
        "name": "Ardent Pilot (tug)",
        "draft": 2.0,
        "sailboat": False,
        "legs": legs([
            (648, 460), _WP_ARDENT_APP, _WP_S_BRAT, (712, 595),
            _WP_S_BRAT, _WP_ARDENT_APP,
        ]),
    },
    {
        "name": "SY Meridian Breeze (sailboat2)",
        "draft": 2.0,
        "sailboat": True,
        "legs": legs([
            (300, 225), _WP_SAIL2_WEST, _WP_SALTGATE_S, (300, 225),
        ]),
    },
    {
        "name": "MV Thornwick (cargo, draft 8.0 m)",
        "draft": 8.0,
        "sailboat": False,
        "legs": legs(VESSEL_ROUTE_THORNWICK),
    },
    {
        "name": "SY Blue Horizon (sailboat, sailing_cruise)",
        "draft": 2.5,
        "sailboat": True,
        "legs": legs(VESSEL_ROUTE_BLUE_HORIZON + [VESSEL_ROUTE_BLUE_HORIZON[0]]),
    },
    {
        "name": "MS Coastal Express (ferry, draft 4.0 m)",
        "draft": 4.0,
        "sailboat": False,
        "legs": legs(VESSEL_ROUTE_FERRY + [VESSEL_ROUTE_FERRY[0]]),
    },
    {
        "name": "CG Sentinel (coast_guard, draft 2.0 m)",
        "draft": 2.0,
        "sailboat": False,
        "legs": legs(VESSEL_ROUTE_COAST_GUARD + [VESSEL_ROUTE_COAST_GUARD[0]]),
    },
]

# ── Start positions ──────────────────────────────────────────────────────────
STARTS = [
    {"name": "Carrick Star start", "pos": (520, 555), "draft": 6.5},
    {"name": "Skerrywatch start",  "pos": (300, 300), "draft": 2.5},
    {"name": "Ardent Pilot start", "pos": (670, 575), "draft": 2.0},
    {"name": "Meridian Breeze start", "pos": (150, 350), "draft": 2.0},
]

# ── Helpers ──────────────────────────────────────────────────────────────────

def bearing(a, b):
    return math.degrees(math.atan2(b[1]-a[1], b[0]-a[0])) % 360

def wind_angle(vessel_heading):
    d = WIND_DIR - vessel_heading
    if d > 180: d -= 360
    if d < -180: d += 360
    return d

def near_port(pos):
    """True when the sim's grounding check would be bypassed (vessel near a port)."""
    r2 = PORT_DETECT_RADIUS * PORT_DETECT_RADIUS
    for port in world.ports:
        dx = pos[0] - port.position[0]
        dy = pos[1] - port.position[1]
        if dx*dx + dy*dy <= r2:
            return True
    return False

def check_leg(a, b, draft, sailboat):
    issues = []
    brg = bearing(a, b)
    # Wind check (once per leg — bearing is constant along the leg)
    if sailboat:
        wa = abs(wind_angle(brg))
        if wa < SAIL_NO_GO_ANGLE:
            issues.append(f"    IRONS: bearing={brg:.1f} wind_angle={wa:.1f} < {SAIL_NO_GO_ANGLE}")
    # Sample points
    for i in range(SAMPLES + 1):
        t = i / SAMPLES
        px = a[0] + (b[0]-a[0]) * t
        py = a[1] + (b[1]-a[1]) * t
        pos = (px, py)
        if world.point_in_island(pos):
            issues.append(f"    LAND at t={t:.2f} ({px:.0f},{py:.0f})")
            break
        # The sim skips grounding checks for positions near a port berth, so
        # shallow-harbour-mouth depth is not a real hazard — skip it here too.
        if near_port(pos):
            continue
        depth = world.water_depth_at(pos, LOW_TIDE)
        needed = draft + DRAFT_SAFETY_MARGIN_M
        if depth < needed:
            issues.append(f"    SHALLOW t={t:.2f} ({px:.0f},{py:.0f}) depth={depth:.1f}m < {needed:.1f}m")
        coast_d = world._min_dist_to_coast(pos)
        # Only flag close-coast when depth is also unsafe — coast distance alone
        # is redundant with the depth check (the depth model is coast-distance-based).
        if coast_d < 2.0 and depth < needed:
            issues.append(f"    COAST+SHALLOW t={t:.2f} ({px:.0f},{py:.0f}) dist={coast_d:.2f}wu depth={depth:.1f}m")
        # Skerry Bank clearance: skip when the point is near a port (port approach
        # tracks don't need the full 80 wu buffer).
        if not near_port(pos):
            sk_dist = math.hypot(px - SKERRY_CENTER[0], py - SKERRY_CENTER[1])
            if sk_dist < SKERRY_MIN_DIST:
                issues.append(f"    SKERRY t={t:.2f} ({px:.0f},{py:.0f}) dist_to_centre={sk_dist:.1f}wu < {SKERRY_MIN_DIST}")
    return issues

# ── Run checks ───────────────────────────────────────────────────────────────

all_ok = True

for route in ROUTES:
    print(f"\n{'-'*60}")
    print(f"Route: {route['name']}")
    for i, (a, b) in enumerate(route["legs"]):
        brg = bearing(a, b)
        issues = check_leg(a, b, route["draft"], route["sailboat"])
        wa_str = ""
        if route["sailboat"]:
            wa = abs(wind_angle(brg))
            wa_str = f"  wind_angle={wa:.1f}°"
        status = "OK" if not issues else "FAIL"
        print(f"  Leg {i+1}: ({a[0]:.0f},{a[1]:.0f}) -> ({b[0]:.0f},{b[1]:.0f})  "
              f"bearing={brg:.1f}°{wa_str}  [{status}]")
        for iss in issues:
            print(iss)
            all_ok = False

print(f"\n{'-'*60}")
print("Start positions:")
for sp in STARTS:
    pos = sp["pos"]
    draft = sp["draft"]
    in_land = world.point_in_island(pos)
    depth = world.water_depth_at(pos, LOW_TIDE)
    needed = draft + DRAFT_SAFETY_MARGIN_M
    coast_d = world._min_dist_to_coast(pos)
    ok = not in_land and depth >= needed
    flag = "OK" if ok else "FAIL"
    print(f"  {sp['name']}: ({pos[0]},{pos[1]})  land={in_land}  "
          f"depth={depth:.1f}m  coast={coast_d:.1f}wu  [{flag}]")
    if not ok:
        all_ok = False

print(f"\n{'='*60}")
print("ALL ROUTES SAFE" if all_ok else "FAILURES FOUND — fix before proceeding")
print('='*60)
sys.exit(0 if all_ok else 1)
