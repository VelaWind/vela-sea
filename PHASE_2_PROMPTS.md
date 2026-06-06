# Maritime Simulator — Phase 2: Make It Alive (Claude Code prompts)

**How to use this file:** Paste **Chunk D** first. Then E, then F, in order, one at a time.
After each chunk, verify with the test described, screenshot if asked, *then* move on.
Don't batch chunks — each one has visual surprises that benefit from a clean look.

The same rules from CLAUDE.md still apply: engine pure, render reads only, all numbers
in config, surgical edits, comment the *why*, and (now) commit + push at the end of each
verified task.

---

## CHUNK D — Make the sea show its depth

> Read CLAUDE.md. This is the render-layer payoff for Chunk C: the engine knows water
> depth at every point, but the chart still only shows hand-drawn shoal circles. Make the
> chart actually visualize the depth model.
>
> In `render/chart.py` + `config.py` only (no engine changes — `world.water_depth_at()`
> already exists and is correct):
>
> 1. **Depth shading across the whole sea.** Sample `world.water_depth_at()` across the
>    chart at a sensible resolution and render water in 3–4 distinct shade bands tied to
>    real depth ranges (e.g. very shallow / shallow / moderate / deep). Use the existing
>    `THEME` palette so it stays muted ECDIS, not vivid. Cache the depth field if needed —
>    don't recompute every frame for every pixel; sample on a grid and either smooth or
>    leave the bands crisp like real chart "colour-filled depth areas."
> 2. **Depth contour lines.** Draw thin contour lines at standard nautical chart depths
>    (e.g. 2m, 5m, 10m, 20m — whatever makes sense for your depth range). Label a couple
>    of them with a small number near a clear edge. Real charts always have these.
> 3. **Remove the now-redundant hand-drawn shoal circles** if the depth shading makes
>    them obviously visible. Skerry Bank should read as a real shallow patch from the
>    shading alone, not from a separate hatched circle on top.
> 4. **Tide affects what's shown.** Since `water_depth_at()` already takes tide into
>    account, the depth shading naturally shifts as tide changes — verify this works.
>    A shoal that's borderline at low tide should visibly grow as tide drops.
> 5. **Performance matters here.** Don't sample every screen pixel every frame — that
>    will tank FPS. Sample on a coarse grid (e.g. every 20–40 screen pixels), build a
>    smaller surface, scale it up with `pygame.transform.scale`. Or pre-bake the depth
>    field once per second since it only changes with tide.
>
> Put all sampling resolution / colour / contour interval values in `config.py`.
>
> **Verification:** Run the sim and screenshot. Then drop the tide (drag Time of Day) and
> screenshot again — shallow areas should visibly expand. Also confirm FPS isn't tanked.

---

## CHUNK E — Vessels doing real journeys (traffic-sim flavour)

> Read CLAUDE.md. Right now each vessel makes one voyage and stops, which makes the sim
> feel like a one-shot demo. Make it a living maritime scene where vessels do round trips
> and the ferry actually runs its route.
>
> Engine + data (`engine/ship.py`, `data/world_data.py`, `main.py`), no render changes
> needed yet:
>
> 1. **Multi-waypoint routes per vessel.** Replace each vessel's single `destination` with
>    a list of waypoints it visits in sequence. The state machine adds a new behaviour:
>    when a vessel docks (arrives at a waypoint), it pauses there for a brief, configurable
>    duration (call it a "port stay" — e.g. 15 sim-minutes for ferries, longer for cargo),
>    then sets the next waypoint and goes `underway` again.
> 2. **Looped routes.** A route can be a loop (`A → B → C → A → B → C…`) or a back-and-forth
>    (`A → B → A → B…`). The ferry MS Coastal Express should run a real schedule between
>    3 or 4 ports. Cargo ships do `home port → destination port → home`. Fishing boat does
>    `harbour → fishing ground → harbour`.
> 3. **Refuel at port stays.** When a fuel-powered vessel docks at a port that has fuel
>    (mark some/all ports as fueling-capable in `data/world_data.py`), it refuels during
>    the port stay back to full (or a configurable %). This fixes the "vessel runs out of
>    fuel forever" problem permanently — long voyages are sustainable.
> 4. **Status during port stay:** add a new status like `"in_port"` (distinct from
>    `docked` which is "arrived, won't move again") or extend the docked semantics so
>    a vessel in port doesn't move/turn/accelerate but DOES count down its stay timer
>    and then transitions back to `underway` with the next waypoint set.
> 5. **All four demo vessels get sensible routes** so the chart is always alive:
>    - Ferry: a 3- or 4-port loop, short port stays, runs constantly.
>    - Cargo: between two major ports, longer stays (loading/unloading).
>    - Fishing: harbour → fishing ground → harbour, repeat.
>    - Sailboat: a leisurely circuit between a few coves, can sit at anchor longer.
>    Pick endpoints that DON'T cross islands or Skerry Bank (or that route the deep-draft
>    cargo ship around it — that's a feature, not a bug).
> 6. **Tunables in `config.py`:** default port stay durations per vessel type, refuel-on-arrival
>    fraction, etc. Comment the *why*.
> 7. **Headless test** in `tests/`: run the sim for a few simulated hours and verify each
>    vessel completes at least one full loop and refuels successfully. Print each vessel's
>    sequence of (timestamp, status, waypoint reached) so we can see the schedule working.
>
> **Verification:** Test output should show every vessel completing multiple legs. Then
> run the sim and watch — ships should now be doing things constantly, not all parking
> after one trip.

---

## CHUNK F — Dynamic weather

> Read CLAUDE.md. The environment is currently a frozen set of slider values. Make it
> *evolve*, so weather is something the sim experiences, not a static condition.
>
> Engine + config (`engine/environment.py`, `config.py`), no render changes needed
> (panels already display the weather values; they'll just start changing on their own):
>
> 1. **Slow drift in normal conditions.** Wind speed and direction shouldn't be perfectly
>    constant — let them drift slowly via a smooth noise function (Perlin/simplex-style,
>    or just low-pass-filtered random walks). Same for current. The drift should be subtle:
>    over a sim-hour you might see wind shift 10–20° and ±2 kn, not flip wildly.
> 2. **Discrete weather events.** Occasionally (probabilistically per sim-hour) a weather
>    *event* starts: a squall, a storm front, a fog bank. Events have a defined lifecycle:
>    build up → peak → fade. While active they push wind speed, wave height, and lower
>    visibility — and they end on their own. Tunable event probabilities and intensities
>    in `config.py`.
> 3. **A small set of named events to start with:**
>    - Fog bank: visibility crashes, wind & seas calm.
>    - Squall: short burst of strong wind, brief.
>    - Storm: longer, big wind + waves + reduced visibility.
>    Each should *feel* different in the sim — the sailboat in a storm should genuinely
>    struggle (heel/no-go zone matters more), and any vessel in fog should worry.
> 4. **Sliders still work but mean "current condition."** A user dragging Wind Speed
>    overrides the dynamic value until they let go (or the sim's auto-drift slowly takes
>    over again). Don't break the controls — extend them. Decide on a sensible policy
>    (e.g. user input pins the value for a few sim-minutes then releases) and document it.
> 5. **No catastrophic mid-step jumps.** Whatever event system you build, the per-frame
>    delta should always be small and smooth so the sim doesn't snap from calm to
>    hurricane in one frame.
> 6. **Headless test:** simulate a long run (e.g. 24 sim-hours) and log the weather state
>    every sim-half-hour. Verify (a) wind direction and speed do drift, (b) at least one
>    weather event triggered and completed, (c) visibility, wave height, and wind all
>    respond to events as designed, (d) nothing went numerically insane (no infinities,
>    no negative wind speeds, etc.).
> 7. **Tunables in `config.py`:** drift rates, event probabilities, event intensity ranges,
>    event duration ranges. All commented.
>
> **Verification:** Run the sim and watch the top status bar over a few minutes — wind
> should drift, and eventually a weather event should hit (the readouts will jump and
> trend back). For a faster look, hit 4 (10× time) and watch the sky "rush." And check
> visually: in fog the visibility readout drops and (if Chunk D landed) shallow areas
> stay where they are but the overall scene should still be legible.

---

## Notes for you, not for the agent

- These three together turn the sim from "running" into "alive." After Chunk F you'll
  have weather rolling through a sea where ships are following real schedules over a
  chart that shows real depth. That's the showpiece version.
- If you want a fourth chunk later: vessel collision avoidance ("traffic" in the real
  sense) is the natural follow-on, where vessels detect each other and adjust course.
  Significantly more work, but very impressive. Hold it for after F.
- The version-control rule is now in CLAUDE.md, so each verified chunk should commit
  and push automatically. If it doesn't, ask the agent why.
