"""Environment and weather simulation for the maritime world.

This is shared, global state that affects all vessels and is what the
settings panel edits. All systems read from here; changes ripple through
the whole simulation.
"""

from dataclasses import dataclass, field
import math
import random
from typing import Optional, Dict


class WeatherEvent:
    """A transient weather event with buildup → peak → fadeout lifecycle.

    Effects ramp smoothly in during buildup, hold at full strength during
    peak, then fade during fadeout.  `intensity` gives the 0→1 scale factor
    at the current moment so callers can interpolate any magnitude.
    """

    def __init__(
        self,
        event_type: str,
        wind_speed_delta: float,
        wind_dir_delta: float,
        wave_height_delta: float,
        visibility_drop: float,
        buildup_duration: float,
        peak_duration: float,
        fadeout_duration: float,
    ) -> None:
        self.event_type = event_type
        self.wind_speed_delta = wind_speed_delta
        self.wind_dir_delta = wind_dir_delta
        self.wave_height_delta = wave_height_delta
        self.visibility_drop = visibility_drop
        self.buildup_duration = buildup_duration
        self.peak_duration = peak_duration
        self.fadeout_duration = fadeout_duration
        self.phase = "buildup"
        self.phase_remaining = buildup_duration

    @property
    def intensity(self) -> float:
        """Return 0.0 (no effect) → 1.0 (full peak strength)."""
        if self.phase == "buildup":
            elapsed = self.buildup_duration - self.phase_remaining
            return elapsed / self.buildup_duration if self.buildup_duration > 0 else 1.0
        elif self.phase == "peak":
            return 1.0
        else:  # fadeout
            return self.phase_remaining / self.fadeout_duration if self.fadeout_duration > 0 else 0.0

    def update(self, dt: float) -> bool:
        """Advance the event by dt sim-seconds.  Returns True while still active."""
        self.phase_remaining -= dt
        if self.phase_remaining <= 0.0:
            if self.phase == "buildup":
                self.phase = "peak"
                self.phase_remaining = self.peak_duration
            elif self.phase == "peak":
                self.phase = "fadeout"
                self.phase_remaining = self.fadeout_duration
            else:
                return False  # fadeout complete
        return True


@dataclass
class Environment:
    """Shared environmental state: weather, time, currents, visibility."""

    # Time of day (continuous 0–24h)
    time_of_day: float = 12.0  # 0 = midnight, 12 = noon, 24 = next midnight

    # Wind
    wind_speed: float = 5.0  # knots (True Wind Speed)
    wind_direction: float = 45.0  # degrees the wind blows FROM (0 = from east)
    wind_gust_strength: float = 2.0  # additional wind speed during gusts
    wind_gust_frequency: float = 0.1  # probability of gust per second

    # Waves
    wave_height: float = 1.0  # meters
    swell_direction: float = 90.0  # degrees
    wave_period: float = 8.0  # seconds

    # Current (pushes vessels)
    current_speed: float = 0.5  # knots (tidal stream / ocean drift magnitude)
    current_direction: float = 90.0  # degrees the current flows TOWARD (0 = toward east)

    # Visibility
    visibility: float = 500.0  # meters
    precipitation: str = "none"  # "none", "rain", "heavy_rain", "storm"
    fog: bool = False

    # Temperature
    air_temperature_c: float = 15.0
    water_temperature_c: float = 12.0

    # Pressure
    barometric_pressure_mb: float = 1013.0
    pressure_trend: str = "stable"  # "rising", "falling", "stable"

    # Tide
    tide_level: float = 0.0  # meters (-TIDE_RANGE to +TIDE_RANGE)
    tide_direction: str = "rising"  # "rising" or "falling"

    # Time control
    time_speed_multiplier: float = 1.0  # 0 = paused, 1 = normal, 2+ = fast-forward

    # ---- Dynamic weather internal state (Chunk F) ----
    # _auto_* values are the system's slowly-drifting "natural" background.
    # The displayed fields equal _auto_* unless a weather event or user
    # override is active.  Not meant to be set from outside — managed by update().
    _auto_wind_speed: float = field(default=5.0, repr=False)
    _auto_wind_direction: float = field(default=45.0, repr=False)
    _auto_wave_height: float = field(default=1.0, repr=False)
    _auto_visibility: float = field(default=500.0, repr=False)
    _auto_current_speed: float = field(default=0.5, repr=False)
    _auto_current_direction: float = field(default=90.0, repr=False)
    _active_event: Optional[WeatherEvent] = field(default=None, repr=False)
    # Maps attr name → remaining sim-seconds of user pin (slider drag override)
    _user_override_timers: Dict[str, float] = field(default_factory=dict, repr=False)
    # Set to False in headless tests that exercise vessel routing / engine logic
    # but not weather dynamics — keeps wind and current constant so route
    # behaviour is deterministic regardless of random seed.
    weather_drift_enabled: bool = field(default=True, repr=False)

    # ---- Core simulation tick ----

    def update(self, dt: float) -> None:
        """Advance the environment by dt simulated seconds.

        `dt` is already in simulated seconds (scaled by TIME_COMPRESSION and
        the UI speed multiplier in main.py).  Tide, weather drift, and event
        lifecycle all advance at the simulated rate.
        """
        # Advance time of day (simulated seconds → hours)
        self.time_of_day += dt / 3600.0
        if self.time_of_day >= 24.0:
            self.time_of_day -= 24.0

        # Tide: sinusoidal 12.42-hour semidiurnal cycle
        tide_period = 12.42 * 3600.0
        tide_phase = (self.time_of_day * 3600.0) / tide_period
        from config import (
            TIDE_RANGE,
            WIND_SPEED_DEFAULT, WAVE_HEIGHT_DEFAULT,
            CURRENT_SPEED_DEFAULT, VISIBILITY_CLEAR,
            WEATHER_DRIFT_WIND_SPEED_SIGMA, WEATHER_DRIFT_WIND_DIR_SIGMA,
            WEATHER_DRIFT_WAVE_HEIGHT_SIGMA, WEATHER_DRIFT_CURRENT_SPEED_SIGMA,
            WEATHER_DRIFT_CURRENT_DIR_SIGMA, WEATHER_DRIFT_VISIBILITY_SIGMA,
            WEATHER_DRIFT_MEAN_REVERSION,
            WEATHER_FOG_PROB_PER_HOUR, WEATHER_SQUALL_PROB_PER_HOUR,
            WEATHER_STORM_PROB_PER_HOUR,
        )
        self.tide_level = TIDE_RANGE * math.sin(2 * math.pi * tide_phase)
        self.tide_direction = "rising" if math.cos(2 * math.pi * tide_phase) > 0 else "falling"

        if not self.weather_drift_enabled:
            return  # headless routing tests: freeze weather, only advance tide

        # ---- Background drift: Ornstein-Uhlenbeck random walk ----
        # Magnitude fields revert to their defaults over ~1.9 sim-hours.
        # Direction fields do a free random walk (no preferred compass direction).
        self._auto_wind_speed = max(0.0, self._ou_step(
            self._auto_wind_speed, WIND_SPEED_DEFAULT,
            WEATHER_DRIFT_WIND_SPEED_SIGMA, WEATHER_DRIFT_MEAN_REVERSION, dt,
        ))
        self._auto_wind_direction = (
            self._auto_wind_direction
            + random.gauss(0.0, WEATHER_DRIFT_WIND_DIR_SIGMA * min(math.sqrt(dt), 1.0))
        ) % 360.0
        self._auto_wave_height = max(0.0, self._ou_step(
            self._auto_wave_height, WAVE_HEIGHT_DEFAULT,
            WEATHER_DRIFT_WAVE_HEIGHT_SIGMA, WEATHER_DRIFT_MEAN_REVERSION * 0.5, dt,
        ))
        self._auto_current_speed = max(0.0, self._ou_step(
            self._auto_current_speed, CURRENT_SPEED_DEFAULT,
            WEATHER_DRIFT_CURRENT_SPEED_SIGMA, WEATHER_DRIFT_MEAN_REVERSION, dt,
        ))
        self._auto_current_direction = (
            self._auto_current_direction
            + random.gauss(0.0, WEATHER_DRIFT_CURRENT_DIR_SIGMA * min(math.sqrt(dt), 1.0))
        ) % 360.0
        self._auto_visibility = min(1000.0, max(50.0, self._ou_step(
            self._auto_visibility, VISIBILITY_CLEAR,
            WEATHER_DRIFT_VISIBILITY_SIGMA, WEATHER_DRIFT_MEAN_REVERSION, dt,
        )))

        # ---- Weather event probability: Poisson process ----
        # Only one event active at a time; skip event roll while one is running.
        if self._active_event is None:
            total_rate = (WEATHER_FOG_PROB_PER_HOUR
                          + WEATHER_SQUALL_PROB_PER_HOUR
                          + WEATHER_STORM_PROB_PER_HOUR) / 3600.0
            if random.random() < total_rate * dt:
                r = random.random() * (WEATHER_FOG_PROB_PER_HOUR
                                        + WEATHER_SQUALL_PROB_PER_HOUR
                                        + WEATHER_STORM_PROB_PER_HOUR)
                if r < WEATHER_FOG_PROB_PER_HOUR:
                    self._active_event = self._create_weather_event("fog")
                elif r < WEATHER_FOG_PROB_PER_HOUR + WEATHER_SQUALL_PROB_PER_HOUR:
                    self._active_event = self._create_weather_event("squall")
                else:
                    self._active_event = self._create_weather_event("storm")

        # ---- Advance active event and compute current effect magnitudes ----
        e_wind_speed = 0.0
        e_wind_dir   = 0.0
        e_wave       = 0.0
        e_vis_drop   = 0.0

        if self._active_event is not None:
            still_alive = self._active_event.update(dt)
            if not still_alive:
                self._active_event = None
            else:
                i = self._active_event.intensity
                e_wind_speed = self._active_event.wind_speed_delta * i
                e_wind_dir   = self._active_event.wind_dir_delta   * i
                e_wave       = self._active_event.wave_height_delta * i
                e_vis_drop   = self._active_event.visibility_drop   * i

        # ---- Write auto + event values to actual fields ----
        # _apply_auto_value skips fields the user has recently pinned via slider.
        self._apply_auto_value("wind_speed",
            max(0.0, self._auto_wind_speed + e_wind_speed), dt)
        self._apply_auto_value("wind_direction",
            (self._auto_wind_direction + e_wind_dir) % 360.0, dt)
        self._apply_auto_value("wave_height",
            max(0.0, self._auto_wave_height + e_wave), dt)
        self._apply_auto_value("current_speed",
            max(0.0, self._auto_current_speed), dt)
        self._apply_auto_value("current_direction",
            self._auto_current_direction, dt)
        self._apply_auto_value("visibility",
            max(10.0, self._auto_visibility - e_vis_drop), dt)

        # ---- Update descriptive flags from active event ----
        if self._active_event is None:
            self.fog = False
            self.precipitation = "none"
        elif self._active_event.event_type == "fog":
            self.fog = self._active_event.intensity > 0.25
            self.precipitation = "none"
        elif self._active_event.event_type == "squall":
            self.fog = False
            self.precipitation = ("heavy_rain" if self._active_event.intensity > 0.6
                                   else "rain")
        else:  # storm
            self.fog = False
            self.precipitation = "storm"

        # ---- Tick down user override timers ----
        for attr in list(self._user_override_timers):
            self._user_override_timers[attr] -= dt
            if self._user_override_timers[attr] <= 0:
                del self._user_override_timers[attr]

    # ---- Dynamic weather helpers ----

    @staticmethod
    def _ou_step(
        current: float,
        center: float,
        sigma: float,
        mean_reversion: float,
        dt: float,
    ) -> float:
        """Euler-Maruyama step of an Ornstein-Uhlenbeck process.

        Drifts `current` randomly around `center` with noise amplitude `sigma`
        (in per-√s units) and slow mean-reversion.  Numerically stable for
        mean_reversion × dt ≪ 1, which is guaranteed at SIM_TIMESTEP=1.0 s
        and WEATHER_DRIFT_MEAN_REVERSION=0.0001 (product = 0.0001 ≪ 1).

        Noise is capped to a dt=1 s equivalent so large-timestep headless
        tests (FULL_DT=10 s) do not amplify per-step drift by sqrt(10)≈3.16×.
        At the real SIM_TIMESTEP=1.0 s the sqrt is exactly 1.0, hitting the cap.
        """
        sqrt_dt = min(math.sqrt(dt), 1.0)
        noise = random.gauss(0.0, sigma * sqrt_dt)
        reversion = mean_reversion * (center - current) * dt
        return current + noise + reversion

    def _create_weather_event(self, event_type: str) -> WeatherEvent:
        """Build a WeatherEvent from config constants."""
        from config import (
            WEATHER_FOG_BUILDUP_S, WEATHER_FOG_PEAK_S, WEATHER_FOG_FADEOUT_S,
            WEATHER_FOG_VIS_DROP, WEATHER_FOG_WIND_DELTA, WEATHER_FOG_WAVE_DELTA,
            WEATHER_SQUALL_BUILDUP_S, WEATHER_SQUALL_PEAK_S, WEATHER_SQUALL_FADEOUT_S,
            WEATHER_SQUALL_WIND_DELTA, WEATHER_SQUALL_WAVE_DELTA, WEATHER_SQUALL_VIS_DROP,
            WEATHER_STORM_BUILDUP_S, WEATHER_STORM_PEAK_S, WEATHER_STORM_FADEOUT_S,
            WEATHER_STORM_WIND_DELTA, WEATHER_STORM_WAVE_DELTA, WEATHER_STORM_VIS_DROP,
        )
        if event_type == "fog":
            return WeatherEvent(
                event_type="fog",
                wind_speed_delta=WEATHER_FOG_WIND_DELTA,
                wind_dir_delta=0.0,
                wave_height_delta=WEATHER_FOG_WAVE_DELTA,
                visibility_drop=WEATHER_FOG_VIS_DROP,
                buildup_duration=WEATHER_FOG_BUILDUP_S,
                peak_duration=WEATHER_FOG_PEAK_S,
                fadeout_duration=WEATHER_FOG_FADEOUT_S,
            )
        elif event_type == "squall":
            return WeatherEvent(
                event_type="squall",
                wind_speed_delta=WEATHER_SQUALL_WIND_DELTA,
                wind_dir_delta=random.uniform(-20.0, 20.0),  # squalls shift wind dir
                wave_height_delta=WEATHER_SQUALL_WAVE_DELTA,
                visibility_drop=WEATHER_SQUALL_VIS_DROP,
                buildup_duration=WEATHER_SQUALL_BUILDUP_S,
                peak_duration=WEATHER_SQUALL_PEAK_S,
                fadeout_duration=WEATHER_SQUALL_FADEOUT_S,
            )
        else:  # storm
            return WeatherEvent(
                event_type="storm",
                wind_speed_delta=WEATHER_STORM_WIND_DELTA,
                wind_dir_delta=random.uniform(-30.0, 30.0),  # storms veer the wind
                wave_height_delta=WEATHER_STORM_WAVE_DELTA,
                visibility_drop=WEATHER_STORM_VIS_DROP,
                buildup_duration=WEATHER_STORM_BUILDUP_S,
                peak_duration=WEATHER_STORM_PEAK_S,
                fadeout_duration=WEATHER_STORM_FADEOUT_S,
            )

    def _apply_auto_value(self, attr: str, target: float, dt: float) -> None:
        """Write `target` to `attr` unless the user has recently pinned it.

        While pinned, silently nudge the corresponding _auto_* field toward
        the user-set value so the transition back to auto-drift is seamless.
        """
        if attr in self._user_override_timers:
            auto_attr = "_auto_" + attr
            if hasattr(self, auto_attr):
                user_val = getattr(self, attr)
                current_auto = getattr(self, auto_attr)
                # Pull at 20 % per sim-second so _auto_* catches up within ~5 s
                setattr(self, auto_attr,
                        current_auto + min(1.0, 0.20 * dt) * (user_val - current_auto))
            return
        setattr(self, attr, target)

    def user_override(self, attr: str, value: float) -> None:
        """Called by the UI when a slider is dragged.

        Sets `attr` immediately and pins it for WEATHER_USER_OVERRIDE_DURATION_S
        sim-seconds before auto-drift is allowed to resume.  This prevents the
        engine from fighting the user's intent right after they set a value.
        """
        from config import WEATHER_USER_OVERRIDE_DURATION_S
        setattr(self, attr, value)
        self._user_override_timers[attr] = WEATHER_USER_OVERRIDE_DURATION_S

    def sync_auto_to_current(self) -> None:
        """Copy current field values into _auto_* baselines and clear all overrides.

        Call after a preset or reset so the drift engine continues from the new
        conditions rather than slowly fighting its way back from the old ones.
        Also cancels any active weather event — presets represent a deliberate
        scene choice.
        """
        self._auto_wind_speed     = self.wind_speed
        self._auto_wind_direction = self.wind_direction
        self._auto_wave_height    = self.wave_height
        self._auto_visibility     = self.visibility
        self._auto_current_speed  = self.current_speed
        self._auto_current_direction = self.current_direction
        self._user_override_timers.clear()
        self._active_event = None

    def active_event_name(self) -> Optional[str]:
        """Return the type name of the current weather event, or None."""
        return self._active_event.event_type if self._active_event is not None else None

    # ---- Existing helper methods (unchanged) ----

    def is_daylight(self) -> bool:
        """Return True if it's currently daylight (roughly 6am to 6pm)."""
        return 6.0 <= self.time_of_day < 18.0

    def day_night_tint(self) -> tuple:
        """Return an RGBA cool overlay for the day/night cycle.

        The tint is deliberately subtle — alpha peaks at full night but stays
        low enough that chart labels and depth colours remain legible. The
        transition through dawn and dusk is smoothed with a cubic curve so
        there is no visible 'step'.
        """
        from config import NIGHT_TINT_MAX_ALPHA, NIGHT_TINT_COLOR
        t = self.time_of_day
        # Full daylight: no tint
        if 7.0 <= t < 17.0:
            return (0, 0, 0, 0)
        # Ramp factor 0→1 from dusk (17 h) through deep night (21 h) and
        # back to 0 at dawn (7 h via 3 h peak).
        if t >= 17.0:
            factor = min(1.0, (t - 17.0) / 4.0)
        elif t < 3.0:
            factor = 1.0
        else:
            factor = max(0.0, 1.0 - (t - 3.0) / 4.0)
        # Smoothstep so the onset/offset feels gradual, not linear
        factor = factor * factor * (3.0 - 2.0 * factor)
        alpha = int(factor * NIGHT_TINT_MAX_ALPHA)
        return (*NIGHT_TINT_COLOR, alpha)

    def get_visibility_notes(self) -> str:
        """Return a text description of current visibility conditions."""
        if self.precipitation == "storm":
            return "STORM — severe visibility"
        elif self.precipitation == "heavy_rain":
            return "Heavy rain — reduced visibility"
        elif self.precipitation == "rain":
            return "Rain — moderate visibility"
        elif self.fog:
            return "Fog — poor visibility"
        else:
            return "Clear"

    def get_visibility_display(self) -> str:
        """Return a human-friendly visibility string.

        The environment stores `visibility` as meters. For display we prefer
        meters for short ranges and kilometres for long ranges so both the
        top status bar and panels show a consistent, sensible value.
        """
        v = float(self.visibility)
        if v >= 1000.0:
            return f"{v/1000.0:.1f} km"
        return f"{v:.0f} m"

    def status_summary(self) -> str:
        """Return a multi-line summary of environmental conditions."""
        lines = [
            f"Time: {int(self.time_of_day):02d}:{int((self.time_of_day % 1) * 60):02d}",
            f"Wind: {self.wind_speed:.1f} units/{self.wind_direction:.0f}°",
            f"Current: {self.current_speed:.1f} units/{self.current_direction:.0f}°",
            f"Visibility: {self.visibility:.0f} units",
            f"Tide: {self.tide_level:.1f}m ({self.tide_direction})",
            f"Conditions: {self.get_visibility_notes()}",
        ]
        return "\n".join(lines)
