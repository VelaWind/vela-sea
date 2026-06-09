# Known Issues — v0.4.0

An honest list of what doesn't work perfectly, with severity ratings.

| # | Issue | Severity |
|---|-------|----------|
| 1 | **Save scope is career-only.** Money, reputation, stats, achievements, and hull are persisted — the active contract, world state, weather, and the player's position are not. "Continue" starts a fresh session at the spawn point with your career restored. | Medium (by design for 0.4.0; full session persistence is future work) |
| 2 | **No Steam packaging yet.** The game runs from source (`python main.py`); there is no built executable, installer, Steamworks integration, or store screenshots. The README has a screenshot placeholder. | High for actual Steam submission — must be done before shipping |
| 3 | **"Clean Record" can become permanently unobtainable.** It requires 5 deliveries with `fines_paid == 0`; a single fine anywhere in the career locks it out forever, because fines never reset. | Low-Medium (arguably fair, but probably should reset per-run) |
| 4 | **Occasional frame spikes in heavy weather.** Sustained averages are well under the 16.7 ms/60 FPS budget (~9 ms at 3× in storm+fog), but isolated frames can hit ~25 ms on a software renderer (OS scheduling / sim catch-up steps). Not visible as sustained stutter. | Low |
| 5 | **Engine hum starts/stops without a fade**, so crossing the 2 kn threshold repeatedly can sound abrupt. | Low |
| 6 | **Fog visibility culling is player-centric.** With the follow cam off, vessels near the camera but far from the player are hidden too. Arguably realistic (it's *your* visibility), but can surprise when browsing the chart in fog. | Low |
| 7 | **Minimap shows only land, ports, and the player** — no zones, no AI traffic. Intentional declutter, listed for transparency. | Low |
| 8 | **AI vessels ignore contract clauses.** Hazmat double-fines and charter speed caps apply to the player only; AI traffic has its own independent mission system. | Low (by design) |
| 9 | **Time speed tops out at 3×** (key 4). Long passages across the full 210 nm sea can still take several real minutes. | Low |
| 10 | **Docking refusal reuses the departure-grace mechanism**: after being refused at a draft-restricted port you must leave its radius before any new docking attempt there registers. | Low |
