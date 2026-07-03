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


def safe_sysfont(name, size, bold=False, italic=False):
    """``pygame.font.SysFont`` that degrades to the default font, never raises."""
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
