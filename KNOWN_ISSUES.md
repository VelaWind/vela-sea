# Known Issues — v0.6.1

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
| 11 | **Displaced vessels have no defined way back to their route.** Routes in `data/world_data.py` are verified as geometry (`tests/verify_new_routes.py`), but rescue duty, MOB searches, trawl wander, party-tender runs and tide refloating all move vessels far off that geometry, and every "hand back to the schedule" site then sets `destination = route[route_index]` — a straight line from wherever the vessel ended up. Measured over 3 seeds x 14 sim-days: **84% of groundings occur >15 wu from the vessel's own route, against 1% on it.** See the design note below. | Medium — the largest remaining source of AI groundings |

---

## Design note — the displacement-return problem (open)

Three separate attempts to fix this each measured *worse* than the shipped
baseline (`b5d7a64`), which is why none of them landed. They are recorded
here because the failures were informative and the patches still apply.

**Why it is a design question, not a bug.** `b5d7a64` reaches a state where
relatively few vessels are displaced, and those that ground mostly stay
grounded. Every change that increases fleet activity or displacement surfaces
grounding the static routes were never validated against. Fixing the symptom
without deciding the model just moves the population around.

Two concrete mechanisms were identified and neither is addressed:

1. **Commanded vessels are invisible to their own schedule.** Routing a
   displaced vessel home via the multi-hop `player_commanded` machinery keeps
   it commanded for most of its life — measured 73–97% of runtime for several
   vessels, with near-zero route-waypoint advances. Being commanded *is* the
   off-route condition, so this cures nothing and starves the fleet
   (arrivals 503 -> 170). `player_commanded` also excludes a vessel from SAR
   dispatch eligibility, so displaced vessels stop being available as rescuers.
2. **The return target is a single scheduled waypoint**, `route[route_index]`,
   rather than the nearest sensible entry point on the route as a whole. A
   vessel dragged 200 wu away is aimed at the one waypoint it happened to be
   heading for, which may be on the far side of an island.

Worth deciding before more code: should a displaced vessel rejoin at its
nearest route *entry point*? Should routes carry explicit entry/exit nodes?
Should rescuers return under schedule control rather than command state?

Rejected patches (each applies cleanly on `b5d7a64`, each fully measured):

| patch | what it does | measured result |
|-------|--------------|-----------------|
| `crab.patch` | leeway/crab-angle compensation in `Vessel.crabbed_heading` — steers course-over-ground, not bearing | **Correct and unit-proven**: holds pinch-leg clearance flat at 4.66 wu across 0–25 kn wind (was bleeding 0.22 wu/kn and grounding at 15 kn). But only ~1% of groundings are on-route, so it does not move the total: uniq/arr 0.125 -> 0.857 |
| `refloat_v2.patch` | on refloat, move to a low-water-sized seaward standoff instead of refloating in place | Kills the 157x same-spot loop and transforms rescue health (never-rescued 10% -> 3%), but re-exposes freed vessels: uniq/arr 0.125 -> 0.742 |
| `return_leg.patch` | route the return leg via `find_safe_path` + `_pending_player_paths` | Off-route share unchanged (84% -> 83%); arrivals 503 -> 170. This is mechanism 1 above |

The patches live in the session scratchpad
(`%LOCALAPPDATA%\Temp\claude\d--VelaSea\<session-id>\scratchpad\`), which is
**ephemeral** — copy them somewhere durable before relying on them, or
regenerate from this note.

Measurement standard for any future attempt: `python tools/diag_groundings.py
--days 14 --seeds 3`, and **normalise by arrivals, not raw event counts** — a
vessel stuck aground stops generating both, so a change that strands traffic
looks like a fix if you only count groundings.
