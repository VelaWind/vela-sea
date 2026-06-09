"""Chart renderer: draws the maritime map with all visual elements.

This module is purely a view — it reads from the simulation state (world, ships,
environment) and draws it. It knows nothing about game logic, only how to render.
"""

import math
import random as _rng
import time
import pygame
import pygame.gfxdraw
from typing import Tuple, Optional

from config import (
    COLOR_WATER, COLOR_SHALLOW_WATER, COLOR_SHALLOW_BAND, COLOR_DEPTH_CONTOUR,
    COLOR_LAND_FILL, COLOR_LAND_COAST, COLOR_LAND_SHADE, COLOR_GRID_MINOR, LAND_COLORS,
    COLOR_GRID_MAJOR, COLOR_GRID_LABEL, COLOR_CHART_BAR_BG, COLOR_SCALE_BAR,
    COLOR_NORTH_ARROW, COLOR_ZONE_LABEL, COLOR_FRAME, COLOR_NO_ENTRY,
    COLOR_SPEED_LIMIT, COLOR_PROTECTED, COLOR_ANCHORAGE, COLOR_TSS,
    COLOR_SHALLOW_HAZARD, COLOR_VESSEL_DEFAULT, COLOR_VESSEL_SELECTED,
    COLOR_VESSEL_DOCKED, COLOR_VESSEL_RANGE, COLOR_HEADING_VECTOR, COLOR_PANEL_BG,
    COLOR_PANEL_BORDER, COLOR_ACCENT, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM, COLOR_WARNING,
    LABEL_ZOOM_THRESHOLD_SHOW_ALL,
    FONT_UI_NAME, FONT_DATA_NAME, FONT_SIZE_SMALL, FONT_SIZE_LABEL,
    FONT_SIZE_MAP_LABEL, FONT_SIZE_DATA, FONT_SIZE_BIG, FONT_SIZE_SECTION,
    WORLD_WIDTH, WORLD_HEIGHT, GRID_SPACING, GRID_LABEL_INTERVAL,
    COMPASS_SIZE, COMPASS_OFFSET_X, COMPASS_OFFSET_Y,
    SCALE_BAR_MAX_WIDTH, SCALE_BAR_TARGET_WIDTH, SCALE_BAR_OFFSET_X, SCALE_BAR_OFFSET_Y,
    SCALE_BAR_HEIGHT, PORT_SYMBOL_SIZE, PORT_LABEL_OFFSET,
    ZONE_BORDER_WIDTH, ZONE_LABEL_OFFSET, ZONE_FILL_ALPHA,
    ZONE_HATCH_ALPHA, ZONE_HATCH_SPACING, SHALLOW_WATER_BAND_WIDTH,
    SHALLOW_WATER_BAND_STEPS, SHALLOW_WATER_BAND_STEP_PX, SHALLOW_WATER_BAND_MAX_ALPHA,
    DEPTH_CONTOUR_WIDTH, SHIP_SELECT_RADIUS, SHIP_SELECT_GLOW_WIDTH,
    SHIP_MIN_SIZE, SHIP_MAX_SIZE, SHIP_LABEL_OFFSET,
    SHIP_PREDICTOR_MINUTES, SHIP_VECTOR_MINUTES, SHIP_RANGE_RING_INTERVAL_NM,
    SHIP_RANGE_RING_COUNT, SHIP_SELECTION_ALPHA,
    SHIP_SYMBOL_ZOOM_SCALE, KNOTS_TO_UNITS_PER_HOUR,
    CURRENT_INFLUENCE,
    COLOR_COG_VECTOR, COG_MIN_DRIFT_DEG,
    COLOR_CURRENT_ARROW, CURRENT_ARROW_SPACING_PX, CURRENT_ARROW_ALPHA, CURRENT_ARROW_SIZE,
    SAIL_IRONS_DISPLAY_THRESHOLD,
    DEPTH_COLOR_SHOAL,
    DEPTH_CONTOUR_DRAW_COLOR,
    DEPTH_SOUNDING_POSITIONS,
    DEPTH_SHOAL_HALO_ALPHA, DEPTH_SHOAL_HALO_STEPS,
    LAND_INLAND_TINT_SHRINK_PX, LAND_INLAND_TINT_COLOR,
    OCEAN_VIGNETTE_WORLD_RADIUS, OCEAN_VIGNETTE_ALPHA,
    OCEAN_VIGNETTE_STEPS, OCEAN_VIGNETTE_COLOR,
    COLOR_BEACH_FRINGE, BEACH_FRINGE_ALPHA, BEACH_FRINGE_WIDTH_PX,
    SHALLOW_WATER_MID_BAND_OFFSET_PX, SHALLOW_WATER_MID_BAND_ALPHA,
    COLOR_COLLISION_AVOID,
    SAR_PULSE_PERIOD, COLOR_SAR_DISTRESS, PORT_ACTIVITY_PULSE_PERIOD,
    PLAYER_PULSE_PERIOD,
    VESSEL_COLOR_CARGO, VESSEL_COLOR_FERRY, VESSEL_COLOR_FISHING,
    VESSEL_COLOR_SAILBOAT, VESSEL_COLOR_TUG, VESSEL_COLOR_SELECTED,
    VESSEL_COLOR_TANKER, VESSEL_COLOR_COAST_GUARD,
    SHIPPING_LANE_ALPHA, SHIPPING_LANE_DASH_PX,
    SHIPPING_LANE_GAP_PX, SHIPPING_LANE_MIN_ZOOM,
    AUTOPILOT_MARKER_SIZE_PX,
    SCREEN_VIGNETTE_DEPTH_PX, SCREEN_VIGNETTE_MAX_ALPHA, SCREEN_VIGNETTE_STEPS,
    PORT_NEAR_PULSE_RANGE_WU,
    FOG_LOW_VIS_THRESHOLD_M, FOG_VESSEL_HIDE_RANGE_WU,
    STORM_TINT_COLOR, STORM_TINT_ALPHA, STORM_WAVE_THRESHOLD,
    STORM_WAVE_LINE_COLOR, STORM_WAVE_LINE_ALPHA,
    STORM_WAVE_LINE_SPACING_PX, STORM_WAVE_SCROLL_PX_S,
    SQUALL_FLASH_ALPHA, SQUALL_FLASH_DURATION_S,
)
from render.camera import Camera

Position = Tuple[float, float]

# AIS/ECDIS vessel type colors — hull tint keyed by vessel_type string.
_VESSEL_TYPE_COLORS: dict = {
    "cargo":       VESSEL_COLOR_CARGO,
    "tanker":      VESSEL_COLOR_TANKER,
    "ferry":       VESSEL_COLOR_FERRY,
    "fishing":     VESSEL_COLOR_FISHING,
    "sailboat":    VESSEL_COLOR_SAILBOAT,
    "tug":         VESSEL_COLOR_TUG,
    "coast_guard": VESSEL_COLOR_COAST_GUARD,
}


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _vessel_hull_points(vessel_type: str, size: int) -> list:
    """Return a 3-point AIS triangle: bow = −y tip, base at +y.

    Each type has a distinct (s, w) pair so vessels are visually distinguishable
    even at small sizes. s = half-height (length), w = half-base (beam).
    Rotation convention: _rotate_points(pts, heading + 90, cx, cy) — see draw_vessel.
    """
    if vessel_type == "tanker":
        s, w = size,                    max(4, size // 3)
    elif vessel_type == "ferry":
        s, w = size,                    max(4, size // 3)
    elif vessel_type == "fishing":
        s, w = max(8, int(size * 0.8)), max(3, int(size * 0.27))
    elif vessel_type in ("sailboat", "coast_guard"):
        s, w = max(7, int(size * 0.75)), max(2, int(size * 0.11))
    elif vessel_type == "tug":
        s, w = max(7, int(size * 0.7)), max(3, int(size * 0.23))
    elif vessel_type == "tender":
        s, w = max(6, int(size * 0.65)), max(2, int(size * 0.18))
    else:  # cargo (and any unrecognised type)
        s, w = size,                    max(3, size // 5)
    return [(0, -s), (-w, s // 2), (w, s // 2)]


def _rotate_points(points: list, angle_deg: float, cx: float, cy: float) -> list:
    """Rotate local (x, y) offsets by angle_deg and translate to screen (cx, cy)."""
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    return [
        (cx + x * cos_a - y * sin_a,
         cy + x * sin_a + y * cos_a)
        for x, y in points
    ]


def _interpolate_point(start: Position, end: Position, fraction: float) -> Position:
    return (
        start[0] + (end[0] - start[0]) * fraction,
        start[1] + (end[1] - start[1]) * fraction,
    )


def _cog_direction(vessel, environment):
    """Return (cog_angle_rad, cog_speed_kn) when the vessel's actual track over
    ground diverges meaningfully from its heading, otherwise None.

    Mirrors the physics in ship.py move() — heading vector + current set-and-drift
    + wind drift — but is read-only and used only for drawing.
    """
    if environment is None or vessel.current_speed <= 0:
        return None

    h_rad = math.radians(vessel.heading)
    vx = math.cos(h_rad) * vessel.current_speed
    vy = math.sin(h_rad) * vessel.current_speed

    # Current set-and-drift (toward current_direction)
    c_rad = math.radians(environment.current_direction)
    vx += math.cos(c_rad) * environment.current_speed * CURRENT_INFLUENCE
    vy += math.sin(c_rad) * environment.current_speed * CURRENT_INFLUENCE

    # Wind drift (away from wind_direction — same sign as ship.py)
    push_rad = math.radians((environment.wind_direction + 180.0) % 360.0)
    wind_kn = environment.wind_speed * vessel._windage_factor()
    vx += math.cos(push_rad) * wind_kn
    vy += math.sin(push_rad) * wind_kn

    cog_rad = math.atan2(vy, vx)
    cog_speed = math.hypot(vx, vy)

    # Shortest signed arc between COG and heading; skip if negligible
    drift = (math.degrees(cog_rad) - vessel.heading + 180.0) % 360.0 - 180.0
    if abs(drift) < COG_MIN_DRIFT_DEG:
        return None

    return cog_rad, cog_speed


class Chart:
    """Renders the maritime chart with all visual elements."""

    def __init__(self, surface: pygame.Surface, camera: Camera):
        self.surface = surface
        self.camera = camera
        self.font_map = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_MAP_LABEL)
        self.font_small = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_SMALL)
        self.font_label = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_LABEL)
        self.font_data = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_DATA)
        self.font_mono = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_SMALL)
        self.font_big = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_BIG, bold=True)
        self.font_section = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_SECTION, bold=True)
        self._label_candidates = []
        # Shoal halo: radial gradient surfaces keyed by screen radius.
        # Built once per unique radius (changes only when zoom changes); never rebuilt mid-frame.
        self._shoal_halo_cache: dict = {}
        # Ocean vignette: cached gradient surface keyed by (zoom_bucket, vw, vh).
        # Rebuilt only when zoom or window size changes — usually never during a run.
        self._ov_surf: Optional[pygame.Surface] = None
        self._ov_key: tuple = ()
        # Shared full-screen SRCALPHA overlay — allocated once, reused for current
        # arrows and the night tint so we never pay the ~1.4 ms SDL surface
        # allocation cost more than once per session.
        self._alpha_surf: Optional[pygame.Surface] = None
        # Coastal depth layer: mid-depth fills + shallow bands for all islands.
        # Cached by (zoom_bucket, vw, vh) — rebuilt only when zoom or window changes.
        self._depth_surf: Optional[pygame.Surface] = None
        self._depth_key: tuple = ()
        # Weather-event transition tracking for the squall lightning flash.
        self._last_weather_event: Optional[str] = None
        self._squall_flash_until: float = 0.0
        # Screen-edge vignette — cached by window size, rebuilt on resize only.
        self._vignette_surf: Optional[pygame.Surface] = None

    def _get_alpha_surf(self) -> pygame.Surface:
        """Return the shared full-screen SRCALPHA surface, creating it once on first use.

        Callers must clear it themselves (``surf.fill((0, 0, 0, 0))``) before drawing.
        This avoids the ~1.4 ms SDL surface allocation that would otherwise happen
        several times per frame (once per island + once for current arrows + night tint).
        """
        vw, vh = self.surface.get_width(), self.surface.get_height()
        if self._alpha_surf is None or self._alpha_surf.get_size() != (vw, vh):
            self._alpha_surf = pygame.Surface((vw, vh), pygame.SRCALPHA)
        return self._alpha_surf

    def draw_background(self, world=None) -> None:
        self.surface.fill(COLOR_WATER)

    def draw_ocean_vignette(self) -> None:
        """Very faint tonal variation in the open ocean, world-anchored.

        A radial gradient is blit at the world-centre screen position each frame.
        The gradient surface is cached by (zoom_bucket, viewport_size) and rebuilt
        only when those change — effectively never during a normal run.  One cheap
        blit per frame is the only per-frame cost.
        """
        vw = self.surface.get_width()
        vh = self.surface.get_height()
        # Round zoom to nearest 0.1 so minor drift doesn't trigger unnecessary rebuilds
        zoom_key = round(self.camera.zoom, 1)
        key = (zoom_key, vw, vh)
        if self._ov_key != key:
            radius = max(80, int(self.camera.distance_to_screen(OCEAN_VIGNETTE_WORLD_RADIUS)))
            # Clamp to something reasonable so it doesn't balloon at high zoom
            radius = min(radius, max(vw, vh))
            size = radius * 2 + 4
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            cx = cy = radius + 2
            for step in range(OCEAN_VIGNETTE_STEPS):
                # Innermost ring at full alpha, outermost near zero
                r = int(radius * (OCEAN_VIGNETTE_STEPS - step) / OCEAN_VIGNETTE_STEPS)
                alpha = int(OCEAN_VIGNETTE_ALPHA * (OCEAN_VIGNETTE_STEPS - step) / OCEAN_VIGNETTE_STEPS)
                if r > 0:
                    pygame.gfxdraw.filled_circle(surf, cx, cy, r,
                                                 (*OCEAN_VIGNETTE_COLOR, alpha))
            self._ov_surf = surf
            self._ov_key = key

        s = self._ov_surf
        cx, cy = self.camera.world_to_screen((WORLD_WIDTH / 2, WORLD_HEIGHT / 2))
        self.surface.blit(s, (int(cx) - s.get_width() // 2, int(cy) - s.get_height() // 2))

    # ------------------------------------------------------------------
    # Depth visualization — flat-zone chartplotter style (Chunk D)
    # ------------------------------------------------------------------

    def _build_shoal_halo(self, sr: int) -> pygame.Surface:
        """Return a cached radial-gradient SRCALPHA surface for a shallow-zone halo.

        Gradient: most-opaque at the centre, fully transparent at radius sr.
        Linear alpha falloff so the shoal reads as a whisper of pale, not a disc.
        Cached by screen radius — rebuilt only when zoom changes enough to alter sr.
        """
        if sr in self._shoal_halo_cache:
            return self._shoal_halo_cache[sr]

        size = sr * 2 + 4
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = sr + 2
        steps = DEPTH_SHOAL_HALO_STEPS

        # Draw from outermost (transparent) inward (most opaque).
        # Each inner filled circle overwrites the previous in its area,
        # producing a stepped linear-alpha gradient.
        for step in range(steps):
            ring_r = int(sr * (steps - step) / steps)
            alpha = int(DEPTH_SHOAL_HALO_ALPHA * (1.0 - ring_r / sr)) if sr > 0 else 0
            if ring_r > 0:
                pygame.gfxdraw.filled_circle(surf, cx, cy, ring_r,
                                             (*DEPTH_COLOR_SHOAL, alpha))

        self._shoal_halo_cache[sr] = surf
        return surf

    def draw_depth_zones(self, world, environment) -> None:
        """Soft depth zone hints for named shallow zones (Skerry Bank etc.).

        Coastal gradient bands are handled by draw_islands (SHALLOW_WATER_BAND
        rings with lowered alpha), so no additional solid fills are needed here.
        Shallow zones get a pre-built radial gradient halo: pale at the centre,
        fully transparent at the zone boundary — a ECDIS-style danger whisper.
        The halo surface is cached by screen radius and rebuilt only on zoom change.
        """
        if not world:
            return

        for zone in world.zones:
            if zone.kind != "shallow":
                continue
            sx, sy = self.camera.world_to_screen(zone.center)
            sr = max(1, int(self.camera.distance_to_screen(zone.radius)))
            halo = self._build_shoal_halo(sr)
            self.surface.blit(halo, (int(sx) - sr - 2, int(sy) - sr - 2))

    def draw_depth_contours(self, world, environment) -> None:
        """Draw depth contour boundary for named shallow zones (Skerry Bank).

        Previously this also drew offset polygon outlines around every island
        coastline, which created a solid full-opacity blue rim just outside each
        island — drawn before draw_islands so the land fill never covered it.
        Those island contour loops have been removed; the Skerry Bank circle is
        the only meaningful contour here (it marks a discrete hazard boundary).
        Coastal depth gradient is handled by the soft band rings in draw_islands.
        """
        if not world or not environment:
            return
        c = DEPTH_CONTOUR_DRAW_COLOR

        # Skerry Bank boundary circle as a contour line
        for zone in world.zones:
            if zone.kind != "shallow":
                continue
            sx, sy = self.camera.world_to_screen(zone.center)
            sr = max(0, int(self.camera.distance_to_screen(zone.radius)))
            if sr > 0:
                pygame.gfxdraw.aacircle(self.surface, int(sx), int(sy), sr, c)

    def draw_depth_soundings(self, world, environment) -> None:
        """Print spot depth soundings at fixed chart positions.

        Each number sits on a small semi-transparent dark pill so it reads
        cleanly over any depth tint.  Uses COLOR_TEXT_SECONDARY — muted,
        not bright white — so soundings feel like chart annotations, not HUD.
        Depth values update live with tide (a handful of cached lookups per frame).
        """
        if not world or not environment:
            return
        tide = environment.tide_level
        vw = self.surface.get_width()
        vh = self.surface.get_height()

        for wx, wy in DEPTH_SOUNDING_POSITIONS:
            sx, sy = self.camera.world_to_screen((wx, wy))
            if sx < -20 or sx > vw + 20 or sy < -20 or sy > vh + 20:
                continue
            depth = world.water_depth_at((wx, wy), tide)
            if depth <= 0:
                continue
            lbl = self.font_mono.render(f"{depth:.0f}", True, COLOR_TEXT_SECONDARY)
            lw, lh = lbl.get_size()
            lx = int(sx - lw / 2)
            ly = int(sy - lh / 2)
            # Semi-transparent dark pill behind the number for legibility over any tint
            pill = pygame.Surface((lw + 8, lh + 4), pygame.SRCALPHA)
            pygame.draw.rect(pill, (5, 12, 24, 160), pill.get_rect(), border_radius=3)
            self.surface.blit(pill, (lx - 4, ly - 2))
            self.surface.blit(lbl, (lx, ly))

    def _draw_shallow_water_bands(self, world) -> None:
        if not world or not getattr(world, "islands", None):
            return

        overlay = pygame.Surface(self.surface.get_size(), pygame.SRCALPHA)
        band_color = (*COLOR_SHALLOW_WATER, 32)
        contour_color = COLOR_DEPTH_CONTOUR

        for island in world.islands:
            screen_polygon = [self.camera.world_to_screen(point) for point in island.polygon]
            int_polygon = [(int(x), int(y)) for x, y in screen_polygon]
            pygame.draw.lines(overlay, band_color, True, int_polygon, 14)
            pygame.gfxdraw.aapolygon(overlay, int_polygon, contour_color)
            offset_polygon = self._offset_screen_polygon(int_polygon, 8)
            if len(offset_polygon) >= 3:
                pygame.gfxdraw.aapolygon(overlay, offset_polygon, contour_color)

        self.surface.blit(overlay, (0, 0))

    def _offset_screen_polygon(self, polygon, offset_pixels: float):
        if not polygon:
            return []

        avg_x = sum(x for x, _ in polygon) / len(polygon)
        avg_y = sum(y for _, y in polygon) / len(polygon)
        scale = 1.0 + offset_pixels / max(1.0, math.hypot(polygon[0][0] - avg_x, polygon[0][1] - avg_y))

        return [(
            int(avg_x + (x - avg_x) * scale),
            int(avg_y + (y - avg_y) * scale),
        ) for x, y in polygon]

    def _build_depth_layer(self, world) -> pygame.Surface:
        """Build and cache the coastal depth gradient surface for all islands.

        Draws three visual layers per island onto a shared SRCALPHA surface:
          1. Mid-depth halo — wide offset fill in COLOR_SHALLOW_WATER, visible
             from coast out to ~40 screen-px; land fill later covers the interior.
          2. Beach fringe — thin sandy ring right on the polygon edge; the land
             fill covers its inner half, leaving ~2 px of warm sand in the water.
          3. Shallow bands — 8 tight rings of COLOR_SHALLOW_BAND fading outward,
             starting 1 step out from the polygon so none bleeds inside the land.

        Cached by (zoom_bucket, vw, vh); rebuilt only when zoom or window changes.
        """
        vw = self.surface.get_width()
        vh = self.surface.get_height()
        zoom_key = round(self.camera.zoom, 1)
        key = (zoom_key, vw, vh)
        if self._depth_key == key and self._depth_surf is not None:
            return self._depth_surf

        surf = pygame.Surface((vw, vh), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))

        if world:
            for island in world.islands:
                screen_polygon = [self.camera.world_to_screen(p) for p in island.polygon]
                if len(screen_polygon) < 3:
                    continue
                int_polygon = [(int(x), int(y)) for x, y in screen_polygon]

                # 1. Mid-depth zone: large offset polygon; land fill covers interior.
                mid_poly = self._offset_screen_polygon(
                    int_polygon, SHALLOW_WATER_MID_BAND_OFFSET_PX)
                if len(mid_poly) >= 3:
                    pygame.gfxdraw.filled_polygon(
                        surf, mid_poly,
                        (*COLOR_SHALLOW_WATER, SHALLOW_WATER_MID_BAND_ALPHA))

                # 2. Beach fringe: thin warm ring on the polygon edge.
                pygame.draw.lines(
                    surf, (*COLOR_BEACH_FRINGE, BEACH_FRINGE_ALPHA),
                    True, int_polygon, BEACH_FRINGE_WIDTH_PX)

                # 3. Shallow bands: start 1 step outward so no ring overlaps land.
                for step in range(SHALLOW_WATER_BAND_STEPS):
                    step_alpha = int(
                        SHALLOW_WATER_BAND_MAX_ALPHA
                        * (1.0 - step / SHALLOW_WATER_BAND_STEPS))
                    step_offset = (step + 1) * SHALLOW_WATER_BAND_STEP_PX
                    band_poly = self._offset_screen_polygon(int_polygon, step_offset)
                    if len(band_poly) >= 3:
                        pygame.draw.lines(
                            surf,
                            (*COLOR_SHALLOW_BAND, step_alpha),
                            True, band_poly,
                            SHALLOW_WATER_BAND_STEP_PX + 1)

        self._depth_surf = surf
        self._depth_key = key
        return surf

    def draw_grid(self) -> None:
        cam_x, cam_y = self.camera.position
        zoom = self.camera.zoom
        vw, vh = self.surface.get_width(), self.surface.get_height()

        world_left = cam_x - vw / (2 * zoom)
        world_right = cam_x + vw / (2 * zoom)
        world_top = cam_y - vh / (2 * zoom)
        world_bottom = cam_y + vh / (2 * zoom)

        x = math.ceil(world_left / GRID_SPACING) * GRID_SPACING
        while x <= world_right:
            screen_x, _ = self.camera.world_to_screen((x, 0))
            is_major = abs(x) % GRID_LABEL_INTERVAL < 1.0
            color = COLOR_GRID_MAJOR if is_major else COLOR_GRID_MINOR
            pygame.draw.aaline(self.surface, color, (screen_x, 0), (screen_x, vh))
            if is_major:
                label = self.font_mono.render(f"{int(x)}", True, COLOR_GRID_LABEL)
                self._blit_text_shadow(label, int(screen_x + 4), 6)
            x += GRID_SPACING

        y = math.ceil(world_top / GRID_SPACING) * GRID_SPACING
        while y <= world_bottom:
            _, screen_y = self.camera.world_to_screen((0, y))
            is_major = abs(y) % GRID_LABEL_INTERVAL < 1.0
            color = COLOR_GRID_MAJOR if is_major else COLOR_GRID_MINOR
            pygame.draw.aaline(self.surface, color, (0, screen_y), (vw, screen_y))
            if is_major:
                label = self.font_mono.render(f"{int(y)}", True, COLOR_GRID_LABEL)
                self._blit_text_shadow(label, 6, int(screen_y + 4))
            y += GRID_SPACING

    def draw_islands(self, world) -> None:
        if not world or not world.islands:
            return

        vw, vh = self.surface.get_width(), self.surface.get_height()

        for island in world.islands:
            screen_polygon = [self.camera.world_to_screen(point) for point in island.polygon]
            if len(screen_polygon) < 3:
                continue

            int_polygon = [(int(x), int(y)) for x, y in screen_polygon]

            # Per-type land colours — fall back to "island" palette if unknown type.
            _lc = LAND_COLORS.get(island.land_type, LAND_COLORS["island"])
            _fill  = _lc["fill"]
            _coast = _lc["coast"]
            _shade = _lc["shade"]

            # Land fill covers the interior of depth bands drawn by _build_depth_layer.
            pygame.gfxdraw.filled_polygon(self.surface, int_polygon, _fill)

            # Inland tint: shrunken polygon in the type-specific shade colour
            # so it reads as a subtle interior highlight rather than a flat fill.
            avg_x = sum(p[0] for p in int_polygon) / len(int_polygon)
            avg_y = sum(p[1] for p in int_polygon) / len(int_polygon)
            typical_r = math.hypot(int_polygon[0][0] - avg_x, int_polygon[0][1] - avg_y)
            if typical_r > LAND_INLAND_TINT_SHRINK_PX:
                inner = self._offset_screen_polygon(int_polygon, -LAND_INLAND_TINT_SHRINK_PX)
                if len(inner) >= 3:
                    pygame.gfxdraw.filled_polygon(self.surface, inner, _shade)

            # 1px anti-aliased coastline in the darker coast colour.
            pygame.gfxdraw.aapolygon(self.surface, int_polygon, _coast)

    def _zone_color(self, kind: str):
        return {
            "no_entry": COLOR_NO_ENTRY,
            "speed_limit": COLOR_SPEED_LIMIT,
            "protected": COLOR_PROTECTED,
            "anchorage": COLOR_ANCHORAGE,
            "tss": COLOR_TSS,
            "shallow": COLOR_SHALLOW_HAZARD,
        }.get(kind, COLOR_TEXT_DIM)

    def _draw_dashed_circle(self, cx: float, cy: float, radius: int,
                            color: tuple, dash_count: int = 20) -> None:
        """Draw a dashed circle as alternating arc segments (for no-entry zones)."""
        if radius < 2:
            return
        rect = pygame.Rect(int(cx) - radius, int(cy) - radius,
                           radius * 2, radius * 2)
        segment = 2 * math.pi / dash_count
        for i in range(0, dash_count, 2):
            start = i * segment
            end = start + segment * 0.65
            pygame.draw.arc(self.surface, color, rect, start, end, 1)

    def draw_zones(self, world) -> None:
        if not world or not world.zones:
            return

        for zone in world.zones:
            screen_center = self.camera.world_to_screen(zone.center)
            screen_x, screen_y = screen_center
            screen_radius = max(4, int(self.camera.distance_to_screen(zone.radius)))

            # Shallow zones: depth shading provides the visual fill.
            # Still show the zone name so the chart remains readable.
            if zone.kind == "shallow":
                if self.surface.get_rect().collidepoint(screen_x, screen_y) and screen_radius > 24:
                    label = self.font_small.render(zone.name, True, COLOR_ZONE_LABEL)
                    self._queue_label(label, int(screen_x - label.get_width() / 2),
                                      int(screen_y + screen_radius + 6),
                                      priority=50, anchor_pos=(screen_x, screen_y))
                continue

            color = self._zone_color(zone.kind)

            overlay = pygame.Surface((screen_radius * 2 + 4, screen_radius * 2 + 4), pygame.SRCALPHA)
            pygame.gfxdraw.filled_circle(overlay, screen_radius + 2, screen_radius + 2, screen_radius, (*color, ZONE_FILL_ALPHA))
            pygame.gfxdraw.aacircle(overlay, screen_radius + 2, screen_radius + 2, screen_radius, color)
            self.surface.blit(overlay, (int(screen_x - screen_radius - 2), int(screen_y - screen_radius - 2)))

            if zone.kind == "no_entry":
                self._draw_zone_hatching(screen_x, screen_y, screen_radius, color)
                self._draw_dashed_circle(screen_x, screen_y, screen_radius, color)
            else:
                pygame.gfxdraw.aacircle(self.surface, int(screen_x), int(screen_y), screen_radius, color)

            if self.surface.get_rect().collidepoint(screen_x, screen_y) and screen_radius > 24:
                label = self.font_small.render(zone.name, True, COLOR_ZONE_LABEL)
                # queue zone label (medium priority)
                self._queue_label(label, int(screen_x - label.get_width() / 2), int(screen_y + screen_radius + 6), priority=50, anchor_pos=(screen_x, screen_y))

    def _draw_zone_hatching(self, center_x: float, center_y: float, radius: int, color: Tuple[int, int, int]) -> None:
        size = radius * 2 + 4
        hatch = pygame.Surface((size, size), pygame.SRCALPHA)
        for offset in range(-radius, radius, ZONE_HATCH_SPACING):
            start = (offset + radius + 2, 0)
            end = (offset + radius + 2 + size, size)
            pygame.draw.line(hatch, (*color, ZONE_HATCH_ALPHA), start, end, 1)

        mask = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.gfxdraw.filled_circle(mask, radius + 2, radius + 2, radius, (255, 255, 255, 255))
        hatch.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.surface.blit(hatch, (int(center_x - radius - 2), int(center_y - radius - 2)))

    def draw_ports(self, world) -> None:
        if not world or not world.ports:
            return

        now = time.time()
        _player = next((v for v in world.vessels
                        if getattr(v, 'is_player', False)), None)
        _near_r2 = PORT_NEAR_PULSE_RANGE_WU * PORT_NEAR_PULSE_RANGE_WU

        for port in world.ports:
            screen_x, screen_y = self.camera.world_to_screen(port.position)
            sx, sy = int(screen_x), int(screen_y)
            symbol_size = PORT_SYMBOL_SIZE

            # Classify docked vessels so we know which activity icons to show.
            has_cargo_docked = False
            has_sail_docked  = False
            any_docked       = False
            if world.vessels:
                for v in world.vessels:
                    if v._docked_port_name == port.name and v.status in ("in_port", "docked"):
                        any_docked = True
                        if v.vessel_type in ("cargo", "tanker", "ferry"):
                            has_cargo_docked = True
                        elif v.vessel_type == "sailboat":
                            has_sail_docked = True

            # Pulsing activity ring when any vessel is docked.
            if any_docked:
                phase   = (now % PORT_ACTIVITY_PULSE_PERIOD) / PORT_ACTIVITY_PULSE_PERIOD
                pulse_t = abs(math.sin(phase * math.pi))
                pulse_r = symbol_size + 4 + int(pulse_t * 6)
                pulse_a = int(70 * pulse_t)
                pygame.gfxdraw.aacircle(
                    self.surface, sx, sy, pulse_r, (200, 210, 220, pulse_a))

                # Animated loading dots — 3 dots cycling upward beside the symbol.
                # Each dot has a 1/3-cycle phase offset so they move in sequence.
                dot_col = (160, 175, 190)
                t_cycle = (now % 2.5) / 2.5
                for k in range(3):
                    ph = (t_cycle + k / 3.0) % 1.0
                    # Rise from sy-6 to sy-16, then snap back (sawtooth)
                    dot_y = sy - 6 - int(ph * 10)
                    dot_x = sx - 8 + k * 8
                    pygame.gfxdraw.filled_circle(
                        self.surface, dot_x, dot_y, 1, (*dot_col, 130))

            # Crane symbol (┐-shape) for commercial ports with cargo/tanker/ferry docked.
            if has_cargo_docked:
                ic = (145, 162, 178)
                cx = sx + symbol_size + 5
                cy = sy
                pygame.draw.line(self.surface, ic, (cx, cy + 5), (cx, cy - 9), 1)  # mast
                pygame.draw.line(self.surface, ic, (cx, cy - 9), (cx + 8, cy - 9), 1)  # boom
                pygame.draw.line(self.surface, ic, (cx + 8, cy - 9), (cx + 8, cy - 4), 1)  # hoist

            # Anchor symbol for marina/anchorage ports with a sailboat docked.
            if has_sail_docked:
                ic = (145, 162, 178)
                ax = sx - symbol_size - 9
                ay = sy
                pygame.draw.line(self.surface, ic, (ax, ay - 7), (ax, ay + 6), 1)  # shaft
                pygame.gfxdraw.aacircle(self.surface, ax, ay - 7, 3, ic)             # ring
                pygame.draw.line(self.surface, ic, (ax - 4, ay - 2), (ax + 4, ay - 2), 1)  # crossbar
                pygame.draw.line(self.surface, ic, (ax - 4, ay + 6), (ax, ay + 3), 1)  # port fluke
                pygame.draw.line(self.surface, ic, (ax + 4, ay + 6), (ax, ay + 3), 1)  # stbd fluke

            # Docking-range pulse: a gentle accent breath when the player is
            # close enough to consider berthing here.
            if _player is not None:
                _pdx = _player.position[0] - port.position[0]
                _pdy = _player.position[1] - port.position[1]
                if _pdx * _pdx + _pdy * _pdy <= _near_r2:
                    _ph = (now % PORT_ACTIVITY_PULSE_PERIOD) / PORT_ACTIVITY_PULSE_PERIOD
                    _pt = abs(math.sin(_ph * math.pi))
                    _pr = symbol_size + 3 + int(_pt * 5)
                    ca, cb, cc = COLOR_ACCENT
                    pygame.gfxdraw.aacircle(
                        self.surface, sx, sy, _pr, (ca, cb, cc, int(60 + 100 * _pt)))

            pygame.gfxdraw.filled_circle(self.surface, sx, sy, symbol_size, COLOR_PANEL_BORDER)
            pygame.gfxdraw.aacircle(self.surface, sx, sy, symbol_size, COLOR_ACCENT)
            name_label = self.font_map.render(port.name, True, COLOR_TEXT_PRIMARY)
            # queue port label (high priority)
            self._queue_label(name_label, sx + PORT_LABEL_OFFSET, sy - PORT_LABEL_OFFSET,
                              priority=80, anchor_pos=(screen_x, screen_y))

    def draw_shipping_lanes(self, world) -> None:
        """Draw faint dashed TSS lines connecting the main ports in route order.

        Shown only at zoom > SHIPPING_LANE_MIN_ZOOM to avoid clutter when the
        whole sea is on screen at once.  Drawn on the shared alpha surface so
        the lanes sit below vessel symbols without adding a new allocation.
        """
        if not world or self.camera.zoom <= SHIPPING_LANE_MIN_ZOOM:
            return

        # Canonical inter-port lane order — matches the primary shipping route.
        lane_sequence = [
            "Port Maren", "Saltgate Harbour", "Port Ardent",
            "Brattlin Light Quay", "Vesper Cove", "Thornwick Roads", "Cape Durran",
        ]
        port_map = {p.name: p.position for p in world.ports}

        lane_pts = []
        for name in lane_sequence:
            if name in port_map:
                lane_pts.append(self.camera.world_to_screen(port_map[name]))

        if len(lane_pts) < 2:
            return

        lane_col = (*COLOR_GRID_MINOR, SHIPPING_LANE_ALPHA)
        surf = self._get_alpha_surf()
        surf.fill((0, 0, 0, 0))

        for i in range(len(lane_pts) - 1):
            clipped = self._clip_line_to_surface(lane_pts[i], lane_pts[i + 1])
            if not clipped:
                continue
            cs, ce = clipped
            dx, dy = ce[0] - cs[0], ce[1] - cs[1]
            dist = math.hypot(dx, dy)
            if dist < 1.0:
                continue
            nx, ny = dx / dist, dy / dist
            traveled = 0.0
            while traveled < dist:
                seg_end = min(traveled + SHIPPING_LANE_DASH_PX, dist)
                p1 = (cs[0] + nx * traveled, cs[1] + ny * traveled)
                p2 = (cs[0] + nx * seg_end,  cs[1] + ny * seg_end)
                pygame.draw.line(surf, lane_col, p1, p2, 1)
                traveled += SHIPPING_LANE_DASH_PX + SHIPPING_LANE_GAP_PX

        self.surface.blit(surf, (0, 0))

    def draw_nav_marks(self, world) -> None:
        if not world or not world.nav_marks:
            return

        for mark in world.nav_marks:
            screen_x, screen_y = self.camera.world_to_screen(mark.position)
            color_map = {
                "safe_water": COLOR_PROTECTED,
                "lateral_port": COLOR_NO_ENTRY,
                "lateral_stbd": COLOR_ANCHORAGE,
                "cardinal_n": COLOR_TSS,
                "cardinal_e": COLOR_TSS,
                "cardinal_s": COLOR_TSS,
                "cardinal_w": COLOR_TSS,
            }
            color = color_map.get(mark.kind, COLOR_TEXT_DIM)
            size = 5
            points = [
                (int(screen_x), int(screen_y - size)),
                (int(screen_x + size), int(screen_y)),
                (int(screen_x), int(screen_y + size)),
                (int(screen_x - size), int(screen_y)),
            ]
            pygame.gfxdraw.filled_polygon(self.surface, points, color)
            pygame.gfxdraw.aapolygon(self.surface, points, COLOR_TEXT_PRIMARY)

    def draw_vessels(self, world, selected_vessel=None, environment=None,
                     hover_vessel=None) -> None:
        if not world or not world.vessels:
            return

        # Fog declutter: in low visibility, traffic beyond visual range of the
        # player vessel disappears from the chart — you can't see what the fog
        # hides.  The player's own ship always stays visible.
        _fog_origin = None
        if (environment is not None
                and environment.visibility < FOG_LOW_VIS_THRESHOLD_M):
            for v in world.vessels:
                if getattr(v, 'is_player', False):
                    _fog_origin = v.position
                    break

        # Two-pass rendering: trails behind everything, then icons on top.
        # Trails are suppressed at low zoom to avoid clutter.
        if self.camera.zoom > 0.6 and selected_vessel is not None:
            self._draw_vessel_trail(selected_vessel, selected=True)

        _hide_r2 = FOG_VESSEL_HIDE_RANGE_WU * FOG_VESSEL_HIDE_RANGE_WU
        for vessel in world.vessels:
            if _fog_origin is not None and not getattr(vessel, 'is_player', False):
                dx = vessel.position[0] - _fog_origin[0]
                dy = vessel.position[1] - _fog_origin[1]
                if dx * dx + dy * dy > _hide_r2:
                    continue
            self.draw_vessel(vessel, vessel == selected_vessel, environment)

        # Hover popup is an AIS aid — unavailable when fog hides the target.
        if hover_vessel is not None and _fog_origin is None:
            self._draw_hover_popup(hover_vessel)

    def _draw_hover_popup(self, vessel) -> None:
        """Draw a small AIS tooltip near the mouse cursor for the hovered vessel."""
        mx, my = pygame.mouse.get_pos()

        status_str = getattr(vessel, "mission_status", "") or vessel.status.upper()
        line1 = self.font_label.render(vessel.name, True, (255, 255, 255))
        line2 = self.font_mono.render(
            f"{vessel.vessel_type.capitalize()} | {status_str}", True, (190, 205, 220))
        line3 = self.font_mono.render(
            f"Speed {vessel.current_speed:.1f} kn | Hdg {vessel.heading:.0f}°",
            True, (190, 205, 220))

        pad = 8
        gap = 3
        w = max(line1.get_width(), line2.get_width(), line3.get_width()) + pad * 2
        h = line1.get_height() + line2.get_height() + line3.get_height() + gap * 2 + pad * 2

        vw, vh = self.surface.get_size()
        ox, oy = 14, 14
        px = mx + ox if mx + ox + w <= vw else mx - w - ox
        py = my + oy if my + oy + h <= vh else my - h - oy

        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(bg, (10, 22, 38, 215), bg.get_rect(), border_radius=6)
        pygame.draw.rect(bg, (70, 110, 150, 180), bg.get_rect(), width=1, border_radius=6)
        self.surface.blit(bg, (px, py))

        cy = py + pad
        self.surface.blit(line1, (px + pad, cy));  cy += line1.get_height() + gap
        self.surface.blit(line2, (px + pad, cy));  cy += line2.get_height() + gap
        self.surface.blit(line3, (px + pad, cy))

    def _draw_vessel_trail(self, vessel, selected: bool) -> None:
        """Draw a fading dotted track of the vessel's recent path.

        The selected vessel uses radius-2 dots and a higher peak alpha so its
        track stands out clearly from background traffic.  Unselected vessels
        get radius-1 at lower brightness so they don't clutter the chart.
        """
        if not vessel.trail:
            return

        r, g, b = self._vessel_color(vessel)
        n = len(vessel.trail)
        peak_alpha = 130 if selected else 52
        radius     = 2   if selected else 1

        # Pre-compute world-space viewport bounds for a fast visibility cull.
        zoom = self.camera.zoom
        vw   = self.surface.get_width()
        vh   = self.surface.get_height()
        cam_x, cam_y = self.camera.position
        half_w = vw / (2.0 * zoom)
        half_h = vh / (2.0 * zoom)
        wx_min = cam_x - half_w
        wx_max = cam_x + half_w
        wy_min = cam_y - half_h
        wy_max = cam_y + half_h

        for i, (wx, wy) in enumerate(vessel.trail):
            # World-space cull: skip points outside the viewport entirely.
            if not (wx_min <= wx <= wx_max and wy_min <= wy <= wy_max):
                continue

            # Linear alpha ramp: oldest points nearly invisible, newest boldest.
            frac  = (i + 1) / n          # 0 → 1 from oldest to newest
            alpha = max(5, int(peak_alpha * frac))

            sx, sy = self.camera.world_to_screen((wx, wy))
            pygame.gfxdraw.filled_circle(
                self.surface, int(sx), int(sy), radius, (r, g, b, alpha)
            )

    def _vessel_color(self, vessel) -> Tuple[int, int, int]:
        if vessel.status == "avoiding":
            return COLOR_COLLISION_AVOID   # amber — vessel actively executing COLREGS manoeuvre
        if vessel.status == "docked":
            return COLOR_VESSEL_DOCKED
        if vessel.status in ("aground", "warning"):
            return COLOR_WARNING
        return COLOR_VESSEL_DEFAULT

    def _draw_dashed_line(
        self,
        start_pos: Position,
        end_pos: Position,
        color: Tuple[int, int, int],
        dash_length: float = 8.0,
        gap_length: float = 6.0,
    ) -> None:
        dx = end_pos[0] - start_pos[0]
        dy = end_pos[1] - start_pos[1]
        distance = math.hypot(dx, dy)
        if distance < 1.0:
            return

        direction = (dx / distance, dy / distance)
        traveled = 0.0
        while traveled < distance:
            segment_end = min(traveled + dash_length, distance)
            start = (
                start_pos[0] + direction[0] * traveled,
                start_pos[1] + direction[1] * traveled,
            )
            end = (
                start_pos[0] + direction[0] * segment_end,
                start_pos[1] + direction[1] * segment_end,
            )
            pygame.draw.line(self.surface, color, start, end, 1)
            traveled += dash_length + gap_length

    def _clip_line_to_surface(
        self,
        start_pos: Position,
        end_pos: Position,
    ) -> Optional[Tuple[Position, Position]]:
        rect = self.surface.get_rect()
        clipped = rect.clipline(
            (int(start_pos[0]), int(start_pos[1])),
            (int(end_pos[0]), int(end_pos[1])),
        )
        if not clipped:
            return None

        if len(clipped) == 4:
            x1, y1, x2, y2 = clipped
        else:
            (x1, y1), (x2, y2) = clipped

        return ((float(x1), float(y1)), (float(x2), float(y2)))

    def draw_vessel(self, vessel, selected: bool = False, environment=None) -> None:
        _is_player = getattr(vessel, 'is_player', False)
        screen_x, screen_y = self.camera.world_to_screen(vessel.position)
        size = max(6, min(int(8 * self.camera.zoom), 18))
        if _is_player:
            size = max(8, min(int(size * 1.4), 26))
        color = self._vessel_color(vessel)
        # Type-based tint when vessel has no special status override.
        if color == COLOR_VESSEL_DEFAULT:
            color = _VESSEL_TYPE_COLORS.get(vessel.vessel_type, COLOR_VESSEL_DEFAULT)
            # Per-vessel color_override replaces the type-based tint.
            if getattr(vessel, 'color_override', None) is not None:
                color = vessel.color_override
        # Player vessel always uses ACCENT unless aground/distress
        if _is_player and vessel.status not in ("aground",) and not vessel.distress:
            color = COLOR_ACCENT
        # Selected vessel: override to white so it stands out regardless of type.
        elif selected and vessel.status not in ("avoiding", "aground") and not vessel.distress:
            color = VESSEL_COLOR_SELECTED

        # Sailboat in-irons: stalled in the no-go zone — override colour before draw
        in_irons = (
            vessel.fuel is None
            and environment is not None
            and vessel.status == "underway"
            and vessel._effective_wind_speed(environment) < SAIL_IRONS_DISPLAY_THRESHOLD
        )
        if in_irons:
            color = COLOR_WARNING

        # ── Player vessel pulsing ring ────────────────────────────────────────
        # Distinct ACCENT-colored pulse so the player ship is immediately obvious.
        # Drawn before SAR ring so SAR overlays on top when player is in distress.
        if _is_player and not vessel.distress:
            p_base_r = size + 8
            p_phase  = (time.time() % PLAYER_PULSE_PERIOD) / PLAYER_PULSE_PERIOD
            p_pulse  = abs(math.sin(p_phase * math.pi))
            p_outer  = int(p_base_r + p_pulse * 10)
            ca, cb, cc = COLOR_ACCENT
            pygame.gfxdraw.aacircle(
                self.surface, int(screen_x), int(screen_y), p_base_r,
                (ca, cb, cc, 180))
            pygame.gfxdraw.aacircle(
                self.surface, int(screen_x), int(screen_y), p_outer,
                (ca, cb, cc, int(120 * p_pulse)))

        # ── SAR distress pulse ────────────────────────────────────────────────
        # Two concentric rings: a fixed inner ring and an outer ring that
        # expands/fades on each pulse cycle.  Drawn before the hull polygon so
        # the hull sits cleanly on top.
        if vessel.distress:
            base_r = size + 6
            phase = (time.time() % SAR_PULSE_PERIOD) / SAR_PULSE_PERIOD
            pulse_t = abs(math.sin(phase * math.pi))   # 0 → 1 → 0 per cycle
            outer_r = int(base_r + pulse_t * 12)
            dr, dg, db = COLOR_SAR_DISTRESS
            pygame.gfxdraw.aacircle(
                self.surface, int(screen_x), int(screen_y), base_r,
                (dr, dg, db, 220))
            pygame.gfxdraw.aacircle(
                self.surface, int(screen_x), int(screen_y), outer_r,
                (dr, dg, db, int(160 * pulse_t)))

        # ── Player autopilot route ────────────────────────────────────────────
        # Dashed track from the player to the right-click waypoint, with a
        # diamond marker at the destination.  Drawn before the hull polygon.
        _ap = getattr(vessel, 'autopilot_destination', None)
        if _is_player and _ap is not None:
            ap_screen = self.camera.world_to_screen(_ap)
            self._draw_dashed_line((screen_x, screen_y), ap_screen, COLOR_ACCENT,
                                   dash_length=8.0, gap_length=5.0)
            adx, ady = int(ap_screen[0]), int(ap_screen[1])
            s = AUTOPILOT_MARKER_SIZE_PX
            diamond = [(adx, ady - s), (adx + s, ady), (adx, ady + s), (adx - s, ady)]
            pygame.gfxdraw.filled_polygon(self.surface, diamond, (*COLOR_ACCENT, 90))
            pygame.gfxdraw.aapolygon(self.surface, diamond, COLOR_ACCENT)

        # ── Player-command route line ─────────────────────────────────────────
        # Drawn before the icon so the hull naturally covers the line's origin.
        if selected and vessel.player_commanded and vessel.destination:
            dest_screen = self.camera.world_to_screen(vessel.destination)
            self._draw_dashed_line(
                (screen_x, screen_y), dest_screen, COLOR_ACCENT,
                dash_length=8.0, gap_length=5.0,
            )

        # ── Hull triangle (AIS-style) ─────────────────────────────────────────
        # Triangle points UP (bow = −y); rotated to heading via heading+90.
        hull_local = _vessel_hull_points(vessel.vessel_type, size)
        hull_screen = _rotate_points(hull_local, vessel.heading + 90.0, screen_x, screen_y)
        hull_int = [(int(x), int(y)) for x, y in hull_screen]
        r, g, b = color[0], color[1], color[2]
        if len(hull_int) >= 3:
            # Semi-transparent fill so chart features show through
            pygame.gfxdraw.filled_polygon(self.surface, hull_int, (r, g, b, 160))
            # Crisp solid outline on top
            pygame.gfxdraw.aapolygon(self.surface, hull_int, (r, g, b, 255))

        # ── Vessel label ──────────────────────────────────────────────────────
        name_label = self.font_map.render(vessel.name, True, COLOR_TEXT_PRIMARY)
        # Player vessel: priority 200 — always drawn regardless of zoom threshold.
        prio = 200 if _is_player else (100 if selected else 30)
        self._queue_label(name_label, int(screen_x - name_label.get_width() / 2),
                          int(screen_y + SHIP_LABEL_OFFSET), priority=prio,
                          anchor_pos=(screen_x, screen_y))

        # ── Range rings: always shown for player, else only when selected ─────
        if selected or _is_player:
            ring_color = COLOR_ACCENT if _is_player else COLOR_VESSEL_RANGE
            for ring_index in range(1, SHIP_RANGE_RING_COUNT + 1):
                radius = int(self.camera.distance_to_screen(
                    ring_index * SHIP_RANGE_RING_INTERVAL_NM))
                if radius <= 0:
                    continue
                pygame.gfxdraw.aacircle(
                    self.surface, int(screen_x), int(screen_y), radius, ring_color)
                label = self.font_mono.render(
                    f"{ring_index * SHIP_RANGE_RING_INTERVAL_NM:g} nm",
                    True, COLOR_TEXT_SECONDARY)
                label_x = int(screen_x - label.get_width() / 2)
                label_y = int(screen_y - radius - label.get_height() - 6)
                self._queue_label(label, label_x, label_y, priority=70,
                                  anchor_pos=(screen_x, screen_y))

        # ── Selection indicators ──────────────────────────────────────────────
        if selected:
            # Selection ring: hull extends `size` from centre to bow tip.
            sel_r = size + 4
            pygame.gfxdraw.aacircle(
                self.surface, int(screen_x), int(screen_y), sel_r, COLOR_VESSEL_RANGE)

            if in_irons:
                irons_lbl = self.font_small.render("IN IRONS", True, COLOR_WARNING)
                self._queue_label(
                    irons_lbl,
                    int(screen_x - irons_lbl.get_width() / 2),
                    int(screen_y - SHIP_LABEL_OFFSET * 2 - irons_lbl.get_height()),
                    priority=110,
                    anchor_pos=(screen_x, screen_y),
                )

    def draw_current_arrows(self, environment) -> None:
        """Draw a sparse field of directional arrows indicating current set-and-drift.

        Arrows are positioned on a world-space grid so they scroll naturally with
        the chart.  Size scales with current speed; alpha is deliberately very low
        so they read as a chart annotation rather than a dominant symbol.
        """
        if environment.current_speed < 0.05:
            return

        vw = self.surface.get_width()
        vh = self.surface.get_height()
        cam_x, cam_y = self.camera.position
        zoom = self.camera.zoom

        # World-space grid spacing converts the screen pixel interval to world units
        world_spacing = CURRENT_ARROW_SPACING_PX / zoom

        world_left   = cam_x - vw / (2 * zoom)
        world_right  = cam_x + vw / (2 * zoom)
        world_top    = cam_y - vh / (2 * zoom)
        world_bottom = cam_y + vh / (2 * zoom)

        # Snap grid origin so arrows don't bunch at the viewport edge
        start_wx = math.ceil(world_left  / world_spacing) * world_spacing
        start_wy = math.ceil(world_top   / world_spacing) * world_spacing

        # Arrow geometry in screen pixels; scale length with current speed
        arrow_len = CURRENT_ARROW_SIZE * min(2.5, environment.current_speed / 1.0)
        head_sz = max(3.0, arrow_len * 0.32)

        cur_rad = math.radians(environment.current_direction)
        cos_c = math.cos(cur_rad)
        sin_c = math.sin(cur_rad)
        # Perpendicular unit vector (for arrowhead arms)
        perp_x = -sin_c
        perp_y =  cos_c

        arrow_col = (*COLOR_CURRENT_ARROW, CURRENT_ARROW_ALPHA)
        surf = self._get_alpha_surf()
        surf.fill((0, 0, 0, 0))

        wx = start_wx
        while wx <= world_right:
            wy = start_wy
            while wy <= world_bottom:
                sx, sy = self.camera.world_to_screen((wx, wy))

                # Shaft: tail 40% behind centre, head 60% ahead (offset so the
                # visual centroid sits on the grid point)
                tail_x = sx - cos_c * arrow_len * 0.4
                tail_y = sy - sin_c * arrow_len * 0.4
                head_x = sx + cos_c * arrow_len * 0.6
                head_y = sy + sin_c * arrow_len * 0.6

                pygame.draw.line(surf, arrow_col,
                                 (int(tail_x), int(tail_y)),
                                 (int(head_x), int(head_y)), 1)

                # Chevron arrowhead — two arms fanning back from the tip
                pygame.draw.line(surf, arrow_col,
                    (int(head_x), int(head_y)),
                    (int(head_x + (-cos_c + perp_x) * head_sz),
                     int(head_y + (-sin_c + perp_y) * head_sz)), 1)
                pygame.draw.line(surf, arrow_col,
                    (int(head_x), int(head_y)),
                    (int(head_x + (-cos_c - perp_x) * head_sz),
                     int(head_y + (-sin_c - perp_y) * head_sz)), 1)

                wy += world_spacing
            wx += world_spacing

        self.surface.blit(surf, (0, 0))

    def draw_screen_vignette(self) -> None:
        """Subtle dark gradient at the screen edges — a cinematic frame.

        Built once per window size as concentric 1-ring border rects whose
        alpha falls off toward the centre; per-frame cost is a single blit.
        """
        vw, vh = self.surface.get_size()
        if (self._vignette_surf is None
                or self._vignette_surf.get_size() != (vw, vh)):
            surf = pygame.Surface((vw, vh), pygame.SRCALPHA)
            step_px = max(1, SCREEN_VIGNETTE_DEPTH_PX // SCREEN_VIGNETTE_STEPS)
            for i in range(SCREEN_VIGNETTE_STEPS):
                alpha = int(SCREEN_VIGNETTE_MAX_ALPHA
                            * (1.0 - i / SCREEN_VIGNETTE_STEPS))
                if alpha <= 0:
                    break
                inset = i * step_px
                pygame.draw.rect(surf, (0, 0, 0, alpha),
                                 (inset, inset, vw - inset * 2, vh - inset * 2),
                                 width=step_px)
            self._vignette_surf = surf
        self.surface.blit(self._vignette_surf, (0, 0))

    def draw_compass_rose(self) -> None:
        center_x = COMPASS_OFFSET_X
        center_y = COMPASS_OFFSET_Y
        radius = COMPASS_SIZE // 2
        pygame.gfxdraw.aacircle(self.surface, center_x, center_y, radius, COLOR_NORTH_ARROW)
        pygame.gfxdraw.filled_circle(self.surface, center_x, center_y, radius - 1, COLOR_CHART_BAR_BG)

        ray_length = radius - 6
        end_x = center_x
        end_y = center_y - ray_length
        pygame.draw.aaline(self.surface, COLOR_NORTH_ARROW, (center_x, center_y), (end_x, end_y))
        _arrow = [
            (end_x, end_y - 6),
            (end_x - 4, end_y + 4),
            (end_x + 4, end_y + 4),
        ]
        pygame.gfxdraw.filled_polygon(self.surface, _arrow, COLOR_NORTH_ARROW)
        pygame.gfxdraw.aapolygon(self.surface, _arrow, COLOR_NORTH_ARROW)

        for direction, label in [((0, -radius + 4), "N"), ((radius - 4, 0), "E"), ((0, radius - 4), "S"), ((-radius + 4, 0), "W")]:
            dx, dy = direction
            pygame.draw.aaline(self.surface, COLOR_NORTH_ARROW, (center_x, center_y), (center_x + dx, center_y + dy))
            text = self.font_small.render(label, True, COLOR_NORTH_ARROW)
            self._blit_text_shadow(text, center_x + dx - text.get_width() / 2, center_y + dy - text.get_height() / 2)

    def draw_scale_bar(self) -> None:
        start_x = SCALE_BAR_OFFSET_X
        start_y = SCALE_BAR_OFFSET_Y
        candidates = [0.5, 1, 2, 5, 10, 20, 50]
        target_pixels = SCALE_BAR_TARGET_WIDTH
        best_distance = candidates[0]
        best_score = float("inf")

        for distance in candidates:
            pixel_length = self.camera.distance_to_screen(distance)
            if pixel_length > SCALE_BAR_MAX_WIDTH:
                break
            score = abs(pixel_length - target_pixels)
            if score < best_score:
                best_score = score
                best_distance = distance

        world_distance = best_distance
        pixel_length = int(_clamp(self.camera.distance_to_screen(world_distance), 40, SCALE_BAR_MAX_WIDTH))
        bar_top = start_y
        bar_bottom = start_y + SCALE_BAR_HEIGHT
        pygame.draw.rect(self.surface, COLOR_SCALE_BAR, (start_x, bar_top, pixel_length, SCALE_BAR_HEIGHT))
        pygame.draw.line(self.surface, COLOR_TEXT_PRIMARY, (start_x, bar_top), (start_x, bar_bottom), 1)
        pygame.draw.line(self.surface, COLOR_TEXT_PRIMARY, (start_x + pixel_length, bar_top), (start_x + pixel_length, bar_bottom), 1)
        pygame.draw.line(self.surface, COLOR_TEXT_PRIMARY, (start_x + pixel_length // 2, bar_top), (start_x + pixel_length // 2, bar_bottom), 1)
        label = self.font_mono.render(f"{world_distance:g} nm", True, COLOR_TEXT_PRIMARY)
        self._blit_text_shadow(label, start_x, bar_bottom + 6)

    def draw_status_bar(self, environment, selected_vessel) -> None:
        bar_height = 40
        bar_rect = pygame.Rect(0, 0, self.surface.get_width(), bar_height)
        pygame.draw.rect(self.surface, (*COLOR_CHART_BAR_BG, 220), bar_rect)
        pygame.draw.line(self.surface, COLOR_FRAME, bar_rect.bottomleft, bar_rect.bottomright, 1)

        time_text = f"{int(environment.time_of_day):02d}:{int((environment.time_of_day % 1) * 60):02d}"
        # Compass bearing ("NE", "SSW") reads faster than raw degrees.
        _dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                 "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        _card = _dirs[round(environment.wind_direction / 22.5) % 16]
        wind_text = f"Wind {environment.wind_speed:.1f} kn {_card}"
        # Use the environment's visibility formatter so status bar and panels match.
        try:
            vis_display = environment.get_visibility_display()
        except Exception:
            vis_display = f"{int(environment.visibility)} m"
        vis_text = f"Vis {vis_display}"
        speed_text = "PAUSED" if environment.time_speed_multiplier == 0 else f"Speed {environment.time_speed_multiplier:.0f}x"

        left_text = self.font_mono.render(time_text, True, COLOR_TEXT_SECONDARY)
        event = environment.active_event_name()
        mid_str = f"{wind_text} | {vis_text}" + (f" | {event.upper()}" if event else "")
        mid_text = self.font_mono.render(mid_str, True, COLOR_TEXT_PRIMARY)
        right_text = self.font_mono.render(speed_text, True, COLOR_ACCENT)

        padding = 18
        self._blit_text_shadow(left_text, padding, 10)
        self._blit_text_shadow(mid_text, self.surface.get_width() // 2 - mid_text.get_width() // 2, 10)
        self._blit_text_shadow(right_text, self.surface.get_width() - right_text.get_width() - padding, 10)

    def _blit_text_shadow(self, text_surface: pygame.Surface, x: int, y: int) -> None:
        shadow = text_surface.copy()
        shadow.fill((0, 0, 0), None, pygame.BLEND_RGBA_MULT)
        self.surface.blit(shadow, (x + 1, y + 1))
        self.surface.blit(text_surface, (x, y))

    def _queue_label(
        self,
        label_surface: pygame.Surface,
        x: int,
        y: int,
        priority: int,
        anchor_pos: Position,
    ) -> None:
        # Priority ≥ 200: always shown (player vessel label, regardless of zoom).
        # Priority ≥ 80: shown at any zoom (ports, selected vessel).
        # Priority < 80: only shown above LABEL_ZOOM_THRESHOLD_SHOW_ALL.
        if priority < 200 and self.camera.zoom < LABEL_ZOOM_THRESHOLD_SHOW_ALL and priority < 80:
            return

        label_rect = pygame.Rect(
            x - 4,
            y - 4,
            label_surface.get_width() + 8,
            label_surface.get_height() + 8,
        )

        # Skip labels whose anchor is entirely off-screen; clamp partially-visible
        # ones inward so text never bleeds past the viewport edge.
        vw, vh = self.surface.get_width(), self.surface.get_height()
        if (label_rect.right < 0 or label_rect.left > vw
                or label_rect.bottom < 0 or label_rect.top > vh):
            return
        label_rect.x = max(0, min(vw - label_rect.width, label_rect.x))
        label_rect.y = max(0, min(vh - label_rect.height, label_rect.y))
        x = label_rect.x + 4
        y = label_rect.y + 4

        self._label_candidates.append({
            "surface": label_surface,
            "x": x,
            "y": y,
            "rect": label_rect,
            "priority": priority,
            "anchor": anchor_pos,
        })

    def _draw_label_pill(self, label_rect: pygame.Rect) -> None:
        pill_surface = pygame.Surface(label_rect.size, pygame.SRCALPHA)
        pill_color = (*COLOR_CHART_BAR_BG, 220)
        border_color = (*COLOR_TEXT_PRIMARY, 40)
        pygame.draw.rect(pill_surface, pill_color, pill_surface.get_rect(), border_radius=8)
        pygame.draw.rect(pill_surface, border_color, pill_surface.get_rect(), width=1, border_radius=8)
        self.surface.blit(pill_surface, label_rect.topleft)

    def _draw_label_leader(self, anchor_pos: Position, label_rect: pygame.Rect) -> None:
        anchor_x, anchor_y = anchor_pos
        nearest_x = _clamp(anchor_x, label_rect.left, label_rect.right)
        nearest_y = _clamp(anchor_y, label_rect.top, label_rect.bottom)
        if label_rect.collidepoint(anchor_x, anchor_y):
            return
        pygame.draw.aaline(
            self.surface,
            COLOR_TEXT_SECONDARY,
            anchor_pos,
            (nearest_x, nearest_y),
        )

    def _resolve_and_draw_labels(self) -> None:
        if not self._label_candidates:
            return

        self._label_candidates.sort(key=lambda candidate: candidate["priority"], reverse=True)
        placed_rects = []

        for candidate in self._label_candidates:
            label_rect = candidate["rect"]
            if any(label_rect.colliderect(existing) for existing in placed_rects):
                continue

            self._draw_label_pill(label_rect)
            self._blit_text_shadow(candidate["surface"], candidate["x"], candidate["y"])
            self._draw_label_leader(candidate["anchor"], label_rect)
            placed_rects.append(label_rect)

        self._label_candidates.clear()

    def draw_weather_effects(self, environment) -> None:
        """Atmospheric overlays: fog, rain/storm streaks, and night stars.

        Called after all chart elements so effects sit on top of everything.
        Uses _get_alpha_surf() for transparency — same pattern as draw_islands().
        Uses a private _rng.Random instance so sim RNG state is never affected.
        """
        vw, vh = self.surface.get_size()
        event = environment.active_event_name()

        # ── (A) Fog overlay ──────────────────────────────────────────────────
        # Pale blue-grey haze: alpha=0 at vis=200, alpha=160 at vis=10.
        # Color (200, 210, 220) reads as real sea fog — grey-white, not darkness.
        if environment.visibility < 200:
            fog_alpha = max(0, min(160, int(160 * (200 - environment.visibility) / 190)))
            if fog_alpha > 0:
                s = self._get_alpha_surf()
                s.fill((200, 210, 220, fog_alpha))
                self.surface.blit(s, (0, 0))

        # ── (B) Rain streaks during squall / storm ───────────────────────────
        # Skip when heavy fog is already obscuring everything.
        elif event in ("squall", "storm"):
            rain_surf = self._get_alpha_surf()
            rain_surf.fill((0, 0, 0, 0))
            # Seed updates 8× per second for a shimmer without being distracting.
            r = _rng.Random(int(time.time() * 8) % 1000)
            for _ in range(80):
                x = r.randint(0, max(1, vw - 6))
                y = r.randint(0, max(1, vh - 10))
                pygame.draw.line(rain_surf, (200, 210, 220, 60),
                                 (x, y), (x + 4, y + 8), 1)
            self.surface.blit(rain_surf, (0, 0))

        # ── (B2) Storm seas: scrolling wave lines + grey-green cast ──────────
        # Keyed to wave_height (not the event) so the visual always agrees with
        # the player speed cap and hull-damage consequences in main.py.
        if environment.wave_height > STORM_WAVE_THRESHOLD:
            s = self._get_alpha_surf()
            s.fill((*STORM_TINT_COLOR, STORM_TINT_ALPHA))
            offset = int(time.time() * STORM_WAVE_SCROLL_PX_S) % STORM_WAVE_LINE_SPACING_PX
            for y in range(offset, vh, STORM_WAVE_LINE_SPACING_PX):
                pygame.draw.line(s, (*STORM_WAVE_LINE_COLOR, STORM_WAVE_LINE_ALPHA),
                                 (0, y), (vw, y), 1)
            self.surface.blit(s, (0, 0))

        # ── (B3) Squall lightning: brief white flash on event onset ──────────
        if event == "squall" and self._last_weather_event != "squall":
            self._squall_flash_until = time.time() + SQUALL_FLASH_DURATION_S
        self._last_weather_event = event
        if time.time() < self._squall_flash_until:
            s = self._get_alpha_surf()
            s.fill((255, 255, 255, SQUALL_FLASH_ALPHA))
            self.surface.blit(s, (0, 0))

        # ── (C) Star field during deep night when zoomed out ─────────────────
        # Fixed seed → no flicker; dots are painted directly on the surface.
        tod = environment.time_of_day
        if (tod >= 20.0 or tod <= 4.0) and self.camera.zoom < 1.5:
            r = _rng.Random(42)
            for _ in range(40):
                sx = r.randint(10, max(11, vw - 10))
                sy = r.randint(50, max(51, vh - 60))  # below status bar
                pygame.gfxdraw.filled_circle(
                    self.surface, sx, sy, 1, (210, 215, 230, 110))

    def draw_all(self, world=None, environment=None, selected_vessel=None,
                 hover_vessel=None) -> None:
        self._label_candidates = []
        self.draw_background(world)
        # Open-ocean vignette sits directly on the water fill, before everything else
        self.draw_ocean_vignette()
        # Coastal depth layer (mid-depth + shallow bands) — cached; land fill drawn
        # later in draw_islands() covers the interior of each offset polygon.
        if world:
            self.surface.blit(self._build_depth_layer(world), (0, 0))
        # Depth zone fills (before islands so land polygons cover the inward part)
        if world and environment:
            self.draw_depth_zones(world, environment)
        self.draw_grid()
        # Shipping lane overlay — below islands and zones, just above the grid
        self.draw_shipping_lanes(world)
        # Depth contour lines (before islands so land naturally covers any coastal overhang)
        if world and environment:
            self.draw_depth_contours(world, environment)
        self.draw_islands(world)
        # Depth soundings — small depth numbers on water, after land so they read clearly
        if world and environment:
            self.draw_depth_soundings(world, environment)
        self.draw_zones(world)
        # Current arrows drawn after zones so they sit above the chart base but
        # below port symbols, nav marks, and vessels.
        if environment:
            self.draw_current_arrows(environment)
        self.draw_ports(world)
        self.draw_nav_marks(world)
        self.draw_vessels(world, selected_vessel, environment, hover_vessel)
        self._resolve_and_draw_labels()
        self.draw_scale_bar()
        self.draw_compass_rose()

        # Apply day/night tint over ALL chart content (water, land, labels,
        # compass) so the whole scene shifts at night — not just the water.
        # Applied here, after chart drawing but before the HUD status bar,
        # so the bar stays at full brightness.
        if environment:
            tint = environment.day_night_tint()
            if tint[3] > 0:
                s = self._get_alpha_surf()
                s.fill(tint)
                self.surface.blit(s, (0, 0))

        # Weather visuals drawn after night tint so fog/rain sit on top of everything
        if environment:
            self.draw_weather_effects(environment)

        # Edge vignette frames the whole scene, under the status bar only.
        self.draw_screen_vignette()

        if environment:
            self.draw_status_bar(environment, selected_vessel)
