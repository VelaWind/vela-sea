"""Design tokens for the render layer — the single source of visual truth.

Two resolutions of the same token set:

* Desktop (IS_WEB False): every token equals the exact legacy value that was
  previously hard-coded at its call sites, so desktop rendering stays
  byte-for-byte identical.
* Web (IS_WEB True): the modern ambient-map look — deep-navy translucent
  surfaces, hairline low-alpha borders, one cyan accent, soft off-white text
  at three opacity levels.  Reference feel: FlightRadar24 / MarineTraffic
  dark mode.

Sizing tokens are design-time pixels: pass them through fonts.ui_px() at the
point of use so they ride the resolution-aware UI scale.
"""

from config import (
    IS_WEB,
    COLOR_PANEL_BG, COLOR_PANEL_BORDER, COLOR_ACCENT,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM,
    COLOR_GRID_MAJOR, COLOR_GRID_MINOR, COLOR_GRID_LABEL,
    COLOR_CHART_BAR_BG, COLOR_FRAME,
)

# ── Core palette ────────────────────────────────────────────────────────────
ACCENT = COLOR_ACCENT                       # one cyan accent, both worlds

if IS_WEB:
    # Text: soft off-white at three opacity levels — never pure white.
    TEXT_HI  = (222, 233, 244)
    TEXT_MID = (164, 184, 204)
    TEXT_LOW = (108, 128, 150)

    # Chart grid: barely-there hairlines; the sea is the subject, not the grid.
    GRID_MAJOR = (43, 62, 84)
    GRID_MINOR = (27, 42, 60)
    GRID_LABEL = (122, 143, 163)

    # Panels: translucent deep navy, hairline low-alpha border, soft radius.
    # 236 alpha, not lower: at ~208 the bright chart chips ghosted straight
    # through panel body text (seen in the preview harness follow.png).
    PANEL_FILL     = (9, 17, 29, 236)
    PANEL_BORDER   = (136, 170, 205, 42)
    PANEL_BORDER_W = 1
    PANEL_RADIUS   = 12

    # Label chips: vessels speak slightly louder than ports.
    CHIP_FILL_VESSEL = (8, 16, 28, 216)
    CHIP_FILL_PORT   = (8, 16, 28, 172)
    CHIP_BORDER      = (150, 182, 214, 34)
    CHIP_BORDER_SEL  = (*ACCENT, 190)       # selected vessel gets the accent
    CHIP_TEXT_VESSEL = TEXT_HI
    CHIP_TEXT_PORT   = TEXT_MID
    CHIP_RADIUS      = 9

    # Top status bar: quieter chrome.  NOTE: these two are drawn straight onto
    # the opaque display (pygame.draw ignores alpha there), so they are
    # pre-blended opaque colors, not alpha tuples.
    BAR_FILL  = (7, 14, 24)
    BAR_LINE  = (33, 49, 67)                # hairline, pre-blended over navy
    BAR_TEXT_L = TEXT_MID                   # clock
    BAR_TEXT_M = TEXT_MID                   # wind / vis / event
    # (speed keeps the accent — it is the one interactive state up there)

    # Fleet panel rows.
    ROW_SEL_FILL   = (*ACCENT, 26)          # selected-row wash (accent-tinted)
    ROW_HOVER_FILL = (255, 255, 255, 12)    # step-2 hover wash
    ROW_NAME       = TEXT_MID
    ROW_NAME_SEL   = TEXT_HI
    ROW_GUTTER     = 12                     # name/status column gap (design px)

    # Event log.
    LOG_FILL   = PANEL_FILL
    LOG_BORDER = PANEL_BORDER
    LOG_RADIUS = PANEL_RADIUS

    # Vessel-info accents.
    INFO_LOG_HEADER = ACCENT                # "Captain's log" header at rest

    # Perf overlay: present but dim — telemetry, not UI.
    FPS_COLOR = (104, 128, 148)
else:
    # Legacy values, verbatim from the previous call sites.
    TEXT_HI  = COLOR_TEXT_PRIMARY
    TEXT_MID = COLOR_TEXT_SECONDARY
    TEXT_LOW = COLOR_TEXT_DIM

    GRID_MAJOR = COLOR_GRID_MAJOR
    GRID_MINOR = COLOR_GRID_MINOR
    GRID_LABEL = COLOR_GRID_LABEL

    PANEL_FILL     = (*COLOR_PANEL_BG, 230)
    PANEL_BORDER   = COLOR_PANEL_BORDER     # opaque legacy border
    PANEL_BORDER_W = 2
    PANEL_RADIUS   = 10

    CHIP_FILL_VESSEL = (*COLOR_CHART_BAR_BG, 220)
    CHIP_FILL_PORT   = (*COLOR_CHART_BAR_BG, 220)
    CHIP_BORDER      = (*COLOR_TEXT_PRIMARY, 40)
    CHIP_BORDER_SEL  = (*COLOR_TEXT_PRIMARY, 40)
    CHIP_TEXT_VESSEL = COLOR_TEXT_PRIMARY
    CHIP_TEXT_PORT   = COLOR_TEXT_PRIMARY
    CHIP_RADIUS      = 8

    BAR_FILL  = (*COLOR_CHART_BAR_BG, 220)
    BAR_LINE  = COLOR_FRAME
    BAR_TEXT_L = COLOR_TEXT_SECONDARY
    BAR_TEXT_M = COLOR_TEXT_PRIMARY

    ROW_SEL_FILL   = (255, 255, 255, 22)
    ROW_HOVER_FILL = (255, 255, 255, 0)     # no hover wash on desktop
    ROW_NAME       = (160, 160, 160)
    ROW_NAME_SEL   = (230, 230, 230)
    ROW_GUTTER     = 6

    LOG_FILL   = (8, 20, 40, 195)
    LOG_BORDER = (40, 65, 95)
    LOG_RADIUS = 0

    INFO_LOG_HEADER = COLOR_ACCENT

    FPS_COLOR = (150, 205, 170)
