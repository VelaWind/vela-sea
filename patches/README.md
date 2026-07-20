# Rejected displacement-return patches

Three measured-and-rejected attempts at KNOWN_ISSUES.md #11 (displaced
vessels have no defined way back to their route). Each applies cleanly on
baseline `b5d7a64`; each measured worse than that baseline by the standard
`python tools/diag_groundings.py --days 14 --seeds 3`, normalised by
arrivals. Full analysis in the KNOWN_ISSUES design note.

- `crab.patch` — leeway/crab-angle compensation in `Vessel.crabbed_heading`
  (steers course-over-ground, not bearing). Rejected: correct and
  unit-proven, but only ~1% of groundings are on-route, so the total does
  not move — uniq groundings/arrival 0.125 -> 0.857.
- `refloat_v2.patch` — on refloat, move to a low-water-sized seaward
  standoff instead of refloating in place. Rejected: fixes the 157x
  same-spot loop and rescue health (never-rescued 10% -> 3%) but re-exposes
  freed vessels — uniq/arr 0.125 -> 0.742.
- `return_leg.patch` — route the return leg via `find_safe_path` +
  `_pending_player_paths`. Rejected: off-route share unchanged
  (84% -> 83%) while arrivals collapsed 503 -> 170 (commanded vessels are
  invisible to their own schedule).
