# Maritime Navigation Simulator

A realistic maritime traffic simulator with an ECDIS-style chartplotter display, built with Python and Pygame.

## What it is

The simulator models the fictional **Meridian Sea** — a 1000×1000 nautical mile world with islands, ports, restricted zones, and 8 vessels operating on continuous schedules. The display is styled after real electronic chart display systems (ECDIS/chartplotters): muted blues, depth contours, zone overlays, vessel icons, and a status bar showing live environmental conditions.

This is not a game. There is no player-controlled vessel. It is a passive traffic simulation you observe and interact with through time controls and vessel selection.

## What it simulates

**8 vessels** running autonomously on fixed routes with port stays and refuelling:

| Vessel | Type | Route |
|--------|------|-------|
| MV Meridian | Cargo | Port Maren ↔ Port Ardent, south corridor |
| MV Carrick Star | Cargo | Port Maren → Port Ardent → Brattlin loop |
| MS Coastal Express | Ferry | Maren → Ardent → Brattlin → Vesper circuit |
| FV Horizon | Fishing | Saltgate grounds circuit |
| FV Skerrywatch | Fishing | Northern fishing grounds |
| SY Windward | Sailboat | Eastern ocean circuit (wind-powered) |
| SY Meridian Breeze | Sailboat | Western triangle from Saltgate |
| Ardent Pilot | Tug | Port Ardent ↔ Brattlin Light Quay shuttle |

Each vessel has its own length, beam, draft, max speed, fuel capacity, and consumption rate. Sailboats have no fuel — they respond to wind angle, can stall in irons, and coast to a stop in no-go zones.

## Key features

- **Vessel physics** — inertia, acceleration/deceleration, speed-dependent turn rate, fuel burn
- **COLREGS collision avoidance** — CPA/TCPA calculation, give-way/stand-on rules, emergency avoidance at close range
- **Dynamic weather** — wind, fog, squalls, storms; visibility drops; active event shown in status bar
- **Tidal depth model** — water depth varies with tide; vessels with deep draft ground on shoals at low water
- **ARPA-style vessel icons** — distinct silhouettes per vessel type (cargo, ferry, fishing, sailboat, tug), rotated to heading
- **Day/night cycle** — chart tint shifts with simulated time of day
- **Five ports** with docking, stay timers, and refuelling
- **Restricted zones** — speed limits, no-entry areas, traffic separation schemes, conservation areas
- **Live info panel** — selected vessel's dimensions, speed, heading, fuel, destination, ETA

## How to run

Requires Python 3.10+ and two free libraries:

```
pip install pygame pillow
python main.py
```

No other dependencies. No accounts, no API keys, no internet connection needed.

## Controls

| Key / Action | Effect |
|---|---|
| Click vessel | Select and follow |
| Tab | Cycle through vessels |
| Click empty water | Deselect |
| Scroll wheel | Zoom in/out |
| Arrow keys | Pan chart |
| Z | Reset zoom |
| Space | Pause / unpause |
| 1 | Pause (same as Space) |
| 2 | 1× speed |
| 3 | 2× speed |
| 4 | 3× speed (max) |
| T | Toggle technical systems panel |
| S / E | Toggle settings panel |
| Esc | Quit |

## Architecture

```
engine/          Pure Python, no Pygame — all simulation logic
  world.py       World, Port, Island, Zone, NavMark
  ship.py        Vessel: position, heading, speed, fuel, state machine
  environment.py Weather, time of day, currents, tide
  collision.py   COLREGS avoidance: CPA/TCPA, give-way logic
  rules.py       Zone restriction enforcement

render/          Pygame drawing — reads engine state, never writes it
  camera.py      Single source of world↔screen coordinate conversion
  chart.py       Chart, grid, depth, zones, vessel icons, status bar
  panels.py      Info, technical, and settings panels
  vessel_icons.py Pre-rendered hull silhouettes per vessel type

data/
  world_data.py  Meridian Sea geography and vessel routes
  missions.py    Mission definitions

tests/           Headless test suite (no display required)
main.py          Main loop: input → update → render
config.py        All tunable constants (colours, sizes, physics)
```

All simulation state lives in `World`, `Vessel`, and `Environment`. Renderers only read — they never mutate engine state. All magic numbers are in `config.py`.

## Tech

- Python 3.10+
- [pygame](https://www.pygame.org/) 2.x — rendering and input
- [pillow](https://python-pillow.org/) — image utilities
- No paid services, no external APIs, fully open source
