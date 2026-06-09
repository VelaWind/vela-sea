# MERIDIAN SEA
### A Maritime Career Simulator

Take the helm of MV Velawind and earn your name on the Meridian Sea. Run cargo through fog-bound straits, race a hazmat deadline past a naval exclusion zone, and limp into port with a storm-battered hull — then decide whether the repair bill is worth it before the next contract. Fifteen AI vessels live their own lives around you: trawlers working the grounds, ferries on schedule, a coast guard cutter that will come for *you* when your fuel runs dry.

![Screenshot placeholder — add chart + storm + docking menu shots before Steam submission]

## Features

- **A living sea** — 15 autonomous vessels with personalities and moods, COLREGS collision avoidance, port schedules, refuelling, trawling, even yacht parties with a dispatched tender
- **Career progression** — accept contracts from the job board, earn money and reputation, climb four ranks from Deckhand to Master Mariner; higher tiers unlock rescue work, hazmat runs, and exclusive VIP charters
- **Seven contract types** — delivery, rescue assist, patrol, hazmat (double zone fines!), passenger charter (10 kn comfort cap), VIP charter
- **Real consequences** — zone fines, grounding hull damage, storm attrition, bankruptcy; lose the hull or the wallet and the run is over (and your save with it)
- **Dynamic weather that matters** — fog hides traffic and disables your AIS, squalls flash and drench the chart, storms cap your speed and grind the hull
- **Navigation your way** — hands-on W/A/S/D helm or right-click autopilot waypoints, with a full-world minimap and ECDIS-style chart: depth shading, tide-aware soundings, restricted zones, traffic separation schemes
- **Ten ports** across a 210 nm sea, from the deep-water Outer Reach Terminal to the draft-restricted Kessock Anchorage (Captains only)
- **Save & continue** — automatic checkpoint every time you dock
- **Achievements** — First Delivery, Storm Sailor, Clean Record, Lucky Escape
- **Generated audio** — engine hum, sea ambience, docking clunks, and distress alarms, synthesised at first launch (no asset downloads)

## Controls

| Key / Action | Effect |
|---|---|
| W / S | Throttle up / down |
| A / D | Steer port / starboard (cancels autopilot) |
| Right-click | Set autopilot waypoint — click a port symbol to target it |
| F | Toggle follow camera |
| J | Career panel & job board |
| M | Toggle minimap |
| E | Environment settings (weather, time, sound) |
| T | Technical systems panel |
| Tab | Cycle vessel selection |
| Click vessel | Select and follow |
| Space | Pause — in port: depart |
| 1 / 2 / 3 / 4 | Time speed: pause / 1× / 2× / 3× |
| Mouse drag / wheel | Pan / zoom the chart |
| Z | Reset zoom |
| Up/Down + Enter | Navigate menus (title, docking) |
| R | Restart after game over |
| Esc | Quit |

**Docking:** drift into a port at 2 knots or less and the port menu opens automatically — refuel, repair the hull, browse the job board, or cast off.

## How to run

Requires Python 3.10+ and pygame:

```
pip install -r requirements.txt
python main.py
```

`python main.py --skip-title` jumps straight into the game (handy for development). No accounts, no API keys, no internet connection needed.

## Architecture (for contributors)

```
engine/          Pure Python, zero Pygame — all simulation logic
  world.py       World, Port (berths, draft limits), Island, Zone, NavMark
  ship.py        Vessel: physics, fuel, route state machine, autopilot field
  environment.py Weather drift, events (fog/squall/storm), tide, day/night
  collision.py   COLREGS avoidance: CPA/TCPA, give-way logic, safe pathfinding
  career.py      PlayerCareer, JobBoard, contracts, tiers, save/load (JSON)
  mission.py     AI mission generation and tracking

render/          Pygame drawing — reads engine state, never mutates it
  camera.py      Single source of world↔screen conversion
  chart.py       Chart layers, vessels, weather visuals, vignette, status bar
  panels.py      HUD, career, docking menu, title, controls, minimap, game over
  sound.py       SoundManager + stdlib WAV synthesis

data/world_data.py   Meridian Sea geography and AI routes
tests/               Headless pytest suite + 14-scenario gameplay bot
main.py              Game loop: input → fixed-timestep sim → render
config.py            Every tunable number in the project
```

Conventions: the engine never imports Pygame; renderers never write state; every constant lives in `config.py`. Run `pytest tests/ -q` and `python tests/test_bot.py` (14 scenarios) before committing.

## Tech

- Python 3.10+ · [pygame](https://www.pygame.org/) 2.x
- Sound effects generated with the standard library — no binary assets
- Fully open source, no external services
