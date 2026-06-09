"""Automated gameplay bot — headless, end-to-end scenario runner.

Drives a real ``Game`` instance with no window/audio (SDL dummy drivers) and
plays through fourteen gameplay scenarios that exercise the player vessel,
the career/contract system, the consequence systems (zone fines, grounding,
hull failure, fuel-exhaustion SAR), and the v0.4.0 features (title screen,
save/load, docking menu, autopilot, contract variety, reputation tiers,
achievements, weather gameplay effects).  Each scenario produces a structured
pass/fail result with enough detail to fix a failure without further digging.

Run directly for the human-readable report::

    python tests/test_bot.py

Run under pytest (all fourteen scenarios collapse into one test)::

    pytest tests/test_bot.py


HOW THE SIM CLOCK WORKS (so the numbers below make sense)
---------------------------------------------------------
``Game.update_simulation(dt)`` scales real ``dt`` by ``TIME_COMPRESSION`` (80)
and the 1x speed multiplier, then steps the physics in fixed ``SIM_TIMESTEP``
(1.0 sim-second) chunks.  Calling it with dt=0.016 advances 0.016*80 = 1.28
simulated seconds per call.  So ``run_sim(game, S)`` issues S/0.016 calls and
advances the world by S*80 simulated seconds.

The player vessel's heading is only changed by held A/D keys in the main loop
(there are none in headless mode), so the bot must steer it itself each step
via ``turn_toward`` — exactly the manoeuvre a human player performs.
"""

import os

# ---------------------------------------------------------------------------
# Headless environment — MUST be set before pygame is imported (main pulls it in).
# ---------------------------------------------------------------------------
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import math
import random
import sys
from dataclasses import dataclass, field
from typing import Optional, Tuple

# Repo root on the import path so `python tests/test_bot.py` and `pytest` both work.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Make the pound sign printable on a cp1252 Windows console without crashing.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import (
    SIM_TIMESTEP, TIME_COMPRESSION, NM_PER_WORLD_UNIT,
    PLAYER_STARTING_MONEY, ZONE_FINE_NO_ENTRY, GROUNDING_HULL_DAMAGE,
    DRAFT_SAFETY_MARGIN_M, SAR_DISPATCH_RANGE_NM,
)
import main as _main_module
from main import Game

# ---------------------------------------------------------------------------
# Save-file isolation: the bot docks the player and triggers game-overs, both
# of which write/delete the career save.  Redirect those calls to a temp file
# so running the test suite never clobbers the player's real save.json.
# ---------------------------------------------------------------------------
import tempfile
from engine import career as _career_module

_BOT_SAVE_PATH = os.path.join(tempfile.gettempdir(), "meridian_bot_save.json")
_main_module.save_career = (
    lambda career, filepath=None, hull_integrity=1.0:
        _career_module.save_career(career, _BOT_SAVE_PATH, hull_integrity))
_main_module.delete_save = (
    lambda filepath=None: _career_module.delete_save(_BOT_SAVE_PATH))

REAL_DT = 0.016           # seconds of "real" frame time fed to update_simulation
SEED = 20260609           # fixed seed → deterministic spawns, contracts, events
POUND = "£"          # £


# ===========================================================================
# Step 1 — Headless game runner
# ===========================================================================

def make_game(seed: int = SEED) -> Game:
    """Return a fresh ``Game`` with a clean, deterministic state.

    Seeding *before* constructing the game makes vessel spawn positions and
    contract generation reproducible.  Weather drift is frozen so currents,
    wind and visibility stay constant (only the tide advances) — this keeps
    every scenario deterministic regardless of run order.
    """
    random.seed(seed)
    game = Game()
    game.environment.weather_drift_enabled = False
    # Belt-and-braces: the sim must not be paused and must run at 1x.
    game.is_paused = False
    game.environment.time_speed_multiplier = 1.0
    return game


def run_sim(game, real_seconds, on_step=None, until=None):
    """Advance the sim for the equivalent of ``real_seconds`` of real time.

    Calls ``game.update_simulation(REAL_DT)`` in a loop, advancing the world by
    REAL_DT*TIME_COMPRESSION simulated seconds per call.

    on_step(game) — optional callback invoked *before* each call, used to steer
                    the player vessel (set heading/throttle) the way a human would.
    until(game)   — optional predicate; the loop stops early when it returns True.

    Returns (calls_made, sim_seconds_advanced).
    """
    calls = max(1, int(round(real_seconds / REAL_DT)))
    sim_before = game.mission_manager.sim_elapsed_s
    made = 0
    for _ in range(calls):
        if on_step is not None:
            on_step(game)
        game.update_simulation(REAL_DT)
        made += 1
        if until is not None and until(game):
            break
    sim_advanced = game.mission_manager.sim_elapsed_s - sim_before
    return made, sim_advanced


# ---------------------------------------------------------------------------
# Result plumbing
# ---------------------------------------------------------------------------

@dataclass
class Result:
    index: int
    name: str
    passed: bool
    summary: str = ""                 # one-liner shown on the PASS row
    expected: str = ""                # shown on failure
    got: str = ""                     # shown on failure
    cause: str = ""                   # shown on failure

    @property
    def failure_detail(self) -> str:
        return (
            f"Scenario {self.index}  {self.name:<22} FAIL\n"
            f"  Expected: {self.expected}\n"
            f"  Got:      {self.got}\n"
            f"  Likely cause: {self.cause}"
        )


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _nm(wu: float) -> float:
    return wu * NM_PER_WORLD_UNIT


def _steer(game, dest, speed):
    """Steer the player vessel toward ``dest`` at ``speed`` knots (one step)."""
    pv = game.player_vessel
    pv.target_speed = float(speed)
    pv.turn_toward(pv.bearing_to(dest), SIM_TIMESTEP)


def find_deep_no_entry_zone(game):
    """Return a no-entry zone whose centre is deep, open water clear of ports.

    The player (draft 5 m) must be able to sit at the centre without grounding,
    so the fine logic — not a grounding — is what fires.
    """
    pv = game.player_vessel
    need = pv.draft_m + DRAFT_SAFETY_MARGIN_M
    for z in game.world.zones:
        if z.kind != "no_entry":
            continue
        if game.world.point_in_island(z.center):
            continue
        if game.world.water_depth_at(z.center, 0.0) < need:
            continue
        if pv._port_at(z.center, game.world) is not None:
            continue
        return z
    return None


def find_island_interior_point(game):
    """Return (island_name, (x, y)) for a point strictly inside an island.

    Prefers a true island over the mainland.  Grid-samples each polygon's
    bounding box and returns the first point that ``point_in_island`` confirms
    is land and that is clear of any port-approach radius.
    """
    pv = game.player_vessel
    islands = sorted(game.world.islands, key=lambda i: i.is_mainland)  # islands first
    for island in islands:
        xs = [p[0] for p in island.polygon]
        ys = [p[1] for p in island.polygon]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        steps = 12
        for ix in range(1, steps):
            for iy in range(1, steps):
                px = x0 + (x1 - x0) * ix / steps
                py = y0 + (y1 - y0) * iy / steps
                pt = (px, py)
                if (game.world.point_in_island(pt)
                        and pv._port_at(pt, game.world) is None):
                    return island.name, pt
    return None, None


# Deep, zone-clean approach stages for ports a draft-5 vessel can safely reach.
# Each value is an open-water point ~30-70 wu seaward of the port with a path
# to the berth that the cargo routes already prove clear (no island, depth OK,
# no speed-limit zone that a 10 kn approach would violate).
_APPROACH_STAGES = {
    "Port Ardent":          (640.0, 500.0),   # _WP_ARDENT_APP — gap E of Carrow
    "Cape Durran":          (1150.0, 500.0),  # W of the berth, inside the 10 kn TSS
    "Brattlin Light Quay":  (640.0, 590.0),   # _WP_S_BRAT — south corridor
}


def setup_delivery_contract(game):
    """Populate the job board and return a rep-0 delivery contract we can deliver.

    The to-port must be one of the deep, zone-clean ports in ``_APPROACH_STAGES``
    (Port Ardent preferred) so the player can stage just offshore and motor in
    without grounding or racking up speed-limit fines.  Refreshes the board
    (each refresh = 4 fresh random contracts) until a match appears.
    """
    preferred = list(_APPROACH_STAGES.keys())
    for _ in range(500):
        game.job_board.refresh_jobs(game.world)
        for port_name in preferred:           # bias toward the cheapest approach
            for c in game.job_board.available:
                if (c.job_type == "delivery"
                        and c.reputation_required <= game.career.reputation
                        and c.to_port == port_name):
                    return c
    return None


# ===========================================================================
# Step 2 — Scenario 1: Player vessel spawns and moves
# ===========================================================================

def scenario_1():
    game = make_game()
    pv = game.player_vessel
    if pv is None:
        return Result(1, "Basic movement", False,
                      expected="player vessel present in world",
                      got="game.player_vessel is None",
                      cause="Game._create_initial_vessels did not register the player")

    ardent = game.world.find_port("Port Ardent")
    start = pv.position
    pv.heading = pv.bearing_to(ardent.position)   # point at the destination to begin

    run_sim(game, 30.0, on_step=lambda g: _steer(g, ardent.position, 10.0))

    end = pv.position
    dist_wu = math.hypot(end[0] - start[0], end[1] - start[1])
    dist_nm = _nm(dist_wu)

    moved = dist_wu > 1e-6
    speed_ok = pv.current_speed > 0.0
    status_ok = pv.status == "underway"
    passed = moved and speed_ok and status_ok

    summary = (f"moved {dist_nm:.2f} nm in 30s "
               f"({start[0]:.0f},{start[1]:.0f})->({end[0]:.0f},{end[1]:.0f}), "
               f"speed {pv.current_speed:.1f} kn")
    return Result(
        1, "Basic movement", passed, summary=summary,
        expected="moved from start, current_speed>0, status=underway",
        got=(f"dist={dist_nm:.2f} nm, current_speed={pv.current_speed:.2f}, "
             f"status={pv.status}"),
        cause=("player not steering or not accelerating — check turn_toward/"
               "update_speed gating on the player vessel"),
    )


# ===========================================================================
# Step 3 — Scenario 2: Contract accept and delivery
# ===========================================================================

def scenario_2():
    game = make_game()
    pv = game.player_vessel
    money_before = game.career.money

    contract = setup_delivery_contract(game)
    if contract is None:
        return Result(2, "Delivery contract", False,
                      expected="a rep-0 delivery contract on the job board",
                      got="none generated to a safely reachable port",
                      cause="JobBoard.refresh_jobs / _CONTRACT_TEMPLATES delivery weighting")

    accepted = game.job_board.accept_job(
        contract.contract_id, game.career, game.mission_manager.sim_elapsed_s)
    if not accepted:
        return Result(2, "Delivery contract", False,
                      expected="accept_job() returns True for the rep-0 delivery",
                      got=f"accept_job returned False (active={game.job_board.active})",
                      cause="JobBoard.accept_job reputation/active-slot guard")

    to_port = game.world.find_port(contract.to_port)
    stage = _APPROACH_STAGES[contract.to_port]

    # Stage the player just offshore, already making way, pointed at the berth.
    pv.position = stage
    pv.heading = pv.bearing_to(to_port.position)
    pv.current_speed = 10.0
    pv.target_speed = 10.0
    pv.player_commanded = False     # must be False or arrive() skips docking
    pv.destination = to_port.position
    pv.status = "underway"

    start = pv.position
    _, sim_s = run_sim(
        game, 120.0,
        on_step=lambda g: _steer(g, to_port.position, 10.0),
        until=lambda g: contract.status == "completed",
    )

    dist_remaining = _nm(pv.distance_to(to_port.position))
    sim_hours = sim_s / 3600.0
    money_after = game.career.money

    status_ok = contract.status == "completed"
    money_ok = money_after > PLAYER_STARTING_MONEY
    deliveries_ok = game.career.total_deliveries == 1
    passed = status_ok and money_ok and deliveries_ok

    summary = (f"{contract.contract_id} ->{contract.to_port}: earned "
               f"{POUND}{money_after - money_before:.0f}, "
               f"{game.career.total_deliveries} delivery, took {sim_hours:.2f} sim-h")
    return Result(
        2, "Delivery contract", passed, summary=summary,
        expected=("contract status=completed, money>5000, total_deliveries=1"),
        got=(f"status={contract.status}, money={money_after:.0f}, "
             f"deliveries={game.career.total_deliveries}, "
             f"distance_remaining={dist_remaining:.2f} nm, ran {sim_hours:.2f} sim-h"),
        cause=("vessel not navigating to to_port, or arrive()/complete_job not "
               "firing on dock (player_commanded must be False to dock)"),
    )


# ===========================================================================
# Step 4 — Scenario 3: Zone fine triggers
# ===========================================================================

def scenario_3():
    game = make_game()
    pv = game.player_vessel

    zone = find_deep_no_entry_zone(game)
    if zone is None:
        return Result(3, "Zone fine", False,
                      expected="a no-entry zone with deep water at its centre",
                      got="none found (all no-entry centres shallow or in port)",
                      cause="world_data ZONES / depth model")

    money_before = game.career.money
    pv.position = zone.center
    pv.status = "underway"
    pv.current_speed = 0.0
    pv.target_speed = 0.0
    pv.destination = None

    # First fine fires after the 10 sim-second grace period; stop as soon as it
    # lands so the figures stay clean (15 real-s = 1200 sim-s is the hard cap).
    run_sim(game, 15.0, until=lambda g: g.career.fines_paid > 0)

    money_after = game.career.money
    fines_ok = game.career.fines_paid > 0
    money_ok = money_after < PLAYER_STARTING_MONEY
    passed = fines_ok and money_ok

    summary = (f"{POUND}{game.career.fines_paid:.0f} fine in {zone.name} "
               f"(money {money_before:.0f}->{money_after:.0f})")
    return Result(
        3, "Zone fine", passed, summary=summary,
        expected="fines_paid>0 and money<5000 after sitting in a no-entry zone",
        got=(f"fines_paid={game.career.fines_paid:.0f}, money={money_after:.0f}, "
             f"player status={pv.status}"),
        cause=("zone-violation fine block in update_simulation not firing — check "
               "the player is 'underway' and not grounded inside the zone"),
    )


# ===========================================================================
# Step 5 — Scenario 4: Grounding and hull damage
# ===========================================================================

def scenario_4():
    game = make_game()
    pv = game.player_vessel

    island_name, pt = find_island_interior_point(game)
    if pt is None:
        return Result(4, "Grounding hull damage", False,
                      expected="an interior point of some island polygon",
                      got="none found",
                      cause="world.point_in_island / island polygons")

    hull_before = pv.hull_integrity
    pv.position = pt
    pv.status = "underway"
    pv.current_speed = 0.0
    pv.target_speed = 0.0
    pv.destination = None

    run_sim(game, 1.0, until=lambda g: g.player_vessel.status == "aground")

    hull_after = pv.hull_integrity
    aground_ok = pv.status == "aground"
    hull_ok = hull_after < 1.0
    passed = aground_ok and hull_ok

    summary = (f"on {island_name}: hull {hull_before * 100:.0f}% -> "
               f"{hull_after * 100:.0f}% (-{(hull_before - hull_after) * 100:.0f})")
    return Result(
        4, "Grounding hull damage", passed, summary=summary,
        expected="status=aground and hull_integrity<1.0 after grounding",
        got=f"status={pv.status}, hull_integrity={hull_after:.2f}",
        cause=("grounding check in update_simulation not firing — depth model or "
               "the player skipped because near a port / not underway"),
    )


# ===========================================================================
# Step 6 — Scenario 5: Game over from hull failure
# ===========================================================================

def scenario_5():
    game = make_game()
    pv = game.player_vessel

    island_name, pt = find_island_interior_point(game)
    if pt is None:
        return Result(5, "Game over hull=0", False,
                      expected="an interior point of some island polygon",
                      got="none found",
                      cause="world.point_in_island / island polygons")

    pv.hull_integrity = 0.05          # one grounding (-0.15) drops it to 0
    pv.position = pt
    pv.status = "underway"
    pv.current_speed = 0.0
    pv.target_speed = 0.0
    pv.destination = None

    run_sim(game, 1.0, until=lambda g: g.game_over)

    passed = game.game_over is True
    summary = (f"hull -> {pv.hull_integrity * 100:.0f}%, game_over={game.game_over} "
               f"({game.game_over_reason})")
    return Result(
        5, "Game over hull=0", passed, summary=summary,
        expected="game.game_over == True after hull hits 0 on grounding",
        got=(f"game_over={game.game_over}, hull_integrity={pv.hull_integrity:.2f}, "
             f"reason='{game.game_over_reason}'"),
        cause=("_trigger_game_over not called when player hull<=0 on grounding "
               "(GROUNDING_HULL_DAMAGE vs starting hull)"),
    )


# ===========================================================================
# Step 7 — Scenario 6: Fuel exhaustion triggers SAR
# ===========================================================================

def scenario_6():
    game = make_game()
    pv = game.player_vessel

    # NOTE: the brief said open water (500,350), but that point is *inside*
    # Skerry Bank shoal (depth 5 m < the player's 5.5 m UKC) and would ground
    # instantly.  (500,250) is genuinely open ocean (101 wu from Skerry centre,
    # depth ~60 m), so fuel exhaustion — not grounding — is what strands us.
    open_water = (500.0, 250.0)
    pv.position = open_water
    pv.heading = 270.0                # due north into clear northern sea
    pv.status = "underway"
    pv.fuel = 0.1                      # nearly empty
    pv.current_speed = 0.0
    pv.target_speed = pv.max_speed     # full throttle to burn the dregs quickly
    pv.destination = None

    # At 0.4 fuel/h, 0.1 fuel lasts ~900 sim-s (~11 real-s), so a literal 5-s run
    # can't deplete it.  Run until the vessel is in distress, then a moment more
    # so SAR dispatch can assign a rescuer; cap at 30 real-s.
    _, sim_s = run_sim(
        game, 30.0,
        until=lambda g: g.player_vessel.distress or g.player_vessel.status == "adrift",
    )
    # Let SAR dispatch settle (rescuer assignment happens on the distress step,
    # but give a couple of extra calls of slack).
    run_sim(game, 2.0,
            until=lambda g: g.player_vessel.rescue_vessel is not None)

    distress_ok = pv.distress or pv.status == "adrift"
    rescuer = pv.rescue_vessel
    others_commanded = [v for v in game.world.vessels
                        if v is not pv and v.player_commanded]
    sar_ok = len(others_commanded) > 0

    passed = distress_ok and sar_ok

    if rescuer is not None:
        dist = _nm(rescuer.distance_to(pv.position))
        dispatched = f"{rescuer.name} ({dist:.1f} nm away)"
    elif others_commanded:
        v = others_commanded[0]
        dist = _nm(v.distance_to(pv.position))
        dispatched = f"{v.name} ({dist:.1f} nm away)"
    else:
        dispatched = "none"

    summary = (f"fuel exhausted in {sim_s / 3600.0:.2f} sim-h, "
               f"status={pv.status}, SAR: {dispatched}")
    return Result(
        6, "Fuel SAR dispatch", passed, summary=summary,
        expected="player distress/adrift AND another vessel player_commanded (SAR)",
        got=(f"distress={pv.distress}, status={pv.status}, fuel={pv.fuel:.3f}, "
             f"rescuer={rescuer.name if rescuer else None}, "
             f"others_commanded={[v.name for v in others_commanded]}"),
        cause=("fuel-exhaustion distress in ship.move() or _sar_dispatch not "
               "triggering — check no eligible underway vessel within range"),
    )


# ===========================================================================
# Step 8 — Scenario 7: --skip-title bypasses the title screen
# ===========================================================================

def scenario_7():
    """run(skip_title=True) must never enter the title loop; False must."""
    calls = []

    def _run_once(skip):
        game = make_game()
        game._title_loop = lambda: calls.append(skip) or "new"
        game.running = False          # main loop exits immediately
        try:
            game.run(skip_title=skip)
        except SystemExit:
            pass                       # run() calls sys.exit() on shutdown

    _run_once(True)
    skipped_ok = len(calls) == 0       # title loop never invoked
    _run_once(False)
    shown_ok = calls == [False]        # invoked exactly once without the flag

    passed = skipped_ok and shown_ok
    return Result(
        7, "Title screen skip", passed,
        summary=f"--skip-title bypassed title loop; without flag it ran",
        expected="title loop not called with skip_title=True, called once with False",
        got=f"calls={calls}",
        cause="Game.run() not honouring the skip_title flag",
    )


# ===========================================================================
# Step 9 — Scenario 8: save/load round-trip is exact
# ===========================================================================

def scenario_8():
    import tempfile
    from engine.career import PlayerCareer, save_career, load_career

    path = os.path.join(tempfile.gettempdir(), "meridian_bot_roundtrip.json")
    career = PlayerCareer()
    career.money             = 7777.25
    career.reputation        = 33
    career.total_deliveries  = 4
    career.total_distance_nm = 123.5
    career.fines_paid        = 950.0
    career.hull_repairs_paid = 400.0
    career.achievements      = {"First Delivery"}
    save_career(career, filepath=path, hull_integrity=0.62)
    data = load_career(filepath=path)

    checks = {
        "money":             (data or {}).get("money") == 7777.25,
        "reputation":        (data or {}).get("reputation") == 33,
        "total_deliveries":  (data or {}).get("total_deliveries") == 4,
        "total_distance_nm": (data or {}).get("total_distance_nm") == 123.5,
        "fines_paid":        (data or {}).get("fines_paid") == 950.0,
        "hull_repairs_paid": (data or {}).get("hull_repairs_paid") == 400.0,
        "hull_integrity":    (data or {}).get("hull_integrity") == 0.62,
    }
    passed = data is not None and all(checks.values())
    bad = [k for k, ok in checks.items() if not ok]
    return Result(
        8, "Save/load round-trip", passed,
        summary="all 7 fields match exactly after save->load",
        expected="every saved field loads back unchanged",
        got=f"mismatched fields: {bad or 'none'}, data={'None' if data is None else 'dict'}",
        cause="save_career/load_career field handling in engine/career.py",
    )


# ===========================================================================
# Step 10 — Scenario 9: docking menu appears with correct fuel cost
# ===========================================================================

def scenario_9():
    from render.panels import DockingMenuPanel
    from config import FUEL_COST_PER_UNIT

    game = make_game()
    pv = game.player_vessel
    maren = game.world.find_port("Port Maren")

    pv.position = (maren.position[0] + 1.0, maren.position[1])
    pv.current_speed = 1.0
    pv.target_speed = 0.0
    pv.fuel = 40.0          # 60 points missing → cost 60 × FUEL_COST_PER_UNIT
    run_sim(game, 2.0, until=lambda g: g.player_vessel.status == "in_port")

    visible_ok = game.docking_menu.visible is True
    expected_cost = 60 * FUEL_COST_PER_UNIT
    got_cost = DockingMenuPanel.fuel_cost(pv)
    cost_ok = got_cost == expected_cost
    passed = pv.status == "in_port" and visible_ok and cost_ok

    return Result(
        9, "Docking menu", passed,
        summary=(f"docked at Port Maren, menu visible, "
                 f"fuel cost {POUND}{got_cost:.0f}"),
        expected=(f"status=in_port, docking_menu.visible=True, "
                  f"fuel_cost={expected_cost:.0f}"),
        got=(f"status={pv.status}, visible={game.docking_menu.visible}, "
             f"fuel_cost={got_cost:.0f}"),
        cause="proximity docking or DockingMenuPanel.fuel_cost formula",
    )


# ===========================================================================
# Step 11 — Scenario 10: autopilot waypoint navigation
# ===========================================================================

def scenario_10():
    from config import ARRIVAL_DISTANCE

    game = make_game()
    pv = game.player_vessel
    dest = (180.0, 370.0)           # ~70 wu SE of spawn, open water
    pv.autopilot_destination = dest
    pv.target_speed = 8.0           # under the Maren Approach 8 kn limit

    run_sim(game, 120.0,
            until=lambda g: g.player_vessel.autopilot_destination is None)

    cleared = pv.autopilot_destination is None
    close = pv.distance_to(dest) <= ARRIVAL_DISTANCE * 3
    logged = any("Waypoint reached" in t for t, c in game.event_log._entries)
    passed = cleared and close and logged

    return Result(
        10, "Autopilot waypoint", passed,
        summary=(f"navigated to ({dest[0]:.0f},{dest[1]:.0f}), "
                 f"final dist {pv.distance_to(dest):.1f} wu, cleared on arrival"),
        expected="autopilot_destination cleared near the waypoint + log entry",
        got=(f"cleared={cleared}, dist={pv.distance_to(dest):.1f} wu, "
             f"logged={logged}"),
        cause="autopilot steering/arrival block in update_simulation",
    )


# ===========================================================================
# Step 12 — Scenario 11: contract type variety
# ===========================================================================

def scenario_11():
    game = make_game()
    want = {"delivery", "rescue_assist", "patrol", "hazmat", "charter"}
    seen = set()
    for _ in range(10):
        game.job_board._contracts = []      # force a full re-roll
        game.job_board.refresh_jobs(game.world)
        seen |= {c.job_type for c in game.job_board.available}

    missing = want - seen
    passed = not missing
    return Result(
        11, "Contract variety", passed,
        summary=f"types over 10 refreshes: {sorted(seen)}",
        expected=f"all of {sorted(want)} appear at least once",
        got=f"missing: {sorted(missing) or 'none'}",
        cause="_CONTRACT_TEMPLATES weighting in engine/career.py",
    )


# ===========================================================================
# Step 13 — Scenario 12: reputation tier progression
# ===========================================================================

def scenario_12():
    game = make_game()
    results = {}
    for rep, want in ((0, "Deckhand"), (25, "First Mate"),
                      (50, "Captain"), (75, "Master Mariner")):
        game.career.reputation = rep
        results[rep] = game.career.tier_name
    passed = all(results[r] == w for r, w in
                 ((0, "Deckhand"), (25, "First Mate"),
                  (50, "Captain"), (75, "Master Mariner")))
    return Result(
        12, "Reputation tiers", passed,
        summary=f"0→{results[0]}, 25→{results[25]}, 50→{results[50]}, 75→{results[75]}",
        expected="Deckhand / First Mate / Captain / Master Mariner at 0/25/50/75",
        got=str(results),
        cause="REP_TIER_TABLE in config.py or reputation_tier_name()",
    )


# ===========================================================================
# Step 14 — Scenario 13: achievement unlock on first delivery
# ===========================================================================

def scenario_13():
    game = make_game()
    pv = game.player_vessel

    contract = setup_delivery_contract(game)
    if contract is None:
        return Result(13, "Achievement unlock", False,
                      expected="a deliverable rep-0 contract",
                      got="none generated",
                      cause="JobBoard.refresh_jobs weighting")
    game.job_board.accept_job(contract.contract_id, game.career,
                              game.mission_manager.sim_elapsed_s)
    to_port = game.world.find_port(contract.to_port)
    pv.position = _APPROACH_STAGES[contract.to_port]
    pv.heading = pv.bearing_to(to_port.position)
    pv.current_speed = 10.0
    pv.target_speed = 10.0
    pv.player_commanded = False
    pv.destination = to_port.position
    pv.status = "underway"
    run_sim(game, 120.0,
            on_step=lambda g: _steer(g, to_port.position, 10.0),
            until=lambda g: contract.status == "completed")

    unlocked = "First Delivery" in game.career.achievements
    passed = contract.status == "completed" and unlocked
    return Result(
        13, "Achievement unlock", passed,
        summary=f"{contract.contract_id} completed, achievements={sorted(game.career.achievements)}",
        expected="contract completed and 'First Delivery' in career.achievements",
        got=f"status={contract.status}, achievements={sorted(game.career.achievements)}",
        cause="_award_achievement hook in Game._on_player_docked",
    )


# ===========================================================================
# Step 15 — Scenario 14: weather gameplay effects
# ===========================================================================

def scenario_14():
    import pygame
    from config import STORM_MAX_SPEED_KN

    game = make_game()
    pv = game.player_vessel

    # Park an AI vessel exactly under the (dummy-driver) mouse position so
    # hover detection finds it in clear weather.
    target = next(v for v in game.world.vessels if v is not pv)
    mouse_world = game.camera.screen_to_world(pygame.mouse.get_pos())
    target.position = mouse_world
    game.selected_vessel = None

    game.environment.visibility = 500.0
    game.render()
    hover_clear = game.hover_vessel is target

    game.environment.visibility = 100.0
    game.render()
    hover_fog = game.hover_vessel is None

    # Storm: wave height above threshold caps the player's target speed.
    game.environment.wave_height = 4.0
    pv.status = "underway"
    pv.target_speed = pv.max_speed
    run_sim(game, 0.5)
    speed_capped = pv.target_speed <= STORM_MAX_SPEED_KN

    passed = hover_clear and hover_fog and speed_capped
    return Result(
        14, "Weather effects", passed,
        summary=(f"hover ok in clear, suppressed in fog, "
                 f"storm caps target to {pv.target_speed:.1f} kn"),
        expected="hover works at vis=500, None at vis=100; target<=6 kn at wave 4.0",
        got=(f"hover_clear={hover_clear}, hover_fog={hover_fog}, "
             f"target_speed={pv.target_speed:.1f}"),
        cause="fog hover suppression in Game.render or storm cap in update_simulation",
    )


# ===========================================================================
# Step 16 — Final report
# ===========================================================================

SCENARIOS = [scenario_1, scenario_2, scenario_3, scenario_4, scenario_5,
             scenario_6, scenario_7, scenario_8, scenario_9, scenario_10,
             scenario_11, scenario_12, scenario_13, scenario_14]


def run_all_scenarios():
    results = []
    for fn in SCENARIOS:
        try:
            results.append(fn())
        except Exception as exc:  # a crash is a failure with a useful trace
            import traceback
            idx = SCENARIOS.index(fn) + 1
            results.append(Result(
                idx, fn.__name__, False,
                expected="scenario runs to completion",
                got=f"{type(exc).__name__}: {exc}",
                cause="unhandled exception:\n" + traceback.format_exc(),
            ))
    return results


def print_report(results):
    line = "=" * 60
    print(line)
    print("GAMEPLAY BOT REPORT")
    print(line)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        if r.passed:
            print(f"Scenario {r.index}  {r.name:<22} {status:<6} {r.summary}")
        else:
            print(f"Scenario {r.index}  {r.name:<22} {status:<6} {r.got}")
    print("-" * 60)
    passed = sum(1 for r in results if r.passed)
    print(f"{passed}/{len(results)} passed")
    print(line)

    failures = [r for r in results if not r.passed]
    if failures:
        print()
        for r in failures:
            print(r.failure_detail)
            print()
    return passed


# ===========================================================================
# Step 9 — pytest wrapper
# ===========================================================================

def test_gameplay_bot():
    results = run_all_scenarios()
    print()
    print_report(results)
    failed = [r for r in results if not r.passed]
    assert not failed, "\n\n".join(r.failure_detail for r in failed)


if __name__ == "__main__":
    results = run_all_scenarios()
    passed = print_report(results)
    sys.exit(0 if passed == len(results) else 1)
