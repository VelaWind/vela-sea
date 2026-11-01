# Known Issues: v0.6.2

An honest list of what doesn't work perfectly, with severity ratings.

| # | Issue | Severity |
|---|-------|----------|
| 1 | **Save scope is career-only.** Money, reputation, stats, achievements, and hull are persisted — the active contract, world state, weather, and the player's position are not. "Continue" starts a fresh session at the spawn point with your career restored. | Medium (by design for 0.4.0; full session persistence is future work) |
| 2 | **No Steam packaging yet.** A Windows build exists: `.github/workflows/release.yml` builds `VelaSea.exe` with PyInstaller and attaches `VelaSea-windows.zip` to each GitHub Release (v0.6.1 is the first). It is unsigned, so Windows SmartScreen warns on first launch, and there is no Mac or Linux build. Still missing for Steam: an installer, Steamworks integration and a store page. | High for actual Steam submission; must be done before shipping |
| 3 | **"Clean Record" can become permanently unobtainable.** It requires 5 deliveries with `fines_paid == 0`; a single fine anywhere in the career locks it out forever, because fines never reset. | Low-Medium (arguably fair, but probably should reset per-run) |
| 4 | **Occasional frame spikes in heavy weather.** Sustained averages are well under the 16.7 ms/60 FPS budget (~9 ms at 3× in storm+fog), but isolated frames can hit ~25 ms on a software renderer (OS scheduling / sim catch-up steps). Not visible as sustained stutter. | Low |
| 5 | **Engine hum starts/stops without a fade**, so crossing the 2 kn threshold repeatedly can sound abrupt. | Low |
| 6 | **Fog visibility culling is player-centric.** With the follow cam off, vessels near the camera but far from the player are hidden too. Arguably realistic (it's *your* visibility), but can surprise when browsing the chart in fog. | Low |
| 7 | **Minimap shows only land, ports, and the player** — no zones, no AI traffic. Intentional declutter, listed for transparency. | Low |
| 8 | **AI vessels ignore contract clauses.** Hazmat double-fines and charter speed caps apply to the player only; AI traffic has its own independent mission system. | Low (by design) |
| 9 | **Time speed tops out at 3×** (key 4). Long passages across the full 210 nm sea can still take several real minutes. | Low |
| 10 | **Docking refusal reuses the departure-grace mechanism**: after being refused at a draft-restricted port you must leave its radius before any new docking attempt there registers. | Low |
| 11 | **Displaced vessels have no defined way back to their route.** Routes in `data/world_data.py` are verified as geometry (`tests/verify_new_routes.py`), but rescue duty, MOB searches, trawl wander, party-tender runs and tide refloating all move vessels far off that geometry, and every "hand back to the schedule" site then sets `destination = route[route_index]` — a straight line from wherever the vessel ended up. Measured over 3 seeds x 14 sim-days: **84% of groundings occur >15 wu from the vessel's own route, against 1% on it.** See the design note below. | Medium — with depth-aware routing closed (`route_refused` = 0) and the emergency lifecycle fixed, refloat flap is now the sole remaining driver |
| 14 | **COG maths and `Vessel.move()` still compute the same velocity separately.** `cog_direction` (heading + current + wind drift, in knots) and `move()` (the same terms as distances) are two implementations. `tools/verify/verify_cog_math.py` now runs one real `move()` step and fails if the two disagree, so drift between them is caught, but merging them would change `move()`'s floating-point order and was not done here. | Low |

## Resolved in v0.6.2: tests that checked copies (branch `fix/tests-use-real-code`)

Three checks used to test hand-copied code instead of the game's own:
`tools/verify/verify_cog_math.py` held a copy of `_cog_direction` from
`render/chart.py` (so it could run without Pygame), and `tests/test_collision.py`
and `tests/test_traffic.py` each re-implemented the AI steering step and the
grounding rule from `main.py`. Nothing kept the copies in step with the
originals.

Those rules now live once, in `engine/navigation.py` (pure Python):
`cog_direction`, `steer_ai_vessel` and `below_safe_depth`. `main.py` calls
`steer_ai_vessel` and `below_safe_depth` in `update_simulation`; the verify
script and both tests import the same functions. The game's behaviour is
unchanged: a seeded 6,000-frame run produces identical vessel state and
identical frames before and after. One difference for the tests: their old
copy of the steering step lacked the game's approach slowdown, so they now
exercise slightly different (the game's real) behaviour, and still pass.

## Resolved in v0.6.2: open items A (branch `fix/open-items-a`)

**COG vector (was #13).** The chart now draws the course-over-ground vector
for the player and the followed vessel: a teal-green line with an arrowhead
from the hull along the track over ground, from
`engine/navigation.cog_direction`, only when it differs from heading by more
than `COG_MIN_DRIFT_DEG`. Its length is `SHIP_VECTOR_MINUTES` of travel,
clamped to 4 to 8 hull sizes so it clears the vessel's name label.

**Zone rules (`engine/rules.py`).** The speed caps and fines the game enforces
used to sit inline in `Game.update_simulation`, while `engine/rules.py` held a
`RulesEngine` that nothing instantiated. They now live in `RulesEngine`
(`speed_cap_kn`, `violated_zone`, `fine_amount`, `step_player`); `main.py`
keeps only the side effects. A seeded harness recorded every fine (sim time,
amount, zone), every warning and a digest of every AI speed cap at each
difficulty, with and without a hazmat contract, and in the tutorial: all
identical before and after. `tests/test_rules.py` covers the rules headlessly.

**Rescue completion (was #12).** A rescuer reaching a waypoint now refloats its
casualty only within `RESCUE_COMPLETE_RANGE_WU` (26 wu, 3.9 nm: the standoff
limit plus the arrival tolerance). Measured with a wrapper around
`_sar_refloat`, 3 seeds x 4 sim-days: before, 145 of 543 rescuer completions
(27%) happened more than 3.9 nm from the casualty, the farthest 58.6 nm away;
after, none of 455.

The fix has a large side effect on the fleet. `tools/diag_groundings.py`
(3 seeds x 14 sim-days) before and after:

| Metric | Before | After |
|---|---|---|
| Arrivals and dockings | 686 | 358 |
| Distress events | 707 | 460 |
| Distress events per arrival | 1.03 | 1.28 |
| Episodes never assigned a rescuer | 81 (11%) | 80 (17%) |
| Still stranded at run end | 38 | 43 |
| Median episode length | 2.1 h | 1.5 h |

A probe of 2 seeds x 4 sim-days found no dispatch loop: 61 rescuers arrived
out of range mid-route and carried on (each a false rescue before), only 14
reached their last waypoint still out of range and were released and
re-dispatched, and casualties dispatched three or more times rose from 13 to
17. Rescuer-hours on SAR duty rose 27% (829 to 1,052): rescuers now sail
their whole route, and that time comes out of port runs. The earlier arrival
and rescue figures were inflated by the bug, so the before column is not a
clean baseline, but arrivals are the diagnostic's health counter and halving them
is a real change in how the sea looks. Open question for review.

## Resolved in v0.6.2: scale bar and range rings (was #15, branch `fix/scale-bar`)

Both passed nautical miles to `Camera.distance_to_screen`, which takes world
units (1 wu = `NM_PER_WORLD_UNIT` = 0.15 nm), so they drew 6.7 times too
short: the "50 nm" bar was 7.5 nm and an "8 nm" ring was 1.2 nm. Chart
annotations now convert through `Camera.nm_to_screen`, and
`render/camera.choose_scale_nm` picks a round distance from
`SCALE_BAR_CANDIDATES_NM` or `SHIP_RANGE_RING_CANDIDATES_NM`. The scale bar is
no longer clamped, since a clamped bar no longer matches its label. The range
rings now step with zoom (16 nm zoomed out, 2 nm zoomed in) to keep their
designed on-screen size; a fixed true 8 nm would have put the outer ring 640 px
out at full zoom. `tests/test_scale.py` converts known world distances, runs
the chart's real drawing code at seven zooms, and fails on the old behaviour.
`tools/verify_chunk4.py` used a copy of the buggy logic and now calls the same
functions.

---

## Design note — the displacement-return problem (open)

Four separate attempts to fix this each measured *worse* than the shipped
baseline current at the time, which is why none of them landed. They are
recorded here because the failures were informative and the patches still
apply.

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

   **Attacked three times, rejected three times** — `return_leg` (route the
   return via `find_safe_path`), `rejoin` v1 (nearest leg-end, non-idempotent),
   and `rejoin_v2` (nearest leg-end, idempotent by construction). All three
   measured worse than their baseline, and v2 failed *with every pre-gate
   green*: proven idempotent over 17,974 displaced start-states x 8 calls,
   proven to actually fire (84.7% of shallow positions), 4/4 unit cases,
   16/16 pytest, 16/16 bot. A correct implementation of the idea still cost
   arrivals 791 -> 538 and drove 13.57 of 16 vessels aground by day 13.

   **The hypothesis the results support: "nearest" is the wrong question.**
   Re-indexing has no notion of *forward progress*. Any nearest-point
   correction — leg-end, entry node, projection, however good the search — can
   silently rewind a vessel onto a corridor it already sailed, where it
   re-sails, re-passes, and can re-ground on the same shoal. The route data
   cannot rule this out, because it does not record which waypoints a vessel
   has already completed: `route_index` is a *cursor*, not a progress log, and
   a displaced vessel's cursor is exactly the thing that is stale. So
   "nearest" and "next" are indistinguishable from the route data alone, and
   no better nearest-point search can distinguish them. v2's anti-rewind guard
   (leave a clear aim alone, re-index only a depth-blocked one) is the best
   available proxy and it is not sufficient — a *blocked* aim is precisely the
   case where the vessel must re-index, and precisely the case where the data
   to re-index *correctly* is missing.

   **Any future attempt needs progress state on the route, not a better
   nearest-point search** — e.g. per-vessel completed-waypoint / lap tracking,
   or explicit directional entry nodes — so that a rejoin can pick the nearest
   waypoint *ahead of* the vessel's actual progress. Adding that state is the
   prerequisite; until it exists, this lane is closed.

Worth deciding before more code. "Should a displaced vessel rejoin at its
nearest route *entry point*?" is now **answered: no** — `rejoin_v2` measured
it and it fails for the reason above. The open questions are the ones that add
progress state rather than search quality: should vessels track completed
waypoints (or laps) so "ahead" is computable? Should routes carry explicit
directional entry/exit nodes? Should rescuers return under schedule control
rather than command state?

Rejected patches (each applies cleanly on `b5d7a64`, each fully measured):

| patch | what it does | measured result |
|-------|--------------|-----------------|
| `crab.patch` | leeway/crab-angle compensation in `Vessel.crabbed_heading` — steers course-over-ground, not bearing | **Correct and unit-proven**: holds pinch-leg clearance flat at 4.66 wu across 0–25 kn wind (was bleeding 0.22 wu/kn and grounding at 15 kn). But only ~1% of groundings are on-route, so it does not move the total: uniq/arr 0.125 -> 0.857 |
| `refloat_v2.patch` | on refloat, move to a low-water-sized seaward standoff instead of refloating in place | Kills the 157x same-spot loop and transforms rescue health (never-rescued 10% -> 3%), but re-exposes freed vessels: uniq/arr 0.125 -> 0.742 |
| `return_leg.patch` | route the return leg via `find_safe_path` + `_pending_player_paths` | Off-route share unchanged (84% -> 83%); arrivals 503 -> 170. This is mechanism 1 above |
| `rejoin_v2.patch` | `Vessel.rejoin_route()` re-indexes a displaced vessel onto the nearest *leg* of its own route (idempotent by construction, anti-rewind guard), wired at all four hand-back sites | **All four gates failed** on `c6338b7` vs `7655ac5`: arrivals 791 -> 538, flap 876 -> 3194, zero-pool 15.2% -> 33.5%, emergency median 10 -> 13; 13.57/16 aground and pool 0.23 by day 13. The never-assigned 9% -> 2% is denominator inflation (74 absolute over 3266 episodes), not a pass. This is mechanism 2 above |

The patches live in `patches/` (the first three preserved in commit
`ec8ceea`), with a README summarising each rejection. The first three apply
cleanly on `b5d7a64`; `rejoin_v2.patch` is cut against `c6338b7`.

Measurement standard for any future attempt: `python tools/diag_groundings.py
--days 14 --seeds 3`, and **normalise by arrivals, not raw event counts** — a
vessel stuck aground stops generating both, so a change that strands traffic
looks like a fix if you only count groundings.


### Re-measurement — 2026-08-24: `refloat_v2.patch` on `7655ac5`

Re-run because the tree gained depth-aware SAR routing (two-hop, eastern hubs,
departure exemption), the rescuer-pointer lease, and the emergency lifecycle
fixes since the patch was rejected on `b5d7a64` — so its failure mode was worth
retesting. `git apply` **failed** on context drift (`rescuer.command_reason = ""`
now sits below the insertion point); `git apply --3way` applied it cleanly with
no conflict and no hand-porting. Both `_sar_refloat` call sites are covered; the
two test call sites pass no `world` and exercise the unchanged path. Gates:
`py_compile` OK, `pytest` 16/16, `test_bot.py` 16/16.

| metric | `7655ac5` | + `refloat_v2` |
|--------|-----------|----------------|
| arrivals | 791 | **830** |
| samples with a ZERO eligible pool | 15.2% | **0.6%** |
| never assigned a rescuer | 9% | **2%** |
| ... of which `pool_empty` | 23% | **2%** |
| eligible pool on day 13 | 1.32 | **3.78** |
| simultaneous emergencies (median) | 10 | **5** |
| engine-failure casualties NEVER rescued | 1 | **0** |
| refloat -> re-ground flap | 876 | **1622** |
| ... share inside one sim-minute | 82% | **0%** (7 events) |
| ... median gap | — | **6.08 sim-min** |

**The original rejection reason no longer holds on this tree.** `refloat_v2` was
rejected for stranding traffic and re-exposing freed vessels; here arrivals
*rise* 791 -> 830 and every rescue-health metric improves sharply — the pool
stops collapsing, `pool_empty` all but disappears, and concurrent emergencies
halve. Whatever it did to `b5d7a64`, it does not do to `7655ac5`.

**What remains is not its bug.** The seaward standoff kills the instant bounce
(sub-minute flap 82% -> 0%, seven events in three seeds) but total post-refloat
re-groundings nearly double, at a 6.08-minute median gap: the vessel is placed in
safe water and then steers straight back into the same shallow patch, because the
re-aim is still `destination = route[route_index]`. That is mechanism 2 of #11 —
the return target is a single scheduled waypoint rather than the nearest sensible
entry point — which this patch never claimed to address.

`refloat_v2` is therefore **blocked on the nearest-entry-point return question,
not rejected on its own merits.** Answer that question and this patch is a
candidate again. (One row is still missing: the matching `7655ac5` uniq/arr was
never measured, so the patched 0.781 cannot be read against the historical
`b5d7a64` figure of 0.742.)

**Update 2026-08-24 — `refloat_v2` remains blocked, and the block got harder.**
The plan was to fix its retimed flap (1622 re-groundings at a 6.08-minute
median gap) with the nearest-entry-point rejoin, since the residue is entirely
`destination = route[route_index]` re-aiming. That rejoin has now been built,
proven idempotent, and **rejected** — see `rejoin_v2` in the design note above,
which failed all four gates on its own. So the fix `refloat_v2` was waiting on
does not exist and is not coming from this direction: the nearest-entry-point
lane is closed until routes carry progress state. `refloat_v2` stays parked.

---

## Baseline measurement — 2026-08-24 (HEAD `6986462`)

`python tools/diag_groundings.py --days 14 --seeds 3` (3 seeds x 14 sim-days),
the standard normalise-by-arrivals run:

| metric | value |
|--------|-------|
| arrivals (the normaliser) | 791 |
| simultaneous emergencies | median **10** / 15 (legacy `displayed` median 13) |
| samples with a ZERO eligible-rescuer pool | **15.2%** |
| casualties holding a dead rescuer pointer (stale) | **0.00** mean |
| casualties never assigned a rescuer | **9%** — 75% `out_of_range`, 23% `pool_empty`, **0% `route_refused`** |
| engine-failure casualties NEVER rescued | **1** |
| refloat -> re-ground flap | **876** re-groundings, **82%** inside one sim-minute |

Two readings of these numbers. **(a)** `route_refused` = 0: not one dispatch
failed because `find_safe_path` could not produce a depth-legal route, so the
depth-aware routing arc is complete and costs zero rescues — that lane is
closed and needs no further work. **(b)** The 75% `out_of_range` share is *not*
evidence for raising `SAR_DISPATCH_RANGE_NM`: the eligible pool collapses from
10.00 on day 0 to 1.32 by day 13, so by then the one surviving candidate is far
away as a matter of geometry, not of range tuning — widening the range would
dispatch that last vessel across the sea and relabel the failure, masking pool
exhaustion rather than fixing it. The pool is the variable to attack, not the
radius.

## Resolved in v0.6.2: web demo on phones (branch `fix/web-small-screen`)

On a phone (375 to 390 CSS px wide) the web demo opened with the fleet list
covering most of the chart, the status bar's visibility readout running into
"Speed 1x", and the top of the compass rose hidden under the status bar.

In the web build, a viewport narrower than `WEB_NARROW_LAYOUT_W` design
pixels (framebuffer width divided by UI scale, so high-density phones count)
now uses a compact layout. The fleet list starts collapsed as a "Fleet (N)"
button that opens on a tap and closes after a vessel is picked. The status
bar picks the longest wording that fits between the clock and the speed. The
compass and scale bar move down by the extra height the UI scale adds to the
status bar. Desktop is unchanged: seeded desktop frames are byte-identical
before and after, as are web frames at the 1440 px layout.

Selecting a vessel used to open the full information card, which filled
almost the whole phone screen (branch `fix/phone-vessel-card`). In the narrow
layout it is now a short sheet along the bottom: name and status; type,
speed and heading; distance and ETA; fuel (or "Wind-powered"); a distress
line when in distress; and "Tap the map to close". The followed ship stays
visible above it. While the sheet is open the event log is hidden and the
mission notice moves above it. Wide windows keep the full card.
