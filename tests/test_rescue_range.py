"""Rescue completion distance (engine/navigation.within_rescue_range).

A SAR rescue may complete only when the rescuer reaches a waypoint within
RESCUE_COMPLETE_RANGE_WU of the casualty, not on reaching the first hop of a
multi-hop route (KNOWN_ISSUES #12).
"""

import sys
sys.path.insert(0, ".")

from engine.ship import Vessel
from engine.navigation import within_rescue_range
from config import RESCUE_COMPLETE_RANGE_WU, STANDOFF_MAX_WU, PORT_DETECT_RADIUS


def _vessel(name, x, y):
    return Vessel(
        name=name, vessel_type="cargo", position=(float(x), float(y)),
        heading=0.0, target_speed=8.0, current_speed=8.0, max_speed=12.0,
        acceleration=0.5, deceleration=0.3, turn_rate=3.0,
        length_m=80.0, beam_m=15.0, draft_m=4.0,
        fuel=100.0, fuel_capacity=100.0, fuel_consumption_rate=2.0,
    )


def test_range_is_standoff_plus_arrival_tolerance():
    assert RESCUE_COMPLETE_RANGE_WU == STANDOFF_MAX_WU + PORT_DETECT_RADIUS


def test_inside_and_at_the_range_completes():
    casualty = _vessel("Casualty", 500, 300)
    assert within_rescue_range(_vessel("Near", 510, 300), casualty)
    assert within_rescue_range(_vessel("Edge", 500 + RESCUE_COMPLETE_RANGE_WU, 300), casualty)


def test_a_far_waypoint_does_not_complete():
    casualty = _vessel("Casualty", 500, 300)
    far = _vessel("FirstHop", 500 + RESCUE_COMPLETE_RANGE_WU + 0.5, 300)
    assert not within_rescue_range(far, casualty)
