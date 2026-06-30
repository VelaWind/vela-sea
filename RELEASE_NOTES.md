# Meridian Sea — v0.6.1 Release Notes

A stability and clarity pass on top of v0.6.0: real fullscreen, the helm can
never be taken away from you, no more pan-into-the-void crash, and hull damage
you can actually see coming.

## Fixes

### Steering & control
- **Your helm always wins.** While avoiding traffic, the player vessel could be
  assigned the give-way role and have its wheel, autopilot, and throttle quietly
  locked out until the encounter cleared (the "steering randomly does nothing"
  bug). The player is now always a stand-on obstacle — AI ships still give way to
  you correctly, but you are never auto-steered, and any manual input instantly
  reclaims the helm.

### Display
- **Fullscreen actually goes fullscreen.** The toggle was sizing the window from
  the current video mode instead of the desktop, so it never filled the screen.
  Fullscreen now uses the true desktop size (or your chosen resolution), windowed
  restores correctly, and toggling repeatedly rebuilds the view without crashing.

### Crashes & stability
- Fixed an **OverflowError crash when free-panning the camera** far off the map —
  the camera is now clamped to the world plus a margin.
- Quitting from the title screen is honoured immediately; **pausing now preserves
  your time-compression setting** instead of snapping it back to 1×.
- Long-session hardening: bounded a slowly-leaking chart cache, corrupt
  `settings.json` values fall back to defaults (a bad volume no longer loads at
  max), Space/R can't be bound over the depart/restart keys, a dropped slider
  drag releases cleanly, and several edge-case guards on save dirs and routes.

### Hull damage you can see
- Taking hull damage now **flashes the screen red** (grounding or storm), a
  persistent pulsing **"HULL CRITICAL"** banner warns you below 25% integrity,
  and the **game-over screen explains the cause in plain English** — "ran aground
  once too often", "caught out in heavy seas", or bankruptcy — instead of a bare
  "Hull failure".

Tests: pytest 16/16; gameplay bot 16/16; draw-budget check passing.

---

# Meridian Sea — v0.6.0 Release Notes

Clickable menus and a complete, persisted settings system, reachable from the
title screen and in-game.

## New in this build

### Clickable menus
- The title menu (New Career / Continue / **Settings** / Quit) is fully
  mouse-driven with hover states; keyboard navigation still works as a fallback.
- New in-game **pause menu** (Esc): Resume / Settings / Save & Quit to Title.
  Opening it freezes the sim; Save & Quit persists your career and returns to the
  title with the save intact.

### Settings (persisted to `settings.json`)
- **Audio:** master / effects / music volume sliders, applied live.
- **Display:** windowed/fullscreen toggle + resolution selector — changes re-init
  the window and rebuild the view without losing your game.
- **Controls:** rebind any core action (throttle, helm, pause, follow-cam, etc.)
  — click a row and press the new key. Duplicate and reserved keys are rejected
  with a warning.
- **Gameplay:** difficulty preset (Easy / Normal / Hard — scales zone fines and
  grounding damage by 0.5× / 1.0× / 1.5×) and a voyage-flavour log toggle.
- Settings save to the same user-writable place as the career save
  (`%APPDATA%/MeridianSea/settings.json` in the packaged build); defaults exactly
  reproduce prior behaviour, so an absent file changes nothing.

### Under the hood
- `engine/settings.py` (pure Python) is the single source of truth; input now
  routes through a rebindable action→key map instead of hardcoded keys.
- Tests: pytest 16/16; gameplay bot 16/16 (new Scenario 16 covers settings
  save/load and a remapped key driving the throttle).

---

# Meridian Sea — v0.4.0 Release Notes

This release turns the passive traffic simulator into a full maritime career
game with a progression loop: accept contract → navigate → dock → earn →
unlock better contracts → repeat.

## New in this build

### Title screen & main menu
- "MERIDIAN SEA" title menu over the live chart: New Career / Continue /
  Controls / Quit, arrow-key navigation
- Continue greys out when no save exists; `--skip-title` flag for development

### Save & load
- Career persisted to `save.json` (stdlib JSON, version-stamped)
- Auto-save every time the player docks; corrupt/wrong-version files are
  rejected cleanly
- Game over deletes the save — a lost run cannot be continued

### Docking & port menu
- Drift into any port at ≤ 2 kn to dock; menu opens automatically
- FUEL (8/pt) and REPAIR HULL (50/pt) purchases — costs shown, unaffordable
  options disabled in red; free auto-refuel removed for the player
- JOB BOARD shortcut and DEPART (also W or SPACE)

### Player autopilot
- Right-click sets a waypoint; clicking a port symbol targets the port
- Dashed route line + diamond marker; A/D manual helm cancels autopilot
- "Waypoint reached" log entry on arrival

### Expanded world
- 2 new ports: **Kessock Anchorage** (draft < 4 m, Tier 3 clearance) and
  **Outer Reach Terminal** (deep-water, open to all)
- **The Twins** rocky island pair + **Twin Rocks Conservation Area** (5 kn)
- All AI routes re-verified safe against the new geography

### New contract types
- **Hazmat** — ×1.8 rate, rep 50+, 4–6 h deadline, zone fines doubled
- **Charter** — 100/nm, 8–12 h deadline, hard 10 kn speed cap
- **VIP charter** — ×2.5 rate, Master Mariner (rep 75) exclusive

### Weather with teeth
- Fog (< 150 m): AIS hover disabled, LOW VISIBILITY HUD warning, traffic
  beyond visual range vanishes from the chart
- Storm seas: scrolling wave lines + grey-green cast at wave > 3.5 m
- Squall onset: lightning flash + SQUALL WARNING banner
- "Weather event cleared: …" log entries

### Career progression
- 4 reputation tiers: Deckhand → First Mate (25) → Captain (50) →
  Master Mariner (75), shown in the career panel
- Tier gates: rescue contracts (T2), hazmat + Kessock clearance (T3),
  VIP charters (T4)
- 4 achievements, persisted in the save: First Delivery, Storm Sailor,
  Clean Record, Lucky Escape

### Sound
- 5 effects synthesised at first launch with the standard library (no
  downloads, no numpy): engine hum, sea ambience, docking, warning, mayday
- Engine loop follows player speed; mayday on distress and game over
- Sound toggle + volume slider in the settings panel; silent fallback on
  machines without audio

### Polish
- Minimap (M): full-world overview with player dot and port squares
- Screen-edge vignette; status-bar wind as compass bearing (NE, SSW…)
- Port symbols pulse within docking range; CONTROLS screen on the title menu
- Player HUD shows active-contract destination and distance
- [YOU] badge in the vessel info panel

### Testing
- Gameplay bot expanded from 6 to 14 scenarios (all passing)
- 6 new save/load round-trip pytest cases; suite total 16 passing
- Soak-tested: ~7 ms average frame at 1×, ~9 ms at 3× in storm+fog
