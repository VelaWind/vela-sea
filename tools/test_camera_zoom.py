"""Headless unit test for Camera.zoom_at behavior.

Creates a Camera, picks a world point, computes screen_pos, performs zoom_at,
then checks that the same world point maps back to the same screen_pos.
"""
import sys
from pathlib import Path

# Ensure project root is on sys.path for local package imports
PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from render.camera import Camera

CAM_W = 800
CAM_H = 600

def approx_equal(a, b, eps=1e-6):
    return abs(a - b) <= eps


def run_test():
    cam = Camera(CAM_W, CAM_H)

    # choose an arbitrary world point (e.g., a port)
    port_world = (520.0, 360.0)

    # find where it lies on screen
    screen_pos = cam.world_to_screen(port_world)

    # zoom in and keep the cursor fixed over that screen_pos
    cam.zoom_at(screen_pos, 1.25)

    # after zoom, the world point under the same screen_pos should equal port_world
    world_after = cam.screen_to_world(screen_pos)

    print('port_world    =', port_world)
    print('world_after   =', world_after)

    ok_x = approx_equal(port_world[0], world_after[0], eps=1e-8)
    ok_y = approx_equal(port_world[1], world_after[1], eps=1e-8)

    if ok_x and ok_y:
        print('TEST PASS: world point stayed under cursor after zoom')
        return 0
    else:
        print('TEST FAIL: point moved under cursor')
        return 2

if __name__ == '__main__':
    raise SystemExit(run_test())
