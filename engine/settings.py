"""Persisted user settings — audio, display, keybindings, gameplay.

Pure Python (no pygame import): the Settings object holds plain data and
serialises to settings.json in the SAME user-writable directory as the career
save (frozen -> %APPDATA%/MeridianSea, source -> cwd), keyed on sys.frozen via
config.user_data_dir().  Defaults EXACTLY reproduce the pre-settings behaviour,
so an absent or corrupt settings.json changes nothing.

main.py applies these (audio volumes via the sound system, keybind lookup,
display mode, difficulty multipliers); render/ only draws the settings screen.

Keybindings are stored as pygame KEY NAMES (e.g. "w", "space", "left") so this
module needs no pygame; main.py converts names<->keycodes with
pygame.key.key_code() / pygame.key.name().
"""

import json
import os
from typing import Optional

from config import SOUND_VOLUME, GAME_VERSION, user_data_dir

SETTINGS_FILEPATH = os.path.join(user_data_dir(), "settings.json")

# Action -> default key NAME.  These reproduce today's hardcoded controls exactly.
DEFAULT_KEYBINDS = {
    "throttle_up":   "w",
    "throttle_down": "s",
    "helm_left":     "a",
    "helm_right":    "d",
    "pause":         "space",
    "follow_cam":    "f",
    "settings":      "e",
    "career":        "j",
    "minimap":       "m",
    "tech":          "t",
    "skip_tutorial": "h",
}

# Display label + order for the rebind rows on the settings screen (Stage 3).
KEYBIND_ACTIONS = [
    ("throttle_up",   "Throttle up"),
    ("throttle_down", "Throttle down"),
    ("helm_left",     "Steer left"),
    ("helm_right",    "Steer right"),
    ("pause",         "Pause"),
    ("follow_cam",    "Follow camera"),
    ("settings",      "Settings"),
    ("career",        "Career / Jobs"),
    ("minimap",       "Minimap"),
    ("tech",          "Tech systems"),
    ("skip_tutorial", "Skip tutorial"),
]

# Difficulty presets scale the player's two main consequences (zone fines and
# grounding hull damage).  "normal" == current behaviour (x1.0) and is the default.
DIFFICULTY_PRESETS = {
    "easy":   {"fine_mult": 0.5, "damage_mult": 0.5},
    "normal": {"fine_mult": 1.0, "damage_mult": 1.0},
    "hard":   {"fine_mult": 1.5, "damage_mult": 1.5},
}
DIFFICULTIES = ("easy", "normal", "hard")

# Resolutions offered on the settings screen (Stage 3).  None = desktop-scaled
# default window (today's behaviour).
RESOLUTION_CHOICES = [None, (1280, 720), (1600, 900), (1920, 1080), (2560, 1440)]


def _clamp01(v, default: float = 1.0) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return default   # bad data falls back to the field's default, not max


class Settings:
    """All runtime-changeable preferences.  Constructed defaults == current game
    behaviour, so the game runs identically when no settings.json exists."""

    def __init__(self) -> None:
        # ── Audio (0.0-1.0).  Effective per-sound = master x category x relative.
        # master = the old single SOUND_VOLUME; categories default to 1.0, so the
        # effective mix is unchanged until the player moves the sliders.
        self.master_volume: float = SOUND_VOLUME
        self.sfx_volume: float = 1.0
        self.music_volume: float = 1.0
        # ── Display.  resolution=None + windowed == today's scaled-window default.
        self.fullscreen: bool = False
        self.resolution: Optional[tuple] = None
        # ── Keybindings: action -> key name (a copy so edits don't mutate defaults).
        self.keybinds: dict = dict(DEFAULT_KEYBINDS)
        # ── Gameplay.
        self.difficulty: str = "normal"
        self.voyage_flavour: bool = True   # cosmetic transit log lines

    # ---- difficulty helpers --------------------------------------------------
    def fine_multiplier(self) -> float:
        return DIFFICULTY_PRESETS.get(self.difficulty,
                                      DIFFICULTY_PRESETS["normal"])["fine_mult"]

    def damage_multiplier(self) -> float:
        return DIFFICULTY_PRESETS.get(self.difficulty,
                                      DIFFICULTY_PRESETS["normal"])["damage_mult"]

    # ---- (de)serialisation ---------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "version": GAME_VERSION,
            "master_volume": self.master_volume,
            "sfx_volume": self.sfx_volume,
            "music_volume": self.music_volume,
            "fullscreen": self.fullscreen,
            "resolution": list(self.resolution) if self.resolution else None,
            "keybinds": dict(self.keybinds),
            "difficulty": self.difficulty,
            "voyage_flavour": self.voyage_flavour,
        }

    def from_dict(self, data: dict) -> "Settings":
        if not isinstance(data, dict):
            return self
        self.master_volume = _clamp01(data.get("master_volume"), self.master_volume)
        self.sfx_volume = _clamp01(data.get("sfx_volume"), self.sfx_volume)
        self.music_volume = _clamp01(data.get("music_volume"), self.music_volume)
        self.fullscreen = bool(data.get("fullscreen", self.fullscreen))
        res = data.get("resolution", None)
        self.resolution = (tuple(res) if isinstance(res, (list, tuple))
                           and len(res) == 2 else None)
        # Merge saved binds over the defaults so an action added in a later
        # version still gets its default if the saved file predates it.
        kb = dict(DEFAULT_KEYBINDS)
        saved = data.get("keybinds", {})
        if isinstance(saved, dict):
            for action in kb:
                if isinstance(saved.get(action), str):
                    kb[action] = saved[action]
        self.keybinds = kb
        diff = data.get("difficulty", self.difficulty)
        self.difficulty = diff if diff in DIFFICULTY_PRESETS else "normal"
        self.voyage_flavour = bool(data.get("voyage_flavour", self.voyage_flavour))
        return self

    def save(self, filepath: str = SETTINGS_FILEPATH) -> None:
        """Write settings.json.  Never raises — a read-only dir just means the
        preferences won't persist, which must not crash the game."""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
        except OSError:
            pass

    @classmethod
    def load(cls, filepath: str = SETTINGS_FILEPATH) -> "Settings":
        """Read settings.json, or return defaults (== current behaviour) when it
        is missing or corrupt.  Always returns a usable Settings object."""
        s = cls()
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return s
        return s.from_dict(data)
