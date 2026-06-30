"""Camera class: handles world↔screen coordinate conversion, zoom, and pan.

This is the single point of truth for translating between the fictional
world (nautical units) and the screen (pixels). Centralizing this prevents
the "where did my click go" bugs that plague games.

The camera is defined by:
- position: where in the world the camera center is
- zoom: how many pixels per world unit (>1 = zoomed in, <1 = zoomed out)
- viewport: the window dimensions in pixels
"""

from dataclasses import dataclass
from typing import Tuple

from config import WORLD_WIDTH, WORLD_HEIGHT, CAMERA_PAN_MARGIN_WU

Position = Tuple[float, float]


@dataclass
class Camera:
    """Manages the view into the world."""

    def __init__(self, viewport_width: int, viewport_height: int):
        """Initialize the camera at world origin with default zoom.
        
        Args:
            viewport_width: window width in pixels
            viewport_height: window height in pixels
        """
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.position: Position = (500.0, 350.0)  # center of world, roughly
        self.zoom = 1.0  # pixels per world unit
        self.follow_target = None  # if set, camera centers on this vessel

    def world_to_screen(self, world_pos: Position) -> Position:
        """Convert a world position to screen coordinates (pixels).
        
        This is the *only* place where world↔screen conversion happens.
        If it's wrong here, it's wrong everywhere.
        """
        world_x, world_y = world_pos
        cam_x, cam_y = self.position

        # Translate world to camera-relative, then scale by zoom
        screen_x = (world_x - cam_x) * self.zoom + self.viewport_width / 2
        screen_y = (world_y - cam_y) * self.zoom + self.viewport_height / 2

        return (screen_x, screen_y)

    def screen_to_world(self, screen_pos: Position) -> Position:
        """Convert a screen position (pixels) to world coordinates.
        
        Used for mouse clicks and intersection tests.
        """
        screen_x, screen_y = screen_pos
        cam_x, cam_y = self.position

        # De-center, de-zoom, then translate back to world
        world_x = cam_x + (screen_x - self.viewport_width / 2) / self.zoom
        world_y = cam_y + (screen_y - self.viewport_height / 2) / self.zoom

        return (world_x, world_y)

    def pan(self, dx: float, dy: float) -> None:
        """Pan the camera by a screen-space delta (pixels).
        
        Args:
            dx: pixels to move right (negative = left)
            dy: pixels to move down (negative = up)
        """
        world_dx = dx / self.zoom
        world_dy = dy / self.zoom
        self.position = (self.position[0] - world_dx, self.position[1] - world_dy)
        self.clamp_position()

    def clamp_position(self) -> None:
        """Bound the camera centre to the world plus a margin.

        Keeps free-pan from wandering into the void and, crucially, keeps every
        on-screen coordinate within SDL's signed-short draw range so the circle
        primitives in the chart can't raise OverflowError.
        """
        m = CAMERA_PAN_MARGIN_WU
        x = max(-m, min(WORLD_WIDTH + m, self.position[0]))
        y = max(-m, min(WORLD_HEIGHT + m, self.position[1]))
        self.position = (x, y)

    def zoom_at(self, screen_pos: Position, zoom_factor: float) -> None:
        """Zoom in or out, keeping a screen position fixed on the world.
        
        This is the "zoom toward cursor" behavior that feels good in maps.
        
        Args:
            screen_pos: the screen position to keep fixed (usually cursor)
            zoom_factor: multiply zoom by this (e.g., 1.1 to zoom in 10%)
        """
        # Where is the cursor in world space, pre-zoom?
        world_pos_before = self.screen_to_world(screen_pos)

        # Apply zoom
        self.zoom *= zoom_factor

        # Where is the cursor now in world space?
        world_pos_after = self.screen_to_world(screen_pos)

        # Pan the camera to re-align the world position with the cursor.
        # Use (before - after) so the camera moves the opposite direction
        # of the world shift induced by zooming, keeping the point fixed.
        pan_x = world_pos_before[0] - world_pos_after[0]
        pan_y = world_pos_before[1] - world_pos_after[1]
        self.position = (self.position[0] + pan_x, self.position[1] + pan_y)
        self.clamp_position()

    def clamp_zoom(self, zoom_min: float, zoom_max: float) -> None:
        """Clamp zoom to a valid range."""
        self.zoom = max(zoom_min, min(zoom_max, self.zoom))

    def distance_to_screen(self, distance_world_units: float) -> float:
        """Convert a world-space distance to screen pixels."""
        return distance_world_units * self.zoom

    def distance_to_world(self, distance_pixels: float) -> float:
        """Convert a screen-space distance to world units."""
        return distance_pixels / self.zoom

    def set_center(self, world_pos: Position) -> None:
        """Center the camera on a world position (overrides any prior pan)."""
        self.position = (float(world_pos[0]), float(world_pos[1]))

    def set_follow_target(self, target) -> None:
        """Make the camera follow a target (e.g., a vessel).
        
        Args:
            target: an object with a `.position` attribute, or None to stop following.
        """
        self.follow_target = target

    def update_follow(self) -> None:
        """If following a target, move the camera to keep it centered.
        
        Call this once per frame to smoothly track a moving target.
        """
        if self.follow_target and hasattr(self.follow_target, "position"):
            self.position = self.follow_target.position
