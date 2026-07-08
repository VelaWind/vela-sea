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

import itertools
from collections import OrderedDict

import pygame

from config import (IS_WEB, FONT_DATA_NAME,
                    FONT_WEB_UI_PATH, FONT_WEB_DATA_PATH)

# ---------------------------------------------------------------------------
# Rendered-text cache
# ---------------------------------------------------------------------------
# font.render is expensive (very expensive under WASM) and the UI re-renders
# dozens of identical strings every frame (fleet rows, port labels, status bar,
# event log...).  Every font in the game is constructed through safe_sysfont,
# which wraps the pygame Font in CachedFont — so .render() is memoized by
# (font, text, color) with ZERO call-site changes.  Changed text is a new key,
# so invalidation is automatic; the cache is LRU-bounded so long sessions with
# churning strings (timestamps, countdowns) can't grow it without limit.
#
# Contract: callers must treat rendered surfaces as immutable (blit-only).
# The one caller that mutates (reward banner set_alpha fade) copies first.
_TEXT_CACHE: "OrderedDict[tuple, pygame.Surface]" = OrderedDict()
_TEXT_CACHE_MAX = 512


class CachedFont:
    """A pygame Font wrapper whose render() is memoized.

    Everything else (size, get_height, metrics...) delegates to the real font,
    so it is a drop-in replacement anywhere a Font is used for UI text.
    """
    __slots__ = ("_font", "_uid")
    _next_uid = itertools.count()   # class-wide; uids never recycle

    def __init__(self, font):
        self._font = font
        # Stable cache identity.  NOT id(self._font): after the web display
        # heal rebuilds all panels, a GC'd font's id() can be reused by a new
        # font, aliasing it onto stale cached surfaces (wrong size/face).
        self._uid = next(CachedFont._next_uid)

    def render(self, text, antialias=True, color=(255, 255, 255), background=None):
        try:
            key = (self._uid, text, bool(antialias),
                   tuple(color), tuple(background) if background else None)
        except TypeError:
            # Unhashable color object — render uncached rather than crash.
            return self._font.render(text, antialias, color, background)
        surf = _TEXT_CACHE.get(key)
        if surf is None:
            surf = self._font.render(text, antialias, color, background)
            try:
                # Match the display format so every cached blit is a straight
                # copy.  Worth doing only for cached surfaces (rendered once).
                surf = surf.convert_alpha()
            except pygame.error:
                pass   # no display yet (bare unit context) — cache as-is
            _TEXT_CACHE[key] = surf
            if len(_TEXT_CACHE) > _TEXT_CACHE_MAX:
                _TEXT_CACHE.popitem(last=False)   # evict least-recently-used
        else:
            _TEXT_CACHE.move_to_end(key)
        return surf

    def __getattr__(self, name):
        return getattr(self._font, name)


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

    Web mode loads the bundled DejaVu faces by FILE PATH instead: the Windows
    face names in config don't exist under emscripten, and SysFont silently
    falls back to freesansbold there — wrong metrics and no arrow/warning/
    dingbat glyphs (the event-log "→" rendered as tofu).  Keyed on IS_WEB so
    the VELA_FORCE_WEB harness exercises this exact branch off-browser;
    desktop (IS_WEB False) never reaches it and keeps SysFont byte-identical.
    """
    size = max(1, int(round(size * _UI_SCALE)))
    if IS_WEB:
        try:
            path = (FONT_WEB_DATA_PATH if name == FONT_DATA_NAME
                    else FONT_WEB_UI_PATH)
            font = pygame.font.Font(path, size)
            font.set_bold(bold)
            font.set_italic(italic)
            return CachedFont(font)
        except Exception:
            pass   # bundled file unreadable — fall through to SysFont chain
    try:
        return CachedFont(pygame.font.SysFont(name, size, bold=bold, italic=italic))
    except Exception:
        # System-font lookup failed (e.g. no fontconfig under emscripten).
        # Ensure the font module is up, then use the bundled default face.
        try:
            if not pygame.font.get_init():
                pygame.font.init()
            return CachedFont(pygame.font.Font(None, size))
        except Exception:
            # Font subsystem is entirely unavailable — the caller will get None;
            # nothing renders, but the game keeps running instead of crashing.
            return None
