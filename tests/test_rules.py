"""Headless tests for engine/rules.py, the one place the zone rules live.

Uses the real Vela Sea map, so the zones are the ones the game enforces.
"""

import sys
sys.path.insert(0, ".")

from engine.world import World
from engine.rules import RulesEngine, ZoneFineState
from data.world_data import populate_world
from config import (ZONE_FINE_NO_ENTRY, ZONE_FINE_SPEED, ZONE_FINE_INTERVAL_S,
                    ZONE_FINE_GRACE_S, HAZMAT_FINE_MULT)

DT = 1.0   # sim-seconds per step in the timing tests


def _rules():
    world = World()
    populate_world(world)
    return world, RulesEngine(world)


def _zone(world, kind=None, limited=False):
    for z in world.zones:
        if kind is not None and z.kind != kind:
            continue
        if limited and z.speed_limit is None:
            continue
        # A centre inside only this zone keeps the expectations unambiguous.
        if len(world.get_zones_containing(z.center)) == 1:
            return z
    raise AssertionError("no suitable zone in the map")


def test_speed_cap_is_zone_limit_and_none_in_open_water():
    world, rules = _rules()
    z = _zone(world, limited=True)
    assert rules.speed_cap_kn(z.center) == z.speed_limit
    assert rules.speed_cap_kn((-500.0, -500.0)) is None


def test_violation_needs_speed_over_the_limit():
    world, rules = _rules()
    z = _zone(world, limited=True)
    assert rules.violated_zone(z.center, z.speed_limit) is None       # at the limit: fine
    assert rules.violated_zone(z.center, z.speed_limit + 0.1) is z    # over it: violation


def test_no_entry_is_a_violation_at_any_speed():
    world, rules = _rules()
    z = _zone(world, kind="no_entry")
    assert rules.violated_zone(z.center, 0.0) is z


def test_fine_amounts():
    world, rules = _rules()
    ne = _zone(world, kind="no_entry")
    sl = _zone(world, limited=True)
    assert rules.fine_amount(ne, hazmat=False, difficulty_mult=1.0) == ZONE_FINE_NO_ENTRY
    assert rules.fine_amount(sl, hazmat=False, difficulty_mult=1.0) == ZONE_FINE_SPEED
    assert rules.fine_amount(sl, hazmat=True, difficulty_mult=1.5) == (
        ZONE_FINE_SPEED * HAZMAT_FINE_MULT * 1.5)


def test_grace_then_cooldown_then_reset():
    world, rules = _rules()
    z = _zone(world, kind="no_entry")
    state = ZoneFineState()
    fines, warns, t = [], 0, 0.0
    total = ZONE_FINE_GRACE_S + 2 * ZONE_FINE_INTERVAL_S + 1
    while t < total:
        step = rules.step_player(state, z.center, 0.0, DT, fines_allowed=True)
        t += DT
        warns += step.warn
        if step.fine_due:
            fines.append(t)
    assert warns == 1                                  # warned once, on entry
    assert fines[0] == ZONE_FINE_GRACE_S               # first fine after the grace
    assert fines[1] - fines[0] == ZONE_FINE_INTERVAL_S # then one per interval
    # Leaving resets the timer and the warning.
    step = rules.step_player(state, (-500.0, -500.0), 0.0, DT, fines_allowed=True)
    assert step.zone is None and state.timer == 0.0 and not state.warning_sent


def test_tutorial_warns_but_never_fines():
    world, rules = _rules()
    z = _zone(world, kind="no_entry")
    state = ZoneFineState()
    steps = [rules.step_player(state, z.center, 0.0, DT, fines_allowed=False)
             for _ in range(int(ZONE_FINE_GRACE_S + ZONE_FINE_INTERVAL_S * 3))]
    assert sum(s.warn for s in steps) == 1
    assert not any(s.fine_due for s in steps)
