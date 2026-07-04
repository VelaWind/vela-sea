"""Fail-safe font construction shared by the render layer.

``pygame.font.SysFont`` looks a face up by name.  On desktop the named Windows
fonts ("segoe ui", "consolas") resolve fine.  In sandboxes where those fonts are
absent and the font subsystem is fragile — notably pygbag / WebAssembly
(``sys.platform == "emscripten"``) — the system-font scan can raise instead of
falling back, which would crash the game at construction time (every panel builds
its fonts in ``__init__``).

``safe_sysfont`` behaves exactly like ``pygame.font.SysFont`` on desktop but can
never raise: it falls back to pygame's bundled default font, so a missing system
face degrades the *look* of the text without ever taking down startup.
"""

import pygame

# Resolution-aware UI scale (web).  Every font in the game is built through
# safe_sysfont, and panel pixel dimensions route through ui_px, so this module
# is the single choke point for scaling the whole UI.  The scale is set ONCE at
# display init (main.Game on web: render_height / 720, clamped to [1, 2]) and
# NEVER set on desktop, where it stays exactly 1.0 — int(round(v * 1.0)) == v,
# so desktop layout is byte-identical.
_UI_SCALE = 1.0


def set_ui_scale(scale: float) -> None:
    """Set the global UI scale.  Call BEFORE constructing Chart/panels (fonts
    and dimensions are computed in their __init__)."""
    global _UI_SCALE
    _UI_SCALE = max(0.5, min(4.0, float(scale)))


def get_ui_scale() -> float:
    return _UI_SCALE


def ui_px(value: float) -> int:
    """Scale a design-time pixel value (tuned for 720p) by the UI scale."""
    return int(round(value * _UI_SCALE))


def safe_sysfont(name, size, bold=False, italic=False):
    """``pygame.font.SysFont`` that degrades to the default font, never raises.

    The requested size is multiplied by the global UI scale (1.0 on desktop),
    so every font in the game scales with resolution through this one function.
    """
    size = max(1, int(round(size * _UI_SCALE)))
    try:
        return pygame.font.SysFont(name, size, bold=bold, italic=italic)
    except Exception:
        # System-font lookup failed (e.g. no fontconfig under emscripten).
        # Ensure the font module is up, then use the bundled default face.
        try:
            if not pygame.font.get_init():
                pygame.font.init()
            return pygame.font.Font(None, size)
        except Exception:
            # Font subsystem is entirely unavailable — the caller will get None;
            # nothing renders, but the game keeps running instead of crashing.
            return None
