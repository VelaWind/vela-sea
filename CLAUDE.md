# CLAUDE.md — AI Context for gps-simulator (Meridian Sea)

## Project Overview
**Meridian Sea** — a Python + Pygame maritime career simulator (v0.5.1,
Steam release candidate). The player captains MV Velawind on a 210 nm
fictional sea: accept contracts, navigate, dock, earn money and reputation,
unlock higher-tier work. 15 AI vessels run autonomous schedules around them
with COLREGS collision avoidance, dynamic weather, tides, and SAR rescue.

## Tech Stack
- **Language:** Python 3.10+
- **Framework:** Pygame 2.x (rendering/input only)
- **Package Manager:** pip (`requirements.txt`)
- **Tests:** pytest + a 14-scenario headless gameplay bot

## Hard Architecture Rules
1. `engine/` is pure Python — **zero Pygame imports, ever**
2. `render/` reads engine state, **never mutates it**
3. **All tunable numbers live in `config.py`** — no magic numbers in logic
4. Compile (`python -m py_compile`) every touched file; run
   `pytest tests/ -q` **and** `python tests/test_bot.py` (must be 14/14)
   after every feature; commit per feature, never batch

## Project Structure
```
engine/            Pure simulation logic
  world.py         World, Port (berths, max_draft_m), Island, Zone, NavMark
  ship.py          Vessel dataclass: physics, fuel, routes, is_player,
                   hull_integrity, autopilot_destination
  environment.py   Weather OU-drift, events (fog/squall/storm), tide, time
  collision.py     CPA/TCPA COLREGS avoidance + find_safe_path
  career.py        PlayerCareer (money/rep/achievements/tier_name), JobBoard,
                   Contract (7 types), save_career/load_career/delete_save,
                   REP tiers, ACHIEVEMENT_DEFS
  mission.py       AI mission generation/tracking
render/            Pygame view layer
  camera.py        World↔screen conversion (single source of truth)
  chart.py         Chart layers, vessels, weather visuals, vignette,
                   squall flash, fog culling, status bar
  panels.py        VesselInfo, TechSystems, Settings (sound controls),
                   EventLog, FleetStatus, Mission, PlayerHUD, Career,
                   DockingMenu, Title, Controls, Minimap, GameOver
  sound.py         SoundManager + stdlib WAV synthesis (5 effects,
                   generated into assets/sounds/ at first run)
data/world_data.py 10 ports, islands (incl. The Twins), zones, AI routes
tests/             pytest suite + test_bot.py (14 scenarios) +
                   verify_new_routes.py (route safety checker)
main.py            Game class: title loop, fixed-timestep sim, input, render
config.py          Every constant: physics, colors, career, sound, polish
```

## Key Systems (where to look)
- **Player loop:** main.py `update_simulation` player branch — keyboard helm,
  autopilot steering, proximity docking (≤ 2 kn inside port radius), storm
  caps, zone fines (hazmat ×2), charter speed cap, grounding damage
- **Docking:** `DockingMenuPanel` (render) + `Game._apply_docking_action` /
  `_player_depart` / `_on_player_docked` (mutations happen in Game only)
- **Persistence:** `engine/career.py` save/load (JSON, version-stamped);
  auto-save on dock; deleted on game over; "Continue" on title restores
- **Progression:** REP_TIER_* in config; tier gates in contract templates;
  Kessock draft clearance at Tier 3; achievements awarded via
  `Game._award_achievement`
- **Weather gameplay:** fog gates hover/labels (chart) + HUD warning (main);
  storm visuals keyed to `STORM_WAVE_THRESHOLD` so they always agree with
  the speed-cap consequence
- **Sound:** `SoundManager` — silent-fallback on any mixer failure; loops
  (engine, ambient) + one-shots (docking, warning, mayday)

## Testing
- `pytest tests/ -q` — 16 tests (collision, traffic, save/load, bot)
- `python tests/test_bot.py` — human-readable 14-scenario report
- `python tests/verify_new_routes.py` — run after ANY geography change
- `python tests/test_visual_perf.py` — draw_all budget (< 8 ms)
- Bot redirects saves to a temp path — never touches the player's save.json

## What to Avoid
- Do not put Pygame imports or rendering state in `engine/`
- Do not mutate vessels/career from `render/` panels — return actions to Game
- Do not commit `save.json` (gitignored) or skip the route safety check
- Do not let FPS fall below 60 at default zoom — profile before committing
