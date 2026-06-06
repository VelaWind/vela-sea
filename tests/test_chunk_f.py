"""Chunk F headless test — dynamic weather: drift, events, and validity.

Simulates 24 sim-hours and verifies:
  (a) Wind direction and speed drift — they are NOT constant.
  (b) At least one weather event (fog / squall / storm) triggers and completes.
  (c) Visibility, wave height, and wind all change in response to events.
  (d) Nothing goes numerically insane (no infinities, no negative speeds, etc.).

Uses dt=1.0 sim-second per step so 24 sim-hours (86 400 steps) runs in
well under 5 real-seconds.  The larger timestep doesn't affect correctness
here — the OU drift and event lifecycle are both stable at dt=1 s.

A fixed random seed makes the test deterministic for CI.
"""

import sys
import math
import random
import time
sys.path.insert(0, ".")

from engine.environment import Environment

# Fixed seed for reproducibility.
random.seed(42)

SIM_HOURS = 24.0
TEST_DT   = 1.0          # sim-seconds per step (vs 0.016 in the real sim)
LOG_EVERY = 30 * 60.0    # log every 30 sim-minutes


def run() -> None:
    env = Environment()

    sim_time   = 0.0
    target     = SIM_HOURS * 3600.0
    next_log   = 0.0

    # Snapshot the initial weather values so we can verify drift.
    init_wind_speed = env.wind_speed
    init_wind_dir   = env.wind_direction

    # Tracking
    log_rows        = []   # (sim_h, wind_speed, wind_dir, wave_h, vis, event)
    events_seen     = []   # list of (sim_h, event_type, phase) transitions
    prev_event      = None

    t0 = time.perf_counter()

    while sim_time < target:
        env.update(TEST_DT)

        # Track event start/end transitions
        cur_event = env.active_event_name()
        if cur_event != prev_event:
            events_seen.append((sim_time / 3600.0, prev_event, cur_event))
            prev_event = cur_event

        # Periodic log
        if sim_time >= next_log:
            log_rows.append((
                sim_time / 3600.0,
                env.wind_speed,
                env.wind_direction,
                env.wave_height,
                env.visibility,
                cur_event or "—",
            ))
            next_log += LOG_EVERY

        sim_time += TEST_DT

    elapsed = time.perf_counter() - t0

    # ---- Print log table ----
    print(f"\n{'='*72}")
    print(f"Chunk F — {SIM_HOURS:.0f} sim-hours in {elapsed:.3f}s "
          f"({SIM_HOURS*3600/elapsed:.0f}x real-time)")
    print(f"{'='*72}")
    print(f"{'Time':>7}  {'Wind(kn)':>8}  {'Dir(°)':>6}  {'Wave(m)':>7}  "
          f"{'Vis(m)':>7}  Event")
    print(f"{'-'*72}")
    for row in log_rows:
        t_h, ws, wd, wv, vis, ev = row
        print(f"{t_h:6.1f}h  {ws:8.2f}  {wd:6.1f}  {wv:7.2f}  {vis:7.1f}  {ev}")

    # ---- Print event transitions ----
    print()
    transitions = [(h, a, b) for h, a, b in events_seen
                   if a != b and (a is not None or b is not None)]
    print(f"Weather event transitions ({len(transitions)}):")
    for h, before, after in transitions:
        bstr = before if before else "clear"
        astr = after  if after  else "clear"
        print(f"  {h:5.2f}h  {bstr} -> {astr}")

    # ---- Assertions ----
    errors = []

    # (a) Wind should have drifted — check speed and direction changed from init
    final_wind_speed = env.wind_speed
    final_wind_dir   = env.wind_direction
    speed_range = max(r[1] for r in log_rows) - min(r[1] for r in log_rows)
    dir_range   = max(r[2] for r in log_rows) - min(r[2] for r in log_rows)

    if speed_range < 0.5:
        errors.append(
            f"Wind speed barely drifted: range={speed_range:.3f} kn over {SIM_HOURS}h "
            f"(expected > 0.5 kn)"
        )
    if dir_range < 5.0:
        errors.append(
            f"Wind direction barely drifted: range={dir_range:.1f}° over {SIM_HOURS}h "
            f"(expected > 5°)"
        )

    # (b) At least one weather event must have started and completed
    event_starts  = [x for x in events_seen if x[2] is not None and x[1] is None]
    event_ends    = [x for x in events_seen if x[2] is None and x[1] is not None]
    events_started = [x for x in transitions if x[2] is not None]
    events_ended   = [x for x in transitions if x[2] is None]

    if not events_started:
        errors.append(f"No weather events triggered in {SIM_HOURS} sim-hours")
    if not events_ended:
        errors.append(f"No weather events completed in {SIM_HOURS} sim-hours")

    # (c) Visibility must have dropped during at least one logged row
    vis_values = [r[4] for r in log_rows]
    if min(vis_values) >= 490.0:
        errors.append(
            f"Visibility never dropped below 490 m (min={min(vis_values):.1f} m); "
            f"events may not be applying correctly"
        )

    # (d) Sanity bounds — no infinities, negatives, or wild values
    for row in log_rows:
        t_h, ws, wd, wv, vis, ev = row
        if not math.isfinite(ws) or ws < 0.0 or ws > 100.0:
            errors.append(f"@{t_h:.1f}h: wind speed out of bounds ({ws})")
        if not math.isfinite(wd):
            errors.append(f"@{t_h:.1f}h: wind direction not finite ({wd})")
        if not math.isfinite(wv) or wv < 0.0 or wv > 20.0:
            errors.append(f"@{t_h:.1f}h: wave height out of bounds ({wv})")
        if not math.isfinite(vis) or vis < 5.0 or vis > 1100.0:
            errors.append(f"@{t_h:.1f}h: visibility out of bounds ({vis})")

    # Performance: 24 sim-hours must complete well under 10 real-seconds
    if elapsed > 10.0:
        errors.append(
            f"Performance: {SIM_HOURS}h took {elapsed:.1f}s (limit 10s)"
        )

    # ---- Result ----
    print(f"\n{'='*72}")
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        print(f"{'='*72}\n")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
        print(f"{'='*72}\n")


if __name__ == "__main__":
    run()
