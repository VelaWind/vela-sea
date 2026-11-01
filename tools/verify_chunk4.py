import os
import sys
import pygame
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import (
    ZOOM_MIN,
    ZOOM_MAX,
    SCALE_BAR_MAX_WIDTH,
    SCALE_BAR_TARGET_WIDTH,
    SCALE_BAR_CANDIDATES_NM,
    SHIP_RANGE_RING_CANDIDATES_NM,
    SHIP_RANGE_RING_TARGET_PX,
    SHIP_RANGE_RING_COUNT,
)
from render.camera import Camera, choose_scale_nm
from render.chart import Chart
from main import Game
from engine.ship import Vessel

os.environ['SDL_VIDEODRIVER'] = 'dummy'
pygame.init()

cam = Camera(1600, 950)

# Uses the chart's own functions (render/camera.py) rather than a copy, so this
# script can no longer drift from what the chart draws (the old copy carried
# the nm-vs-world-unit bug, KNOWN_ISSUES #15).
def choose_scale(zoom):
    cam.zoom = zoom
    nm = choose_scale_nm(cam.nm_to_screen(1.0), SCALE_BAR_TARGET_WIDTH,
                         SCALE_BAR_MAX_WIDTH, SCALE_BAR_CANDIDATES_NM)
    return nm, cam.nm_to_screen(nm)

low_dist, low_px = choose_scale(ZOOM_MIN)
high_dist, high_px = choose_scale(ZOOM_MAX)
print(f'zoom={ZOOM_MIN} -> {low_dist} nm, {low_px:.1f} px')
print(f'zoom={ZOOM_MAX} -> {high_dist} nm, {high_px:.1f} px')

v = Vessel(
    name='Test', vessel_type='generic', position=(500.0, 350.0), heading=0.0,
    target_speed=0.0, current_speed=0.0, max_speed=10.0, acceleration=1.0,
    turn_rate=5.0, length_m=50.0, beam_m=10.0, draft_m=3.0,
    fuel=10.0, fuel_capacity=20.0, fuel_consumption_rate=1.0,
)
for status in ['underway', 'docked', 'aground']:
    v.status = status
    screen_pos = cam.world_to_screen(v.position)
    assert screen_pos == (800.0, 475.0)
    ring_info = []
    ring_nm = choose_scale_nm(cam.nm_to_screen(1.0), SHIP_RANGE_RING_TARGET_PX,
                              float("inf"), SHIP_RANGE_RING_CANDIDATES_NM)
    for ring_index in range(1, SHIP_RANGE_RING_COUNT + 1):
        nm_radius = ring_index * ring_nm
        px_radius = cam.nm_to_screen(nm_radius)
        ring_info.append((nm_radius, px_radius))
    print(f'status={status} ring radii: {ring_info}')

v.status = 'docked'
v.current_speed = 0.0
print('predictor_drawn_docked', v.current_speed > 0 and v.status == 'underway')
v.status = 'underway'
v.current_speed = 5.0
print('predictor_drawn_underway', v.current_speed > 0 and v.status == 'underway')

# Render one offscreen frame with a selected vessel.
game = Game()
game.selected_vessel = game.world.vessels[0]

surface = pygame.Surface((1600, 950))
chart = Chart(surface, game.camera)
chart.draw_all(world=game.world, environment=game.environment, selected_vessel=game.selected_vessel)
pygame.image.save(surface, os.path.join(os.path.dirname(__file__), '..', 'debug_frame.png'))
print('debug_frame.png written')
