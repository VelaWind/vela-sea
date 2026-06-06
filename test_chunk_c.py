"""Headless verification for Chunk C — depth, draft, and tidal grounding.

Tests:
  1. Deep-draft cargo (8 m) at Skerry Bank → grounds.
     Shallow-draft fishing (3 m) at same spot → passes safely.
  2. Tidal depth cycle at a coastal approach position:
     show that depth-under-keel changes with tide, and that the cargo vessel
     is safe at high water but aground at mid/low water.

No Pygame required.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from engine.world import World
from engine.environment import Environment
from engine.ship import Vessel
from data.world_data import populate_world
from config import (
    DEPTH_SHOAL_SKERRY, DRAFT_SAFETY_MARGIN_M,
    TIDAL_DEPTH_INFLUENCE, TIDE_RANGE,
)

# ---------------------------------------------------------------------------
# Build world
# ---------------------------------------------------------------------------
w = World()
populate_world(w)

# ---------------------------------------------------------------------------
# Test positions
# ---------------------------------------------------------------------------
SKERRY_CENTER  = (445.0, 335.0)   # centre of Skerry Bank shallow zone
COASTAL_POINT  = (90.0, 307.0)    # ~2 wu from mainland coast → base depth ~8 m
                                   # (coast vertex (90,305) is 2 wu below this point)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_cargo(pos):
    return Vessel(
        name="Cargo Test", vessel_type="cargo",
        position=pos, heading=0.0,
        target_speed=8.0, current_speed=8.0,
        max_speed=12.0, acceleration=0.020, deceleration=0.017,
        turn_rate=1.0, length_m=150.0, beam_m=25.0, draft_m=8.0,
        fuel=80.0, fuel_capacity=100.0, fuel_consumption_rate=3.5,
    )

def make_fishing(pos):
    return Vessel(
        name="Fishing Test", vessel_type="fishing",
        position=pos, heading=0.0,
        target_speed=6.0, current_speed=6.0,
        max_speed=10.0, acceleration=0.10, deceleration=0.06,
        turn_rate=3.0, length_m=40.0, beam_m=8.0, draft_m=3.0,
        fuel=40.0, fuel_capacity=50.0, fuel_consumption_rate=2.8,
    )

def grounds(vessel, depth) -> bool:
    return depth < vessel.draft_m + DRAFT_SAFETY_MARGIN_M

# ===========================================================================
# Test 1 — Draft differential at Skerry Bank
# ===========================================================================
print("=" * 58)
print("TEST 1: Draft differential — Skerry Bank (mid-tide)")
print("=" * 58)

tide_mt = 0.0
depth_skerry = w.water_depth_at(SKERRY_CENTER, tide_level=tide_mt)

cargo   = make_cargo(SKERRY_CENTER)
fishing = make_fishing(SKERRY_CENTER)

cargo_needs   = cargo.draft_m   + DRAFT_SAFETY_MARGIN_M
fishing_needs = fishing.draft_m + DRAFT_SAFETY_MARGIN_M

cargo_aground   = grounds(cargo,   depth_skerry)
fishing_aground = grounds(fishing, depth_skerry)

print(f"  Skerry Bank depth (tide={tide_mt:+.1f} m):  {depth_skerry:.1f} m")
print(f"  Expected charted depth:              {DEPTH_SHOAL_SKERRY:.1f} m")
print()
print(f"  Cargo   draft={cargo.draft_m:.1f} m  needs={cargo_needs:.1f} m  "
      f"aground={cargo_aground}   (want True)")
print(f"  Fishing draft={fishing.draft_m:.1f} m  needs={fishing_needs:.1f} m  "
      f"aground={fishing_aground}  (want False)")

ok1 = (depth_skerry == DEPTH_SHOAL_SKERRY + tide_mt * TIDAL_DEPTH_INFLUENCE
       and cargo_aground and not fishing_aground)
print(f"\n  PASS: {ok1}")

# ===========================================================================
# Test 2 — Tidal depth cycle at coastal approach point
# ===========================================================================
print()
print("=" * 58)
print("TEST 2: Tidal depth cycle at coastal approach point")
print(f"        Position {COASTAL_POINT}  (approx 2 wu from coast)")
print("=" * 58)

# Tide steps: from low water through high water
tide_steps = [-TIDE_RANGE, -TIDE_RANGE/2, 0.0, TIDE_RANGE/2, TIDE_RANGE]
tide_labels = ["Low water  ", "Mid-ebb    ", "Mid-tide   ", "Mid-flood  ", "High water "]

print(f"\n  {'Tide':>12}  {'Depth':>8}  {'Cargo UKC':>10}  {'Fishing UKC':>12}  {'Notes'}")
print(f"  {'-'*12}  {'-'*8}  {'-'*10}  {'-'*12}  {'-'*30}")

cargo_c   = make_cargo(COASTAL_POINT)
fishing_c = make_fishing(COASTAL_POINT)

tide_results = []
for label, tide in zip(tide_labels, tide_steps):
    depth = w.water_depth_at(COASTAL_POINT, tide_level=tide)
    ukc_cargo   = depth - cargo_c.draft_m
    ukc_fishing = depth - fishing_c.draft_m
    ag_cargo    = grounds(cargo_c,   depth)
    ag_fishing  = grounds(fishing_c, depth)
    note = ""
    if ag_cargo and ag_fishing:
        note = "BOTH aground"
    elif ag_cargo:
        note = "Cargo aground, fishing safe"
    else:
        note = "Both safe"
    tide_results.append((depth, ag_cargo, ag_fishing))
    print(f"  {label} {tide:>+5.1f} m  {depth:>7.1f} m  {ukc_cargo:>+9.1f} m  "
          f"{ukc_fishing:>+11.1f} m  {note}")

# The coastal point should show tide DOES change depth and UKC noticeably
depths = [w.water_depth_at(COASTAL_POINT, t) for t in tide_steps]
depth_range = max(depths) - min(depths)
ok2a = abs(depth_range - TIDE_RANGE * 2 * TIDAL_DEPTH_INFLUENCE) < 0.01
print(f"\n  Depth range across full tidal cycle: {depth_range:.2f} m "
      f"(expected {TIDE_RANGE * 2 * TIDAL_DEPTH_INFLUENCE:.2f} m)  PASS: {ok2a}")

# At this point (~8 m base depth), cargo should be aground at low/mid water
# and safe at high water (8m + 3m tide - 8.5m needed = +2.5m UKC at HW).
hw_depth = w.water_depth_at(COASTAL_POINT, tide_level=TIDE_RANGE)
lw_depth = w.water_depth_at(COASTAL_POINT, tide_level=-TIDE_RANGE)
ok2b = not grounds(cargo_c, hw_depth) and grounds(cargo_c, lw_depth)
print(f"  Cargo safe at HW ({hw_depth:.1f} m), aground at LW ({lw_depth:.1f} m):  PASS: {ok2b}")

# ===========================================================================
# Test 3 — Skerry Bank tidal cycle (shoal depth + tide)
# ===========================================================================
print()
print("=" * 58)
print("TEST 3: Skerry Bank tidal cycle")
print(f"        (base shoal depth = {DEPTH_SHOAL_SKERRY} m)")
print("=" * 58)
print(f"\n  {'Tide':>12}  {'Depth':>8}  {'Cargo':>10}  {'Fishing':>8}")
print(f"  {'-'*12}  {'-'*8}  {'-'*10}  {'-'*8}")
for label, tide in zip(tide_labels, tide_steps):
    d = w.water_depth_at(SKERRY_CENTER, tide_level=tide)
    print(f"  {label} {tide:>+5.1f} m  {d:>7.1f} m  "
          f"{'AGROUND' if grounds(cargo, d) else 'safe':>10}  "
          f"{'AGROUND' if grounds(fishing, d) else 'safe':>8}")

# Cargo should ALWAYS be aground at Skerry Bank (max depth 5+3=8 m < 8.5 m needed)
ok3 = all(grounds(cargo, w.water_depth_at(SKERRY_CENTER, t)) for t in tide_steps)
print(f"\n  Cargo always aground on Skerry Bank: PASS: {ok3}")

# ===========================================================================
# Summary
# ===========================================================================
print()
print("=" * 58)
all_ok = ok1 and ok2a and ok2b and ok3
print(f"ALL TESTS PASSED: {all_ok}")
