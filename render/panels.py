"""UI Panels for the maritime simulator: vessel info, technical systems, settings.

These panels display and interact with simulation state. They read from the
world/environment/vessel state each frame and draw live, responsive UI.
"""

import time
import math as _math
import pygame
from typing import Optional, Tuple, Dict
from math import atan2, degrees

import math
from render.chart import _vessel_hull_points, _rotate_points
from config import (
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM, COLOR_WARNING,
    COLOR_PANEL_BG, COLOR_PANEL_BORDER, COLOR_ACCENT, COLOR_FRAME,
    FONT_UI_NAME, FONT_DATA_NAME, FONT_SIZE_TITLE, FONT_SIZE_SECTION,
    FONT_SIZE_LABEL, FONT_SIZE_DATA, FONT_SIZE_BIG, FONT_SIZE_SMALL,
    DRAFT_SAFETY_MARGIN_M, COLOR_EVENT_REFLOATED, COLOR_COLLISION_AVOID,
    COLOR_EVENT_MEDICAL,
    VESSEL_COLOR_CARGO, VESSEL_COLOR_TANKER, VESSEL_COLOR_FERRY,
    VESSEL_COLOR_FISHING, VESSEL_COLOR_SAILBOAT, VESSEL_COLOR_TUG,
    VESSEL_COLOR_COAST_GUARD, VESSEL_COLOR_TENDER,
    KNOTS_TO_UNITS_PER_HOUR, NM_PER_WORLD_UNIT,
    AIS_CPA_WARNING_NM, AIS_NEARBY_MAX,
    PLAYER_THROTTLE_STEP,
    HULL_REPAIR_COST_PER_POINT, FUEL_COST_PER_UNIT,
    STORM_WAVE_THRESHOLD,
    HULL_BAR_HIGH_COLOR, HULL_BAR_MID_COLOR, HULL_BAR_LOW_COLOR,
    GAME_VERSION,
    TITLE_FONT_SIZE, TITLE_SUBTITLE_SIZE, TITLE_MENU_FONT_SIZE,
    TITLE_PANEL_WIDTH, TITLE_PANEL_HEIGHT, TITLE_PANEL_ALPHA,
    MINIMAP_WIDTH_PX, MINIMAP_HEIGHT_PX, MINIMAP_MARGIN_PX,
    WORLD_WIDTH, WORLD_HEIGHT, LAND_COLORS, COLOR_WATER,
)


# AIS vessel-type colour map — same convention as chart.py _VESSEL_TYPE_COLORS.
_AIS_TYPE_COLORS: dict = {
    "cargo":       VESSEL_COLOR_CARGO,
    "tanker":      VESSEL_COLOR_TANKER,
    "ferry":       VESSEL_COLOR_FERRY,
    "fishing":     VESSEL_COLOR_FISHING,
    "sailboat":    VESSEL_COLOR_SAILBOAT,
    "tug":         VESSEL_COLOR_TUG,
    "coast_guard": VESSEL_COLOR_COAST_GUARD,
    "tender":      VESSEL_COLOR_TENDER,
}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _truncate_text(text: str, font: pygame.font.Font, max_width: int) -> str:
    if font.size(text)[0] <= max_width:
        return text

    ellipsis = "…"
    available = max_width - font.size(ellipsis)[0]
    if available <= 0:
        return ellipsis

    truncated = text
    while truncated and font.size(truncated)[0] > available:
        truncated = truncated[:-1]
    return truncated + ellipsis


def _format_duration(hours: float) -> str:
    total_minutes = int(round(max(0.0, hours) * 60))
    if total_minutes <= 0:
        return "0m"

    hours_part = total_minutes // 60
    minutes_part = total_minutes % 60
    if hours_part > 0:
        return f"{hours_part}h {minutes_part:02d}m" if minutes_part else f"{hours_part}h"
    return f"{minutes_part}m"


class VesselInfoPanel:
    def __init__(self, surface: pygame.Surface):
        self.surface = surface
        self.font_title = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_TITLE, bold=True)
        self.font_header = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_SECTION, bold=True)
        self.font_label = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_LABEL)
        self.font_value = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_DATA, bold=True)
        self.font_big = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_BIG, bold=True)
        self.font_small = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_SMALL)
        self.font_log   = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_SMALL)
        self.width = 360
        self.height = 420

    def _required_panel_height(self, vessel) -> int:
        """Compute the pixel height needed to fit all rows for this vessel.

        Mirrors the exact current_y increments in draw() so the background
        rect is always tall enough, regardless of vessel type or destination.
        """
        h = 18  # top padding
        h += self.font_title.get_height() + 12  # vessel name + gap
        h += 16   # divider gap
        h += 26   # Type row
        h += 32   # Status row
        h += 24 + 22 + 22 + 30   # Dimensions: header + LOA + Beam + (Draft + section gap)
        h += 24 + 22 + 22 + 22 + 30  # Navigation: header + 4 rows + section gap
        if vessel.destination:
            h += 24 + 22 + 30    # Nav Target: header + Distance + (ETA + section gap)
        h += 24  # Fuel/Propulsion header
        if vessel.fuel is not None:
            h += 26 + 32         # fuel label + bar row
        else:
            h += 26 + 26         # "Wind-powered" + "Wind Note" rows
        if vessel.status == "aground" and getattr(vessel, 'distress', False):
            h += 24 + 22 + 22 + 22 + 18  # DISTRESS header + 4 rows + gap
        log = getattr(vessel, 'captain_log', [])
        if log:
            _has_mood_line = bool(getattr(vessel, 'personality', '') or getattr(vessel, 'mood', ''))
            h += 16 + 24 + (18 if _has_mood_line else 0) + min(5, len(log)) * 18
        h += 18  # bottom padding
        return h

    def draw(self, vessel: Optional[object], environment: Optional[object], world: Optional[object] = None) -> None:
        # No selection → no panel.  The fleet list and Tab already advertise
        # how to select a vessel; an empty placeholder just blocks the chart.
        if vessel is None:
            return

        panel_margin = 20
        panel_width = min(360, max(280, self.surface.get_width() - panel_margin * 2))
        panel_height = min(
            self._required_panel_height(vessel),
            self.surface.get_height() - panel_margin * 2,
        )
        x = self.surface.get_width() - panel_width - panel_margin
        y = panel_margin
        self._draw_panel_background(x, y, panel_width, panel_height)

        padding = 18
        current_y = y + padding
        title_text = self.font_title.render(vessel.name, True, COLOR_ACCENT)
        self.surface.blit(title_text, (x + padding, current_y))
        # [YOU] badge marks the player's own ship in the info panel.
        if getattr(vessel, 'is_player', False):
            you_surf = self.font_small.render("[YOU]", True, (60, 220, 120))
            self.surface.blit(you_surf,
                              (x + padding + title_text.get_width() + 8,
                               current_y + (title_text.get_height() - you_surf.get_height()) // 2))
        current_y += title_text.get_height() + 12

        self._draw_divider(x, current_y, panel_width)
        current_y += 16

        self._draw_label_value(x, current_y, panel_width, "Type", vessel.vessel_type.capitalize())
        # Small hull silhouette on the same row, pointing right (east, heading=0).
        _inner_margin = 20
        _val_w = self.font_value.size(vessel.vessel_type.capitalize())[0]
        _ico_cx = x + (panel_width - _inner_margin) - _val_w - 4 - 12
        _ico_cy = current_y + 12
        _hull_pts = _vessel_hull_points(vessel.vessel_type, 10)
        _hull_screen = _rotate_points(_hull_pts, 90.0, _ico_cx, _ico_cy)
        _hull_int = [(int(px), int(py)) for px, py in _hull_screen]
        if len(_hull_int) >= 3:
            pygame.draw.polygon(self.surface, COLOR_TEXT_SECONDARY, _hull_int)
        current_y += 26
        # Show mission_status when available (e.g. "TRAWLING", "BOARDING"), else status
        _status_display = getattr(vessel, 'mission_status', '') or vessel.status.upper()
        self._draw_label_value(x, current_y, panel_width, "Status", _status_display)
        current_y += 32

        self._draw_section_header(x, current_y, "Dimensions")
        current_y += 24
        self._draw_label_value(x, current_y, panel_width, "LOA", f"{vessel.length_m:.1f} m")
        current_y += 22
        self._draw_label_value(x, current_y, panel_width, "Beam", f"{vessel.beam_m:.1f} m")
        current_y += 22
        self._draw_label_value(x, current_y, panel_width, "Draft", f"{vessel.draft_m:.1f} m")
        current_y += 30

        self._draw_section_header(x, current_y, "Navigation")
        current_y += 24
        self._draw_label_value(x, current_y, panel_width, "Heading", f"{vessel.heading:.0f}°")
        current_y += 22
        self._draw_label_value(x, current_y, panel_width, "Speed", f"{vessel.current_speed:.1f} kn")
        current_y += 22
        self._draw_label_value(x, current_y, panel_width, "Target", f"{vessel.target_speed:.1f} kn")
        current_y += 22
        self._draw_label_value(x, current_y, panel_width, "Max", f"{vessel.max_speed:.1f} kn")
        current_y += 30

        if vessel.destination:
            dist_nm = vessel.distance_to(vessel.destination) * NM_PER_WORLD_UNIT
            eta_text = "—"
            if vessel.current_speed > 0.1:
                eta_text = _format_duration(dist_nm / vessel.current_speed)
            self._draw_section_header(x, current_y, "Navigation Target")
            current_y += 24
            self._draw_label_value(x, current_y, panel_width, "Distance", f"{dist_nm:.1f} nm")
            current_y += 22
            self._draw_label_value(x, current_y, panel_width, "ETA", eta_text)
            current_y += 30

        self._draw_section_header(x, current_y, "Fuel / Propulsion")
        current_y += 24
        if vessel.fuel is not None:
            fuel_pct = (vessel.fuel / vessel.fuel_capacity) * 100 if vessel.fuel_capacity else 0
            fuel_color = COLOR_ACCENT if fuel_pct > 25 else COLOR_WARNING
            self._draw_label_value(x, current_y, panel_width, "Fuel", f"{vessel.fuel:.1f} / {vessel.fuel_capacity:.1f} L", value_color=fuel_color)
            current_y += 26
            self._draw_fuel_bar(x, current_y, fuel_pct, fuel_color, panel_width)
            current_y += 32
        else:
            self._draw_label_value(x, current_y, panel_width, "Propulsion", "Wind-powered", value_color=COLOR_ACCENT)
            current_y += 26
            self._draw_label_value(x, current_y, panel_width, "Wind Note", "Effective sail power", value_color=COLOR_TEXT_SECONDARY)
            current_y += 26

        # ── SAR distress section ──────────────────────────────────────────────
        if vessel.status == "aground" and getattr(vessel, 'distress', False):
            self._draw_section_header(x, current_y, "DISTRESS")
            current_y += 24

            hrs = int(vessel.distress_timer // 3600)
            mins = int((vessel.distress_timer % 3600) // 60)
            time_str = f"{hrs}h {mins:02d}m" if hrs else f"{mins}m"
            self._draw_label_value(x, current_y, panel_width,
                                   "Time aground", time_str, value_color=COLOR_WARNING)
            current_y += 22

            rescuer = getattr(vessel, 'rescue_vessel', None)
            rescue_name = rescuer.name if rescuer is not None else "None dispatched"
            rescue_color = COLOR_ACCENT if rescuer is not None else COLOR_TEXT_SECONDARY
            self._draw_label_value(x, current_y, panel_width,
                                   "Rescue vessel", rescue_name, value_color=rescue_color)
            current_y += 22

            if world is not None and environment is not None:
                try:
                    depth = world.water_depth_at(vessel.position, environment.tide_level)
                    req = vessel.draft_m + DRAFT_SAFETY_MARGIN_M
                    depth_color = COLOR_ACCENT if depth >= req else COLOR_WARNING
                    self._draw_label_value(x, current_y, panel_width,
                                           "Depth / Draft",
                                           f"{depth:.1f} m / {vessel.draft_m:.1f} m",
                                           value_color=depth_color)
                except Exception:
                    self._draw_label_value(x, current_y, panel_width, "Depth", "—")
            current_y += 22

        # ── Captain's log section ─────────────────────────────────────────────
        log = getattr(vessel, 'captain_log', [])
        if log:
            current_y += 16
            # Thinking indicator: header briefly turns amber after a new log entry.
            _last_dec = getattr(vessel, '_last_decision_time', 0.0)
            _thinking = time.time() - _last_dec < 0.5
            _hdr_col = (255, 200, 80) if _thinking else COLOR_ACCENT
            hdr_surf = self.font_header.render("CAPTAIN'S LOG", True, _hdr_col)
            self.surface.blit(hdr_surf, (x + 20, current_y))
            current_y += 24
            # Personality / mood sub-header
            _pers = getattr(vessel, 'personality', '').capitalize()
            _mood = getattr(vessel, 'mood', '').capitalize()
            if _pers or _mood:
                _pm = f"{_pers} · {_mood}" if (_pers and _mood) else (_pers or _mood)
                _pm_surf = self.font_small.render(_pm, True, COLOR_TEXT_SECONDARY)
                self.surface.blit(_pm_surf, (x + 20, current_y))
                current_y += 18
            inner_w = panel_width - 36
            for entry in log[-5:]:
                # Color-code entries by content: amber=hazard, green=positive, dim=normal
                _el = entry.lower()
                if any(kw in _el for kw in (
                        "aground", "mayday", "distress", "caution", "warning",
                        "reducing speed", "collision", "emergency", "fatigue", "long watch")):
                    _ec = (220, 165, 50)    # amber — hazard or alert
                elif any(kw in _el for kw in (
                        "clear", "refreshed", "confident", "favorable", "perfect",
                        "smooth", "rested", "refloated", "party on deck")):
                    _ec = (80, 200, 120)    # dim green — positive
                else:
                    _ec = COLOR_TEXT_DIM
                entry_surf = self.font_log.render(
                    _truncate_text(entry, self.font_log, inner_w), True, _ec,
                )
                self.surface.blit(entry_surf, (x + 20, current_y))
                current_y += 18

    def _draw_panel_background(self, x: int, y: int, width: int, height: int) -> None:
        pygame.draw.rect(self.surface, (*COLOR_PANEL_BG, 230), (x, y, width, height), border_radius=16)
        pygame.draw.rect(self.surface, COLOR_PANEL_BORDER, (x, y, width, height), 2, border_radius=16)

    def _draw_section_header(self, x: int, y: int, title: str) -> None:
        header = self.font_header.render(title, True, COLOR_ACCENT)
        self.surface.blit(header, (x + 20, y))

    def _draw_label_value(self, x: int, y: int, panel_width: int, label: str, value: str, value_color: tuple = COLOR_TEXT_PRIMARY) -> None:
        inner_margin = 20
        inner_width = panel_width - inner_margin * 2
        label_text = _truncate_text(label, self.font_label, inner_width)
        value_text = _truncate_text(value, self.font_value, inner_width)
        label_surf = self.font_label.render(label_text, True, COLOR_TEXT_SECONDARY)
        value_surf = self.font_value.render(value_text, True, value_color)
        self.surface.blit(label_surf, (x + inner_margin, y))
        self.surface.blit(value_surf, (x + inner_margin + inner_width - value_surf.get_width(), y - 2))

    def _draw_fuel_bar(self, x: int, y: int, percent: float, fill_color: tuple, panel_width: int) -> None:
        inner_margin = 20
        bar_w = panel_width - inner_margin * 2
        bar_h = 14
        bar_x = x + inner_margin
        pygame.draw.rect(self.surface, COLOR_FRAME, (bar_x, y, bar_w, bar_h), border_radius=6)
        fill_w = int(bar_w * percent / 100)
        pygame.draw.rect(self.surface, fill_color, (bar_x, y, fill_w, bar_h), border_radius=6)

    def _draw_divider(self, x: int, y: int, panel_width: int) -> None:
        inner_margin = 20
        pygame.draw.line(self.surface, COLOR_FRAME, (x + inner_margin, y), (x + panel_width - inner_margin, y), 1)


class TechnicalSystemsPanel:
    def __init__(self, surface: pygame.Surface):
        self.surface = surface
        self.font_title = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_TITLE, bold=True)
        self.font_header = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_SECTION, bold=True)
        self.font_label = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_LABEL)
        self.font_value = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_DATA)
        self.font_small = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_SMALL)
        self.is_visible = False

    def toggle_visibility(self) -> None:
        self.is_visible = not self.is_visible

    def draw(self, world: Optional[object], environment: Optional[object], vessel: Optional[object]) -> None:
        if not self.is_visible or environment is None:
            return

        panel_margin = 20
        panel_x = panel_margin
        panel_width = min(440, max(320, self.surface.get_width() - panel_margin * 2))
        # Fixed content height; docked to the bottom-left so it doesn't
        # overlap the FleetStatusPanel which occupies the top-left.
        panel_height = min(540, self.surface.get_height() - 150)
        panel_y = self.surface.get_height() - panel_height - 10
        pygame.draw.rect(self.surface, (*COLOR_PANEL_BG, 230), (panel_x, panel_y, panel_width, panel_height), border_radius=16)
        pygame.draw.rect(self.surface, COLOR_PANEL_BORDER, (panel_x, panel_y, panel_width, panel_height), 2, border_radius=16)

        y = panel_y + 22
        title = self.font_title.render("TECHNICAL SYSTEMS", True, COLOR_ACCENT)
        self.surface.blit(title, (panel_x + 20, y))
        y += title.get_height() + 18

        y = self._draw_data_section(panel_x, y, panel_width, "WEATHER", self._weather_entries(environment))
        y += 16
        y = self._draw_data_section(panel_x, y, panel_width, "ENVIRONMENT", self._environment_entries(environment, vessel, world))
        y += 16
        y = self._draw_data_section(panel_x, y, panel_width, "EXTERNAL AWARENESS", self._awareness_entries(world, vessel))
        if vessel:
            y += 16
            y = self._draw_data_section(panel_x, y, panel_width, "FUEL & PROPULSION", self._fuel_entries(vessel, environment))

    def _draw_data_section(self, x: int, y: int, panel_width: int, title: str, entries: list) -> int:
        header = self.font_header.render(title, True, COLOR_ACCENT)
        self.surface.blit(header, (x + 20, y))
        y += header.get_height() + 10
        for entry in entries:
            label, value, color = entry[0], entry[1], entry[2]
            # Optional 4th element: dot_color for a small vessel-type indicator circle.
            dot_color = entry[3] if len(entry) > 3 else None
            self._draw_label_value(x, y, panel_width, label, value, color,
                                   dot_color=dot_color)
            y += max(self.font_label.get_height(), self.font_value.get_height()) + 6
        return y

    def _draw_label_value(self, x: int, y: int, panel_width: int, label: str, value: str,
                          value_color: tuple = COLOR_TEXT_PRIMARY,
                          dot_color: tuple = None) -> None:
        inner_margin = 20
        inner_width  = panel_width - inner_margin * 2
        label_x_off  = 0
        if dot_color is not None:
            # Small filled circle as vessel-type indicator, vertically centred on the row.
            dot_cx = x + inner_margin + 5
            dot_cy = y + self.font_label.get_height() // 2
            pygame.gfxdraw.filled_circle(
                self.surface, dot_cx, dot_cy, 4, (*dot_color, 210))
            label_x_off = 13
        label_text = _truncate_text(label, self.font_label, inner_width - label_x_off)
        value_text = _truncate_text(value, self.font_value, inner_width)
        label_surf = self.font_label.render(label_text, True, COLOR_TEXT_SECONDARY)
        value_surf = self.font_value.render(value_text, True, value_color)
        self.surface.blit(label_surf, (x + inner_margin + label_x_off, y))
        self.surface.blit(value_surf, (x + inner_margin + inner_width - value_surf.get_width(), y - 2))

    def _weather_entries(self, environment) -> list:
        wind_cardinal = self._direction_to_cardinal(environment.wind_direction)
        return [
            ("Wind", f"{environment.wind_speed:.1f} kn @ {wind_cardinal}", COLOR_TEXT_PRIMARY),
            ("Wind Dir", f"{environment.wind_direction:.0f}°", COLOR_TEXT_PRIMARY),
            ("Gust", f"{environment.wind_gust_strength:.1f} kn", COLOR_TEXT_PRIMARY),
            ("Wave Height", f"{environment.wave_height:.1f} m", COLOR_TEXT_PRIMARY),
            ("Swell Dir", f"{environment.swell_direction:.0f}°", COLOR_TEXT_PRIMARY),
            ("Visibility", environment.get_visibility_display(), COLOR_TEXT_PRIMARY),
            ("Precipitation", environment.precipitation.title(), COLOR_WARNING if environment.precipitation != "none" else COLOR_TEXT_PRIMARY),
            ("Pressure", f"{environment.barometric_pressure_mb:.1f} mb", COLOR_TEXT_PRIMARY),
            ("Temp Air", f"{environment.air_temperature_c:.1f}°C", COLOR_TEXT_PRIMARY),
            ("Temp Water", f"{environment.water_temperature_c:.1f}°C", COLOR_TEXT_PRIMARY),
        ]

    def _environment_entries(self, environment, vessel, world=None) -> list:
        current_cardinal = self._direction_to_cardinal(environment.current_direction)
        entries = [
            ("Current", f"{environment.current_speed:.1f} kn @ {current_cardinal}", COLOR_TEXT_PRIMARY),
            ("Tide", f"{environment.tide_level:.2f} m ({environment.tide_direction})", COLOR_TEXT_PRIMARY),
            ("Time", f"{int(environment.time_of_day):02d}:{int((environment.time_of_day % 1) * 60):02d}", COLOR_ACCENT),
            ("Daylight", "YES" if environment.is_daylight() else "NO", COLOR_TEXT_PRIMARY),
            ("Visibility", environment.get_visibility_notes(), COLOR_TEXT_PRIMARY),
        ]
        if vessel:
            if world is not None:
                depth = world.water_depth_at(vessel.position, environment.tide_level)
            else:
                depth = 50.0
            under_keel = depth - vessel.draft_m
            ukc_color = COLOR_WARNING if under_keel < 1.0 else COLOR_TEXT_PRIMARY
            entries.extend([
                ("Water Depth", f"{depth:.1f} m", COLOR_TEXT_PRIMARY),
                ("Depth Under Keel", f"{under_keel:.1f} m", ukc_color),
            ])
        return entries

    def _awareness_entries(self, world, vessel) -> list:
        if not vessel or not world or not world.vessels:
            return [("Traffic", "No nearby vessels", COLOR_TEXT_DIM)]

        nearby = []
        for other in world.vessels:
            if other is vessel:
                continue
            dist = vessel.distance_to(other.position)
            if dist < 200.0:
                bearing = vessel.bearing_to(other.position)
                nearby.append((dist, bearing, other))
        if not nearby:
            return [("Traffic", "No nearby vessels", COLOR_TEXT_DIM)]

        nearby.sort(key=lambda item: item[0])
        entries = []
        for dist, bearing, other in nearby[:AIS_NEARBY_MAX]:
            dist_nm = dist * NM_PER_WORLD_UNIT
            card    = self._direction_to_cardinal(bearing)
            spd_kn  = other.current_speed
            status  = getattr(other, 'mission_status', '') or other.status.upper()
            value   = f"{dist_nm:.1f}nm {card} • {spd_kn:.1f}kn • {status}"
            dot_col = _AIS_TYPE_COLORS.get(other.vessel_type)
            entries.append((other.name, value, COLOR_TEXT_PRIMARY, dot_col))

            # CPA proximity warning — only when both vessels are moving.
            cpa = self._compute_cpa_nm(vessel, other)
            if cpa is not None and cpa < AIS_CPA_WARNING_NM:
                cpa_col = (255, 80, 80) if cpa < 0.5 else (220, 165, 50)
                entries.append((f"  ↳ CPA", f"{cpa:.1f} nm", cpa_col))

        return entries

    @staticmethod
    def _compute_cpa_nm(v1, v2):
        """Closest Point of Approach in nm.  Returns None when vessels diverge.

        Uses the standard CPA formula: TCPA = -dp·dv / |dv|²,
        then CPA distance = |dp + dv·TCPA|.
        Speeds converted from knots to world-units/s with KNOTS_TO_UNITS_PER_HOUR.
        """
        wu_per_s = KNOTS_TO_UNITS_PER_HOUR / 3600.0
        h1, h2 = math.radians(v1.heading), math.radians(v2.heading)
        vx1 = math.cos(h1) * v1.current_speed * wu_per_s
        vy1 = math.sin(h1) * v1.current_speed * wu_per_s
        vx2 = math.cos(h2) * v2.current_speed * wu_per_s
        vy2 = math.sin(h2) * v2.current_speed * wu_per_s
        dpx = v2.position[0] - v1.position[0]
        dpy = v2.position[1] - v1.position[1]
        dvx, dvy = vx2 - vx1, vy2 - vy1
        dv2 = dvx * dvx + dvy * dvy
        if dv2 < 1e-10:
            return math.hypot(dpx, dpy) * NM_PER_WORLD_UNIT
        tcpa = -(dpx * dvx + dpy * dvy) / dv2
        if tcpa <= 0:
            return None  # already diverging — no future CPA concern
        cpa_x = dpx + dvx * tcpa
        cpa_y = dpy + dvy * tcpa
        return math.hypot(cpa_x, cpa_y) * NM_PER_WORLD_UNIT

    def _fuel_entries(self, vessel, environment) -> list:
        if vessel.fuel is None:
            effective_speed = vessel._effective_wind_speed(environment)
            wind_angle = vessel._wind_angle_to_heading(environment)
            return [
                ("Propulsion", "Wind", COLOR_ACCENT),
                ("Effective Speed", f"{effective_speed:.1f} kn", COLOR_TEXT_PRIMARY),
                ("Wind Angle", f"{wind_angle:.0f}°", COLOR_TEXT_PRIMARY),
            ]
        fuel_rate = vessel.fuel_consumption_rate * (vessel.current_speed / max(0.1, vessel.max_speed)) ** 2
        entries = [
            ("Propulsion", "Fuel", COLOR_ACCENT),
            ("Fuel", f"{vessel.fuel:.1f} / {vessel.fuel_capacity:.1f} L", COLOR_TEXT_PRIMARY),
            ("Consumption", f"{fuel_rate:.2f} L/s", COLOR_TEXT_PRIMARY),
        ]
        if fuel_rate > 0 and vessel.current_speed > 0:
            range_seconds = vessel.fuel / fuel_rate
            range_nm = range_seconds / 3600.0 * vessel.current_speed
            entries.append(("Range", f"{range_nm:.0f} nm", COLOR_TEXT_PRIMARY))
        else:
            entries.append(("Range", "Stopped", COLOR_TEXT_DIM))
        if vessel.fuel and (vessel.fuel / vessel.fuel_capacity) * 100 < 25:
            entries.append(("Alert", "Low fuel", COLOR_WARNING))
        return entries

    @staticmethod
    def _direction_to_cardinal(degrees_: float) -> str:
        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                      "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        return directions[round(degrees_ / 22.5) % 16]


class SettingsPanel:
    def __init__(self, surface: pygame.Surface):
        self.surface = surface
        self.font_title = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_TITLE, bold=True)
        self.font_header = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_SECTION, bold=True)
        self.font_label = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_LABEL)
        self.font_value = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_DATA)
        self.font_small = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_SMALL)
        self.is_visible = False
        self.sliders: Dict[str, Tuple[int, int, int, float, float, str]] = {}
        self.buttons: Dict[str, pygame.Rect] = {}
        self.preset_definitions = {
            "Clear": {
                "precipitation": "none",
                "fog": False,
                "wind_speed": 4.0,
                "wind_direction": 60.0,
                "current_speed": 0.5,
                "current_direction": 80.0,
                "wave_height": 1.2,
                "visibility": 800.0,
                "air_temperature_c": 18.0,
                "water_temperature_c": 14.0,
                "pressure_trend": "stable",
            },
            "Cloudy": {
                "precipitation": "rain",
                "fog": False,
                "wind_speed": 6.0,
                "wind_direction": 110.0,
                "current_speed": 0.8,
                "current_direction": 100.0,
                "wave_height": 1.8,
                "visibility": 600.0,
                "air_temperature_c": 16.0,
                "water_temperature_c": 13.0,
                "pressure_trend": "falling",
            },
            "Fog": {
                "precipitation": "none",
                "fog": True,
                "wind_speed": 2.0,
                "wind_direction": 70.0,
                "current_speed": 0.3,
                "current_direction": 90.0,
                "wave_height": 0.8,
                "visibility": 50.0,
                "air_temperature_c": 12.0,
                "water_temperature_c": 11.0,
                "pressure_trend": "stable",
            },
            "Storm": {
                "precipitation": "storm",
                "fog": False,
                "wind_speed": 12.0,
                "wind_direction": 140.0,
                "current_speed": 1.5,
                "current_direction": 120.0,
                "wave_height": 4.0,
                "visibility": 250.0,
                "air_temperature_c": 11.0,
                "water_temperature_c": 12.0,
                "pressure_trend": "falling",
            },
        }
        self.reset_defaults = {
            "time_of_day": 12.0,
            "wind_speed": 5.0,
            "wind_direction": 45.0,
            "current_speed": 0.5,
            "current_direction": 90.0,
            "wave_height": 1.0,
            "visibility": 500.0,
            "precipitation": "none",
            "fog": False,
            "air_temperature_c": 15.0,
            "water_temperature_c": 12.0,
            "pressure_trend": "stable",
        }

    def toggle_visibility(self) -> None:
        self.is_visible = not self.is_visible

    def apply_preset(self, environment, preset_name: str) -> None:
        preset = self.preset_definitions.get(preset_name)
        if not preset:
            return
        for key, value in preset.items():
            setattr(environment, key, value)
        # Sync _auto_* baselines so drift continues from the new conditions
        # rather than fighting back to the previous state.
        if hasattr(environment, "sync_auto_to_current"):
            environment.sync_auto_to_current()

    def reset_environment(self, environment) -> None:
        for key, value in self.reset_defaults.items():
            setattr(environment, key, value)
        if hasattr(environment, "sync_auto_to_current"):
            environment.sync_auto_to_current()

    def handle_mouse_click(self, environment, mouse_pos: Tuple[int, int],
                           sound=None) -> None:
        if not self.is_visible or not environment:
            return

        mx, my = mouse_pos
        for label, rect in self.buttons.items():
            if rect.collidepoint(mx, my):
                if label in self.preset_definitions:
                    self.apply_preset(environment, label)
                    return
                if label == "Reset":
                    self.reset_environment(environment)
                    return
                if label == "SoundToggle" and sound is not None:
                    sound.set_enabled(not sound.enabled)
                    return

        # Fields managed by the dynamic weather engine get user_override() so
        # the engine knows to pin the value briefly before resuming auto-drift.
        _WEATHER_DYNAMIC = {
            "wind_speed", "wind_direction", "wave_height",
            "current_speed", "current_direction", "visibility",
        }
        for label, (bar_x, bar_y, bar_width, min_val, max_val, attr_name) in self.sliders.items():
            if bar_x <= mx <= bar_x + bar_width and bar_y <= my <= bar_y + 12:
                ratio = (mx - bar_x) / bar_width
                new_value = min_val + ratio * (max_val - min_val)
                # Sound volume routes to the SoundManager, not the environment.
                if attr_name == "sound_volume":
                    if sound is not None:
                        sound.set_volume(new_value)
                    return
                if attr_name in _WEATHER_DYNAMIC and hasattr(environment, "user_override"):
                    environment.user_override(attr_name, new_value)
                else:
                    setattr(environment, attr_name, new_value)
                return

    def draw(self, environment: Optional[object], sound=None) -> None:
        if not self.is_visible or environment is None:
            return

        overlay = pygame.Surface(self.surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.surface.blit(overlay, (0, 0))

        panel_margin = 20
        panel_x = panel_margin
        panel_y = 60
        panel_width = min(520, max(340, self.surface.get_width() - panel_margin * 2))
        panel_height = self.surface.get_height() - 80
        pygame.draw.rect(self.surface, (*COLOR_PANEL_BG, 230), (panel_x, panel_y, panel_width, panel_height), border_radius=18)
        pygame.draw.rect(self.surface, COLOR_PANEL_BORDER, (panel_x, panel_y, panel_width, panel_height), 2, border_radius=18)

        current_y = panel_y + 22
        title = self.font_title.render("ENVIRONMENT SETTINGS", True, COLOR_ACCENT)
        self.surface.blit(title, (panel_x + 24, current_y))
        current_y += title.get_height() + 18

        self.buttons = {}
        button_x = panel_x + 24
        for name in self.preset_definitions:
            rect = pygame.Rect(button_x, current_y, 92, 30)
            self._draw_button(rect, name)
            self.buttons[name] = rect
            button_x += 96
        current_y += 44

        self.sliders = {}
        current_y = self._draw_slider(panel_x, current_y, "Time of Day", environment.time_of_day, 0.0, 24.0, "time_of_day", suffix="h")
        current_y = self._draw_slider(panel_x, current_y, "Wind Speed", environment.wind_speed, 0.0, 20.0, "wind_speed")
        current_y = self._draw_slider(panel_x, current_y, "Wind Direction", environment.wind_direction, 0.0, 360.0, "wind_direction", integer=True)
        current_y = self._draw_slider(panel_x, current_y, "Current Speed", environment.current_speed, 0.0, 3.0, "current_speed")
        current_y = self._draw_slider(panel_x, current_y, "Current Direction", environment.current_direction, 0.0, 360.0, "current_direction", integer=True)
        current_y = self._draw_slider(panel_x, current_y, "Wave Height", environment.wave_height, 0.0, 5.0, "wave_height")
        # Raw float for bar math; formatted string shown as the label.
        current_y = self._draw_slider(panel_x, current_y, "Visibility", environment.visibility, 50.0, 1000.0, "visibility", display_value=environment.get_visibility_display())
        current_y += 14

        time_speed = "PAUSED" if environment.time_speed_multiplier == 0 else f"{int(environment.time_speed_multiplier)}x"
        self._draw_label_value(panel_x + 24, current_y, "Time Speed", time_speed)
        current_y += 34

        reset_rect = pygame.Rect(panel_x + 24, current_y, 120, 32)
        self._draw_button(reset_rect, "Reset")
        self.buttons["Reset"] = reset_rect
        current_y += 46

        # ── Sound controls ────────────────────────────────────────────────────
        if sound is not None:
            hdr = self.font_header.render("SOUND", True, COLOR_ACCENT)
            self.surface.blit(hdr, (panel_x + 24, current_y))
            current_y += hdr.get_height() + 8

            toggle_rect = pygame.Rect(panel_x + 24, current_y, 120, 30)
            self._draw_button(toggle_rect,
                              "Sound: ON" if sound.enabled else "Sound: OFF")
            self.buttons["SoundToggle"] = toggle_rect
            current_y += 40

            current_y = self._draw_slider(
                panel_x, current_y, "Volume", sound.volume,
                0.0, 1.0, "sound_volume")

        instructions = [
            "Click presets to apply common conditions.",
            "Slide any bar to update the environment live.",
            "Adjust Time of Day to influence tide and lighting.",
            "",
            "Keys: E = Settings  |  T = Tech panel  |  1 = Pause  2 = 1×  3 = 2×  4 = 3×",
            "Tab = Select vessel, Esc = Quit",
        ]
        for line in instructions:
            text = self.font_small.render(line, True, COLOR_TEXT_DIM)
            self.surface.blit(text, (panel_x + 24, current_y))
            current_y += 18

    def _draw_button(self, rect: pygame.Rect, text: str) -> None:
        pygame.draw.rect(self.surface, COLOR_FRAME, rect, border_radius=8)
        pygame.draw.rect(self.surface, COLOR_ACCENT, rect, 2, border_radius=8)
        label_surf = self.font_label.render(text, True, COLOR_TEXT_PRIMARY)
        self.surface.blit(label_surf, (rect.centerx - label_surf.get_width() // 2, rect.centery - label_surf.get_height() // 2))

    def _draw_slider(self, x: int, y: int, label: str, value: float, min_val: float, max_val: float, attr_name: str, suffix: str = "", integer: bool = False, display_value: str = "") -> int:
        label_surf = self.font_label.render(label, True, COLOR_TEXT_SECONDARY)
        # display_value overrides the auto-formatted label (e.g. "1.2 km" for visibility).
        # value must always be the raw float so bar-fill math below works correctly.
        if display_value:
            value_text = display_value
        elif integer:
            value_text = f"{int(value)}{suffix}"
        else:
            value_text = f"{value:.1f}{suffix}"
        value_surf = self.font_value.render(value_text, True, COLOR_TEXT_PRIMARY)
        self.surface.blit(label_surf, (x + 24, y))
        self.surface.blit(value_surf, (x + 420 - value_surf.get_width() - 24, y))

        bar_x = x + 24
        bar_y = y + 26
        bar_width = 372
        bar_height = 12
        self.sliders[label] = (bar_x, bar_y, bar_width, min_val, max_val, attr_name)
        pygame.draw.rect(self.surface, COLOR_FRAME, (bar_x, bar_y, bar_width, bar_height), border_radius=6)
        fill = int(bar_width * ((value - min_val) / max(1e-6, max_val - min_val)))
        pygame.draw.rect(self.surface, COLOR_ACCENT, (bar_x, bar_y, fill, bar_height), border_radius=6)
        return y + 50

    def _draw_label_value(self, x: int, y: int, label: str, value: str) -> None:
        label_surf = self.font_label.render(label, True, COLOR_TEXT_SECONDARY)
        value_surf = self.font_value.render(value, True, COLOR_TEXT_PRIMARY)
        self.surface.blit(label_surf, (x, y))
        self.surface.blit(value_surf, (x + 240, y))


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------

# Colors for each event category — used by EventLog.add() callers in main.py.
EVENT_COLOR_MAYDAY   = COLOR_WARNING           # red — vessel aground / engine failure / MOB
EVENT_COLOR_RESCUE   = COLOR_ACCENT            # cyan — rescuer dispatched
EVENT_COLOR_REFLOAT  = COLOR_EVENT_REFLOATED   # green — vessel refloated
EVENT_COLOR_WEATHER  = COLOR_COLLISION_AVOID   # amber — weather event change
EVENT_COLOR_MEDICAL  = COLOR_EVENT_MEDICAL     # amber — medical emergency


class EventLog:
    """Scrolling feed of the last 6 maritime events, drawn in the bottom-left corner.

    Callers append entries with add(); draw() renders the feed each frame.
    The list is capped at MAX_ENTRIES; oldest entries are dropped when full.
    """

    MAX_ENTRIES = 6
    WIDTH       = 360
    LINE_H      = 18
    PAD         = 10

    def __init__(self, surface: pygame.Surface) -> None:
        self.surface = surface
        self._entries: list = []   # [(text, color), ...]
        self._font = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_SMALL)

    def add(self, sim_time: str, message: str, color: tuple) -> None:
        """Append an event; drop the oldest if over capacity."""
        self._entries.append((f"[{sim_time}] {message}", color))
        if len(self._entries) > self.MAX_ENTRIES:
            self._entries.pop(0)

    def draw(self) -> None:
        """Render the feed; no-op when empty."""
        if not self._entries:
            return

        h = len(self._entries) * self.LINE_H + self.PAD * 2
        vw, vh = self.surface.get_size()
        x = 20
        y = vh - h - 20

        # Semi-transparent dark background
        bg = pygame.Surface((self.WIDTH, h), pygame.SRCALPHA)
        bg.fill((8, 20, 40, 195))
        self.surface.blit(bg, (x, y))
        pygame.draw.rect(self.surface, (40, 65, 95), (x, y, self.WIDTH, h), 1)

        # Entries — oldest at top, most recent at bottom
        for i, (text, color) in enumerate(self._entries):
            line_surf = self._font.render(text, True, color)
            self.surface.blit(line_surf, (x + self.PAD, y + self.PAD + i * self.LINE_H))


# ---------------------------------------------------------------------------
# Fleet status panel
# ---------------------------------------------------------------------------

# Status display styles: (label, color)
_FLEET_STATUS_STYLE: dict = {
    "underway":  ("UNDERWAY",  (180, 180, 180)),
    "avoiding":  ("AVOIDING",  (220, 165,  50)),
    "in_port":   ("IN PORT",   (120, 120, 120)),
    "docked":    ("DOCKED",    (120, 120, 120)),
    "aground":   ("AGROUND",   (255,  80,  50)),
    "adrift":    ("ADRIFT",    (220, 165,  50)),
    "anchored":  ("ANCHORED",  (160, 160, 160)),
}


class FleetStatusPanel:
    """Compact fleet overview in the top-left corner, below the compass.

    One row per vessel: name on the left, status label on the right.
    Click a row to select and follow that vessel.
    Hidden when the settings panel is open.
    """

    ROW_H  = 22
    WIDTH  = 200   # compact; long names truncate with "…", status stays right-aligned
    PAD_X  = 10
    PAD_Y  = 6
    TOP_Y  = 130   # below compass + scale bar area

    def __init__(self, surface: pygame.Surface) -> None:
        self.surface = surface
        self._font_name   = pygame.font.SysFont(FONT_UI_NAME,  FONT_SIZE_SMALL)
        self._font_status = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_SMALL)
        self._rows: list = []   # [(pygame.Rect, vessel), ...] for click detection

    def draw(self, world, selected_vessel) -> None:
        if not world or not world.vessels:
            return

        # Cap the row count so the panel always ends ≥ 10 px above the bottom
        # edge, however short the window or long the fleet.
        vh = self.surface.get_height()
        max_rows = max(1, (vh - self.TOP_Y - 10 - self.PAD_Y * 2) // self.ROW_H)
        vessels = world.vessels[:max_rows]
        n = len(vessels)
        h = n * self.ROW_H + self.PAD_Y * 2
        x = 20
        y = self.TOP_Y

        # Background — themed translucent panel matching the other UI panels
        # (rounded corners, 2 px border).  A flat alpha-200 fill with a 1 px
        # border read as "floating text" over dark water because PANEL_BG is
        # almost the water colour; the brighter 2 px border + rounded corners
        # outline the panel so it's legible over water and land alike, exactly
        # like the vessel-info and mission panels.
        bg = pygame.Surface((self.WIDTH, h), pygame.SRCALPHA)
        pygame.draw.rect(bg, (*COLOR_PANEL_BG, 230), bg.get_rect(), border_radius=10)
        self.surface.blit(bg, (x, y))
        pygame.draw.rect(self.surface, COLOR_PANEL_BORDER, (x, y, self.WIDTH, h), 2,
                         border_radius=10)

        self._rows = []
        for i, vessel in enumerate(vessels):
            row_y   = y + self.PAD_Y + i * self.ROW_H
            row_rect = pygame.Rect(x, row_y, self.WIDTH, self.ROW_H)
            self._rows.append((row_rect, vessel))

            is_sel = (vessel == selected_vessel)
            if is_sel:
                hl = pygame.Surface((self.WIDTH, self.ROW_H), pygame.SRCALPHA)
                hl.fill((255, 255, 255, 22))
                self.surface.blit(hl, (x, row_y))

            # Determine display status and color
            mission_st = getattr(vessel, 'mission_status', '')
            if vessel.mob_timer > 0:
                label, col = "MOB",     (255, 140,  50)
            elif vessel.engine_failure:
                label, col = "ENG FAIL",(255,  80,  50)
            elif vessel.distress:
                label, col = "DISTRESS",(255,  80,  50)
            elif vessel.player_commanded and not vessel.distress:
                label, col = "MEDICAL", (220, 165,  50)
            elif mission_st:
                label = mission_st
                col   = (180, 180, 180) if vessel.status == "underway" else (120, 120, 120)
            else:
                style = _FLEET_STATUS_STYLE.get(vessel.status, ("???", (150, 150, 150)))
                label, col = style

            name_col = (230, 230, 230) if is_sel else (160, 160, 160)
            status_surf = self._font_status.render(label, True, col)
            # Leave 6 px gap between name and status; truncate name if needed.
            max_name_w = self.WIDTH - self.PAD_X * 2 - status_surf.get_width() - 6
            name_surf = self._font_name.render(
                _truncate_text(vessel.name, self._font_name, max_name_w),
                True, name_col,
            )

            cy = row_y + (self.ROW_H - name_surf.get_height()) // 2
            self.surface.blit(name_surf,   (x + self.PAD_X, cy))
            sx = x + self.WIDTH - self.PAD_X - status_surf.get_width()
            self.surface.blit(status_surf, (sx, cy))

    def handle_click(self, screen_pos) -> object:
        """Return the vessel whose row was clicked, or None."""
        for rect, vessel in self._rows:
            if rect.collidepoint(screen_pos):
                return vessel
        return None


class MissionPanel:
    """Small bottom-right panel showing the active player mission.

    Auto-hides when no mission is active.  Shows a green flash for
    MISSION_COMPLETE_DISPLAY_S seconds when a mission completes, then
    fades out and waits for the next mission.
    """

    WIDTH    = 280
    PAD      = 10
    MARGIN   = 12   # pixels from the screen edge

    def __init__(self, surface: pygame.Surface) -> None:
        self.surface = surface
        self._font_tag  = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_SMALL,   bold=True)
        self._font_desc = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_LABEL,   bold=True)
        self._font_obj  = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_SMALL)
        self._font_done = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_SECTION, bold=True)

    def draw(self, mission_manager, sim_elapsed_s: float = 0.0,
             bottom_offset: int = 0) -> None:
        """Draw the mission panel if a mission is active.

        bottom_offset lifts the panel (e.g. above the minimap) so the two
        bottom-right elements never overlap.
        """
        m = mission_manager.active_mission
        if m is None:
            return

        vw, vh = self.surface.get_size()
        vh -= bottom_offset
        pad = self.PAD

        if m.complete:
            self._draw_complete(m, vw, vh, pad)
        else:
            self._draw_active(m, vw, vh, pad, sim_elapsed_s)

    # ------------------------------------------------------------------ helpers

    def _panel_bg(self, x: int, y: int, w: int, h: int) -> None:
        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(bg, (*COLOR_PANEL_BG[:3], 215),
                         bg.get_rect(), border_radius=8)
        pygame.draw.rect(bg, COLOR_PANEL_BORDER,
                         bg.get_rect(), width=1, border_radius=8)
        self.surface.blit(bg, (x, y))

    def _draw_active(self, m, vw: int, vh: int, pad: int,
                     sim_elapsed_s: float = 0.0) -> None:
        tag_h  = self._font_tag.get_height()
        desc_h = self._font_desc.get_height()
        obj_h  = self._font_obj.get_height()
        # Extra row for deadline countdown when mission has a deadline.
        has_deadline = (m.mission_type == "cargo_deadline"
                        and getattr(m, "deadline_sim_time", 0) > 0)
        dl_extra = (4 + obj_h) if has_deadline else 0
        panel_h = pad * 2 + tag_h + 4 + desc_h + 4 + obj_h + dl_extra

        x = vw - self.WIDTH - self.MARGIN
        y = vh - panel_h - self.MARGIN - 44  # clear status bar and fleet gap

        self._panel_bg(x, y, self.WIDTH, panel_h)

        cy = y + pad
        tag_col = {
            "delivery":         (160, 210, 255),
            "rescue":           (255, 160, 100),
            "patrol":           (160, 230, 160),
            "passenger_pickup": (180, 230, 255),
            "cargo_deadline":   (255, 200,  80),
            "vip_cruise":       (220, 190, 255),
        }.get(m.mission_type, COLOR_ACCENT)

        tag_label = {
            "delivery":         "▼ DELIVERY",
            "rescue":           "⚠ RESCUE",
            "patrol":           "◆ PATROL",
            "passenger_pickup": "★ PASSENGER",
            "cargo_deadline":   "⏱ DEADLINE",
            "vip_cruise":       "⛵ VIP CRUISE",
        }.get(m.mission_type, "MISSION")

        tag_surf = self._font_tag.render(tag_label, True, tag_col)
        self.surface.blit(tag_surf, (x + pad, cy));  cy += tag_h + 4

        desc_surf = self._font_desc.render(
            _truncate_text(m.description, self._font_desc, self.WIDTH - pad * 2),
            True, COLOR_TEXT_PRIMARY)
        self.surface.blit(desc_surf, (x + pad, cy));  cy += desc_h + 4

        obj_surf = self._font_obj.render(
            _truncate_text(m.objective, self._font_obj, self.WIDTH - pad * 2),
            True, COLOR_TEXT_SECONDARY)
        self.surface.blit(obj_surf, (x + pad, cy));  cy += obj_h + 4

        # Deadline countdown — amber when > 1 h remaining, red when < 1 h or missed.
        if has_deadline:
            remaining = m.deadline_sim_time - sim_elapsed_s
            if remaining > 0:
                h_part = int(remaining // 3600)
                m_part = int((remaining % 3600) // 60)
                dl_text = f"Time remaining: {h_part}h {m_part:02d}m" if h_part else f"Time remaining: {m_part}m"
                dl_col  = (255, 80, 80) if remaining < 3600 else (224, 161, 58)
            else:
                dl_text = "DEADLINE MISSED"
                dl_col  = (255, 80, 80)
            dl_surf = self._font_obj.render(
                _truncate_text(dl_text, self._font_obj, self.WIDTH - pad * 2),
                True, dl_col)
            self.surface.blit(dl_surf, (x + pad, cy))

    def _draw_complete(self, m, vw: int, vh: int, pad: int) -> None:
        done_h   = self._font_done.get_height()
        reward_h = self._font_obj.get_height()
        panel_h  = pad * 2 + done_h + 6 + reward_h

        x = vw - self.WIDTH - self.MARGIN
        y = vh - panel_h - self.MARGIN - 44

        self._panel_bg(x, y, self.WIDTH, panel_h)

        cy = y + pad
        failed = getattr(m, "failed", False)
        if failed:
            done_text = "DEADLINE MISSED"
            done_col  = (255, 80, 80)
            reward_col = (255, 150, 150)
        else:
            done_text = "MISSION COMPLETE"
            done_col  = (80, 220, 120)
            reward_col = (160, 220, 170)

        done_surf = self._font_done.render(done_text, True, done_col)
        self.surface.blit(done_surf, (x + pad, cy));  cy += done_h + 6

        reward_surf = self._font_obj.render(
            _truncate_text(m.reward_text, self._font_obj, self.WIDTH - pad * 2),
            True, reward_col)
        self.surface.blit(reward_surf, (x + pad, cy))


# ---------------------------------------------------------------------------
# Player HUD panel
# ---------------------------------------------------------------------------

class PlayerHUDPanel:
    """Bottom-center HUD for the human-controlled vessel.

    Shows: name + [PLAYER] badge, speed/throttle bar, heading + compass arc,
    fuel bar, hull integrity bar, status label, and a key-hint line.
    Hidden entirely when no player vessel is provided.
    """

    WIDTH    = 340
    PAD      = 12
    MARGIN   = 8    # pixels from bottom of screen
    BAR_H    = 10

    def __init__(self, surface: pygame.Surface) -> None:
        self.surface = surface
        self._font_name   = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_SECTION, bold=True)
        self._font_badge  = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_SMALL,   bold=True)
        self._font_label  = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_SMALL)
        self._font_value  = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_LABEL,   bold=True)
        self._font_hint   = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_SMALL)

    # ------------------------------------------------------------------ public

    def draw(self, vessel, career=None, zone_violation=False, frame_count=0,
             low_visibility=False, active_contract=None, world=None) -> None:
        if vessel is None:
            return

        # Active-contract destination line: "→ Port Ardent  12.4 nm".
        _contract_line = None
        if active_contract is not None and world is not None:
            _to_port = world.find_port(active_contract.to_port)
            if _to_port is not None:
                _dist_nm = vessel.distance_to(_to_port.position) * NM_PER_WORLD_UNIT
                _contract_line = f"→ {active_contract.to_port}  {_dist_nm:.1f} nm"

        vw, vh = self.surface.get_size()
        pad = self.PAD
        w   = self.WIDTH

        hull = getattr(vessel, 'hull_integrity', 1.0)
        _low_funds = (career is not None and career.money < 500.0)
        _in_storm  = (getattr(vessel, 'current_speed', 0) >= 0
                      and getattr(vessel, 'status', '') == 'underway')  # presence check

        # Measure content height dynamically
        row_h   = self._font_label.get_height() + 4
        bar_row = self.BAR_H + 6
        content_h = (
            self._font_name.get_height() + 6   # name + badge
            + row_h                             # speed label + throttle bar
            + bar_row
            + row_h                             # heading label + bar
            + bar_row
            + row_h                             # fuel label + bar
            + bar_row
            + row_h                             # hull label + bar
            + bar_row
            + (_low_funds and row_h or 0)       # low-funds warning (conditional)
            + (low_visibility and row_h or 0)   # fog warning (conditional)
            + (_contract_line and row_h or 0)   # contract destination (conditional)
            + row_h                             # status
            + row_h                             # hint
        )
        h = content_h + pad * 2
        x = vw // 2 - w // 2
        y = vh - h - self.MARGIN  # anchor to the very bottom (MARGIN = 8 px)

        # Zone violation flashing banner above the panel
        if zone_violation:
            _flash_on = (frame_count % 2 == 0)
            zv_col  = COLOR_WARNING if _flash_on else (180, 50, 50)
            zv_surf = self._font_badge.render("!! ZONE VIOLATION !!", True, zv_col)
            self.surface.blit(zv_surf,
                              (vw // 2 - zv_surf.get_width() // 2,
                               y - zv_surf.get_height() - 4))

        # Background
        border_col = (COLOR_WARNING if zone_violation and frame_count % 2 == 0
                      else COLOR_ACCENT)
        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(bg, (*COLOR_PANEL_BG[:3], 220), bg.get_rect(), border_radius=10)
        pygame.draw.rect(bg, border_col, bg.get_rect(), width=1, border_radius=10)
        self.surface.blit(bg, (x, y))

        cy = y + pad

        # ── Name + [PLAYER] badge ─────────────────────────────────────────────
        name_surf  = self._font_name.render(vessel.name, True, COLOR_ACCENT)
        badge_surf = self._font_badge.render("[PLAYER]", True, (60, 220, 120))
        self.surface.blit(name_surf, (x + pad, cy))
        bx = x + pad + name_surf.get_width() + 8
        by = cy + (name_surf.get_height() - badge_surf.get_height()) // 2
        self.surface.blit(badge_surf, (bx, by))
        cy += name_surf.get_height() + 6

        # ── Speed + throttle bar ──────────────────────────────────────────────
        spd_str  = f"{vessel.current_speed:.1f} kn"
        tgt_str  = f"/ {vessel.target_speed:.1f}"
        spd_surf = self._font_value.render(spd_str, True, COLOR_TEXT_PRIMARY)
        tgt_surf = self._font_label.render(tgt_str, True, COLOR_TEXT_SECONDARY)
        lbl_surf = self._font_label.render("SPD", True, COLOR_TEXT_DIM)
        self.surface.blit(lbl_surf, (x + pad, cy))
        self.surface.blit(spd_surf, (x + pad + 36, cy - 2))
        self.surface.blit(tgt_surf, (x + pad + 36 + spd_surf.get_width() + 4, cy))
        cy += row_h
        self._draw_bar(x + pad, cy, w - pad * 2,
                       vessel.target_speed / max(0.1, vessel.max_speed), COLOR_ACCENT)
        cy += bar_row

        # ── Heading + compass arc ─────────────────────────────────────────────
        hdg_str  = f"HDG  {vessel.heading:05.1f}°"
        hdg_surf = self._font_value.render(hdg_str, True, COLOR_TEXT_PRIMARY)
        self.surface.blit(hdg_surf, (x + pad, cy))
        arc_cx = x + w - pad - 18
        arc_cy = cy + self._font_value.get_height() // 2
        self._draw_compass_arc(arc_cx, arc_cy, 14, vessel.heading)
        cy += row_h
        # Proportional heading bar: fill scales 0–360°, so 090° reads 25 % full.
        # min_fill_px keeps a 2 px sliver visible even at 000° (due north).
        self._draw_bar(x + pad, cy, w - pad * 2,
                       (vessel.heading % 360.0) / 360.0, COLOR_ACCENT,
                       min_fill_px=2)
        cy += bar_row

        # ── Fuel bar ─────────────────────────────────────────────────────────
        if vessel.fuel is not None and vessel.fuel_capacity:
            fuel_pct = vessel.fuel / vessel.fuel_capacity
            fuel_col = COLOR_ACCENT if fuel_pct > 0.25 else COLOR_WARNING
            fuel_str = f"FUEL  {fuel_pct * 100:.0f}%"
            fuel_surf = self._font_label.render(fuel_str, True, fuel_col)
            self.surface.blit(fuel_surf, (x + pad, cy))
            cy += row_h
            self._draw_bar(x + pad, cy, w - pad * 2, fuel_pct, fuel_col)
            cy += bar_row

        # ── Hull integrity bar — colour-coded so it never reads as the fuel bar.
        # Green > 50%, yellow 25-50%, red < 25% (flashing darker when critical).
        if hull < 0.25:
            hull_col = HULL_BAR_LOW_COLOR if (frame_count % 2 == 0) else (120, 30, 30)
        elif hull <= 0.5:
            hull_col = HULL_BAR_MID_COLOR
        else:
            hull_col = HULL_BAR_HIGH_COLOR
        hull_str  = f"HULL  {hull * 100:.0f}%"
        hull_surf = self._font_label.render(hull_str, True, hull_col)
        self.surface.blit(hull_surf, (x + pad, cy))
        cy += row_h
        self._draw_bar(x + pad, cy, w - pad * 2, hull, hull_col)
        cy += bar_row

        # ── Low-funds warning ─────────────────────────────────────────────────
        if _low_funds:
            lf_surf = self._font_label.render(
                f"LOW FUNDS  \xa3{career.money:.0f}", True, COLOR_WARNING)
            self.surface.blit(lf_surf, (x + pad, cy))
            cy += row_h

        # ── Fog warning ───────────────────────────────────────────────────────
        if low_visibility:
            lv_surf = self._font_label.render(
                "LOW VISIBILITY", True, (220, 165, 50))
            self.surface.blit(lv_surf, (x + pad, cy))
            cy += row_h

        # ── Active-contract destination ───────────────────────────────────────
        if _contract_line:
            cl_surf = self._font_label.render(_contract_line, True, COLOR_ACCENT)
            self.surface.blit(cl_surf, (x + pad, cy))
            cy += row_h

        # ── Status ────────────────────────────────────────────────────────────
        status_str  = vessel.status.upper()
        status_col  = COLOR_WARNING if vessel.status in ("aground", "adrift") else COLOR_TEXT_SECONDARY
        status_surf = self._font_label.render(status_str, True, status_col)
        self.surface.blit(status_surf, (x + pad, cy))
        cy += row_h

        # ── Key hint ──────────────────────────────────────────────────────────
        hint = "W/S throttle  A/D turn  F follow  J career  M map  Z zoom"
        hint_surf = self._font_hint.render(hint, True, COLOR_TEXT_DIM)
        self.surface.blit(hint_surf, (x + w // 2 - hint_surf.get_width() // 2, cy))

    # ----------------------------------------------------------------- helpers

    def _draw_bar(self, x: int, y: int, width: int, fraction: float,
                  fill_color: tuple, min_fill_px: int = 0) -> None:
        fraction = max(0.0, min(1.0, fraction))
        pygame.draw.rect(self.surface, COLOR_FRAME, (x, y, width, self.BAR_H),
                         border_radius=4)
        # Fill shares the background's x/y exactly.  min_fill_px guarantees a
        # visible sliver for "always a bar" readouts (heading at 000°); value
        # bars leave it 0 so an empty tank/hull genuinely reads as empty.
        fill_w = min(width, max(min_fill_px, int(width * fraction)))
        if fill_w > 0:
            pygame.draw.rect(self.surface, fill_color, (x, y, fill_w, self.BAR_H),
                             border_radius=4)

    def _draw_compass_arc(self, cx: int, cy: int, radius: int,
                          heading_deg: float) -> None:
        """Draw a small arc ring with a tick mark at the current heading."""
        pygame.gfxdraw.aacircle(self.surface, cx, cy, radius,
                                (*COLOR_FRAME, 200))
        # Tick mark at heading direction
        rad = _math.radians(heading_deg - 90.0)  # -90 so 0° = north = up
        tx = cx + int(_math.cos(rad) * radius)
        ty = cy + int(_math.sin(rad) * radius)
        ti = cx + int(_math.cos(rad) * (radius - 4))
        tj = cy + int(_math.sin(rad) * (radius - 4))
        pygame.draw.line(self.surface, COLOR_ACCENT, (ti, tj), (tx, ty), 2)


# ---------------------------------------------------------------------------
# Career panel
# ---------------------------------------------------------------------------

_JOB_TYPE_COLORS: dict = {
    "delivery":      (160, 210, 255),
    "rescue_assist": (255, 160, 100),
    "patrol":        (160, 230, 160),
    "hazmat":        (255, 120,  60),
    "charter":       (200, 170, 255),
    "vip_charter":   (255, 215, 120),
}

# Short special-requirement tags shown beside payout/deadline on contract rows.
_JOB_SPECIAL_NOTES: dict = {
    "hazmat":      "2× fines",
    "charter":     "max 10 kn",
    "vip_charter": "VIP",
}

from engine.career import ACHIEVEMENT_DEFS


class CareerPanel:
    """Right-side panel showing wallet, reputation, job board, and active contract.

    Toggled with J key.  Click the ACCEPT button on a contract row to take the job.
    """

    WIDTH  = 320
    MARGIN = 12
    PAD    = 12
    ROW_H  = 64   # height of a single contract row

    def __init__(self, surface: pygame.Surface) -> None:
        self.surface = surface
        self.is_visible = False
        self._job_rects: list = []   # [(pygame.Rect, contract), ...] for click detection

        self._font_title  = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_TITLE,   bold=True)
        self._font_header = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_SECTION, bold=True)
        self._font_label  = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_LABEL)
        self._font_value  = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_DATA,    bold=True)
        self._font_small  = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_SMALL)

    def toggle_visibility(self) -> None:
        self.is_visible = not self.is_visible

    def handle_click(self, screen_pos, job_board, career, sim_elapsed_s: float):
        """Accept the clicked contract. Returns contract_id on success, else None."""
        if not self.is_visible:
            return None
        mx, my = screen_pos
        for rect, contract in self._job_rects:
            if rect.collidepoint(mx, my):
                if job_board.accept_job(contract.contract_id, career, sim_elapsed_s):
                    return contract.contract_id
        return None

    def draw(self, career, job_board, sim_elapsed_s: float) -> None:
        if not self.is_visible or career is None or job_board is None:
            return

        vw, vh = self.surface.get_size()
        pad = self.PAD
        w   = self.WIDTH
        x   = vw - w - self.MARGIN
        y   = self.MARGIN

        available_contracts = job_board.available
        active_contract     = job_board.active

        # Dynamic height: title + stats + divider + jobs header + N rows
        # + divider + active contract + divider + achievements
        stats_h   = 24 + 6 + 22 * 4 + 10 + 2   # header + 4 stat rows + gap + divider
        jobs_rows = max(1, len(available_contracts[:4]))
        jobs_h    = 24 + 6 + jobs_rows * (self.ROW_H + 4) + 10 + 2
        active_h  = 24 + 6 + (100 if active_contract else 20) + pad
        ach_h     = 12 + 24 + 6 + len(ACHIEVEMENT_DEFS) * 18
        title_h   = self._font_title.get_height() + 8 + 2 + 10   # title + gap + divider
        total_h   = pad * 2 + title_h + stats_h + jobs_h + active_h + ach_h
        h = min(vh - self.MARGIN * 2, total_h)

        # Background
        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(bg, (*COLOR_PANEL_BG[:3], 230), bg.get_rect(), border_radius=14)
        pygame.draw.rect(bg, COLOR_PANEL_BORDER, bg.get_rect(), 2, border_radius=14)
        self.surface.blit(bg, (x, y))

        cy = y + pad

        # ── Title ─────────────────────────────────────────────────────────────
        title_surf = self._font_title.render("CAREER", True, COLOR_ACCENT)
        self.surface.blit(title_surf, (x + pad, cy))
        cy += title_surf.get_height() + 8
        pygame.draw.line(self.surface, COLOR_FRAME, (x + pad, cy), (x + w - pad, cy), 1)
        cy += 10

        # ── Wallet & Reputation ────────────────────────────────────────────────
        hdr = self._font_header.render("WALLET & REPUTATION", True, COLOR_ACCENT)
        self.surface.blit(hdr, (x + pad, cy))
        cy += hdr.get_height() + 6

        self._lv(x, cy, w, "Balance", f"\xa3{career.money:.0f}")
        cy += 22

        rep_col = (COLOR_ACCENT if career.reputation >= 50
                   else (220, 165, 50) if career.reputation >= 20
                   else COLOR_WARNING)
        self._lv(x, cy, w, "Reputation",
                 f"{career.reputation}/100 · {career.tier_name}", rep_col)
        cy += 22

        self._lv(x, cy, w, "Deliveries", str(career.total_deliveries))
        cy += 22

        self._lv(x, cy, w, "Hull repairs", f"\xa3{career.hull_repairs_paid:.0f}")
        cy += 16

        pygame.draw.line(self.surface, COLOR_FRAME, (x + pad, cy), (x + w - pad, cy), 1)
        cy += 10

        # ── Job Board ─────────────────────────────────────────────────────────
        hdr = self._font_header.render("JOB BOARD", True, COLOR_ACCENT)
        self.surface.blit(hdr, (x + pad, cy))
        cy += hdr.get_height() + 6

        self._job_rects = []
        if not available_contracts:
            hint = self._font_small.render("No jobs available — dock to refresh.", True, COLOR_TEXT_DIM)
            self.surface.blit(hint, (x + pad, cy))
            cy += 20
        else:
            for c in available_contracts[:4]:
                cy = self._draw_contract_row(x, cy, w, c, career, job_board)
                cy += 4

        pygame.draw.line(self.surface, COLOR_FRAME, (x + pad, cy), (x + w - pad, cy), 1)
        cy += 10

        # ── Active Contract ────────────────────────────────────────────────────
        hdr = self._font_header.render("ACTIVE CONTRACT", True, COLOR_ACCENT)
        self.surface.blit(hdr, (x + pad, cy))
        cy += hdr.get_height() + 6

        if active_contract is None:
            none_surf = self._font_small.render("No active contract.", True, COLOR_TEXT_DIM)
            self.surface.blit(none_surf, (x + pad, cy))
            cy += 20
        else:
            c = active_contract
            tc = _JOB_TYPE_COLORS.get(c.job_type, COLOR_ACCENT)
            tag = self._font_small.render(c.job_type.upper().replace("_", " "), True, tc)
            self.surface.blit(tag, (x + pad, cy));  cy += tag.get_height() + 2

            route_text = _truncate_text(
                f"{c.from_port} → {c.to_port}",
                self._font_label, w - pad * 2)
            route_surf = self._font_label.render(route_text, True, COLOR_TEXT_PRIMARY)
            self.surface.blit(route_surf, (x + pad, cy));  cy += route_surf.get_height() + 2

            pay_surf = self._font_small.render(f"Payout: \xa3{c.payout:.0f}", True, (80, 220, 120))
            self.surface.blit(pay_surf, (x + pad, cy));  cy += pay_surf.get_height() + 2

            # Special-requirement line for hazmat/charter contracts.
            if getattr(c, "description", ""):
                desc_surf = self._font_small.render(
                    _truncate_text(c.description, self._font_small, w - pad * 2),
                    True, (220, 165, 50))
                self.surface.blit(desc_surf, (x + pad, cy));  cy += desc_surf.get_height() + 2

            deadline_s  = c.accepted_at_sim_s + c.deadline_sim_hours * 3600.0
            remaining_s = deadline_s - sim_elapsed_s
            if remaining_s > 0:
                h_l = int(remaining_s // 3600)
                m_l = int((remaining_s % 3600) // 60)
                dl_text = (f"Time left: {h_l}h {m_l:02d}m" if h_l
                           else f"Time left: {m_l}m")
                dl_col = (255, 80, 80) if remaining_s < 3600 else (220, 165, 50)
            else:
                dl_text = "DEADLINE MISSED"
                dl_col  = (255, 80, 80)
            dl_surf = self._font_small.render(dl_text, True, dl_col)
            self.surface.blit(dl_surf, (x + pad, cy))
            cy += dl_surf.get_height() + 4

        # ── Achievements ──────────────────────────────────────────────────────
        cy += 8
        pygame.draw.line(self.surface, COLOR_FRAME, (x + pad, cy), (x + w - pad, cy), 1)
        cy += 10
        hdr = self._font_header.render("ACHIEVEMENTS", True, COLOR_ACCENT)
        self.surface.blit(hdr, (x + pad, cy))
        cy += hdr.get_height() + 6
        for name, how in ACHIEVEMENT_DEFS:
            unlocked = name in getattr(career, "achievements", set())
            mark = "✓" if unlocked else "·"
            col = (80, 220, 120) if unlocked else COLOR_TEXT_DIM
            row_txt = _truncate_text(f"{mark} {name} — {how}",
                                     self._font_small, w - pad * 2)
            row_surf = self._font_small.render(row_txt, True, col)
            self.surface.blit(row_surf, (x + pad, cy))
            cy += 18

    # ----------------------------------------------------------------- helpers

    def _draw_contract_row(self, panel_x: int, cy: int, panel_w: int,
                           contract, career, job_board) -> int:
        """Draw one job-board contract row; append clickable rect. Returns new cy."""
        pad = self.PAD
        rx  = panel_x + pad
        rw  = panel_w - pad * 2
        rh  = self.ROW_H

        can_accept = (job_board.active is None
                      and career.reputation >= contract.reputation_required)

        # Row background
        row_bg = pygame.Surface((rw, rh), pygame.SRCALPHA)
        row_bg.fill((20, 40, 60, 160 if can_accept else 70))
        self.surface.blit(row_bg, (rx, cy))
        pygame.draw.rect(self.surface, COLOR_FRAME if can_accept else (40, 40, 50),
                         (rx, cy, rw, rh), 1)

        tc = _JOB_TYPE_COLORS.get(contract.job_type, COLOR_ACCENT)
        tag_surf = self._font_small.render(
            contract.job_type.upper().replace("_", " "), True, tc)
        self.surface.blit(tag_surf, (rx + 4, cy + 4))

        route_txt = _truncate_text(
            f"{contract.from_port} → {contract.to_port}",
            self._font_small, rw - 80)
        route_surf = self._font_small.render(route_txt, True, COLOR_TEXT_PRIMARY)
        self.surface.blit(route_surf, (rx + 4, cy + 4 + tag_surf.get_height() + 2))

        detail_txt = f"\xa3{contract.payout:.0f}  |  {int(contract.deadline_sim_hours)}h"
        _note = _JOB_SPECIAL_NOTES.get(contract.job_type)
        if _note:
            detail_txt += f"  |  {_note}"
        detail_surf = self._font_small.render(detail_txt, True, COLOR_TEXT_SECONDARY)
        detail_y = cy + 4 + tag_surf.get_height() + 2 + route_surf.get_height() + 2
        self.surface.blit(detail_surf, (rx + 4, detail_y))

        # ACCEPT button
        btn_w, btn_h = 62, 22
        btn_x = rx + rw - btn_w - 4
        btn_y = cy + (rh - btn_h) // 2
        btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)

        if can_accept:
            pygame.draw.rect(self.surface, (15, 70, 35), btn_rect, border_radius=4)
            pygame.draw.rect(self.surface, (80, 200, 120), btn_rect, 1, border_radius=4)
            lbl_surf = self._font_small.render("ACCEPT", True, (80, 220, 120))
            self._job_rects.append((btn_rect, contract))
        elif career.reputation < contract.reputation_required:
            pygame.draw.rect(self.surface, (30, 30, 40), btn_rect, border_radius=4)
            pygame.draw.rect(self.surface, (60, 60, 70), btn_rect, 1, border_radius=4)
            lbl_surf = self._font_small.render(
                f"REP {contract.reputation_required}+", True, (80, 80, 100))
        else:
            pygame.draw.rect(self.surface, (30, 30, 40), btn_rect, border_radius=4)
            pygame.draw.rect(self.surface, (60, 60, 70), btn_rect, 1, border_radius=4)
            lbl_surf = self._font_small.render("BUSY", True, (80, 80, 100))

        self.surface.blit(lbl_surf, (
            btn_x + btn_w // 2 - lbl_surf.get_width() // 2,
            btn_y + btn_h // 2 - lbl_surf.get_height() // 2,
        ))

        return cy + rh

    def _lv(self, px: int, y: int, pw: int, label: str, value: str,
            value_color: tuple = None) -> None:
        """Draw a label/value pair spanning the panel width."""
        if value_color is None:
            value_color = COLOR_TEXT_PRIMARY
        pad  = self.PAD
        iw   = pw - pad * 2
        lbl  = self._font_label.render(label, True, COLOR_TEXT_SECONDARY)
        val  = self._font_value.render(value, True, value_color)
        self.surface.blit(lbl, (px + pad, y))
        self.surface.blit(val, (px + pad + iw - val.get_width(), y - 2))


# ---------------------------------------------------------------------------
# Minimap
# ---------------------------------------------------------------------------

class MinimapPanel:
    """Fixed-zoom overview of the whole sea in the bottom-right corner.

    Static content (water, islands, port squares) is rendered once into a
    cached surface; per-frame work is one blit plus the live player dot.
    Toggled with the M key.
    """

    def __init__(self, surface: pygame.Surface) -> None:
        self.surface = surface
        self.is_visible = True
        self._static: Optional[pygame.Surface] = None

    # Scale factors world → minimap pixels.
    _SX = MINIMAP_WIDTH_PX / WORLD_WIDTH
    _SY = MINIMAP_HEIGHT_PX / WORLD_HEIGHT

    def _build_static(self, world) -> pygame.Surface:
        surf = pygame.Surface((MINIMAP_WIDTH_PX, MINIMAP_HEIGHT_PX), pygame.SRCALPHA)
        surf.fill((*COLOR_WATER, 235))
        for island in world.islands:
            pts = [(int(x * self._SX), int(y * self._SY)) for x, y in island.polygon]
            if len(pts) >= 3:
                fill = LAND_COLORS.get(island.land_type, LAND_COLORS["island"])["fill"]
                pygame.draw.polygon(surf, fill, pts)
        for port in world.ports:
            px = int(port.position[0] * self._SX)
            py = int(port.position[1] * self._SY)
            pygame.draw.rect(surf, COLOR_ACCENT, (px - 1, py - 1, 3, 3))
        pygame.draw.rect(surf, COLOR_PANEL_BORDER, surf.get_rect(), 1)
        return surf

    def draw(self, world, player) -> None:
        if not self.is_visible or world is None:
            return
        if self._static is None:
            self._static = self._build_static(world)

        vw, vh = self.surface.get_size()
        x = vw - MINIMAP_WIDTH_PX - MINIMAP_MARGIN_PX
        y = vh - MINIMAP_HEIGHT_PX - MINIMAP_MARGIN_PX
        self.surface.blit(self._static, (x, y))

        if player is not None:
            px = x + int(player.position[0] * self._SX)
            py = y + int(player.position[1] * self._SY)
            pygame.gfxdraw.filled_circle(self.surface, px, py, 2, COLOR_ACCENT)
            pygame.gfxdraw.aacircle(self.surface, px, py, 4, COLOR_ACCENT)


# ---------------------------------------------------------------------------
# Controls screen (reachable from the title menu)
# ---------------------------------------------------------------------------

class ControlsScreen:
    """Full keybinding table shown from the title menu; ESC dismisses it."""

    BINDINGS = [
        ("W / S",        "Throttle up / down"),
        ("A / D",        "Steer port / starboard"),
        ("Right-click",  "Set autopilot waypoint (click a port to target it)"),
        ("F",            "Toggle follow camera"),
        ("J",            "Career panel & job board"),
        ("M",            "Toggle minimap"),
        ("E",            "Environment settings"),
        ("T",            "Technical systems panel"),
        ("Tab",          "Cycle vessel selection"),
        ("Space",        "Pause  (in port: depart)"),
        ("1 / 2 / 3 / 4", "Time speed: pause / 1× / 2× / 3×"),
        ("Z",            "Reset zoom"),
        ("Mouse drag",   "Pan the chart"),
        ("Mouse wheel",  "Zoom at cursor"),
        ("R",            "Restart (after game over)"),
        ("Esc",          "Quit"),
    ]

    def __init__(self, surface: pygame.Surface) -> None:
        self.surface = surface
        self._font_title = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_TITLE, bold=True)
        self._font_key   = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_LABEL, bold=True)
        self._font_desc  = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_LABEL)
        self._font_hint  = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_SMALL)

    def draw(self) -> None:
        vw, vh = self.surface.get_size()
        row_h = 26
        w = 560
        h = 110 + len(self.BINDINGS) * row_h
        x = vw // 2 - w // 2
        y = vh // 2 - h // 2

        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(panel, (*COLOR_PANEL_BG[:3], TITLE_PANEL_ALPHA),
                         panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, COLOR_PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.surface.blit(panel, (x, y))

        cy = y + 24
        title = self._font_title.render("CONTROLS", True, COLOR_ACCENT)
        self.surface.blit(title, (vw // 2 - title.get_width() // 2, cy))
        cy += title.get_height() + 18

        for key, desc in self.BINDINGS:
            key_surf = self._font_key.render(key, True, COLOR_TEXT_PRIMARY)
            desc_surf = self._font_desc.render(desc, True, COLOR_TEXT_SECONDARY)
            self.surface.blit(key_surf, (x + 36, cy))
            self.surface.blit(desc_surf, (x + 200, cy))
            cy += row_h

        hint = self._font_hint.render("ESC to return", True, COLOR_TEXT_DIM)
        self.surface.blit(hint, (vw // 2 - hint.get_width() // 2, y + h - 30))


# ---------------------------------------------------------------------------
# Docking menu
# ---------------------------------------------------------------------------

class DockingMenuPanel:
    """Centered port-services menu shown automatically while the player is in port.

    The panel never mutates game state: Game asks selected_action()/handle_click()
    which action the player chose and applies the purchase/departure itself.
    Game sets .visible each sim step from the player vessel's status.
    """

    WIDTH  = 380
    PAD    = 16
    ROW_H  = 44

    def __init__(self, surface: pygame.Surface) -> None:
        self.surface = surface
        self.visible = False
        self.selected_index = 0
        self.panel_rect: Optional[pygame.Rect] = None
        self._item_rects: list = []   # [(pygame.Rect, action, enabled), ...]

        self._font_title = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_TITLE,   bold=True)
        self._font_item  = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_SECTION, bold=True)
        self._font_cost  = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_LABEL,   bold=True)
        self._font_hint  = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_SMALL)

    # ------------------------------------------------------------------ costs

    @staticmethod
    def fuel_cost(vessel) -> float:
        """£ to refill the tank: missing percentage points × FUEL_COST_PER_UNIT."""
        if vessel is None or vessel.fuel is None or not vessel.fuel_capacity:
            return 0.0
        missing_pct = (1.0 - vessel.fuel / vessel.fuel_capacity) * 100.0
        return round(missing_pct) * FUEL_COST_PER_UNIT

    @staticmethod
    def repair_cost(vessel) -> float:
        """£ to restore the hull: same per-point formula the career system uses."""
        hull = getattr(vessel, "hull_integrity", 1.0)
        return round((1.0 - hull) * 100.0) * HULL_REPAIR_COST_PER_POINT

    # ------------------------------------------------------------------ input

    def move_selection(self, delta: int) -> None:
        self.selected_index = (self.selected_index + delta) % 4

    def _menu_items(self, vessel, career) -> list:
        """Return [(label, cost_text, action, enabled, unaffordable), ...]."""
        items = []

        fc = self.fuel_cost(vessel)
        if fc <= 0:
            items.append(("FUEL", "TANK FULL", "fuel", False, False))
        else:
            afford = career.money >= fc
            items.append(("FUEL", f"\xa3{fc:.0f}", "fuel", afford, not afford))

        rc = self.repair_cost(vessel)
        if rc <= 0:
            items.append(("REPAIR HULL", "NO DAMAGE", "repair", False, False))
        else:
            afford = career.money >= rc
            items.append(("REPAIR HULL", f"\xa3{rc:.0f}", "repair", afford, not afford))

        items.append(("JOB BOARD", "", "jobs", True, False))
        items.append(("DEPART", "", "depart", True, False))
        return items

    def selected_action(self, vessel, career) -> Optional[str]:
        """Return the action of the highlighted row, or None when it's disabled."""
        items = self._menu_items(vessel, career)
        label, cost, action, enabled, _ = items[self.selected_index % len(items)]
        return action if enabled else None

    def handle_click(self, screen_pos, vessel, career) -> Optional[str]:
        """Return the action of an enabled row under the cursor, or None."""
        for rect, action, enabled in self._item_rects:
            if rect.collidepoint(screen_pos) and enabled:
                return action
        return None

    # ------------------------------------------------------------------ draw

    def draw(self, vessel, port_name: str, career) -> None:
        if not self.visible or vessel is None or career is None:
            return

        items = self._menu_items(vessel, career)
        vw, vh = self.surface.get_size()
        pad = self.PAD
        w   = self.WIDTH
        h   = pad * 2 + self._font_title.get_height() + 14 + len(items) * (self.ROW_H + 6) + 24
        x   = vw // 2 - w // 2
        y   = vh // 2 - h // 2
        self.panel_rect = pygame.Rect(x, y, w, h)

        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(bg, (*COLOR_PANEL_BG[:3], 235), bg.get_rect(), border_radius=14)
        pygame.draw.rect(bg, COLOR_ACCENT, bg.get_rect(), 2, border_radius=14)
        self.surface.blit(bg, (x, y))

        cy = y + pad
        title_surf = self._font_title.render(port_name, True, COLOR_ACCENT)
        self.surface.blit(title_surf, (x + w // 2 - title_surf.get_width() // 2, cy))
        cy += title_surf.get_height() + 14

        self._item_rects = []
        for i, (label, cost_text, action, enabled, unaffordable) in enumerate(items):
            row_rect = pygame.Rect(x + pad, cy, w - pad * 2, self.ROW_H)
            self._item_rects.append((row_rect, action, enabled))

            if i == self.selected_index:
                hl = pygame.Surface(row_rect.size, pygame.SRCALPHA)
                hl.fill((255, 255, 255, 18))
                self.surface.blit(hl, row_rect.topleft)
                pygame.draw.rect(self.surface, COLOR_ACCENT, row_rect, 1, border_radius=6)
            else:
                pygame.draw.rect(self.surface, COLOR_FRAME, row_rect, 1, border_radius=6)

            lbl_col = COLOR_TEXT_PRIMARY if enabled else COLOR_TEXT_DIM
            lbl_surf = self._font_item.render(label, True, lbl_col)
            self.surface.blit(lbl_surf,
                              (row_rect.x + 12,
                               row_rect.centery - lbl_surf.get_height() // 2))

            if cost_text:
                cost_col = (COLOR_WARNING if unaffordable
                            else COLOR_TEXT_SECONDARY if not enabled
                            else (80, 220, 120))
                cost_surf = self._font_cost.render(cost_text, True, cost_col)
                self.surface.blit(cost_surf,
                                  (row_rect.right - cost_surf.get_width() - 12,
                                   row_rect.centery - cost_surf.get_height() // 2))

            cy += self.ROW_H + 6

        hint = "UP/DOWN select  |  ENTER confirm  |  W or SPACE depart"
        hint_surf = self._font_hint.render(hint, True, COLOR_TEXT_DIM)
        self.surface.blit(hint_surf, (x + w // 2 - hint_surf.get_width() // 2, cy + 4))


# ---------------------------------------------------------------------------
# Title screen
# ---------------------------------------------------------------------------

class TitleScreen:
    """Main-menu overlay drawn over the live chart before the game starts.

    The caller owns the loop: it draws the chart first, then calls draw(),
    and feeds KEYDOWN events to handle_key().  handle_key() returns an action
    string ("new" | "continue" | "quit") when a menu item is confirmed, or
    None while the player is still browsing.
    """

    # (label, action) in display order.  "Continue" is greyed out when no
    # save file exists; confirming it then is a no-op.
    MENU_ITEMS = [
        ("New Career", "new"),
        ("Continue",   "continue"),
        ("Controls",   "controls"),
        ("Quit",       "quit"),
    ]

    def __init__(self, surface: pygame.Surface) -> None:
        self.surface = surface
        self.selected_index = 0
        self._font_title    = pygame.font.SysFont(FONT_UI_NAME, TITLE_FONT_SIZE,    bold=True)
        self._font_subtitle = pygame.font.SysFont(FONT_UI_NAME, TITLE_SUBTITLE_SIZE)
        self._font_menu     = pygame.font.SysFont(FONT_UI_NAME, TITLE_MENU_FONT_SIZE, bold=True)
        self._font_hint     = pygame.font.SysFont(FONT_UI_NAME, FONT_SIZE_SMALL)

    def handle_key(self, key: int, has_save: bool):
        """Process one KEYDOWN. Returns an action string on confirm, else None."""
        n = len(self.MENU_ITEMS)
        if key == pygame.K_UP:
            self.selected_index = (self.selected_index - 1) % n
        elif key == pygame.K_DOWN:
            self.selected_index = (self.selected_index + 1) % n
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            action = self.MENU_ITEMS[self.selected_index][1]
            # Continue without a save is disabled — stay on the title.
            if action == "continue" and not has_save:
                return None
            return action
        elif key == pygame.K_ESCAPE:
            return "quit"
        return None

    def draw(self, has_save: bool) -> None:
        vw, vh = self.surface.get_size()
        w, h = TITLE_PANEL_WIDTH, TITLE_PANEL_HEIGHT
        x = vw // 2 - w // 2
        y = vh // 2 - h // 2

        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(panel, (*COLOR_PANEL_BG[:3], TITLE_PANEL_ALPHA),
                         panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, COLOR_PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.surface.blit(panel, (x, y))

        cy = y + 44

        title_surf = self._font_title.render("MERIDIAN SEA", True, COLOR_ACCENT)
        self.surface.blit(title_surf, (vw // 2 - title_surf.get_width() // 2, cy))
        cy += title_surf.get_height() + 6

        sub_surf = self._font_subtitle.render(
            "A Maritime Career Simulator", True, COLOR_TEXT_SECONDARY)
        self.surface.blit(sub_surf, (vw // 2 - sub_surf.get_width() // 2, cy))
        cy += sub_surf.get_height() + 40

        for i, (label, action) in enumerate(self.MENU_ITEMS):
            disabled = (action == "continue" and not has_save)
            display = f"{label}  [no save]" if disabled else label
            if disabled:
                col = COLOR_TEXT_DIM
            elif i == self.selected_index:
                col = COLOR_ACCENT
            else:
                col = COLOR_TEXT_PRIMARY

            item_surf = self._font_menu.render(display, True, col)
            ix = vw // 2 - item_surf.get_width() // 2
            # Selection highlight bar behind the focused row.
            if i == self.selected_index:
                hl = pygame.Surface((w - 80, item_surf.get_height() + 10), pygame.SRCALPHA)
                hl.fill((255, 255, 255, 18))
                self.surface.blit(hl, (x + 40, cy - 5))
                pygame.draw.rect(self.surface, COLOR_ACCENT,
                                 (x + 40, cy - 5, w - 80, item_surf.get_height() + 10),
                                 1, border_radius=6)
            self.surface.blit(item_surf, (ix, cy))
            cy += item_surf.get_height() + 22

        hint = f"v{GAME_VERSION}  |  Arrow keys to select  |  ENTER to confirm"
        hint_surf = self._font_hint.render(hint, True, COLOR_TEXT_DIM)
        self.surface.blit(hint_surf,
                          (vw // 2 - hint_surf.get_width() // 2, y + h - hint_surf.get_height() - 16))


# ---------------------------------------------------------------------------
# Game Over screen
# ---------------------------------------------------------------------------

def _fmt_session(seconds: float) -> str:
    """Format session seconds as 'Xh Ym' or 'Ym'."""
    m = int(seconds // 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


class GameOverScreen:
    """Full-screen overlay shown when the player vessel is lost.

    Displays the reason, career statistics, and restart / quit prompts.
    """

    def __init__(self, surface: pygame.Surface) -> None:
        self.surface = surface
        self._font_big   = pygame.font.SysFont(FONT_UI_NAME,   64, bold=True)
        self._font_sub   = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_TITLE, bold=True)
        self._font_stats = pygame.font.SysFont(FONT_DATA_NAME, FONT_SIZE_DATA)
        self._font_hint  = pygame.font.SysFont(FONT_UI_NAME,   FONT_SIZE_LABEL)

    def draw(self, reason: str, career, session_seconds: float) -> None:
        vw, vh = self.surface.get_size()

        # Dark overlay
        overlay = pygame.Surface((vw, vh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 210))
        self.surface.blit(overlay, (0, 0))

        cy = vh // 2 - 120

        # "VESSEL LOST"
        title_surf = self._font_big.render("VESSEL LOST", True, COLOR_WARNING)
        self.surface.blit(title_surf,
                          (vw // 2 - title_surf.get_width() // 2, cy))
        cy += title_surf.get_height() + 10

        # Reason
        reason_surf = self._font_sub.render(reason, True, COLOR_TEXT_SECONDARY)
        self.surface.blit(reason_surf,
                          (vw // 2 - reason_surf.get_width() // 2, cy))
        cy += reason_surf.get_height() + 28

        # Stats
        stats = [
            ("Final balance",   f"\xa3{career.money:.0f}"),
            ("Deliveries",      str(career.total_deliveries)),
            ("Fines paid",      f"\xa3{career.fines_paid:.0f}"),
            ("Hull repairs",    f"\xa3{career.hull_repairs_paid:.0f}"),
            ("Session time",    _fmt_session(session_seconds)),
        ]
        for label, value in stats:
            line_surf = self._font_stats.render(
                f"{label}:  {value}", True, COLOR_TEXT_PRIMARY)
            self.surface.blit(line_surf,
                              (vw // 2 - line_surf.get_width() // 2, cy))
            cy += line_surf.get_height() + 6

        cy += 20
        hint_surf = self._font_hint.render(
            "Press R to restart  |  ESC to quit", True, COLOR_TEXT_DIM)
        self.surface.blit(hint_surf,
                          (vw // 2 - hint_surf.get_width() // 2, cy))
