"""Scale bar and range rings show true nautical miles (KNOWN_ISSUES #15).

The bug: chart code passed nautical miles to Camera.distance_to_screen, which
takes world units (1 wu = NM_PER_WORLD_UNIT nm), so every distance read about
6.7 times too short.  These tests convert known world distances and check the
label the chart would print, then run the chart's real drawing code.
"""

import os
import sys
sys.path.insert(0, ".")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from render.camera import Camera, choose_scale_nm, scale_label
from config import (NM_PER_WORLD_UNIT, ZOOM_MIN, ZOOM_MAX,
                    SCALE_BAR_TARGET_WIDTH, SCALE_BAR_MAX_WIDTH,
                    SCALE_BAR_CANDIDATES_NM, SHIP_RANGE_RING_COUNT)

ZOOMS = (ZOOM_MIN, 0.5, 1.0, 1.5, 1.8, 2.5, ZOOM_MAX)


def test_known_world_distance_converts_to_true_nm():
    cam = Camera(1600, 900)
    cam.zoom = 1.5
    # 200 world units (one chart grid square) is exactly 30 nm.
    world_wu = 200.0
    nm = world_wu * NM_PER_WORLD_UNIT
    assert nm == 30.0
    assert cam.nm_to_screen(nm) == cam.distance_to_screen(world_wu) == 300.0
    assert scale_label(nm) == "30 nm"


def test_scale_bar_pick_is_true_at_every_zoom():
    cam = Camera(1600, 900)
    for z in ZOOMS:
        cam.zoom = z
        nm = choose_scale_nm(cam.nm_to_screen(1.0), SCALE_BAR_TARGET_WIDTH,
                             SCALE_BAR_MAX_WIDTH, SCALE_BAR_CANDIDATES_NM)
        px = cam.nm_to_screen(nm)
        # The drawn length must equal the labelled distance in world units.
        assert abs(px - (nm / NM_PER_WORLD_UNIT) * z) < 1e-9
        assert 40 <= px <= SCALE_BAR_MAX_WIDTH, (z, nm, px)


def test_zoom_min_shows_50_nm_bar_at_133_px():
    cam = Camera(1600, 900)
    cam.zoom = ZOOM_MIN   # 0.4 px per wu: 50 nm = 333.3 wu = 133.3 px
    nm = choose_scale_nm(cam.nm_to_screen(1.0), SCALE_BAR_TARGET_WIDTH,
                         SCALE_BAR_MAX_WIDTH, SCALE_BAR_CANDIDATES_NM)
    assert scale_label(nm) == "50 nm"
    assert round(cam.nm_to_screen(nm), 1) == 133.3


def _chart(zoom):
    pygame.init()
    surface = pygame.Surface((1600, 900))
    from render.chart import Chart
    cam = Camera(1600, 900)
    cam.zoom = zoom
    return Chart(surface, cam), cam


def test_chart_scale_bar_draws_true_length_and_label():
    """Run the real Chart.draw_scale_bar and check what it paints."""
    for z in ZOOMS:
        chart, cam = _chart(z)
        painted = {}
        chart._paint_scale_bar = (
            lambda x, y, px, nm: painted.update(px=px, nm=nm))
        chart.draw_scale_bar()
        true_px = painted["nm"] / NM_PER_WORLD_UNIT * z
        assert abs(painted["px"] - true_px) <= 0.5, (z, painted, true_px)


def test_chart_range_rings_draw_true_radii_and_labels():
    """Run the real Chart.draw_vessel and check every ring's radius and label."""
    from engine.ship import Vessel
    import render.chart as chart_mod
    for z in ZOOMS:
        chart, cam = _chart(z)
        v = Vessel(name="Ringer", vessel_type="cargo",
                   position=cam.position, heading=0.0, target_speed=0.0,
                   current_speed=0.0, max_speed=10.0, acceleration=1.0,
                   deceleration=1.0,
                   turn_rate=5.0, length_m=50.0, beam_m=10.0, draft_m=3.0,
                   fuel=10.0, fuel_capacity=20.0, fuel_consumption_rate=1.0)
        radii, labels = [], []
        real_circle = chart_mod.pygame.gfxdraw.aacircle
        real_font = chart.font_mono
        cx, cy = (int(c) for c in cam.world_to_screen(v.position))

        def circle(surf, x, y, r, col):
            if (x, y) == (cx, cy):
                radii.append(r)
            return real_circle(surf, x, y, r, col)

        class RecordingFont:
            """Stands in for the chart's mono font and records label text."""
            def render(self, text, *a, **k):
                if text.endswith(" nm"):
                    labels.append(text)
                return real_font.render(text, *a, **k)

            def __getattr__(self, name):
                return getattr(real_font, name)

        chart_mod.pygame.gfxdraw.aacircle = circle
        chart.font_mono = RecordingFont()
        try:
            chart.draw_vessel(v, selected=True)
        finally:
            chart_mod.pygame.gfxdraw.aacircle = real_circle
        ring_labels = labels[:SHIP_RANGE_RING_COUNT]
        assert len(ring_labels) == SHIP_RANGE_RING_COUNT, (z, labels)
        for label in ring_labels:
            nm = float(label.split()[0])
            true_r = int(nm / NM_PER_WORLD_UNIT * z)
            assert true_r in radii, (z, label, true_r, radii)
