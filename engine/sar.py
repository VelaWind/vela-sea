"""Search and rescue: dispatching rescuers and completing rescues.

Pure Python, no Pygame.  Moved out of main.py unchanged in behaviour; main.py
calls these through the names _sar_dispatch and _sar_refloat, so tests and
tools/diag_groundings.py that patch those names keep working.  Logging goes
through an event-log object (see engine/events.py).
"""

from config import (SIM_TIMESTEP, SAR_DISPATCH_RETRY_S,
                    FUEL_EMERGENCY_REFUEL_FRACTION)
from .collision import find_safe_path, find_standoff
from .events import EVENT_RESCUE, EVENT_REFLOAT


def sar_refloat(grounded, event_log=None, sim_time: str = "") -> None:
    """Refloat a grounded/adrift vessel and release its rescuer (if any).

    Calls vessel.refloat() for the grounded vessel's own state, then
    clears the rescuer's player_commanded flag and restores its schedule.

    Fuel-exhaustion case: when the vessel ran dry (fuel == 0), give it an
    emergency partial refuel so it can motor to the nearest port instead of
    immediately going adrift again the moment the rescuer leaves.
    """
    rescuer = grounded.rescue_vessel
    # Emergency refuel for fuel-exhausted vessels so they can reach a port.
    fuel_rescue = (grounded.fuel is not None
                   and grounded.fuel == 0.0
                   and grounded.fuel_capacity is not None)
    if fuel_rescue:
        grounded.fuel = grounded.fuel_capacity * FUEL_EMERGENCY_REFUEL_FRACTION
    grounded.refloat()
    if rescuer is not None and rescuer.player_commanded:
        rescuer.player_commanded = False
        rescuer.command_reason = ""
        if rescuer.route:
            rescuer.destination = rescuer.route[rescuer.route_index]
    if event_log is not None:
        msg = (f"RESCUED — {grounded.name} (emergency fuel)"
               if fuel_rescue else f"REFLOATED — {grounded.name}")
        event_log.add(sim_time, msg, EVENT_REFLOAT)


def sar_dispatch(vessels, range_wu: float, event_log=None, sim_time: str = "",
                  player_paths: dict = None, world=None) -> None:
    """Auto-dispatch the nearest eligible vessel to each unrescued distressed vessel.

    Eligibility: underway, not already player_commanded, not already a rescuer.
    Only one rescuer is dispatched per grounded vessel.

    When world is provided, find_safe_path() is used so the rescuer avoids
    islands en-route.  Multi-hop paths are stored in player_paths (keyed by
    id(vessel)) and advanced in the main update loop on each arrival.
    """
    # Build set of vessel IDs already acting as rescuers so we can skip them.
    # Using id() because Vessel is a dataclass with __eq__ and is not hashable.
    active_rescuer_ids = {id(v.rescue_vessel) for v in vessels if v.rescue_vessel is not None}

    for grounded in vessels:
        if not grounded.distress:
            continue
        # The rescue_vessel pointer is a LEASE, not a lock.  This skip used to be
        # unconditional on "rescue_vessel is not None", and the field is cleared
        # only by refloat(): which needs the assigned rescuer to arrive.  So when
        # a rescuer broke down en route (the random-event sweep below has no
        # player_commanded guard, so a rescuer can take an engine failure or run
        # aground like anyone else) the casualty held a pointer to a vessel that
        # would never come, and was never re-swept.  Observed live: Ardent Pilot
        # aground 70 h 55 m holding "FV North Fisher", itself flagged DISTRESS.
        # Measured 3.70 casualties on average holding a dead pointer, rising to
        # 6.33 by sim-day 13.  Drop the lease and re-sweep instead.
        _r = grounded.rescue_vessel
        if _r is not None:
            if (_r.distress or _r.engine_failure
                    or not _r.player_commanded
                    or _r.status not in ("underway", "avoiding")):
                grounded.rescue_vessel = None
                grounded._sar_retry_timer = 0.0
                # Deliberately NOT touching the ex-rescuer.  Releasing it here
                # with destination = route[route_index] was measured and reverted:
                # it is a new instance of the displacement-return problem
                # (KNOWN_ISSUES #11 mechanism 2: aiming a displaced vessel at the
                # one waypoint it happened to be heading for), and it cost
                # arrivals 498 -> 430 while shifting the whole port-visit
                # distribution (Saltgate 112 -> 41, Thornwick 45 -> 88).  The
                # ex-rescuer clears its own command state through arrive() as it
                # always did; only the casualty's dead lease is our business here.
            else:
                continue
        # Retry cooldown.  A casualty nobody can route to used to be re-swept
        # against every candidate on every sim step, at ~2,500 depth lookups per
        # attempt: 271k router calls in three sim-days, 89% of wall time, which
        # would put the frame budget on the floor.  After a failed sweep, sit the
        # casualty out for SAR_DISPATCH_RETRY_S; the fleet will have moved by then
        # and a route may exist.  Counted down here rather than compared against a
        # clock because environment.time_of_day wraps at 24 h and is not monotonic.
        _cooldown = getattr(grounded, "_sar_retry_timer", 0.0)
        if _cooldown > 0.0:
            grounded._sar_retry_timer = _cooldown - SIM_TIMESTEP
            continue
        candidates = []
        for v in vessels:
            if v is grounded:
                continue
            if v.status not in ("underway", "avoiding"):
                continue
            if id(v) in active_rescuer_ids:
                continue
            if v.player_commanded:
                # An ORPHANED rescuer is available.  Dropping a dead lease (above)
                # leaves the ex-rescuer carrying a live "sar" command it will only
                # shed when it happens to arrive somewhere: 7.52 of 16 vessels by
                # sim-day 13, all of them ineligible, which is why zero-eligible
                # samples rose to 48.5%.  It is serving no casualty by definition
                # (nothing points at it, checked above), so it is free to be
                # re-dispatched.  Its navigation is left completely alone: the
                # alternative, handing it a fresh route waypoint, is the
                # displacement-return pattern that cost arrivals 663 -> 430.
                if not (v.command_reason == "sar"
                        and v.status in ("underway", "avoiding")):
                    continue
            d = v.distance_to(grounded.position)
            if d <= range_wu:
                candidates.append((d, v))
        candidates.sort(key=lambda c: c[0])

        # Try candidates nearest-first and take the first one that can actually
        # get there.  The nearest vessel is not always the right answer: it may
        # be the far side of a shoal, and find_safe_path now returns [] rather
        # than a leg it knows is too shallow.  Walking the list keeps a casualty
        # from going unrescued just because its closest neighbour is blocked.
        best, waypoints = None, None
        for _d, v in candidates:
            if world is None:
                best, waypoints = v, [grounded.position]
                break
            # Aim at a standoff, not the casualty itself: the casualty is aground,
            # so its exact position is by definition too shallow to float it: and
            # a rescuer steered there grounds alongside it.  The standoff must
            # clear the RESCUER's draft, which may be deeper than the casualty's.
            target = find_standoff(grounded.position, v.draft_m, world)
            path = find_safe_path(v.position, target, world, v.draft_m)
            if path:
                best, waypoints = v, path
                break

        if best is not None:
            grounded._sar_retry_timer = 0.0
            best.destination = waypoints[0]
            best.player_commanded = True
            best.command_reason = "sar"
            grounded.rescue_vessel = best
            active_rescuer_ids.add(id(best))
            if player_paths is not None and len(waypoints) > 1:
                player_paths[id(best)] = waypoints[1:]
            if event_log is not None:
                event_log.add(sim_time,
                              f"RESCUE — {best.name} → {grounded.name}",
                              EVENT_RESCUE)
        else:
            # No reachable rescuer this sweep: stamp the cooldown so the next
            # attempt waits for the fleet to move instead of re-running the same
            # doomed search every tick.  Deliberately not logged: even at one
            # message per cooldown this would clutter the event log with a
            # situation the player cannot act on.
            grounded._sar_retry_timer = SAR_DISPATCH_RETRY_S
