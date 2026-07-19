"""world_data.py
The fictional sea this simulator takes place in: the VELA SEA.

This is NOT a real place, but it is laid out like a real one would be — a
mainland coast in the southwest, a scatter of islands, a narrow shipping strait,
designated zones (naval exclusion, conservation, anchorage, traffic separation),
a charted shoal to avoid, and an offshore energy field. Ports sit at the water's
edge of land, near natural harbours, the way real ports do.

COORDINATE SYSTEM
-----------------
World units are "nautical units" on a 1400 x 980 plane.
  x increases to the EAST, y increases SOUTHWARD (y=0 = top = north coast).
The Camera is responsible for flipping/scaling this to screen pixels — this file
only deals in world coordinates, never pixels.

HOW TO USE
----------
Everything below is plain data (lists of dicts) so it stays independent of your
exact class constructors. The `populate_world(world)` helper at the bottom shows
how to load it into the engine's World object. If your World/Port/Island/Zone
constructors use different argument names, adapt the calls there — the DATA does
not need to change.
"""

# ---------------------------------------------------------------------------
# WORLD BOUNDS
# ---------------------------------------------------------------------------
WORLD_NAME = "The Vela Sea"
WORLD_WIDTH = 1400
WORLD_HEIGHT = 980


# ---------------------------------------------------------------------------
# LANDMASSES (islands + mainland)
# Each landmass is a closed polygon: a list of (x, y) points. Vessels cannot
# sail across land — touching one is a grounding. The mainland is just a very
# large landmass flagged is_mainland for the renderer.
# ---------------------------------------------------------------------------
ISLANDS = [
    {
        "name": "Mainland (Carrick Coast)",
        "is_mainland": True,
        "land_type": "mainland",
        "polygon": [
            (0, 0), (0, 270), (90, 305), (185, 285),
            (265, 235), (350, 210), (430, 150),
            (390, 80), (300, 30), (175, 0),
        ],
    },
    {
        "name": "Carrow Island",
        "is_mainland": False,
        "land_type": "island",
        "polygon": [
            (480, 430), (498, 502), (560, 532),
            (622, 492), (632, 420), (580, 378), (508, 390),
        ],
    },
    {
        "name": "Vesper Isle",
        "is_mainland": False,
        "land_type": "island",
        "polygon": [
            (430, 688), (442, 762), (502, 782),
            (542, 740), (520, 678), (462, 668),
        ],
    },
    {
        "name": "Brattlin North",
        "is_mainland": False,
        "land_type": "island",
        "polygon": [
            (658, 508), (670, 572), (722, 582), (742, 528), (708, 498),
        ],
    },
    {
        "name": "Brattlin South",
        "is_mainland": False,
        "land_type": "island",
        "polygon": [
            (738, 612), (750, 672), (802, 682), (822, 628), (790, 600),
        ],
    },
    {
        "name": "Sable Rock",   # small rocky islet near the conservation area
        "is_mainland": False,
        "land_type": "rocky",
        "polygon": [
            (372, 540), (380, 568), (408, 572), (416, 546), (396, 528),
        ],
    },
    {
        # Irregular island group northeast — guards the approach to Thornwick Roads.
        "name": "Thornwick Rocks",
        "is_mainland": False,
        "land_type": "rocky",
        "polygon": [
            (1002, 250), (1020, 228), (1052, 220), (1080, 238),
            (1092, 265), (1082, 300), (1055, 322), (1022, 315), (1000, 280),
        ],
    },
    {
        # Small rocky outcrop southeast, between Cape Durran and Merin Bay.
        "name": "Durran Shoal",
        "is_mainland": False,
        "land_type": "rocky",
        "polygon": [
            (938, 582), (952, 574), (968, 578), (974, 594), (966, 610), (940, 606),
        ],
    },
    {
        # The Twins (west) — small rocky pair in the open northeast sea.
        # Kept north of y=120 so FV North Fisher's y=150 trawl leg stays clear.
        "name": "Twin Rock West",
        "is_mainland": False,
        "land_type": "rocky",
        "polygon": [
            (862, 52), (876, 44), (892, 50), (896, 66), (884, 78), (866, 72),
        ],
    },
    {
        "name": "Twin Rock East",
        "is_mainland": False,
        "land_type": "rocky",
        "polygon": [
            (916, 84), (932, 78), (946, 88), (942, 104), (926, 110), (912, 100),
        ],
    },
]


# ---------------------------------------------------------------------------
# PORTS (destinations)
# type:  "commercial" | "fishing" | "marina" | "quay"
# size:  "large" | "medium" | "small"
# refuel: whether powered vessels can take on fuel here
# speed_limit: harbour-approach speed limit in knots (None = no specific limit)
# ---------------------------------------------------------------------------
PORTS = [
    {
        "name": "Port Maren",
        "x": 105, "y": 315,
        "type": "commercial", "size": "large",
        "refuel": True, "speed_limit": 8,
        "notes": "Principal commercial port of the Carrick Coast. Deep-water "
                 "berths for cargo and tankers.",
    },
    {
        "name": "Saltgate Harbour",
        "x": 300, "y": 225,
        "type": "fishing", "size": "small",
        "refuel": True, "speed_limit": 6,
        "notes": "Working fishing harbour. Limited fuel; small craft only.",
    },
    {
        "name": "Port Ardent",
        "x": 648, "y": 460,
        "type": "commercial", "size": "medium",
        "refuel": True, "speed_limit": 8,
        "notes": "Island commercial port on Carrow. Main hub of the eastern sea.",
    },
    {
        "name": "Vesper Cove",
        "x": 512, "y": 654,
        "type": "marina", "size": "small",
        "refuel": True, "speed_limit": 5,
        "notes": "Sheltered marina favoured by sailing vessels.",
    },
    {
        "name": "Brattlin Light Quay",
        "x": 712, "y": 595,
        "type": "quay", "size": "small",
        "refuel": False, "speed_limit": 6,
        "notes": "Tiny supply quay beside the strait. No refuelling.",
    },
    {
        "name": "Thornwick Roads",
        "x": 1100, "y": 200,
        "type": "anchorage", "size": "medium",
        "refuel": True, "speed_limit": 6,
        "notes": "Deep-water northeastern anchorage east of Thornwick Rocks. "
                 "Natural shelter; large vessels await favourable tides here.",
    },
    {
        "name": "Cape Durran",
        "x": 1200, "y": 500,
        "type": "commercial", "size": "small",
        "refuel": True, "speed_limit": 8,
        "notes": "Eastern trading post. Regional cargo and supply runs; "
                 "small commercial quay with alongside berths.",
    },
    {
        "name": "Merin Bay",
        "x": 900, "y": 750,
        "type": "marina", "size": "small",
        "refuel": True, "speed_limit": 5,
        "notes": "Southern leisure marina, popular with cruising yachts. "
                 "Well-sheltered; excellent holding ground.",
    },
    {
        "name": "Kessock Anchorage",
        "x": 845, "y": 400,
        "type": "anchorage", "size": "small",
        "refuel": False, "speed_limit": 4,
        "max_draft_m": 4.0,
        "notes": "Small-craft anchorage in the lee of the Kessock naval area. "
                 "Shallow holding ground — vessels drawing 4 m or more refused.",
    },
    {
        "name": "Outer Reach Terminal",
        "x": 1320, "y": 620,
        "type": "commercial", "size": "large",
        "refuel": True, "speed_limit": 8,
        "notes": "Large offshore deep-water terminal on the eastern reach. "
                 "Open to all vessels; principal hub for long-haul cargo.",
    },
]


# ---------------------------------------------------------------------------
# ZONES (rules & hazards)
# Circular areas with a 'kind' the rules system interprets:
#   "no_entry"    – entry prohibited (naval/security/energy fields)
#   "speed_limit" – must not exceed 'speed_limit' knots inside
#   "protected"   – marine conservation; restricted activity, slow transit only
#   "anchorage"   – designated anchoring area (informational/where you may stop)
#   "tss"         – traffic separation scheme; directional transit rules apply
#   "shallow"     – charted shoal; grounding/depth hazard for deep-draft vessels
# ---------------------------------------------------------------------------
ZONES = [
    {
        "name": "Maren Approach",
        "x": 150, "y": 320, "radius": 75,
        "kind": "speed_limit", "speed_limit": 8,
        "notes": "Reduced-speed approach to Port Maren.",
    },
    {
        "name": "Kessock Naval Exclusion Zone",
        "x": 830, "y": 270, "radius": 95,
        "kind": "no_entry", "speed_limit": None,
        "notes": "Live naval area. Entry strictly prohibited.",
    },
    {
        "name": "Aubrey Marine Conservation Area",
        "x": 400, "y": 555, "radius": 90,
        "kind": "protected", "speed_limit": 6,
        "notes": "Protected habitat around Sable Rock. Slow, careful transit; "
                 "no fishing.",
    },
    {
        "name": "Carrow Strait (Traffic Separation Scheme)",
        "x": 760, "y": 595, "radius": 55,
        "kind": "tss", "speed_limit": 10,
        "notes": "Narrow strait between the Brattlins. Keep to your lane; "
                 "directional traffic only.",
    },
    {
        "name": "North Field Anchorage",
        "x": 300, "y": 615, "radius": 70,
        "kind": "anchorage", "speed_limit": 4,
        "notes": "Designated waiting/anchoring area for vessels awaiting a berth.",
    },
    {
        "name": "Skerry Bank",
        "x": 445, "y": 335, "radius": 58,
        "kind": "shallow", "speed_limit": None,
        "notes": "Charted shoal. Insufficient depth for deep-draft vessels at "
                 "low tide — grounding hazard.",
    },
    {
        "name": "Tarn Offshore Wind Array",
        "x": 655, "y": 805, "radius": 65,
        "kind": "no_entry", "speed_limit": None,
        "notes": "Offshore wind field. Entry prohibited.",
    },
    {
        "name": "Thornwick Approach",
        "x": 1100, "y": 200, "radius": 40,
        "kind": "speed_limit", "speed_limit": 6,
        "notes": "Reduced-speed approach to Thornwick Roads anchorage.",
    },
    {
        "name": "Cape Durran TSS",
        "x": 1200, "y": 500, "radius": 50,
        "kind": "tss", "speed_limit": 10,
        "notes": "Traffic separation scheme for the eastern shipping lane. "
                 "Keep to your lane; directional transit only.",
    },
    {
        "name": "Merin Bay Conservation",
        "x": 900, "y": 750, "radius": 45,
        "kind": "protected", "speed_limit": 4,
        "notes": "Protected marine conservation area. Slow transit; "
                 "no anchoring outside the marina.",
    },
    {
        "name": "Twin Rocks Conservation Area",
        "x": 905, "y": 80, "radius": 60,
        "kind": "protected", "speed_limit": 5,
        "notes": "Protected seabird colony around The Twins. "
                 "Slow, careful transit only.",
    },
]


# ---------------------------------------------------------------------------
# NAVIGATION MARKS (buoys / beacons) — optional but adds realism on the chart.
# kind: "lateral_port" (red, keep to port inbound), "lateral_stbd" (green),
#       "cardinal_n/e/s/w" (marks the safe side of a hazard), "safe_water".
# ---------------------------------------------------------------------------
NAV_MARKS = [
    {"name": "Maren No.1", "x": 205, "y": 360, "kind": "safe_water"},
    {"name": "Maren No.2", "x": 150, "y": 335, "kind": "lateral_stbd"},
    {"name": "Maren No.3", "x": 130, "y": 318, "kind": "lateral_port"},
    {"name": "Skerry N Cardinal", "x": 445, "y": 400, "kind": "cardinal_n"},
    {"name": "Skerry S Cardinal", "x": 445, "y": 272, "kind": "cardinal_s"},
    {"name": "Strait N Approach", "x": 760, "y": 660, "kind": "safe_water"},
    {"name": "Strait S Approach", "x": 760, "y": 530, "kind": "safe_water"},
    {"name": "Ardent Fairway", "x": 670, "y": 410, "kind": "safe_water"},
]


# ---------------------------------------------------------------------------
# FERRY ROUTES — fixed routes for ferry-type vessels, as ordered port names.
# Useful for spawning ferries that ply sensible lanes.
# ---------------------------------------------------------------------------
FERRY_ROUTES = [
    {"name": "Coastal Line", "stops": ["Port Maren", "Port Ardent", "Vesper Cove"]},
    {"name": "Island Hopper", "stops": ["Port Ardent", "Brattlin Light Quay", "Vesper Cove"]},
]


# ---------------------------------------------------------------------------
# VESSEL ROUTES (Chunk E)
# Ordered (x, y) position lists.  Port coordinates are exact; open-sea
# waypoints are chosen to avoid Skerry Bank (centre 445,335 r=58) and all
# island polygons.  All routes loop continuously (A→B→C→A→…).
#
# COORDINATE NOTE: y increases downward on screen (y=0 = top = mainland).
# Safe passages must go SOUTH (higher y) around all hazards, not north.
# Every waypoint below was verified: not in any island, depth=60 m (open sea).
#
# Key clearances:
#   Mainland coast: y > 310 for x < 200; y > 220 for x 200–400.
#   Skerry Bank south edge: y > 393 clears the shoal.
#   Carrow Island: x < 480 clears the west side; y > 532 clears the south side.
#   Brattlin North: y > 582 or x > 742 to pass clear.
# ---------------------------------------------------------------------------

# Intermediate open-sea waypoints — all verified at depth ≥ 60 m, no island.
_WP_SE_OPEN    = (350, 460)  # SE of Port Maren; clear of mainland and Skerry south edge
# Moved south from (500, 565): the old position put the leg to _WP_ARDENT_APP
# within 4.66 wu of Carrow's south rim at (562,536).  An 8 m-draft cargo grounds
# at 2.88 wu off any coast at low water, and uncompensated leeway costs ~0.22 wu
# of clearance per knot of onshore wind — so ~8 kn was enough to beach it, which
# made this the busiest grounding site on the chart.  (505, 580) opens the pinch
# to 13.25 wu, i.e. ~41 kn of tolerance, at the cost of ~5 wu of extra passage.
_WP_S_ISLANDS  = (505, 580)  # south of Carrow Island (island max y 532)
_WP_ARDENT_APP = (640, 500)  # E of Carrow (max x 632), W of Brattlin N (min x 658)
_WP_S_BRAT     = (640, 590)  # S of Brattlin North (max y 582), N of Brattlin South
_WP_S_CARROW   = (580, 610)  # S of Carrow, S of Brattlin North, W of Brattlin South
_WP_WEST_SEA   = (250, 560)  # open west sea
_WP_FISH_OUT   = (360, 450)  # fishing outbound — south of Skerry Bank south edge
_WP_FISH_GND   = (415, 520)  # fishing ground — open sea, south of Skerry & Carrow
_WP_SAIL_MID   = (350, 450)  # sailboat mid-leg waypoint

# Skerry Bank clearance — 140.9 wu from centre (83 wu from the 58 wu zone boundary).
# At tide=0 Skerry depth is only 5 m; at low tide (−3 m) it drops to 2 m, below the
# ferry's 4.5 m and even below the CG's 2.5 m UKC requirement.  Both vessels must
# pass through this waypoint on the eastbound leg to maintain ≥ 80 wu zone clearance.
_WP_SKERRY_CLEAR = (380, 460)  # south of Skerry Bank; depth 60 m, no zones

# New waypoints for the 4 additional vessels (all verified by verify_new_routes.py)
_WP_W_APPROACH  = (300, 420)  # south of Saltgate — western approach corridor
_WP_W_FISH_GND  = (200, 480)  # western fishing ground; dist to coast > 200 wu
# SY Morning Breeze: single SW mark at bearing 135°/315° from Saltgate (beam reach
# both ways with default NE wind, wind_angle=±90°, full drive on both legs).
_WP_SAIL2_WEST  = (52, 473)   # SW open sea; 135° beam reach from Saltgate
_WP_SALTGATE_S  = (300, 320)  # due-south approach; x=300 keeps path clear of coast edge

# Ferry: 4-port clockwise loop using the south corridor.
# _WP_SKERRY_CLEAR gives an explicit 80+ wu buffer from Skerry Bank on the eastbound leg.
VESSEL_ROUTE_FERRY = [
    (105, 315),       # Port Maren
    _WP_SE_OPEN,      # SE open sea; clears mainland coast
    _WP_SKERRY_CLEAR, # explicit 140.9 wu clearance from Skerry Bank centre
    _WP_S_ISLANDS,    # south of Carrow Island
    _WP_ARDENT_APP,   # gap between Carrow (max x 632) and Brattlin N (min x 658)
    (648, 460),      # Port Ardent
    _WP_S_BRAT,      # south of Brattlin North
    (712, 595),      # Brattlin Light Quay
    _WP_S_CARROW,    # south of Carrow, west of Brattlin South
    (512, 654),      # Vesper Cove
    _WP_WEST_SEA,    # west return leg
]

# Cargo: Port Maren ↔ Port Ardent, south corridor (safe for 8 m draft).
# Retraces the same waypoints on the return leg for predictable routing.
VESSEL_ROUTE_CARGO = [
    (105, 315),      # Port Maren
    _WP_SE_OPEN,
    _WP_S_ISLANDS,
    _WP_ARDENT_APP,
    (648, 460),      # Port Ardent
    _WP_ARDENT_APP,  # retrace on return
    _WP_S_ISLANDS,
    _WP_SE_OPEN,
]

# Fishing: Saltgate Harbour → fishing ground → back.
VESSEL_ROUTE_FISHING = [
    (300, 225),      # Saltgate Harbour
    _WP_FISH_OUT,    # south into open sea
    _WP_FISH_GND,    # fishing ground
    _WP_FISH_OUT,    # retrace inbound
]

# Cargo2: MV Carrick Star — Port Maren ↔ Brattlin Light Quay via south corridor.
# Smaller than Vela (draft 6.5 m), retraces same corridor but different phase.
# Brattlin has no refuel, so the ship tanks up fully at Port Maren each visit.
VESSEL_ROUTE_CARGO2 = [
    (105, 315),       # Port Maren (refuel)
    _WP_SE_OPEN,
    _WP_S_ISLANDS,
    _WP_ARDENT_APP,
    _WP_S_BRAT,
    (712, 595),       # Brattlin Light Quay (no refuel)
    _WP_S_BRAT,       # retrace on return
    _WP_ARDENT_APP,
    _WP_S_ISLANDS,
    _WP_SE_OPEN,
]

# Fishing2: FV Skerrywatch — Saltgate Harbour to the western fishing ground.
# Different corridor from FV Horizon (which works the SE / Skerry Bank approach).
VESSEL_ROUTE_FISHING2 = [
    (300, 225),       # Saltgate Harbour (refuel)
    _WP_W_APPROACH,   # south, open western approach
    _WP_W_FISH_GND,   # western fishing ground
    _WP_W_APPROACH,   # retrace inbound
]

# Tug: Ardent Pilot — short shuttle Port Ardent ↔ Brattlin Light Quay.
# Quick turnaround; refuels only at Ardent (Brattlin has no fuel).
VESSEL_ROUTE_TUG = [
    (648, 460),       # Port Ardent (refuel)
    _WP_ARDENT_APP,
    _WP_S_BRAT,
    (712, 595),       # Brattlin Light Quay (no refuel)
    _WP_S_BRAT,       # retrace
    _WP_ARDENT_APP,
]

# Sailboat2: SY Morning Breeze — western triangle from Saltgate.
# Outbound leg is a pure beam reach; return via a due-south approach waypoint
# to avoid the shallow zone where bearing 315° runs near-parallel to the coast:
#   Saltgate→WP_SAIL2_WEST: bearing=135°, wind_angle=90° (beam reach ✓)
#   WP_SAIL2_WEST→WP_SALTGATE_S: bearing=334°, wind_angle=77° (close reach ✓)
#   WP_SALTGATE_S→Saltgate:  bearing=270°, wind_angle=135° (broad reach ✓)
# Approach along x=300 keeps coast distance > 3 wu until within PORT_DETECT_RADIUS.
VESSEL_ROUTE_SAILBOAT2 = [
    (300, 225),       # Saltgate Harbour (only port in loop)
    _WP_SAIL2_WEST,   # SW open sea beam reach
    _WP_SALTGATE_S,   # due-south approach waypoint — clears coast on final leg
]

# Sailboat: eastern circuit that avoids Vesper Isle entirely.
# With NE wind (wind_direction=45°) the no-go zone is headings 0–90°.
# All four legs have abs(wind_angle) > 45°, verified with grid-cell depth model:
#   Vesper→(660,600):  bearing≈340°, wa≈65°, min_grid_dist=21.9 wu ✓
#   (660,600)→(590,760): bearing≈114°, wa≈69°, min_grid_dist=30.0 wu ✓
#   (590,760)→(570,660): bearing≈259°, wa≈146°, min_grid_dist=42.8 wu ✓
#   (570,660)→Vesper:    bearing≈186°, wa≈141°, min_grid_dist=21.9 wu ✓
# The critical lesson: the direct S→Vesper return hugged Vesper Isle's eastern
# edge (542,740)→(520,678).  Routing via (570,660) — north of Vesper Isle — keeps
# every grid cell ≥ 21.9 wu from coast (depth ≥ 58 m at any tide state).
VESSEL_ROUTE_SAILBOAT = [
    (512, 654),    # Vesper Cove (only port — stays here on each loop)
    (660, 600),    # NE mark — south of Brattlin North, east of Carrow
    (590, 760),    # SE mark — east of Vesper Isle (x>542), outside Tarn (dist≈75 wu)
    (570, 660),    # NW approach — north of Vesper Isle (y=660<668), clean return
]

# Tanker: MT Amber Star — slow deep-sea loop, Port Maren → NE open ocean → back.
# Uses _WP_SE_OPEN as an intermediate to clear the mainland coast.
# (800, 200) is in the open NE ocean, well clear of all islands and Skerry Bank.
VESSEL_ROUTE_TANKER = [
    (105, 315),    # Port Maren
    (350, 460),    # _WP_SE_OPEN — clear of mainland
    (800, 200),    # deep NE open ocean
    (350, 460),    # retrace via SE open
]

# Coast Guard: CG Sentinel — all-ports patrol loop.
# At low tide (−3 m) Skerry Bank depth = 2.0 m, below the CG's 2.5 m UKC.
# _WP_SKERRY_CLEAR routes the eastbound leg 140.9 wu clear of Skerry Bank centre.
VESSEL_ROUTE_COAST_GUARD = [
    (105, 315),       # Port Maren
    (200, 420),       # open water south — clears mainland NE edge
    (300, 420),       # _WP_W_APPROACH — safe Saltgate approach from south
    (300, 225),       # Saltgate Harbour
    (300, 420),       # return south before swinging east
    _WP_SKERRY_CLEAR, # explicit 140.9 wu clearance from Skerry Bank centre
    _WP_S_ISLANDS,    # south of Carrow Island (avoids land) — use the constant
                      # so this route cannot drift out of sync with the others
    (640, 500),    # _WP_ARDENT_APP
    (648, 460),    # Port Ardent
    (640, 590),    # _WP_S_BRAT
    (712, 595),    # Brattlin Light Quay
    (580, 610),    # _WP_S_CARROW
    (512, 654),    # Vesper Cove
    (250, 560),    # _WP_WEST_SEA — return west
]

# New eastern-corridor waypoints (verified safe for draft 8 m):
#   _WP_BRAT_EAST:  y=590 is south of Brattlin N (max y=582) AND north of Brattlin S
#                   (min y=600), x=850 is east of both islands (x_max=822). 10 wu gap.
#   _WP_NE_GATE:    east of Thornwick Rocks (island x_max ≈ 1092); leg to (850,590)
#                   passes north of Durran Shoal (y min=574 → leg y=512 at x=938).
_WP_BRAT_EAST  = (850, 590)   # east of Brattlin islands, in the open SE corridor
_WP_NE_GATE    = (1120, 350)  # NE gate — east of Thornwick Rocks

# Thornwick waypoint connecting Merin Bay area to Vesper Cove, bypassing Tarn wind farm.
# (750, 680) is outside Brattlin South polygon and 157 wu clear of Tarn (655, 805, r=65).
_WP_MERIN_VESPER = (750, 680)

# MV Thornwick (cargo): Port Maren ↔ Thornwick Roads via south corridor then NE.
# Uses proven south-corridor waypoints (SE_OPEN → S_ISLANDS → ARDENT_APP → S_BRAT)
# to clear Carrow Island and Brattlin N, then (850,590) east of Brattlin S (x_max=822),
# then NE_GATE at x=1120 east of Thornwick Rocks (x_max≈1092, clearance≈16.5 wu).
VESSEL_ROUTE_THORNWICK = [
    (105, 315),       # Port Maren
    _WP_SE_OPEN,      # (350, 460) — clears mainland coast and Skerry Bank south edge
    _WP_S_ISLANDS,    # (505, 580) — south of Carrow Island (max y=532)
    _WP_ARDENT_APP,   # (640, 500) — gap between Carrow (max x=632) and Brattlin N
    _WP_S_BRAT,       # (640, 590) — south of Brattlin North (max y=582)
    _WP_BRAT_EAST,    # (850, 590) — east of Brattlin South (max x=822)
    _WP_NE_GATE,      # (1120, 350) — east of Thornwick Rocks
    (1100, 200),      # Thornwick Roads
    _WP_NE_GATE,      # retrace on return
    _WP_BRAT_EAST,
    _WP_S_BRAT,
    _WP_ARDENT_APP,
    _WP_S_ISLANDS,
    _WP_SE_OPEN,
]

# SY Blue Horizon (sailboat): leisure cruise, Vesper Cove → Cape Durran → Merin Bay.
# All legs verified out of irons (|wind_angle| > 45° at default NE wind, direction=45°):
#   Vesper → Cape Durran:  bearing≈347°, wind_angle≈ 58° ✓
#   Cape Durran → Merin:   bearing≈140°, wind_angle≈−95° (abs 95°) ✓
#   Merin → _WP_MERIN_VESPER: bearing≈205°, wind_angle≈−160° (abs 160°) ✓
#   _WP → Vesper:          bearing≈186°, wind_angle≈−141° (abs 141°) ✓
# The Merin→Vesper leg routes via (750, 680) to stay clear of Tarn Wind Farm.
VESSEL_ROUTE_BLUE_HORIZON = [
    (512, 654),       # Vesper Cove
    (1200, 500),      # Cape Durran
    (900, 750),       # Merin Bay
    _WP_MERIN_VESPER, # clears Tarn Wind Farm on return to Vesper
]

# New east-coast corridor waypoint between Cape Durran and Thornwick Roads.
# x=1150 provides 58+ wu clearance from Thornwick Rocks (x_max ≈ 1092).
_WP_EASTERN_STAR_MID = (1150, 350)

# MV Eastern Star — inter-port cargo, Cape Durran ↔ Thornwick Roads.
# Short east-coast shuttle; stays at x ≥ 1150 to clear Thornwick Rocks.
VESSEL_ROUTE_EASTERN_STAR = [
    (1200, 500),              # Cape Durran
    _WP_EASTERN_STAR_MID,     # (1150, 350) NE passage — clear of Thornwick Rocks
    (1100, 200),              # Thornwick Roads
    _WP_EASTERN_STAR_MID,     # retrace on return
]

# FV North Fisher — Thornwick-based trawler working northern open grounds.
# (900, 150) and (700, 150) are open northern sea, depth ≥ 60 m, no islands.
VESSEL_ROUTE_NORTH_FISHER = [
    (1100, 200),   # Thornwick Roads (home port, refuel)
    (900, 150),    # eastern northern fishing ground
    (700, 150),    # western northern fishing ground
    (900, 150),    # retrace inbound
]

# MV Tender I — service tender, Vesper Cove ↔ Merin Bay.
# Routes via _WP_MERIN_VESPER (750, 680) to clear Brattlin South (x_max=822)
# and Tarn Wind Farm (655, 805, r=65; clearance ≈ 141 wu >> r).
VESSEL_ROUTE_TENDER = [
    (512, 654),        # Vesper Cove
    _WP_MERIN_VESPER,  # (750, 680) — clear of Brattlin South and Tarn
    (900, 750),        # Merin Bay
    _WP_MERIN_VESPER,  # retrace waypoint
]


# ---------------------------------------------------------------------------
# LOADER
# Wires the data above into your engine's World object. Adapt the constructor
# calls to match your actual World/Port/Island/Zone signatures if they differ —
# the data itself stays the same.
# ---------------------------------------------------------------------------
def populate_world(world):
    """Load all map data into a World instance and return it."""

    # Landmasses
    for land in ISLANDS:
        world.add_island(
            name=land["name"],
            polygon=land["polygon"],
            is_mainland=land["is_mainland"],
            land_type=land.get("land_type", "island"),
        )

    # Ports
    for p in PORTS:
        world.add_port(
            name=p["name"], x=p["x"], y=p["y"],
            port_type=p["type"], size=p["size"],
            refuel=p["refuel"], speed_limit=p["speed_limit"],
            max_draft_m=p.get("max_draft_m"),
        )

    # Zones
    for z in ZONES:
        world.add_zone(
            name=z["name"], x=z["x"], y=z["y"], radius=z["radius"],
            kind=z["kind"], speed_limit=z["speed_limit"],
        )

    # Navigation marks
    for m in NAV_MARKS:
        world.add_nav_mark(name=m["name"], x=m["x"], y=m["y"], kind=m["kind"])

    return world
