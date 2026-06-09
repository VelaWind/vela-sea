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
