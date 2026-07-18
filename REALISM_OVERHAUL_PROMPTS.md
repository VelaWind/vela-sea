# Maritime Simulator — Realism Overhaul (Claude Code prompts)

**How to use this file:** Paste **Chunk 0** into Claude Code first. Then paste Chunks 1→7
one at a time, in order. At the top of *every* chunk after Chunk 0, re-paste the short
**PREAMBLE** block (it survives Claude Code's mid-task "compaction" so it doesn't drift).

Do **not** paste all of this at once — it will compact and lose the plan.

---

## PREAMBLE (re-paste this at the top of every chunk)

> **Project:** Python + Pygame maritime navigation simulator at `D:\VelaSea`.
> **Goal:** Make it look and behave like a real ECDIS / chartplotter (think Navionics /
> Garmin BlueChart), not a game. Calm, muted, professional, legible.
> **Hard rules:**
> - Engine (`engine/`) stays pure Python, no Pygame. Rendering (`render/`) only *reads*
>   engine state, never mutates it and never stores its own copy of a value.
> - All tunable numbers live in `config.py`, never hard-coded in logic.
> - Comment *why*, not just *what* — I'm learning from this code.
> - Work from the **actual files on disk**, not from memory. Read a file before editing it.
> - After each change, run `python -m py_compile` on touched files and tell me what you
>   changed and how to verify it visually.

---

## CHUNK 0 — Read, report, don't change yet

Paste this exactly:

> Using the PREAMBLE above: **do not edit anything yet.** First read these files in full
> and give me a short report: `main.py`, `config.py`, `engine/ship.py`, `engine/world.py`,
> `engine/environment.py`, `render/camera.py`, `render/chart.py`, `render/panels.py`.
>
> In the report, confirm for me:
> 1. Exactly how the simulation clock works today — does `is_paused` actually stop vessel
>    movement, and does the 1/2/3/4 time-speed multiplier actually scale vessel movement,
>    or only the environment?
> 2. The exact math in `camera.zoom_at()` and `screen_to_world()` / `world_to_screen()`.
> 3. What units vessel speed is in right now, and how far a vessel travels per real second.
> 4. How vessel labels and the destination/route line are drawn in `chart.py`.
>
> Then wait for my next message. Don't fix anything yet.

*(This makes Claude Code ground itself in the real code before touching it. Send me its
report if you want a second opinion before continuing.)*

---

## CHUNK 1 — Fix the clock: pause, speed, and realistic motion (highest priority)

> Re-paste PREAMBLE. Then:
>
> **Problem:** Ships move even when paused, the 1/2/3/4 keys don't change ship speed (only
> the environment), and ships are absurdly fast because speed is "units per real second."
>
> **Fix the simulation clock so one single scaled timestep drives everything:**
> 1. Treat world units as **nautical miles** and vessel speed as **knots** (nautical miles
>    per hour). Add to `config.py`:
>    - `KNOTS_TO_UNITS_PER_HOUR = 1.0`  # 1 knot = 1 unit/hour (units are nm)
>    - `TIME_COMPRESSION = 90.0`  # sim-seconds advanced per real second at 1x (tune later)
>    - Keep `SIM_TIMESTEP = 0.016` as the *fixed physics step* (stability), separate from speed.
> 2. In `main.py`'s `update_simulation`, compute one effective multiplier:
>    `sim_speed = 0.0 if self.is_paused else self.environment.time_speed_multiplier`
>    Then scale the *incoming* real `dt` by `sim_speed * TIME_COMPRESSION` BEFORE the
>    fixed-step accumulator loop. If `sim_speed == 0`, advance nothing (full freeze:
>    environment AND vessels).
> 3. Pass the **same** scaled timestep into `environment.update(...)`, `vessel.update_speed(...)`,
>    `vessel.turn_toward(...)`, and `vessel.move(...)`. Nothing should ever move on an
>    unscaled `SIM_TIMESTEP` again.
> 4. In `engine/ship.py`, make `move()` convert knots→units correctly:
>    distance this step = `current_speed * KNOTS_TO_UNITS_PER_HOUR * (timestep_seconds / 3600.0)`.
> 5. **Fix the docked-spin bug:** when a vessel's status is `"docked"` or `"aground"`, it must
>    NOT call `turn_toward`, must NOT accelerate, and must hold heading. Only navigate toward
>    a destination when status is something like `"underway"`. Add a clear status state machine
>    in `ship.py` and document it.
> 6. Make arrival hysteresis sane: arrive within `ARRIVAL_DISTANCE`, then latch `docked` and
>    stop re-evaluating navigation so it can't jitter back to "underway."
>
> **Acceptance check (tell me how to test):** At 1x a ferry should visibly but slowly cross
> the chart over a minute or two; pressing 1 (pause) should freeze *everything*; 3 and 4
> should make ships visibly faster; a docked vessel's heading must stay constant.
> If `TIME_COMPRESSION = 90` feels too fast or slow, tell me the one number to change.

---

## CHUNK 2 — Fix zoom-toward-cursor and verify coordinate math

> Re-paste PREAMBLE. Then:
>
> **Problem:** Scrolling to zoom moves the view toward the *opposite* side of the cursor.
>
> **Fix `render/camera.py` so the world point under the cursor stays pinned during zoom:**
> 1. Implement `zoom_at(screen_pos, factor)` as the canonical version:
>    - `world_before = self.screen_to_world(screen_pos)`
>    - apply and clamp the new zoom
>    - `world_after = self.screen_to_world(screen_pos)`
>    - shift the camera's world-center by `(world_before - world_after)` so the cursor's
>      world point lands back under the cursor.
> 2. Make sure `screen_to_world` and `world_to_screen` are exact inverses. Add a tiny
>    self-test function (run once at import or behind a `--selftest` flag) that asserts
>    `world_to_screen(screen_to_world(p)) == p` for several points and zoom levels.
> 3. Add scroll-wheel **anchored zoom limits** so clamping zoom doesn't break the pin.
> 4. Comment the formula clearly — explain *why* we measure the world point before and after.
>
> **Acceptance check:** Put the cursor over a specific port and scroll; that port must stay
> exactly under the cursor as the map grows/shrinks.

NOTE: Chunk 2 is already done — the zoom now pins correctly. Skip unless asked.

---

## CHUNK 3 — Make the chart read like a real plotter (the big visual jump)

> Re-paste PREAMBLE. Then, in `render/chart.py` and `config.py` only (no engine changes):
>
> **Target aesthetic:** a calm, professional ECDIS/Navionics day palette. Reference feel:
> pale blue-grey deep water, lighter shallow water, buff/tan land, thin clean coastlines,
> subtle grid. Everything muted and low-contrast except vessels and warnings.
>
> 1. **Water depth shading:** render deep water, a lighter shallow band near coasts, and one
>    or two thin depth-contour lines. Even a faked 2–3 band gradient reads far more "chart"
>    than a single flat fill. Drive colors from `config.THEME`.
> 2. **Land:** fill buff/tan, draw a crisp 1px coastline a shade darker, drop the heavy black
>    look. Optional faint inland shading for depth.
> 3. **Graticule:** keep the grid but make minor lines very faint and major lines slightly
>    stronger; label the axes cleanly (units, or fake lat/lon ticks) in a small mono font with
>    a dark halo so labels never fight the grid.
> 4. **Zones:** keep the standard color language (magenta = restricted/no-entry, etc.) but
>    make fills very low-alpha and hatching thin and sparse — right now they look heavy/"game-y."
>    Draw zone labels with a halo and only when the zone is reasonably on-screen.
> 5. **Scale bar + north arrow:** make the scale bar reflect real nautical-mile distance at the
>    current zoom (e.g. "5 nm"), and give it a clean tick design. Tidy the compass rose.
> 6. **Top data bar:** turn the cramped header into a clean strip: UTC/sim time, wind, vis,
>    and current sim speed, evenly spaced, muted mono font.
>
> **Acceptance check:** A screenshot should look like a marine chartplotter, not a flat
> diagram: layered water, clean coast, faint grid, restrained zones, readable scale.

NOTE: Chunk 3 is already done. Skip unless asked.

---

## CHUNK 4 — Vessel symbols: own-ship triangle, heading + course vectors, range rings

> Re-paste PREAMBLE. Then, in `render/chart.py` + `config.py`. Heading and COG vectors
> already exist — refine them, don't duplicate them:
>
> 1. Draw each vessel as a proper directional symbol (a slim isosceles triangle / boat shape)
>    that points along its **heading**, sized sensibly and scaling gently with zoom (clamp to
>    `SHIP_MIN_SIZE` / `SHIP_MAX_SIZE`).
> 2. Keep the thin **heading line** from the bow, and refine the **COG/SOG predictor**: a
>    dashed line showing where the vessel will be in N minutes at current speed. The long
>    unclipped line on screen right now is this predictor (or the selected connector) drawn
>    with no limit — cap it to N minutes of travel and clip all vessel lines to the visible
>    chart so nothing shoots across the whole window.
> 3. **Selected vessel:** highlight with a clean ring/glow (not a fat circle), and draw 2–3
>    faint **range rings** around it labelled in nm. Deselected vessels stay subtle.
> 4. Color vessels by state subtly: underway = default, docked = dimmed, aground/warning = the
>    warning color. Keep it tasteful.
>
> **Acceptance check:** Selecting a vessel shows a clear pointed symbol, a heading line, a
> dashed course predictor, and range rings — and the old yellow cross-screen line is gone.

---

## CHUNK 5 — Declutter labels (stop the text pile-up)

> Re-paste PREAMBLE. Then, in `render/chart.py`:
>
> **Problem:** Labels overlap badly ("SY Windward" over "Vesper Cove", vessel names over port
> names). Real plotters declutter aggressively.
>
> 1. Add a small text helper that draws every label with a dark semi-transparent halo/pill
>    behind it so text is readable over any background.
> 2. Implement simple **label priority + collision avoidance**: collect candidate label rects,
>    and if two overlap, keep the higher-priority one (selected vessel > ports > zones >
>    other vessels) and either hide or offset the loser. A short leader line to the offset
>    label is a nice touch.
> 3. **Zoom-based decluttering:** when zoomed out, show only port names and the selected
>    vessel's name; reveal more labels as the user zooms in.
> 4. Make sure a label is anchored to its symbol with a small consistent offset, and never
>    drawn off the visible chart edge.
>
> **Acceptance check:** No two labels visibly overlap at default zoom; zooming in progressively
> reveals more detail.

---

## CHUNK 6 — Fix panel layout and overflow

> Re-paste PREAMBLE. Then, in `render/panels.py`:
>
> **Problems seen:** stray floating characters (e.g. a lone "—" under ETA), text that risks
> running past the panel edge, and panels that may not fit when the window is resized.
>
> 1. Give every panel a single layout system: fixed inner margin, consistent line height, and
>    a helper that draws a "label … value" row right-aligned within the panel's inner width.
>    No value should ever be drawn outside the panel rect.
> 2. Wrap or truncate long strings (e.g. "Effective sail power", wind notes) to the panel width;
>    truncate with an ellipsis rather than overflowing.
> 3. Audit for stray glyphs / empty rows (the lone dash) and remove them. If ETA is undefined,
>    print a clean "—" *as the value column*, aligned like every other row.
> 4. Make panel position/size derive from the current window size so panels stay fully on-screen
>    at the larger window dimensions, with a small margin from the edges.
> 5. Keep the dark ECDIS panel styling but ensure section headers, labels, and values use a
>    consistent type scale from `config.py`.
>
> **Acceptance check:** Every panel's text sits cleanly inside its border at the real window
> size; no overflow, no orphan characters, values right-aligned in a tidy column.

---

## CHUNK 7 — Final polish pass

> Re-paste PREAMBLE. Then do a polish sweep (small, safe changes only):
>
> 1. Day/night tint from time-of-day should be subtle (a gentle warm/cool overlay), never so
>    dark it hurts legibility.
> 2. Anti-alias vessel triangles, rings, and the compass (use `pygame.draw.aa*` or draw to a
>    higher-res surface and downscale) so nothing looks jagged.
> 3. Verify keyboard help text matches the real keys (the settings panel listed `E` for
>    settings — make sure `S` and `E` either both work intentionally or pick one and document it).
> 4. Soften the shallow-water band so it reads as a depth fade, not a heavy outline.
> 5. Re-run `python -m py_compile` on all touched files and give me a final summary + a short
>    "what to click to verify each fix" checklist.
>
> **Acceptance check:** One clean screenshot that genuinely looks like a usable marine
> chartplotter, plus a verification checklist.
