"""Tunable configuration constants for the maritime simulator.

This file centralizes all magic numbers, colors, sizes, and rates so the
simulation is easy to balance and tweak without hunting through the code.
"""

# ============================================================================
# Game identity & persistence
# ============================================================================
GAME_VERSION  = "0.4.0"        # shown on the title screen and stamped into saves
SAVE_FILEPATH = "save.json"    # career save file, relative to the working dir

# ============================================================================
# Title screen
# ============================================================================
TITLE_FONT_SIZE        = 52    # "MERIDIAN SEA" headline
TITLE_SUBTITLE_SIZE    = 18    # "A Maritime Career Simulator" subtitle
TITLE_MENU_FONT_SIZE   = 22    # menu item rows
TITLE_PANEL_WIDTH      = 560   # centered overlay panel width (px)
TITLE_PANEL_HEIGHT     = 420   # centered overlay panel height (px)
TITLE_PANEL_ALPHA      = 215   # overlay darkness — chart stays faintly visible behind

# ============================================================================
# Window & Display
# ============================================================================
WINDOW_MIN_WIDTH = 1600
WINDOW_MIN_HEIGHT = 950
WINDOW_SCALE_FACTOR = 0.90
WINDOW_TITLE = "Maritime Navigation Simulator"
TARGET_FPS = 60

# ============================================================================
# Theme colors
# ============================================================================
# A muted ECDIS palette: deep blues for water, sand-tones for land, and soft
# chart accents that stay legible without high contrast.
THEME = {
    "VOID": (7, 14, 25),
    "DEEP_WATER": (10, 28, 52),
    "SHALLOW_WATER": (40, 84, 115),
    "SHALLOW_BAND": (89, 142, 196),
    "DEPTH_CONTOUR": (135, 170, 195),
    "LAND_FILL": (196, 173, 124),
    "LAND_COAST": (145, 126, 82),
    "LAND_SHADE": (217, 200, 157),
    "GRID_MINOR": (95, 116, 131),
    "GRID_MAJOR": (150, 172, 190),
    "GRID_LABEL": (210, 220, 230),
    "CHART_BAR_BG": (12, 22, 36),
    "SCALE_BAR": (220, 230, 240),
    "NORTH_ARROW": (220, 230, 240),
    "ZONE_LABEL": (240, 242, 245),
    "FRAME": (46, 74, 107),
    "NO_ENTRY": (217, 74, 140),
    "SPEED_LIMIT": (224, 161, 58),
    "PROTECTED": (63, 191, 143),
    "ANCHORAGE": (90, 143, 214),
    "TSS": (160, 111, 214),
    "SHALLOW_HAZARD": (224, 200, 74),
    "BEACH_FRINGE": (200, 178, 125),
    "VESSEL_DEFAULT": (215, 227, 240),
    "VESSEL_SELECTED": (255, 210, 63),
    "VESSEL_DOCKED": (150, 170, 190),
    "HEADING_VECTOR": (143, 184, 224),
    "PANEL_BG": (12, 20, 32),
    "PANEL_BORDER": (46, 74, 107),
    "ACCENT": (79, 209, 224),
    "TEXT_PRIMARY": (232, 241, 251),
    "TEXT_SECONDARY": (159, 179, 200),
    "TEXT_DIM": (95, 116, 136),
    "WARNING": (255, 107, 94),
}

# Per-type land colours.  Renderer uses island.land_type to look up fill/coast/shade.
# "island"       — sandy-brown (default, same as historic COLOR_LAND_FILL)
# "mainland"     — dark olive-brown (larger mass, heavier tone)
# "rocky"        — dark grey-brown (rocky outcrops and shoals)
# "shallow_bank" — pale sandy (submerged or near-submerged banks)
# "shade" is a ~15 % lighter version of "fill" used for the inland highlight polygon.
LAND_COLORS = {
    "mainland":     {"fill": (139, 119,  84), "coast": (100,  85,  56), "shade": (162, 140, 100)},
    "island":       {"fill": (185, 160, 105), "coast": (135, 115,  72), "shade": (203, 181, 133)},
    "rocky":        {"fill": (110,  95,  75), "coast": ( 78,  66,  50), "shade": (130, 113,  90)},
    "shallow_bank": {"fill": (210, 195, 155), "coast": (165, 148, 110), "shade": (225, 212, 175)},
}

# Convenience aliases for compatibility
COLOR_BACKGROUND = THEME["VOID"]
COLOR_WATER = THEME["DEEP_WATER"]
COLOR_SHALLOW_WATER = THEME["SHALLOW_WATER"]
COLOR_DEPTH_CONTOUR = THEME["DEPTH_CONTOUR"]
COLOR_LAND_FILL = THEME["LAND_FILL"]
COLOR_LAND_COAST = THEME["LAND_COAST"]
COLOR_LAND_SHADE = THEME["LAND_SHADE"]
COLOR_SHALLOW_BAND = THEME["SHALLOW_BAND"]
COLOR_GRID_MINOR = THEME["GRID_MINOR"]
COLOR_GRID_MAJOR = THEME["GRID_MAJOR"]
COLOR_GRID_LABEL = THEME["GRID_LABEL"]
COLOR_CHART_BAR_BG = THEME["CHART_BAR_BG"]
COLOR_SCALE_BAR = THEME["SCALE_BAR"]
COLOR_NORTH_ARROW = THEME["NORTH_ARROW"]
COLOR_ZONE_LABEL = THEME["ZONE_LABEL"]
COLOR_FRAME = THEME["FRAME"]
COLOR_NO_ENTRY = THEME["NO_ENTRY"]
COLOR_SPEED_LIMIT = THEME["SPEED_LIMIT"]
COLOR_PROTECTED = THEME["PROTECTED"]
COLOR_ANCHORAGE = THEME["ANCHORAGE"]
COLOR_TSS = THEME["TSS"]
COLOR_SHALLOW_HAZARD = THEME["SHALLOW_HAZARD"]
COLOR_BEACH_FRINGE = THEME["BEACH_FRINGE"]
COLOR_VESSEL_DEFAULT = THEME["VESSEL_DEFAULT"]
COLOR_VESSEL_SELECTED = THEME["VESSEL_SELECTED"]
COLOR_VESSEL_DOCKED = THEME["VESSEL_DOCKED"]
COLOR_HEADING_VECTOR = THEME["HEADING_VECTOR"]
COLOR_PANEL_BG = THEME["PANEL_BG"]
COLOR_PANEL_BORDER = THEME["PANEL_BORDER"]
COLOR_ACCENT = THEME["ACCENT"]
COLOR_TEXT_PRIMARY = THEME["TEXT_PRIMARY"]
COLOR_TEXT_SECONDARY = THEME["TEXT_SECONDARY"]
COLOR_TEXT_DIM = THEME["TEXT_DIM"]
COLOR_WARNING = THEME["WARNING"]
COLOR_VESSEL_RANGE = THEME["TEXT_SECONDARY"]

# ============================================================================
# Typography
# ============================================================================
FONT_UI_NAME = "segoe ui, calibri, arial"
FONT_DATA_NAME = "consolas, cascadia mono, dejavu sans mono"
FONT_SIZE_TITLE = 22
FONT_SIZE_SECTION = 16
FONT_SIZE_LABEL = 15
FONT_SIZE_DATA = 18
FONT_SIZE_BIG = 24
FONT_SIZE_MAP_LABEL = 15
FONT_SIZE_SMALL = 12

# ============================================================================
# World Scale — Meridian Sea
# ============================================================================
# This block is the single canonical definition of the sea's physical size.
# All physics code derives unit conversions from here; nothing else should
# hard-code a nm↔world-unit ratio.  To upscale from a regional passage to an
# ocean chart, change SEA_WIDTH_NM (and SEA_HEIGHT_NM proportionally) — the
# physics automatically follow.
#
# Current setting: ~Irish-Sea / English-Channel scale (regional).
SEA_WIDTH_NM  = 210.0    # real east–west extent of the Meridian Sea (nm)
SEA_HEIGHT_NM = 147.0    # real north–south extent (preserves WORLD_WIDTH/HEIGHT ratio)

# Derived scale factors — computed once here, imported everywhere they're needed.
# One world-coordinate unit = NM_PER_WORLD_UNIT nautical miles.
# e.g. a position of (100, 0) is 15 nm east of (0, 0).
WORLD_WIDTH  = 1400.0    # coordinate-space width  (do not interpret as nm directly)
WORLD_HEIGHT =  980.0    # coordinate-space height
NM_PER_WORLD_UNIT       = SEA_WIDTH_NM / WORLD_WIDTH   # 0.15 nm per wu
# Velocity conversion: 1 knot = 1 nm/hr.  At this scale, a vessel doing 1 kn
# covers KNOTS_TO_UNITS_PER_HOUR world-units per simulated hour.
KNOTS_TO_UNITS_PER_HOUR = WORLD_WIDTH  / SEA_WIDTH_NM  # ≈ 6.667 wu / (kn·hr)

# ============================================================================
# Chart / Map View
# ============================================================================
GRID_SPACING = 100.0
GRID_LABEL_INTERVAL = 200.0
ZOOM_MIN = 0.4
ZOOM_MAX = 4.0
ZOOM_DEFAULT = 1.0
ZOOM_SCROLL_SPEED = 0.10
PAN_SPEED = 300.0
# Label declutter: when zoom is below this, only show ports and selected vessel labels.
# Default zoom on 1080p ≈ 1.05, on 1440p ≈ 1.40 — threshold must be above both.
LABEL_ZOOM_THRESHOLD_SHOW_ALL = 1.5

# ============================================================================
# Compass & Scale
# ============================================================================
COMPASS_SIZE = 48
COMPASS_OFFSET_X = 70
COMPASS_OFFSET_Y = 70
SCALE_BAR_MAX_WIDTH = 220
SCALE_BAR_TARGET_WIDTH = 140
SCALE_BAR_OFFSET_X = 70
SCALE_BAR_OFFSET_Y = 100
SCALE_BAR_HEIGHT = 8

# ============================================================================
# Vessel trails
# ============================================================================
VESSEL_TRAIL_MAX_POINTS   = 200   # maximum positions kept per vessel
VESSEL_TRAIL_SAMPLE_STEPS = 30    # append position once every N move() calls

# ============================================================================
# Vessel type colors (AIS/ECDIS convention — type readable by hull color)
# ============================================================================
VESSEL_COLOR_CARGO       = (50,  205,  50)   # bright green   — MarineTraffic AIS cargo
VESSEL_COLOR_FERRY       = (100, 180, 255)   # bright blue    — passenger/ferry
VESSEL_COLOR_FISHING     = (255, 220,   0)   # bright yellow  — fishing vessel
VESSEL_COLOR_SAILBOAT    = (0,   220, 220)   # bright cyan    — sailing vessel
VESSEL_COLOR_TUG         = (255, 140,   0)   # bright orange  — tug / small craft
VESSEL_COLOR_TANKER      = (255,  80,  80)   # bright red     — tanker (high-risk cargo)
VESSEL_COLOR_COAST_GUARD = (255,  60, 120)   # bright magenta — SAR / coast guard
VESSEL_COLOR_SELECTED    = (255, 255, 255)   # white — selected vessel override

# ============================================================================
# Mission port stay durations (sim-seconds)
# ============================================================================
PORT_STAY_CARGO_LOAD_S     = 21600.0   # 6 sim-h  — cargo loading / unloading
PORT_STAY_FERRY_BOARD_S    =  1200.0   # 20 sim-min — passenger boarding
PORT_STAY_FISHING_UNLOAD_S =  2700.0   # 45 sim-min — unloading catch
PORT_STAY_SAIL_ANCHOR_S    =  2700.0   # 45 sim-min — leisure anchor stop
PORT_STAY_TUG_S            =   300.0   # 5 sim-min  — quick tug turnaround

# Fishing trawl session parameters
TRAWL_DURATION_S        = 4500.0   # 75 sim-min trawl session
TRAWL_WANDER_INTERVAL_S =  750.0   # 12.5 sim-min between heading changes
TRAWL_SPEED_KN          =    3.0   # knots while trawling

# Sailboat open-sea anchor stop
SAIL_ANCHOR_DURATION_S  = 2700.0   # 45 sim-min at each waypoint

# ============================================================================
# Vessel / Ship Symbols
# ============================================================================
SHIP_SELECT_RADIUS = 24
SHIP_SELECT_GLOW_WIDTH = 3
SHIP_MIN_SIZE = 20
SHIP_MAX_SIZE = 30
SHIP_LABEL_OFFSET = 18
SHIP_PREDICTOR_MINUTES = 5.0
# Speed vector display time (sim-minutes).  Kept short so the vector is a clean
# directional tick — 2-3× the triangle body, not a long streak.
# At 8 kn, 3 min: raw screen length ≈ 5 px at default zoom → floored to 16 px
# by the max(16, ...) guard.  The hard pixel cap (max(size*3, 20)) in chart.py
# then trims it further at high zoom so it never dominates the symbol.
SHIP_VECTOR_MINUTES = 3.0
SHIP_RANGE_RING_INTERVAL_NM = 8.0
SHIP_RANGE_RING_COUNT = 3
SHIP_SELECTION_ALPHA = 48
SHIP_PREDICTOR_ALPHA = 120
SHIP_SYMBOL_ZOOM_SCALE = 0.85

# ============================================================================
# Ports
# ============================================================================
PORT_SYMBOL_SIZE = 8
PORT_LABEL_OFFSET = 16

# ============================================================================
# Zones
# ============================================================================
ZONE_BORDER_WIDTH = 1
ZONE_LABEL_OFFSET = 12
ZONE_FILL_ALPHA = 10
ZONE_HATCH_ALPHA = 40
ZONE_HATCH_SPACING = 20
SHALLOW_WATER_BAND_WIDTH = 20
# Gradient-fade coastal band: STEPS rings at STEP_PX intervals, innermost at MAX_ALPHA.
# Kept soft and low-alpha so the coast reads as a whisper of depth, not a neon rim.
SHALLOW_WATER_BAND_STEPS = 8
SHALLOW_WATER_BAND_STEP_PX = 4
SHALLOW_WATER_BAND_MAX_ALPHA = 130
SHALLOW_WATER_MID_BAND_OFFSET_PX = 40   # pixel outset for the mid-depth fill halo
SHALLOW_WATER_MID_BAND_ALPHA = 55        # fill alpha for mid-depth zone
BEACH_FRINGE_ALPHA = 160                 # alpha for sandy beach fringe ring on coastline
BEACH_FRINGE_WIDTH_PX = 4               # line width for beach fringe
DEPTH_CONTOUR_WIDTH = 2

# ============================================================================
# Vessel Simulation
# ============================================================================
VESSEL_MAX_SPEED = 12.0
VESSEL_ACCELERATION = 3.0
VESSEL_TURN_RATE = 20.0
FUEL_CAPACITY_DEFAULT = 100.0
FUEL_CONSUMPTION_BASELINE = 0.5
ARRIVAL_DISTANCE = 1.0

# Berth offset (world units) from port centre to each of 4 berth positions.
# Must be < PORT_DETECT_RADIUS (2.0) so _port_at() finds the port from the berth.
# At 1.5 wu, adjacent berths are ≥ 2.12 wu apart (sqrt(1.5²+1.5²)) — well
# above the 1.5-wu port-separation test minimum.
PORT_BERTH_OFFSET = 1.5

# ============================================================================
# Multi-waypoint routing and port stays (Chunk E)
# ============================================================================
# Durations are in simulated seconds.  At TIME_COMPRESSION=120 and 1× speed,
# 900 sim-s ≈ 7.5 real-s — quick enough to watch while feeling like real time.
# At 3× (max speed) those same 900 sim-s play out in 2.5 real-s.
# Reference: ISPS Code & IMO guidelines on minimum port turnaround times.
PORT_STAY_FERRY_S    =  900.0   # 15 sim-min — short ferry turnaround
PORT_STAY_PATROL_S   =  300.0   # 5 sim-min  — coast guard rapid-response
PORT_STAY_CARGO_S    = 3600.0   # 60 sim-min — loading / unloading
PORT_STAY_FISHING_S  = 1800.0   # 30 sim-min — unload catch, resupply
PORT_STAY_SAILBOAT_S = 5400.0   # 90 sim-min — anchor, longer rest

# Fraction of fuel capacity restored during a port stay at a fuelling berth.
# 1.0 = fill to 100 % — eliminates "vessel runs dry forever" on long voyages.
REFUEL_FRACTION = 1.0

# Radius (world units) within which a waypoint position is considered a port.
# 2.0 wu ≫ ARRIVAL_DISTANCE (1.0) so port detection is reliable even with
# floating-point position drift on arrival.  All open-sea waypoints are at
# least 50 wu from any port.
PORT_DETECT_RADIUS = 2.0

# ---- Linear inertia ----
# All rates are in knots per simulated-second.  Because the physics integrator
# receives simulated time (already scaled by TIME_COMPRESSION), these values
# represent physical knot-change per simulated second — independent of the
# time-compression factor chosen in the UI.
#
# Reference: IMO MSC/Circ.1053 defines manoeuvrability standards.  A fully-
# loaded Panamax cargo ship (≈200 m) stops from 14 kn in roughly 15 ship-
# lengths (~3 km).  A 150 m vessel at 12 kn stopping in ~1.2 nm (2200 m)
# is within realistic bounds.
#
# deceleration < acceleration: ships build speed faster with forward thrust
# than they shed it — large displacement and low hydrodynamic braking.
# Per-vessel acceleration/deceleration live on the Vessel dataclass in ship.py.

# Out-of-fuel coast: no reverse thrust, only water drag.
# At 0.005 kn/sim-s a vessel at 8 kn drifts ≈ 1.8 nm before stopping.
FUEL_COAST_DECELERATION = 0.005

# ---- Turning physics ----
# Rudder effectiveness peaks at TURN_OPTIMAL_SPEED_FRACTION × max_speed,
# where water-flow over the blade is sufficient for full lateral force.
# Below that fraction the rudder barely bites (vessel nearly stopped).
# Above it, hull momentum widens the turning circle.
#
# Basis: SOLAS II-1 and empirical data from bridge-simulator trials.
# A typical cargo ship has maximum rudder effect at ~50–60 % of sea speed.
TURN_OPTIMAL_SPEED_FRACTION   = 0.5   # effectiveness peaks at 50 % of max_speed
TURN_MIN_EFFECTIVENESS        = 0.08  # 8 % at dead-slow (headway but barely steerable)
TURN_HIGH_SPEED_EFFECTIVENESS = 0.70  # 70 % at full speed (momentum widens circle)

# Speed bled per deg/s of actual yaw rate, per simulated second.
# Real ships lose ~10–15 % of speed through a full tactical turn owing to
# increased hydrodynamic drag on the hull in the turn.
# At 1 °/s yaw for 360 sim-s (full circle): 0.003 × 1 × 360 = 1.08 kn lost.
TURN_SPEED_BLEED = 0.003   # kn lost per (°/s yaw) per sim-second

# ============================================================================
# Time & Physics
# ============================================================================
SIM_TIMESTEP = 1.0
WORLD_TIME_DEFAULT = 12.0
TIME_SPEED_PAUSED = 0.0
TIME_SPEED_NORMAL = 1.0
TIME_SPEED_FAST = 2.0
TIME_SPEED_VERY_FAST = 3.0

# Simulation scaling
# SIM_TIMESTEP = 1.0 sim-second: one physics step advances 1 simulated second.
# At 60 FPS with TIME_COMPRESSION=120 and 1× speed:
#   scaled_dt = (1/60) × 1 × 120 = 2.0 sim-s per frame → 2 steps per frame.
# At 3×: 6 sim-s per frame → 6 steps per frame — comfortably under the 12-step cap.
# The previous value (0.016 s) produced 375 steps/frame at 3×, causing crash feedback.
#
# TIME_COMPRESSION controls how many simulated seconds advance per real-world
# second at 1× UI speed.  With KNOTS_TO_UNITS_PER_HOUR ≈ 6.667 (150 nm sea)
# a value of 90 produced only ~1.9 px/s of visible vessel movement — barely
# perceptible.  300 gives ~6–7 px/s at default zoom: clearly watchable.
# 120 is a stable compromise: ships are visibly moving at 1× and fast at 3×.
# The 2×/3× presets multiply this, so at 3× a 150 nm crossing takes ~75 s.
TIME_COMPRESSION = 80.0

# ============================================================================
# Environment / Weather (starting values)
# ============================================================================
WIND_SPEED_DEFAULT = 5.0
WIND_DIRECTION_DEFAULT = 45.0
WAVE_HEIGHT_DEFAULT = 1.0
CURRENT_SPEED_DEFAULT = 0.5
CURRENT_DIRECTION_DEFAULT = 90.0
VISIBILITY_CLEAR = 500.0
TIDE_RANGE = 3.0

# ============================================================================
# Day / Night Tint
# ============================================================================
# Color must be visually distinct from the dark-navy water (10, 28, 52) so
# the overlay is perceptible.  Indigo-violet reads clearly against both water
# and warm-tan land without turning the chart unreadably dark.
NIGHT_TINT_COLOR = (20, 0, 80)
# Halved from 120: at 120 the land went mauve and soundings were hard to read
# at peak night; 60 keeps the night atmosphere while leaving the chart legible.
NIGHT_TINT_MAX_ALPHA = 60

# ============================================================================
# Depth Visualization — flat-zone chartplotter style (Chunk D)
# ============================================================================
# Convention: shallower = lighter (pale = danger), deeper = darker (safe passage).
# Matches ECDIS / Navionics / paper chart convention universally.
# All rendering is vector-only (polygon offsets + circles) — zero pixel sampling,
# zero baking, 60 FPS guaranteed at all time speeds including 3×.

# Depth thresholds that define the flat fill zones (metres).
DEPTH_ZONE_SHOAL_M   = 5.0    # < this → shoal/very-shallow — lightest colour
DEPTH_ZONE_COASTAL_M = 20.0   # < this → coastal shelf  — mid-tone
# Deeper than DEPTH_ZONE_COASTAL_M = COLOR_WATER dark navy (background, no fill needed)

# Zone fill colours (RGB — matched to muted ECDIS palette; lighter = shallower).
DEPTH_COLOR_SHOAL   = (75, 130, 180)   # pale blue — shoal / danger
DEPTH_COLOR_COASTAL = (18,  44,  78)   # dark-mid  — coastal shelf (kept for contour use)

# Shallow-zone radial gradient halo (Skerry Bank).
# A pre-built SRCALPHA surface — rebuilt only when zoom changes the screen radius.
# Linear falloff: pale at centre, fully transparent at the edge (ECDIS shoal whisper).
DEPTH_SHOAL_HALO_ALPHA = 55    # peak alpha at the very centre
DEPTH_SHOAL_HALO_STEPS = 28    # number of concentric rings; more = smoother gradient

# Depth contour levels drawn as thin lines (metres).
DEPTH_CONTOUR_LEVELS_DRAW = [5.0, 10.0, 20.0]

# Contour line colour — slightly lighter than deep water, clearly legible.
DEPTH_CONTOUR_DRAW_COLOR = (100, 145, 180)

# Spot sounding positions (world_x, world_y).  Depths queried live from
# water_depth_at() — just a handful of cached lookups per frame, negligible cost.
# Selected for navigational value: shoal, coastal approaches, narrow fairways.
# All confirmed in-water at neutral tide; transitional depths (5-16m) where useful.
DEPTH_SOUNDING_POSITIONS = [
    (445, 335),   # Skerry Bank centre        — critical shoal  (~5 m)
    (260, 240),   # mainland coastal approach — shallow fringe  (~9 m)
    (480, 440),   # Carrow Island SW fringe   — coastal         (~8 m)
    (540, 380),   # Carrow north channel      — approach        (~16 m)
    (700, 580),   # Brattlin strait           — narrow passage  (~10 m)
    (780, 680),   # Brattlin South fringe     — coastal         (~10 m)
]

# ============================================================================
# Game Physics
# ============================================================================
GROUNDING_DEPTH = 0.5  # legacy — superseded by draft-vs-depth check below

# ============================================================================
# Depth Model — Bathymetry
# ============================================================================
# A simplified analytic depth model: open water deepens linearly with distance
# from the nearest coastline up to DEPTH_OFFSHORE.  Named shoals override the
# coastal gradient with their own charted depth.
#
# Scale reference: 1 world-unit ≈ 0.15 nm ≈ 278 m.
# At DEPTH_COASTAL_SLOPE = 4 m/wu the seabed reaches full depth at ~15 wu
# (~2.25 nm offshore) — steeper than open ocean but typical for a rocky passage.
# Basis: UKHO chart conventions; IMO SOLAS II-1 depth clearance guidance.

DEPTH_OFFSHORE      = 60.0   # metres — asymptotic open-water depth
DEPTH_COASTAL_SLOPE = 4.0    # metres per world-unit from nearest coastline

# Skerry Bank shoal: charted depth inside the named shallow zone.
# 5 m threatens cargo (draft ~8 m) at any tide;
# fishing/ferry (3-4 m draft) pass safely even at low water (+0.5 m margin).
DEPTH_SHOAL_SKERRY  = 5.0    # metres

# Grounding alarm threshold: depth < vessel.draft_m + DRAFT_SAFETY_MARGIN_M.
# Mirrors the ECDIS shallow-water alarm: a configurable under-keel clearance
# (UKC) that fires before the keel actually touches.
DRAFT_SAFETY_MARGIN_M = 0.5  # metres UKC — 0.5 m is standard for coastal cargo

# Fraction of tide_level added to water depth.  1.0 is physically correct:
# a +2 m tide raises every water column by exactly 2 m.
TIDAL_DEPTH_INFLUENCE = 1.0

# ============================================================================
# Environment Forces (wind & current acting on hulls)
# ============================================================================

# Current — set-and-drift model.
# The current is treated as a velocity vector added directly to the vessel's
# through-water displacement each timestep, so COG ≠ heading whenever current
# is non-zero.  CURRENT_INFLUENCE = 1.0 is the physically correct value (full
# vector sum); reduce only for deliberate game-feel tuning.
# Basis: IHO SP-44 and COLREGS §2 define set and drift as a vector sum.
CURRENT_INFLUENCE = 1.0

# Windage per vessel class (fraction of wind speed → lateral drift in knots)
# Approximates (above-waterline profile area) / (underwater lateral resistance).
# Values from Lewandowski (1994) "The Dynamics of Marine Craft" and RYA
# Yachtmaster theory guides; typical range 2–5 % for commercial vessels.
WINDAGE_CARGO    = 0.040   # large freeboard, boxy hull cross-section
WINDAGE_FERRY    = 0.045   # extra topsides vs a cargo freighter
WINDAGE_FISHING  = 0.020   # low freeboard, heavy keel reduces leeway
WINDAGE_SAILBOAT = 0.010   # deep keel resists leeway; sail manages the rest
WINDAGE_GENERIC  = 0.030   # sensible default for unlisted types

# Sailboat true-wind polar constants
# ISAF and IMS racing rules recognise a "no-go zone" where the sails cannot
# fill regardless of trim — typically ~45 ° either side of the true wind
# direction, giving a 90 ° dead zone centred on head-to-wind.
SAIL_NO_GO_ANGLE = 45.0    # degrees either side of wind → total 90 ° dead zone

# Maximum drive efficiency at the optimal angle (beam reach ≈ 90 ° to true wind).
# 0.80 → a 10-kn breeze drives a 35 m cruising yacht at 8 kn on a beam reach,
# which matches published polar data for a passage-making monohull.
SAIL_EFFICIENCY  = 0.80

# Dead-downwind speed penalty: the mainsail collapses in its own wind-shadow
# when running (180 °), so speed ≈ 65 % of the beam-reach maximum.
# Rule-of-thumb from "Heavy Weather Sailing" (Coles) and cruising polars.
SAIL_RUN_FACTOR  = 0.65

# ============================================================================
# Environmental Force Visuals
# ============================================================================
# Course-over-ground vector — drawn as a solid teal-green line when the actual
# track over ground diverges from heading by more than COG_MIN_DRIFT_DEG.
# The existing muted-blue dashed predictor shows heading direction; this line
# shows real track, making current set-and-drift immediately readable.
COLOR_COG_VECTOR   = (100, 210, 170)   # soft teal-green; distinct from heading blue
COG_MIN_DRIFT_DEG  = 0.5               # suppress when drift is visually negligible

# Sparse current-flow arrow field drawn as a chart layer.
# Light steel-blue at low alpha evokes isobar/current conventions on paper charts
# while staying subordinate to vessel symbols and coastlines.
COLOR_CURRENT_ARROW    = (110, 170, 225)   # light steel-blue
CURRENT_ARROW_SPACING_PX = 140            # screen pixels between arrow centres
CURRENT_ARROW_ALPHA    = 45               # very faint — chart annotation, not HUD
CURRENT_ARROW_SIZE     = 20               # pixel length at 1.0-kn reference speed

# Sailboat in-irons stall cue — applied when effective wind speed falls below
# this threshold, indicating the vessel is in the no-go zone and not making way.
SAIL_IRONS_DISPLAY_THRESHOLD = 0.3        # knots effective wind speed

# ============================================================================
# Dynamic Weather — Chunk F
# ============================================================================
# Background drift uses an Ornstein-Uhlenbeck process: a random walk that
# slowly mean-reverts toward each field's default value.
# Halflife of mean-reversion ≈ ln(2) / WEATHER_DRIFT_MEAN_REVERSION.
#
# Per-step noise = sigma × √(dt).  At SIM_TIMESTEP=0.016 s, σ=0.020 gives
# ~0.003 kn per step; over 3600 sim-s the expected drift is σ×√3600 ≈ 1.2 kn.

# Noise amplitude (σ) in per-√(sim-second).
WEATHER_DRIFT_WIND_SPEED_SIGMA    = 0.020  # kn/√s  → ~1–2 kn drift per sim-hr
WEATHER_DRIFT_WIND_DIR_SIGMA      = 0.25   # deg/√s → ~10–20° drift per sim-hr
WEATHER_DRIFT_WAVE_HEIGHT_SIGMA   = 0.008  # m/√s   → ~0.5 m drift per sim-hr
WEATHER_DRIFT_CURRENT_SPEED_SIGMA = 0.008  # kn/√s
WEATHER_DRIFT_CURRENT_DIR_SIGMA   = 0.10   # deg/√s
WEATHER_DRIFT_VISIBILITY_SIGMA    = 1.0    # m/√s   → ~60 m drift per sim-hr

# Mean-reversion rate for magnitude fields (1/sim-s); halflife ≈ 1.9 sim-hr.
# Direction fields do a free random walk (weather can come from any direction).
WEATHER_DRIFT_MEAN_REVERSION      = 0.0001

# When a slider is dragged the value is pinned for this many sim-seconds before
# auto-drift resumes.  At 1× speed with TIME_COMPRESSION=120, 300 sim-s ≈ 2.5 s.
WEATHER_USER_OVERRIDE_DURATION_S  = 300.0  # 5 sim-minutes

# ---- Event rates (Poisson, events per sim-hour) ----
# Only one event can be active at once.  Over 24 sim-hours expect roughly:
# Fog ×3–4, Squall ×4–5, Storm ×1–2 (minus mutual blocking).
WEATHER_FOG_PROB_PER_HOUR    = 0.15   # ~once per 6–7 sim-hours
WEATHER_SQUALL_PROB_PER_HOUR = 0.20   # ~once per 5 sim-hours
WEATHER_STORM_PROB_PER_HOUR  = 0.08   # ~once per 12 sim-hours

# ---- Fog event: visibility crashes, wind & sea calm ----
WEATHER_FOG_BUILDUP_S  =  600.0   # 10 sim-min buildup
WEATHER_FOG_PEAK_S     = 1800.0   # 30 sim-min peak
WEATHER_FOG_FADEOUT_S  =  900.0   # 15 sim-min fade
WEATHER_FOG_VIS_DROP   =  490.0   # at peak: visibility → max(10, auto − 490)
WEATHER_FOG_WIND_DELTA =   -2.0   # light air ahead of dense fog
WEATHER_FOG_WAVE_DELTA =   -0.3   # calmer surface in fog

# ---- Squall event: short sharp wind burst ----
WEATHER_SQUALL_BUILDUP_S  =  120.0   # 2 sim-min onset
WEATHER_SQUALL_PEAK_S     =  600.0   # 10 sim-min peak
WEATHER_SQUALL_FADEOUT_S  =  300.0   # 5 sim-min fade
WEATHER_SQUALL_WIND_DELTA =   12.0   # +12 kn at peak
WEATHER_SQUALL_WAVE_DELTA =    1.5   # +1.5 m at peak
WEATHER_SQUALL_VIS_DROP   =  200.0   # spray-reduced visibility

# ---- Weather gameplay & visual effects (render-side) ----
# Fog: below this visibility (m) the AIS hover popup is disabled, the HUD
# shows LOW VISIBILITY, and traffic beyond visual range vanishes from chart.
# 150 m matches the AI captains' own low-visibility threshold in main.py.
FOG_LOW_VIS_THRESHOLD_M  = 150.0
# World-unit range around the player within which other vessels stay visible
# during fog.  100 wu ≈ 15 nm of chart — close traffic only.
FOG_VESSEL_HIDE_RANGE_WU = 100.0

# Storm seas: scrolling horizontal wave lines + a grey-green cast, shown
# whenever wave_height exceeds STORM_WAVE_THRESHOLD (same trigger as the
# player speed cap so visuals and consequences always agree).
STORM_TINT_COLOR          = (60, 90, 80)     # grey-green storm cast
STORM_TINT_ALPHA          = 26
STORM_WAVE_LINE_COLOR     = (170, 190, 185)  # pale foam-grey line
STORM_WAVE_LINE_ALPHA     = 30
STORM_WAVE_LINE_SPACING_PX = 48              # vertical gap between wave lines
STORM_WAVE_SCROLL_PX_S    = 10               # slow downward scroll speed

# Squall lightning: a brief full-screen white flash on the frame the squall
# event first becomes active.
SQUALL_FLASH_ALPHA      = 70
SQUALL_FLASH_DURATION_S = 0.18   # real seconds the flash persists (~11 frames)

# ---- Storm event: sustained severe weather ----
WEATHER_STORM_BUILDUP_S  = 1800.0   # 30 sim-min buildup
WEATHER_STORM_PEAK_S     = 5400.0   # 90 sim-min peak
WEATHER_STORM_FADEOUT_S  = 2700.0   # 45 sim-min fade
WEATHER_STORM_WIND_DELTA =   20.0   # +20 kn at peak
WEATHER_STORM_WAVE_DELTA =    3.0   # +3 m at peak
WEATHER_STORM_VIS_DROP   =  450.0   # near-zero visibility

# ============================================================================
# Chart Polish — visual refinements
# ============================================================================

# Land inland tint: a shrunken-polygon solid fill 12 px inside the coastline,
# drawn directly onto the main surface with NO per-frame SRCALPHA allocation.
# The colour is a pre-blended midpoint between LAND_FILL and LAND_SHADE so the
# visual is identical to an alpha=50 overlay while costing almost nothing.
# Delta from LAND_FILL is ~7–10 units per channel — "sense of body," not texture.
LAND_INLAND_TINT_SHRINK_PX = 12                # px to shrink the island polygon inward
LAND_INLAND_TINT_COLOR     = (203, 181, 133)   # pre-blended ~1/3 between FILL and SHADE

# Ocean vignette: one cached gradient circle anchored at the world centre.
# The slight lightening of the deep open ocean breaks the perfectly-uniform
# dark-water fill without any per-pixel sampling.  Rebuilt only on zoom change.
OCEAN_VIGNETTE_WORLD_RADIUS = 220.0  # world units (~1/3 of the sea width)
OCEAN_VIGNETTE_ALPHA        = 15     # peak alpha at the world centre
OCEAN_VIGNETTE_STEPS        = 5      # concentric rings; 5 is smooth at this alpha
OCEAN_VIGNETTE_COLOR        = (18, 50, 85)  # faint mid-blue, slightly above DEEP_WATER

# Predictor label: fraction along the dashed line where "5 min" is placed.
# 0.65 keeps the label on the line, away from port symbols that often sit at
# the line endpoint.
SHIP_PREDICTOR_LABEL_FRAC  = 0.65

# ============================================================================
# Screen polish — vignette, port pulse, minimap
# ============================================================================
# Screen-edge vignette: concentric border rings fading from the edge inward.
# Very low alpha — a cinematic frame, not a tunnel.
SCREEN_VIGNETTE_DEPTH_PX  = 90   # how far the fade reaches into the screen
SCREEN_VIGNETTE_MAX_ALPHA = 42   # alpha of the outermost ring
SCREEN_VIGNETTE_STEPS     = 18   # ring count; 18 is smooth at this alpha

# Port symbols pulse gently when the player is within docking range.
PORT_NEAR_PULSE_RANGE_WU = 50.0

# Minimap: fixed-zoom overview of the whole sea, bottom-right corner.
MINIMAP_WIDTH_PX  = 200
MINIMAP_HEIGHT_PX = 140
MINIMAP_MARGIN_PX = 12

# ============================================================================
# Collision Avoidance — COLREGS-simplified CPA/TCPA model
# ============================================================================
# All distance values are in nautical miles; time values are in simulated seconds.
# With NM_PER_WORLD_UNIT ≈ 0.15, 1 nm ≈ 6.67 world units.

# How far ahead to look for other vessels (nm).
# 8 nm gives reliable detection even in the narrow south-corridor passages where
# multiple vessels share the same track waypoints (Carrick Star + Ardent Pilot
# through (640,500)↔(640,590)).  At 8 kn head-on, 8 nm = 30 min look-ahead.
COLLISION_DETECTION_RANGE_NM = 8.0

# Minimum acceptable Closest Point of Approach (nm).
# Raised from 0.5 to 0.8 nm: the south corridor has multiple vessels on near-
# parallel tracks where a 0.5 nm trigger was insufficient — vessels still made
# physical contact in the channel.  0.8 nm gives a wider buffer without causing
# spurious avoidance in open water.
COLLISION_SAFE_CPA_NM = 0.8

# Maximum TCPA (sim-seconds) that triggers avoidance.
# 7200 sim-s = 2 simulated hours.  At 3× speed with TIME_COMPRESSION=120 this is
# 7200/(120×3) = 20 real seconds of look-ahead — enough to react before a slow
# convergence becomes a collision.  600 was too short: vessels on near-parallel
# courses with TCPA > 600 sim-s were never detected and eventually collided.
COLLISION_SAFE_TCPA_S = 7200.0

# Maximum course change applied when giving way (degrees, always to starboard).
# 30° is the IMO/COLREGS minimum "substantial" alteration to make the manoeuvre
# obvious to the stand-on vessel.
COLLISION_MAX_AVOID_DEG = 30.0

# Rate at which a vessel returns to its route heading after risk clears (deg/sim-s).
# The vessel uses its normal turn_toward() at this rate — gradual, not a snap.
# 3 °/s means a 30° recovery takes ~10 sim-seconds; clearly visible to the user.
COLLISION_RETURN_RATE = 3.0

# CPA clearance multiplier for hysteresis: a vessel stays in "avoiding" until
# CPA exceeds COLLISION_SAFE_CPA_NM × this factor, preventing rapid oscillation
# between "avoiding" and "underway" near the trigger boundary.
# Set to 1.5 (not 2.0) with CPA_NM=0.8 nm: clear at 1.2 nm, not 1.6 nm.
# 2.0 was too wide — vessels on near-parallel tracks with 1.0–1.5 nm separation
# stayed in "avoiding" indefinitely because CPA never reached the clear threshold.
COLLISION_CLEAR_HYSTERESIS = 1.5

# Emergency avoidance: when CPA is within this fraction of COLLISION_SAFE_CPA_NM
# the risk is acute and we boost to maximum severity regardless of the exact CPA.
# 0.5 means emergency triggers below 0.25 nm when SAFE_CPA_NM = 0.5.
COLLISION_EMERGENCY_CPA_FRAC = 0.5

# Maximum course change during emergency avoidance (degrees, always to starboard).
# Doubles the normal COLLISION_MAX_AVOID_DEG for acute risk — a more aggressive
# manoeuvre that makes the intent clear and separates vessels faster.
COLLISION_EMERGENCY_AVOID_DEG = 60.0

# Hard cap on fixed-timestep iterations per real frame.
# With SIM_TIMESTEP=1.0 and TIME_COMPRESSION=120 at 1/2/3× speed, the loop runs
# exactly 2/4/6 steps per frame at 60 FPS — well under the cap in normal operation.
# The cap only fires when a frame takes unusually long (e.g. OS context switch):
#   At 3×, cap triggers when frame_time > 12 × 1.0 / (3 × 120) = 33 ms (< 30 FPS).
# Excess accumulated time is then discarded to prevent the feedback spiral that
# previously caused the OS to kill the process at high time compression.
MAX_SIM_STEPS_PER_FRAME = 12

# Heading-line color shown when a vessel is in "avoiding" status.
# Soft amber: distinct from the steel-blue normal heading vector but still muted
# and chart-appropriate.  Matches ECDIS danger-highlight conventions.
COLOR_COLLISION_AVOID  = (220, 165, 50)
COLOR_EVENT_REFLOATED  = (80, 200, 120)   # green — vessel successfully refloated

# ============================================================================
# SAR (Search and Rescue)
# ============================================================================
SAR_DISPATCH_RANGE_NM = 50.0    # nautical miles — auto-dispatch only within this range
# Fuel-exhaustion rescue: fraction of fuel capacity given to a stranded vessel
# when a SAR rescuer reaches it, so it can motor to the nearest port for a full
# refuel.  0.20 = 20 % capacity — enough for ~4 sim-hours at cruise speed.
FUEL_EMERGENCY_REFUEL_FRACTION = 0.20
SAR_PULSE_PERIOD            = 2.0   # seconds — one full pulse cycle on the distress ring
PORT_ACTIVITY_PULSE_PERIOD  = 4.0   # seconds — slower pulse shown when a vessel is in port
COLOR_SAR_DISTRESS    = (255, 70, 50)   # red-orange distress pulse ring

# ============================================================================
# Random sudden events
# ============================================================================
# Probability per vessel per sim-second of triggering a random event.
# At 0.00005: expected interval ≈ 1/0.00005 = 20 000 s ≈ 5.5 sim-hours per vessel.
RANDOM_EVENT_PROBABILITY = 0.000008
MOB_SEARCH_DURATION_S    = 3600.0   # sim-seconds the vessel spends searching after MOB
MOB_SEARCH_SPEED_KN      = 2.0      # knots during MOB search pattern
COLOR_EVENT_MEDICAL      = (220, 165, 50)   # amber — medical emergency log entry

# ============================================================================
# Shipping Lanes (Traffic Separation Scheme overlay)
# ============================================================================
# Dashed lines trace the main inter-port routes so chart readers can see the
# recommended fairways at a glance — exactly as a TSS appears on a paper chart.
SHIPPING_LANE_ALPHA    = 40     # overlay alpha for the dashed lane lines
SHIPPING_LANE_DASH_PX  = 10     # screen pixels per dash segment
SHIPPING_LANE_GAP_PX   = 12     # screen pixels per inter-dash gap
SHIPPING_LANE_MIN_ZOOM = 0.5    # declutter: hide lanes below this zoom level

# ============================================================================
# AIS / External Awareness (Technical Systems Panel)
# ============================================================================
AIS_CPA_WARNING_NM = 2.0    # show CPA proximity alert when < this value (nm)
AIS_NEARBY_MAX     = 6      # max vessels shown in the awareness section

# ============================================================================
# Vessel AI — personality, mood, and party yacht system
# ============================================================================
# Cruise-speed fractions per personality archetype.  Applied as a baseline
# when no higher-priority override (fog, port congestion, fuel economy) is set.
PERSONALITY_CAUTIOUS_SPEED   = 0.70   # reduced-risk passage; 70 % max
PERSONALITY_EFFICIENT_SPEED  = 0.85   # balanced economy cruise; 85 % max
PERSONALITY_AGGRESSIVE_SPEED = 1.00   # always push rated speed
PERSONALITY_LEISURE_SPEED    = 0.55   # no hurry; 55 % max

# Mood transition thresholds (simulated seconds)
MOOD_TIRED_AFTER_S     = 10800.0   # 3 sim-h continuous underway → tired
MOOD_CONFIDENT_AFTER_S =  7200.0   # 2 sim-h without incident → confident
MOOD_RESTED_AFTER_S    =  1800.0   # 30 sim-min in port → back to normal

# Party yacht system
PARTY_DURATION_MIN_S = 3600.0   # 60 sim-min minimum party duration
PARTY_DURATION_MAX_S = 5400.0   # 90 sim-min maximum party duration
PORT_STAY_TENDER_S   = 1800.0   # 30 sim-min stop at each end of tender run
PARTY_TENDER_NAME    = "MV Tender I"   # the tender vessel that services parties

# Tender vessel color — white/cream so it stands out from standard AIS types
VESSEL_COLOR_TENDER = (240, 240, 240)

# ============================================================================
# Player Vessel
# ============================================================================
PLAYER_THROTTLE_STEP = 1.0    # knots per key press for throttle up/down
PLAYER_TURN_RATE     = 2.5    # degrees per sim-second while turn key held
PLAYER_FOLLOW_CAM    = True   # follow player vessel on startup
PLAYER_PULSE_PERIOD  = 1.5    # seconds per full pulse cycle on the player ring

# ============================================================================
# Career System
# ============================================================================
PLAYER_STARTING_MONEY      = 5000.0   # opening wallet balance (currency units)
PLAYER_STARTING_REPUTATION = 10       # opening reputation score (0–100)

# ── Reputation tiers ─────────────────────────────────────────────────────────
# Each tier unlocks privileges: Tier 2 → rescue contracts, Tier 3 → hazmat
# contracts and Kessock Anchorage clearance, Tier 4 → VIP charters.
REP_TIER_1 = 0    # Deckhand (starting rank)
REP_TIER_2 = 25   # First Mate
REP_TIER_3 = 50   # Captain
REP_TIER_4 = 75   # Master Mariner
# Highest-first lookup table: the first threshold ≤ reputation wins.
REP_TIER_TABLE = (
    (REP_TIER_4, "Master Mariner"),
    (REP_TIER_3, "Captain"),
    (REP_TIER_2, "First Mate"),
    (REP_TIER_1, "Deckhand"),
)

# VIP charter (Tier 4 exclusive): premium payout multiplier on the base
# delivery rate — the highest-paying contract type in the game.
VIP_CHARTER_RATE_MULT = 2.5

# "Lucky Escape" achievement: survive a grounding with hull above this.
LUCKY_ESCAPE_HULL_MIN = 0.10
HULL_REPAIR_COST_PER_POINT = 50.0    # cost per 1 % hull integrity restored at port
CONTRACT_PENALTY           = 200.0   # fine deducted for a missed contract deadline

# Docking menu economics & behaviour
# Fuel is priced per percentage point of tank refilled, mirroring the hull
# formula: a full refuel from empty costs 100 × 8 = £800 — meaningful against
# typical contract payouts (£2000–8000) without being punishing.
FUEL_COST_PER_UNIT = 8.0
# Player docks by drifting into the port radius at or below this speed.
# 2 kn ≈ bare steerage way — fast approaches sail straight through the harbour.
PLAYER_DOCKING_MAX_SPEED_KN = 2.0

# ── Special contract types ───────────────────────────────────────────────────
# Hazmat: premium rate for dangerous cargo, short deadline, double zone fines.
HAZMAT_RATE_MULT        = 1.8          # payout multiplier vs the standard delivery rate
HAZMAT_REP_REQUIRED     = REP_TIER_3   # Captain rank — hazmat is a Tier 3 privilege
HAZMAT_DEADLINE_RANGE_H = (4, 6)  # tight window — the cargo can't sit around
HAZMAT_FINE_MULT        = 2.0     # zone fines double while a hazmat job is active

# Charter: passenger comfort run — relaxed deadline but a hard speed ceiling.
CHARTER_RATE_PER_NM      = 100.0    # £ per nm — between delivery (80) and rescue (150)
CHARTER_DEADLINE_RANGE_H = (8, 12)  # generous window; speed is the constraint
CHARTER_MAX_SPEED_KN     = 10.0     # player speed cap while a charter is active

# Standard deadline window for all other contract types.
CONTRACT_DEADLINE_RANGE_H = (4, 12)

# ============================================================================
# Player autopilot (right-click waypoint navigation)
# ============================================================================
PORT_CLICK_RADIUS_PX     = 14   # screen px around a port symbol that snaps the
                                # right-click destination to the port itself
AUTOPILOT_MARKER_SIZE_PX = 6    # half-size of the diamond waypoint marker

# ============================================================================
# Sound
# ============================================================================
SOUND_ENABLED = True
SOUND_VOLUME  = 0.6              # master volume 0.0–1.0 (UI slider adjusts this)
SOUND_DIR     = "assets/sounds"  # generated .wav files live here
# Engine hum plays only while the player is underway above this speed.
ENGINE_SOUND_MIN_SPEED_KN = 2.0
# Per-sound mix levels, multiplied by the master volume.  The loops sit low
# beneath the one-shot alerts so warnings always cut through.
SOUND_RELATIVE_VOLUMES = {
    "engine_loop": 0.55,
    "ambient_sea": 0.40,
    "docking":     0.90,
    "warning":     0.90,
    "mayday":      1.00,
}

# ============================================================================
# Consequences — zone fines, hull damage, storm limits
# ============================================================================
ZONE_FINE_NO_ENTRY   = 500.0    # £ fine for entering a no-entry zone
ZONE_FINE_SPEED      = 150.0    # £ fine for exceeding a speed-limit zone
ZONE_FINE_INTERVAL_S = 30.0     # minimum seconds between successive fines in the same zone

GROUNDING_HULL_DAMAGE  = 0.15   # hull integrity lost per grounding event (15 %)
STORM_WAVE_THRESHOLD   = 3.5    # wave height (m) above which storm consequences apply
STORM_HULL_DAMAGE_RATE = 0.0002 # hull integrity lost per sim-second while in storm

STORM_MAX_SPEED_KN = 6.0        # player's max effective speed during storm conditions
