"""
Headless screenshot: run one frame of the simulator in SDL dummy mode,
save what the chart renders to a PNG, then exit.
No real window needed — everything goes to an off-screen surface.
"""
import os, sys
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, r"d:\gps-simulator")

import pygame
pygame.init()

SCREEN_W, SCREEN_H = 1600, 900
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))

from render.camera import Camera
from render.chart import Chart
from engine.world import World
from engine.environment import Environment
from engine.ship import Vessel
from engine.collision import update_collision_avoidance
from data.world_data import populate_world, VESSEL_ROUTE_CARGO, VESSEL_ROUTE_FERRY
from config import PORT_STAY_CARGO_S, PORT_STAY_FERRY_S

world = World()
populate_world(world)

env = Environment()
env.time_speed_multiplier = 1.0

# Add two vessels: one underway, one that will be in avoiding status
cargo = Vessel(
    name="MV Tidewater", vessel_type="cargo",
    position=(105.0, 315.0), heading=90.0,
    target_speed=8.0, current_speed=8.0,
    max_speed=12.0, acceleration=0.020, deceleration=0.017,
    turn_rate=1.0, length_m=150.0, beam_m=25.0, draft_m=8.0,
    fuel=100.0, fuel_capacity=100.0, fuel_consumption_rate=3.5,
    route=VESSEL_ROUTE_CARGO, route_index=0,
    port_stay_duration=PORT_STAY_CARGO_S,
    destination=VESSEL_ROUTE_CARGO[0],
)
world.add_vessel(cargo)

# Force one vessel into avoiding to show amber colour
from config import NM_PER_WORLD_UNIT
SEP_WU = 1.0 / NM_PER_WORLD_UNIT   # 1 nm
v_a = Vessel(
    name="MS Coastal Express", vessel_type="ferry",
    position=(400.0, 400.0), heading=0.0,
    target_speed=10.0, current_speed=10.0,
    max_speed=14.0, acceleration=0.08, deceleration=0.04,
    turn_rate=2.0, length_m=80.0, beam_m=15.0, draft_m=4.0,
    fuel=80.0, fuel_capacity=80.0, fuel_consumption_rate=5.0,
    route=VESSEL_ROUTE_FERRY, route_index=3,
    port_stay_duration=PORT_STAY_FERRY_S,
    destination=VESSEL_ROUTE_FERRY[3],
)
v_b = Vessel(
    name="FV Horizon", vessel_type="fishing",
    position=(400.0 + SEP_WU, 400.0), heading=180.0,
    target_speed=8.0, current_speed=8.0,
    max_speed=10.0, acceleration=0.10, deceleration=0.06,
    turn_rate=3.0, length_m=40.0, beam_m=8.0, draft_m=3.0,
    fuel=50.0, fuel_capacity=50.0, fuel_consumption_rate=2.8,
    route=[], route_index=0, port_stay_duration=0,
)
world.add_vessel(v_a)
world.add_vessel(v_b)

# Tick collision avoidance so v_a becomes "avoiding"
update_collision_avoidance(world.vessels)
print(f"v_a status after avoidance tick: {v_a.status}  avoid_heading={v_a.avoid_heading:.1f}")

camera = Camera(SCREEN_W, SCREEN_H)
chart = Chart(screen, camera)

# ---- Screenshot 1: full chart at 1x ----
screen.fill((10, 28, 52))
chart.draw_all(world=world, environment=env, selected_vessel=None)
pygame.image.save(screen, r"d:\gps-simulator\tests\screenshot_1x.png")
print("Saved screenshot_1x.png")

# ---- Screenshot 2: with a selected vessel ----
screen.fill((10, 28, 52))
chart.draw_all(world=world, environment=env, selected_vessel=cargo)
pygame.image.save(screen, r"d:\gps-simulator\tests\screenshot_selected.png")
print("Saved screenshot_selected.png")

# ---- Screenshot 3: zoom into the avoiding vessels ----
# Centre camera on the head-on encounter area
camera.position = (v_a.position[0] + SEP_WU / 2, v_a.position[1])
camera.zoom = 4.0
screen.fill((10, 28, 52))
chart.draw_all(world=world, environment=env, selected_vessel=None)
pygame.image.save(screen, r"d:\gps-simulator\tests\screenshot_avoiding.png")
print("Saved screenshot_avoiding.png  (zoomed on avoiding vessel)")

pygame.quit()
