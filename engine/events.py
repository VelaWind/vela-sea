"""Event-log vocabulary shared by the simulation and the game.

Pure Python, no Pygame.  Engine code reports what happened as an event KIND
(for example EVENT_RESCUE); main.py maps each kind to the colour the event
log draws it in.  That keeps colours, which live in render/, out of engine/.

An "event log" passed to engine functions is any object with
add(sim_time: str, message: str, kind: str), or None for no logging.
"""

EVENT_MAYDAY = "mayday"      # vessel aground, engine failure, man overboard
EVENT_RESCUE = "rescue"      # rescuer dispatched
EVENT_REFLOAT = "refloat"    # vessel refloated or rescued
EVENT_MEDICAL = "medical"    # medical diversion
EVENT_WEATHER = "weather"    # weather change (logged by main.py)


def sim_time_str(environment) -> str:
    """Format environment.time_of_day as HH:MM for event log entries."""
    h = int(environment.time_of_day)
    m = int((environment.time_of_day % 1) * 60)
    return f"{h:02d}:{m:02d}"
