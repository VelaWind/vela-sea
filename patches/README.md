# Rejected displacement-return patches

Four measured attempts at KNOWN_ISSUES.md #11 (displaced vessels have no
defined way back to their route), each rejected against the baseline current
at the time — but see `refloat_v2` below, which re-measures clean on the
current tree. The first three apply cleanly on `b5d7a64`; `rejoin_v2` is cut
against `c6338b7`. Each measured worse than its baseline by the standard
`python tools/diag_groundings.py --days 14 --seeds 3`, normalised by
arrivals. Full analysis in the KNOWN_ISSUES design note.

- `crab.patch` — leeway/crab-angle compensation in `Vessel.crabbed_heading`
  (steers course-over-ground, not bearing). Rejected: correct and
  unit-proven, but only ~1% of groundings are on-route, so the total does
  not move — uniq groundings/arrival 0.125 -> 0.857.
- `refloat_v2.patch` — on refloat, move to a low-water-sized seaward
  standoff instead of refloating in place. Rejected on `b5d7a64`: fixed the
  157x same-spot loop and rescue health (never-rescued 10% -> 3%) but
  re-exposed freed vessels — uniq/arr 0.125 -> 0.742.
  **Re-measured 2026-08-24 on `7655ac5` (--3way; context drift): that
  rejection no longer holds.** Arrivals rise 791 -> 830, zero-pool
  15.2% -> 0.6%, never-assigned 9% -> 2%, emergency median 10 -> 5. It now
  only *retimes* the flap (876 -> 1622 re-groundings, sub-minute 82% -> 0%,
  median gap 6.08 sim-min) because the re-aim is still `route[route_index]`.
  **Blocked on the nearest-entry-point return question (mechanism 2), not
  rejected on its merits.** See the KNOWN_ISSUES re-measurement note.
- `rejoin_v2.patch` — `Vessel.rejoin_route()`: re-index a displaced vessel
  onto the nearest LEG of its own route (perpendicular projection to the
  polyline, not the nearest waypoint), instead of resuming on the stale
  `route[route_index]` it happened to hold when it was pulled off station.
  **Idempotent by construction** — the answer depends only on position,
  route and depth, never on the current index — with an anti-rewind guard
  that leaves a clear current aim alone and re-indexes only a depth-blocked
  one, walking forward up to `ROUTE_REJOIN_MAX_LOOKAHEAD` for a clear
  run-in. Extracts `find_safe_path`'s nested `_leg_clear` to a module-level
  `engine.collision.leg_is_clear` (behaviour-neutral) so the depth test is
  shared. Wired at all four hand-back sites: `_sar_refloat`, the party
  tender, MOB-search completion, and trawl-pause completion — each already
  firing on its transition edge, not per tick.
  **Rejected 2026-08-24 on `c6338b7`, all four gates failed** (3 seeds x
  14 sim-days, vs `7655ac5`): arrivals 791 -> **538**, refloat -> re-ground
  flap 876 -> **3194** (96% sub-minute, median gap 0.02 sim-min), zero
  eligible pool 15.2% -> **33.5%**, simultaneous emergencies median
  10 -> **13**. The fleet ratchets into permanent grounding: by day 13,
  **13.57 of 16** vessels aground and an eligible pool of **0.23**
  (baseline 1.32).
  The never-assigned row reads 9% -> **2%**, and that is *not* a pass — it
  is denominator inflation. Absolute never-assigned is **74** against
  **3266** episodes, and 3194 of those episodes are the flap re-groundings
  above. Normalise by arrivals, never by episode count.
  Pre-gates were all green before the run, so this is not a defective
  implementation of the idea: an idempotency probe over 17,974 displaced
  start-states x 8 calls found 0 non-constant indices on both the
  world-aware and no-world paths, unit cases 4/4, `pytest` 16/16,
  `test_bot` 16/16. A separate probe confirmed rejoin genuinely fires
  (84.7% of shallow positions), disproving the theory that the departure-end
  depth exemption made the guard blind. The idea itself is what failed.
- `return_leg.patch` — route the return leg via `find_safe_path` +
  `_pending_player_paths`. Rejected: off-route share unchanged
  (84% -> 83%) while arrivals collapsed 503 -> 170 (commanded vessels are
  invisible to their own schedule).
