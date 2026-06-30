"""Sound manager: programmatically generated effects, loops, and one-shots.

All five .wav files are synthesised with the standard library (wave + math)
the first time the game runs, so the repo never depends on downloaded assets
and numpy is not required.  Every mixer call is wrapped so that any audio
failure (no sound card, dummy SDL driver, missing files) degrades to silence
instead of crashing the game.
"""

import math
import os
import random
import struct
import wave

import pygame

from config import (
    SOUND_ENABLED, SOUND_VOLUME, SOUND_DIR,
    ENGINE_SOUND_MIN_SPEED_KN, SOUND_RELATIVE_VOLUMES,
)

SAMPLE_RATE = 22050

SOUND_NAMES = ("engine_loop", "docking", "warning", "mayday", "ambient_sea",
               "throttle_click", "success_chime")

# Loops/ambience scale with the MUSIC slider; everything else with the SFX slider.
MUSIC_SOUNDS = frozenset({"engine_loop", "ambient_sea"})


# ---------------------------------------------------------------------------
# WAV synthesis — pure stdlib, deterministic output
# ---------------------------------------------------------------------------

def _write_wav(path: str, samples) -> None:
    """Write a list of floats in [-1, 1] as a 16-bit mono WAV."""
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for s in samples:
            v = max(-1.0, min(1.0, s))
            frames += struct.pack("<h", int(v * 32767))
        w.writeframes(bytes(frames))


def _gen_engine_loop():
    """Low diesel hum: stacked low sines with a slow throb.

    2.0 s duration gives whole cycles for every component (55/110/220 Hz and
    the 8 Hz throb), so the loop point is click-free.
    """
    n = int(SAMPLE_RATE * 2.0)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        s = (0.50 * math.sin(2 * math.pi * 55.0 * t)
             + 0.30 * math.sin(2 * math.pi * 110.0 * t)
             + 0.08 * math.sin(2 * math.pi * 220.0 * t))
        throb = 0.85 + 0.15 * math.sin(2 * math.pi * 8.0 * t)
        out.append(0.35 * s * throb)
    return out


def _gen_docking():
    """Berthing bump: a fast-decaying low thud with a burst of fender noise."""
    rnd = random.Random(7)  # fixed seed → identical file every generation
    n = int(SAMPLE_RATE * 0.45)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        thud = math.sin(2 * math.pi * 70.0 * t) * math.exp(-t * 12.0)
        noise = (rnd.random() * 2.0 - 1.0) * 0.30 * math.exp(-t * 30.0)
        out.append(0.80 * (thud + noise))
    return out


def _gen_warning():
    """Two short 880 Hz beeps — the classic bridge alert."""
    n = int(SAMPLE_RATE * 0.6)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        in_beep = (0.00 <= t < 0.15) or (0.30 <= t < 0.45)
        if in_beep:
            # 5 ms attack/release ramps remove the click at beep edges.
            seg_t = t % 0.30
            env = min(1.0, seg_t / 0.005, max(0.0, (0.15 - seg_t) / 0.005))
            out.append(0.40 * env * math.sin(2 * math.pi * 880.0 * t))
        else:
            out.append(0.0)
    return out


def _gen_mayday():
    """Distress alarm: alternating 600/450 Hz two-tone, four 0.3 s segments."""
    n = int(SAMPLE_RATE * 1.2)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        seg = int(t / 0.3)
        freq = 600.0 if seg % 2 == 0 else 450.0
        seg_t = t - seg * 0.3
        env = min(1.0, seg_t / 0.008, max(0.0, (0.3 - seg_t) / 0.008))
        out.append(0.45 * env * math.sin(2 * math.pi * freq * t))
    return out


def _gen_ambient_sea():
    """Quiet sea wash: low-pass filtered noise with a slow swell.

    3.0 s with exactly one swell cycle keeps the loop point seamless; the
    one-pole low-pass turns white noise into a soft "shhh".
    """
    rnd = random.Random(42)
    n = int(SAMPLE_RATE * 3.0)
    out = []
    lp = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        lp += 0.08 * ((rnd.random() * 2.0 - 1.0) - lp)   # one-pole low-pass
        swell = 0.6 + 0.4 * math.sin(2 * math.pi * t / 3.0)
        out.append(0.18 * lp * swell * 4.0)
    return out


def _gen_throttle_click():
    """Soft helm click: a brief, gentle blip fired on each throttle change.

    60 ms with a fast exponential decay — felt more than heard, so repeated
    throttle taps never become annoying.
    """
    n = int(SAMPLE_RATE * 0.06)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = math.exp(-t * 60.0)
        out.append(0.25 * env * math.sin(2 * math.pi * 520.0 * t))
    return out


def _gen_success_chime():
    """Bright rising two-note reward sting (≈660 Hz → 880 Hz), 0.34 s total.

    Each note has its own attack/release envelope dipping to zero at the
    boundary, so the frequency jump is click-free.  Played after the docking
    thud when a contract is paid out.
    """
    n = int(SAMPLE_RATE * 0.34)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        if t < 0.16:
            freq, seg_t, seg_len = 660.0, t, 0.16
        else:
            freq, seg_t, seg_len = 880.0, t - 0.16, 0.18
        env = min(1.0, seg_t / 0.01, max(0.0, (seg_len - seg_t) / 0.04))
        out.append(0.38 * env * math.sin(2 * math.pi * freq * t))
    return out


_GENERATORS = {
    "engine_loop": _gen_engine_loop,
    "docking":     _gen_docking,
    "warning":     _gen_warning,
    "mayday":      _gen_mayday,
    "ambient_sea": _gen_ambient_sea,
    "throttle_click": _gen_throttle_click,
    "success_chime": _gen_success_chime,
}


def ensure_sound_files(sound_dir: str = SOUND_DIR) -> None:
    """Generate any missing .wav files into sound_dir.

    Never raises: a packaged build on a read-only install dir (where the wavs are
    already bundled, so nothing needs writing) must degrade gracefully rather
    than crash any caller.
    """
    try:
        os.makedirs(sound_dir, exist_ok=True)
        for name, gen in _GENERATORS.items():
            path = os.path.join(sound_dir, name + ".wav")
            if not os.path.exists(path):
                _write_wav(path, gen())
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Sound manager
# ---------------------------------------------------------------------------

class SoundManager:
    """Owns the mixer: loops (engine, ambient) and one-shot effects.

    Construction never raises: any failure flips self.enabled to False and
    every later call becomes a no-op, so the game runs silently rather than
    crashing on machines without audio.
    """

    def __init__(self, sound_dir: str = SOUND_DIR) -> None:
        self.enabled = SOUND_ENABLED
        self.volume = SOUND_VOLUME       # master
        self.sfx_volume = 1.0            # one-shot effects category
        self.music_volume = 1.0          # loops / ambience category
        self._sounds: dict = {}
        self._engine_channel = None
        self._ambient_channel = None
        if not self.enabled:
            return
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            ensure_sound_files(sound_dir)
            for name in SOUND_NAMES:
                self._sounds[name] = pygame.mixer.Sound(
                    os.path.join(sound_dir, name + ".wav"))
            self._apply_volumes()
        except Exception:
            self.enabled = False

    # ------------------------------------------------------------------ public

    def set_volume(self, volume: float) -> None:
        """Set the master volume (0.0–1.0) and reapply the per-sound mix."""
        self.volume = max(0.0, min(1.0, volume))
        if self.enabled:
            self._apply_volumes()

    def set_volumes(self, master: float, sfx: float, music: float) -> None:
        """Set master + per-category (sfx / music) volumes and reapply the mix."""
        self.volume = max(0.0, min(1.0, master))
        self.sfx_volume = max(0.0, min(1.0, sfx))
        self.music_volume = max(0.0, min(1.0, music))
        if self.enabled:
            self._apply_volumes()

    def set_enabled(self, enabled: bool) -> None:
        """Toggle all audio; stops loops immediately when switching off."""
        if not enabled:
            self.stop_all()
        if enabled and not self._sounds:
            # Sounds never loaded (construction failed) — stay silent.
            return
        self.enabled = enabled and bool(self._sounds)
        if self.enabled:
            self._apply_volumes()

    def play(self, name: str) -> None:
        """Fire a one-shot effect (docking, warning, mayday)."""
        if not self.enabled:
            return
        try:
            self._sounds[name].play()
        except Exception:
            pass

    def start_ambient(self) -> None:
        """Begin the always-on sea ambience loop (idempotent)."""
        if not self.enabled or self._ambient_channel is not None:
            return
        try:
            self._ambient_channel = self._sounds["ambient_sea"].play(loops=-1)
        except Exception:
            pass

    def update_engine(self, speed_kn: float) -> None:
        """Start/stop the engine hum based on the player's current speed."""
        if not self.enabled:
            return
        try:
            if speed_kn > ENGINE_SOUND_MIN_SPEED_KN:
                if self._engine_channel is None or not self._engine_channel.get_busy():
                    self._engine_channel = self._sounds["engine_loop"].play(loops=-1)
            elif self._engine_channel is not None:
                self._engine_channel.stop()
                self._engine_channel = None
        except Exception:
            pass

    def stop_all(self) -> None:
        """Silence every channel (used on restart and shutdown)."""
        try:
            pygame.mixer.stop()
        except Exception:
            pass
        self._engine_channel = None
        self._ambient_channel = None

    # ----------------------------------------------------------------- private

    def _apply_volumes(self) -> None:
        # Effective per-sound = master x category (music/sfx) x relative mix.
        for name, snd in self._sounds.items():
            category = self.music_volume if name in MUSIC_SOUNDS else self.sfx_volume
            snd.set_volume(self.volume * category
                           * SOUND_RELATIVE_VOLUMES.get(name, 1.0))
