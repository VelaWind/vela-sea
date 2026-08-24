# Rejected displacement-return patches

Three measured attempts at KNOWN_ISSUES.md #11 (displaced vessels have no
defined way back to their route), each rejected against baseline `b5d7a64`
at the time — but see `refloat_v2` below, which re-measures clean on the
current tree. Each applies cleanly on `b5d7a64`; each measured worse than
that baseline by the standard
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
- `return_leg.patch` — route the return leg via `find_safe_path` +
  `_pending_player_paths`. Rejected: off-route share unchanged
  (84% -> 83%) while arrivals collapsed 503 -> 170 (commanded vessels are
  invisible to their own schedule).
