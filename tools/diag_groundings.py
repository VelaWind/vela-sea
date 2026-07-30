"""Grounding / distress regression harness.

Not shipped with the game and not part of the test suite — it takes ~20 minutes
per run, so it is a deliberate manual check for changes that touch navigation,
routing, SAR dispatch, or route geometry.  Read-only w.r.t. the repo: it never
writes to any project file (career saves are redirected to a temp path).

Reports, per 3-seed 14-day run: distress events de-duplicated into unique
incidents, incidents per landmass and coast face, rescuer share, wind
correlation, rescue reachability (episodes never assigned a rescuer), and
harness-health counters (arrivals, port cycling) so a broken sim cannot be
mistaken for a clean result.  Normalise by ARRIVALS, not by raw event count:
vessels stuck aground stop generating both, so raw totals can fall while the
sim is getting worse.

Why it drives the real ``Game`` instead of a pure-engine loop:
the grounding trigger and SAR dispatch do NOT live in ``engine/`` — they live
in ``main.py`` (``update_simulation``, ``_sar_dispatch``).  Re-implementing
that loop would measure the re-implementation, not the game.  So we import
``main`` under SDL dummy drivers (no window, no audio, no render calls) and
step ``update_simulation`` directly.  Rendering is never invoked.

Usage:  python tools/diag_groundings.py [--days 14] [--seeds 3]
"""
import argparse
import json
import math
import os
import random
import sys
import time
from collections import Counter, defaultdict

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import tempfile
from engine import career as _career_module
import main as _main_module
from main import Game
from config import (SIM_TIMESTEP, TIME_COMPRESSION, DRAFT_SAFETY_MARGIN_M,
                    DEPTH_COASTAL_SLOPE, SAR_DISPATCH_RANGE_NM)

# Save isolation — never touch the player's real save.json.
_TMP_SAVE = os.path.join(tempfile.gettempdir(), "vela_diag_save.json")
_main_module.save_career = (
    lambda career, filepath=None, hull_integrity=1.0:
        _career_module.save_career(career, _TMP_SAVE, hull_integrity))
_main_module.delete_save = lambda filepath=None: None

REAL_DT = 0.016

# One update_simulation(REAL_DT) call advances REAL_DT * TIME_COMPRESSION sim-s.
SIM_S_PER_CALL = REAL_DT * TIME_COMPRESSION

# Full emergency-state classification is sampled every N calls rather than every
# call: at ~1.92 sim-s per call, 30 calls is ~1 sim-minute, which resolves every
# emergency type here (the shortest, MOB, lasts 3600 sim-s) at 1/60th the cost of
# per-tick sampling over 630k calls.  The ONE sub-minute phenomenon —
# refloat -> immediate re-ground flapping — is counted per-tick instead, below.
EMERG_SAMPLE_CALLS = 30

# The five emergency/duty states a vessel can be in.  Deliberately split so that
# the two very different causes of status == "adrift" (mechanical engine failure
# vs fuel exhaustion) are never conflated, and so the three very different causes
# of player_commanded (SAR rescuer duty, medical divert, party tender) are
# separated -- the fleet-status panel labels ALL THREE "MEDICAL", which is what
# made the live fleet look sicker than it was.
EMERG_STATES = ("aground", "eng_fail", "fuel_adrift", "mob", "medical",
                "rescuer", "tender_party")


def _rescuer_ids(vessels):
    """IDs of vessels currently pointed at by some casualty's rescue_vessel.

    Mirrors _sar_dispatch's own active_rescuer_ids construction exactly.
    """
    return {id(v.rescue_vessel) for v in vessels if v.rescue_vessel is not None}


def _emerg_flags(v, rescuer_ids):
    """Classify one vessel into EMERG_STATES (a vessel can hold several).

    Returns (tuple_of_bools, displayed_emergency).  `displayed_emergency`
    reproduces exactly what FleetStatusPanel paints as an emergency-coloured
    label (MOB / ENG FAIL / DISTRESS / MEDICAL), i.e. the number a viewer
    counts off the screen -- see render/panels.py:977-991.
    """
    vid = id(v)
    pc = bool(v.player_commanded)
    aground = v.status == "aground"
    eng = bool(v.engine_failure)
    # status == "adrift" with no mechanical failure == ran the tank dry.
    fuel_adrift = (v.status == "adrift" and not eng)
    mob = v.mob_timer > 0
    # command_reason is authoritative when present.  Deriving "is a rescuer" from
    # the rescue_vessel pointers instead is WRONG once the pointer is a lease: an
    # ex-rescuer whose lease was dropped still carries a live "sar" command but is
    # no longer pointed at by any casualty, and the pointer test files it as
    # medical -- which inflated medical from 2.33 to 8.67 vessels/day before this
    # was caught.  Fall back to the pointer scan only for pre-command_reason runs.
    reason = getattr(v, "command_reason", "")
    if pc and reason:
        is_rescuer = reason == "sar"
        tender = reason == "party"
        medical = reason == "medical"
    else:
        is_rescuer = vid in rescuer_ids
        tender = pc and v.vessel_type == "tender"
        medical = pc and not is_rescuer and not tender
    displayed = bool(mob or eng or v.distress or pc)
    return (aground, eng, fuel_adrift, mob, medical, is_rescuer, tender), displayed


def _stale_assignments(vessels):
    """Casualties whose assigned rescuer can no longer perform the rescue.

    _sar_dispatch skips any casualty with rescue_vessel is not None, so an
    assignment that goes bad is never reissued -- the pointer is a permanent
    lock, not a lease.  Counts casualties whose rescuer is itself in distress
    or is no longer in a state that can steer (aground/adrift/in_port/docked).
    """
    n = 0
    for v in vessels:
        r = v.rescue_vessel
        if v.distress and r is not None:
            if r.distress or r.status not in ("underway", "avoiding"):
                n += 1
    return n


# ---------------------------------------------------------------------------
# Geometry helpers (independent of engine internals, so they cross-check it)
# ---------------------------------------------------------------------------

def _seg_dist(p, a, b):
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def hazard_at(world, pos):
    """Attribute a position to the hazard that actually made it shallow.

    water_depth_at() evaluates named shallow ZONES before the coastal-slope
    model, so a vessel can ground 100+ wu from any coastline (Skerry Bank).
    Attributing those to the nearest island would fabricate a cluster.
    """
    for z in world.zones:
        if z.kind == "shallow" and z.contains(pos):
            return f"[shoal] {z.name}", 0.0, True
    land, d = nearest_land(world, pos)
    return land, d, False


def nearest_land(world, pos):
    """Return (island_name, distance_wu) for the closest landmass polygon."""
    best, best_d = None, float("inf")
    for isl in world.islands:
        poly = isl.polygon
        n = len(poly)
        for i in range(n):
            d = _seg_dist(pos, poly[i], poly[(i + 1) % n])
            if d < best_d:
                best_d, best = d, isl.name
    return best, best_d


def coast_face(world, island_name, pos):
    """Compass face of `island_name` that `pos` lies off.

    Screen convention: +x = east, +y = SOUTH (pygame y grows downward), which
    is how chart.py renders it. Bearing computed from the island centroid.
    """
    isl = next(i for i in world.islands if i.name == island_name)
    cx = sum(p[0] for p in isl.polygon) / len(isl.polygon)
    cy = sum(p[1] for p in isl.polygon) / len(isl.polygon)
    ang = math.degrees(math.atan2(-(pos[1] - cy), pos[0] - cx)) % 360.0  # 0=E, 90=N
    for lo, hi, name in [(22.5, 67.5, "NE"), (67.5, 112.5, "N"), (112.5, 157.5, "NW"),
                         (157.5, 202.5, "W"), (202.5, 247.5, "SW"), (247.5, 292.5, "S"),
                         (292.5, 337.5, "SE")]:
        if lo <= ang < hi:
            return name
    return "E"


def wind_onshore_component(world, island_name, pos, wind_dir_from, wind_speed):
    """Knots of wind pushing the vessel TOWARD the island (negative = offshore)."""
    isl = next(i for i in world.islands if i.name == island_name)
    cx = sum(p[0] for p in isl.polygon) / len(isl.polygon)
    cy = sum(p[1] for p in isl.polygon) / len(isl.polygon)
    # Push vector = direction wind blows toward = from + 180.
    pr = math.radians((wind_dir_from + 180.0) % 360.0)
    pxv, pyv = math.cos(pr), math.sin(pr)
    tx, ty = cx - pos[0], cy - pos[1]
    L = math.hypot(tx, ty) or 1.0
    return wind_speed * (pxv * tx / L + pyv * ty / L)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run(days, seed, verbose=True):
    random.seed(seed)
    game = Game()
    game.is_paused = False
    game.environment.time_speed_multiplier = 1.0
    # Weather drift LEFT ON — wind variation is part of what we are testing.

    world = game.world
    target_sim_s = days * 86400.0
    calls = int(target_sim_s / (REAL_DT * TIME_COMPRESSION))

    events = []
    arrivals = Counter()
    port_visits = Counter()
    prev_status = {id(v): v.status for v in world.vessels}
    prev_incident = {id(v): False for v in world.vessels}
    episodes = []      # closed distress episodes
    active_ep = {}     # vid -> episode still open at this instant

    # --- emergency-lifecycle tracking (all states, not just aground/adrift) ---
    em_open = {}                       # (vid, state) -> start_h
    em_eps = []                        # closed/never-closed per-state episodes
    em_entries = Counter()             # state -> entry count
    em_census = []                     # sampled: per-state simultaneous counts
    prev_em = {id(v): tuple([False] * len(EMERG_STATES)) for v in world.vessels}
    # Per-tick aground flap detection (sub-minute refloat -> re-ground cycling).
    prev_aground = {id(v): v.status == "aground" for v in world.vessels}
    last_afloat_h = {}                 # vid -> sim_h of most recent refloat
    reground_gaps = []                 # hours between refloat and next grounding

    t0 = time.time()
    for i in range(calls):
        game.update_simulation(REAL_DT)
        sim_s = i * SIM_S_PER_CALL
        sim_h = sim_s / 3600.0

        # Per-tick: refloat -> re-ground flapping.  Measured every call because
        # the observed loop closes inside one sim-minute and 1-min sampling
        # would step straight over it.
        for v in world.vessels:
            vid = id(v)
            ag_now = v.status == "aground"
            if prev_aground[vid] and not ag_now:
                last_afloat_h[vid] = sim_h
            elif ag_now and not prev_aground[vid] and vid in last_afloat_h:
                reground_gaps.append(sim_h - last_afloat_h.pop(vid))
            prev_aground[vid] = ag_now

        # Sampled: full state classification, census, and rescuer-pool depth.
        if i % EMERG_SAMPLE_CALLS == 0:
            rids = _rescuer_ids(world.vessels)
            counts = dict.fromkeys(EMERG_STATES, 0)
            n_displayed = 0
            for v in world.vessels:
                vid = id(v)
                flags, displayed = _emerg_flags(v, rids)
                if displayed:
                    n_displayed += 1
                for si, st in enumerate(EMERG_STATES):
                    if flags[si]:
                        counts[st] += 1
                    was, now = prev_em[vid][si], flags[si]
                    if now and not was:
                        em_entries[st] += 1
                        em_open[(vid, st)] = sim_h
                    elif was and not now and (vid, st) in em_open:
                        em_eps.append({"vessel": v.name, "state": st,
                                       "start_h": em_open.pop((vid, st)),
                                       "end_h": sim_h})
                prev_em[vid] = flags
            # Dispatch eligibility, replicating _sar_dispatch's candidate filter.
            eligible = sum(
                1 for v in world.vessels
                if v.status in ("underway", "avoiding")
                and not v.player_commanded
                and id(v) not in rids)
            em_census.append({
                "sim_h": round(sim_h, 3),
                "displayed": n_displayed,
                "eligible": eligible,
                "stale": _stale_assignments(world.vessels),
                **counts,
            })

        for v in world.vessels:
            vid = id(v)
            was, now = prev_status[vid], v.status
            if was != now:
                if now in ("in_port", "docked") and was in ("underway", "avoiding"):
                    arrivals[v.name] += 1
                    if v.destination:
                        p = min(world.ports,
                                key=lambda q: math.hypot(q.position[0] - v.position[0],
                                                         q.position[1] - v.position[1]))
                        port_visits[p.name] += 1
                prev_status[vid] = now

            incident = bool(v.distress)
            if incident and not prev_incident[vid]:
                land, dist, is_shoal = hazard_at(world, v.position)
                # How many OTHER casualties were already active, and how close?
                others = [o for o in world.vessels
                          if o is not v and o.distress]
                nearest_cas = min(
                    (math.hypot(o.position[0] - v.position[0],
                                o.position[1] - v.position[1]) for o in others),
                    default=None)
                env = game.environment
                # Is the point this vessel was STEERING TO itself safe water?
                dest_land, dest_d, dest_depth = None, None, None
                if v.destination:
                    dest_land, dest_d = nearest_land(world, tuple(v.destination))
                    dest_depth = world.water_depth_at(tuple(v.destination),
                                                      env.tide_level)
                events.append({
                    "seed": seed,
                    "sim_h": round(sim_s / 3600.0, 2),
                    "vessel": v.name,
                    "type": v.vessel_type,
                    "status": v.status,
                    "kind": ("aground" if v.status == "aground"
                             else "adrift/engine" if v.status == "adrift" else v.status),
                    "pos": [round(v.position[0], 1), round(v.position[1], 1)],
                    "draft_m": v.draft_m,
                    "dest": (list(v.destination) if v.destination else None),
                    "route": [list(w) for w in getattr(v, "route", [])],
                    "route_idx": getattr(v, "route_index", None),
                    "was_rescuer": bool(v.player_commanded),
                    "dest_land_dist_wu": (round(dest_d, 2)
                                          if dest_d is not None else None),
                    "dest_depth_m": (round(dest_depth, 2)
                                     if dest_depth is not None else None),
                    "dest_unsafe": (dest_depth is not None
                                    and dest_depth < v.draft_m + DRAFT_SAFETY_MARGIN_M),
                    "land": land,
                    "land_dist_wu": round(dist, 2),
                    "is_shoal": is_shoal,
                    "face": ("-" if is_shoal
                             else coast_face(world, land, v.position)),
                    "wind_dir_from": round(env.wind_direction, 1),
                    "wind_kn": round(env.wind_speed, 2),
                    "tide_m": round(env.tide_level, 2),
                    "onshore_kn": (None if is_shoal else round(
                        wind_onshore_component(world, land, v.position,
                                               env.wind_direction, env.wind_speed), 2)),
                    "n_active_casualties": len(others),
                    "nearest_casualty_wu": (round(nearest_cas, 1)
                                            if nearest_cas is not None else None),
                })
            # --- distress-episode tracking ---------------------------------
            # Depth-aware rescue routing can REFUSE to dispatch (no safe leg),
            # which trades rescuer groundings for permanently stranded
            # casualties.  That shows up as falling arrivals, not as grounding
            # events, so episodes are tracked explicitly: was a rescuer ever
            # assigned, and did the episode ever end?
            if incident and not prev_incident[vid]:
                active_ep[vid] = {"vessel": v.name, "start_h": sim_s / 3600.0,
                                  "rescued": False,
                                  "land": hazard_at(world, v.position)[0]}
            if incident and vid in active_ep and v.rescue_vessel is not None:
                active_ep[vid]["rescued"] = True
            if prev_incident[vid] and not incident and vid in active_ep:
                ep = active_ep.pop(vid)
                ep["end_h"] = sim_s / 3600.0
                ep["stranded_at_end"] = False
                episodes.append(ep)
            prev_incident[vid] = incident

        if verbose and i % max(1, calls // 10) == 0:
            print(f"    seed {seed}: {sim_s/86400:5.2f} d  "
                  f"events={len(events):4d}  {time.time()-t0:6.1f}s", flush=True)

    # Episodes still open when the run ends = casualties never freed at all.
    for ep in active_ep.values():
        ep["end_h"] = None
        ep["stranded_at_end"] = True
        episodes.append(ep)

    # Emergency episodes still open at run end never resolved: end_h = None.
    _vid_name = {id(v): v.name for v in world.vessels}
    for (vid, st), start_h in em_open.items():
        em_eps.append({"vessel": _vid_name.get(vid, "?"), "state": st,
                       "start_h": start_h, "end_h": None})

    return {
        "seed": seed,
        "sim_days": target_sim_s / 86400.0,
        "n_vessels": len(world.vessels),
        "vessel_hours": len(world.vessels) * target_sim_s / 3600.0,
        "events": events,
        "episodes": episodes,
        "arrivals": dict(arrivals),
        "port_visits": dict(port_visits),
        "em_eps": em_eps,
        "em_entries": dict(em_entries),
        "em_census": em_census,
        "reground_gaps": [round(g, 4) for g in reground_gaps],
        "wall_s": round(time.time() - t0, 1),
    }


def report(runs):
    world_ref = None
    all_ev = [e for r in runs for e in r["events"]]
    total_vh = sum(r["vessel_hours"] for r in runs)
    total_arr = Counter()
    total_pv = Counter()
    for r in runs:
        total_arr.update(r["arrivals"])
        total_pv.update(r["port_visits"])

    print("\n" + "=" * 74)
    print("HARNESS HEALTH CHECK")
    print("=" * 74)
    print(f"  seeds={len(runs)}  sim_days/seed={runs[0]['sim_days']:.0f}  "
          f"vessels={runs[0]['n_vessels']}  vessel-hours={total_vh:,.0f}")
    print(f"  wall time: {sum(r['wall_s'] for r in runs):.0f}s")
    print(f"  total arrivals/dockings: {sum(total_arr.values())}")
    print(f"  vessels that arrived at least once: "
          f"{len(total_arr)}/{runs[0]['n_vessels']}")
    print("  port cycling (visits):")
    for p, n in total_pv.most_common():
        print(f"      {p:<26} {n:4d}")

    print("\n" + "=" * 74)
    print("DISTRESS EVENTS")
    print("=" * 74)
    print(f"  total distress events: {len(all_ev)}")
    by_kind = Counter(e["kind"] for e in all_ev)
    for k, n in by_kind.most_common():
        print(f"      {k:<16} {n:4d}")

    all_eps = [e for r in runs for e in r.get("episodes", [])]
    if all_eps:
        never = [e for e in all_eps if not e["rescued"]]
        stranded = [e for e in all_eps if e["stranded_at_end"]]
        print("\n  --- distress episodes (rescue reachability) ---")
        print(f"      episodes                     {len(all_eps):4d}")
        print(f"      never assigned a rescuer     {len(never):4d}  "
              f"({100.0*len(never)/max(1,len(all_eps)):.0f}%)")
        print(f"      still stranded at run end    {len(stranded):4d}")
        durs = [e["end_h"] - e["start_h"] for e in all_eps if e["end_h"] is not None]
        if durs:
            durs.sort()
            print(f"      median episode length        {durs[len(durs)//2]:6.1f} h")

    print("\n  --- events per landmass (aground only) ---")
    ag = [e for e in all_ev if e["kind"] == "aground"]
    per_land = Counter(e["land"] for e in ag)
    for land, n in per_land.most_common():
        pct = 100.0 * n / max(1, len(ag))
        print(f"      {land:<26} {n:4d}   {pct:5.1f}%")

    print("\n  --- coast face on the top landmass ---")
    if per_land:
        top = per_land.most_common(1)[0][0]
        faces = Counter(e["face"] for e in ag if e["land"] == top)
        for f, n in faces.most_common():
            print(f"      {top} / {f:<4} {n:4d}  "
                  f"{100.0*n/max(1,per_land[top]):5.1f}%")
        print(f"\n  --- positions on {top} ---")
        for e in ag:
            if e["land"] == top:
                print(f"      ({e['pos'][0]:6.1f},{e['pos'][1]:6.1f}) "
                      f"face={e['face']:<3} d={e['land_dist_wu']:5.2f}wu "
                      f"tide={e['tide_m']:+5.2f} wind={e['wind_kn']:5.1f}kn"
                      f"@{e['wind_dir_from']:5.1f}  onshore={(e['onshore_kn'] or 0):+5.2f}kn "
                      f"rescuer={str(e['was_rescuer']):5} "
                      f"othercas={e['n_active_casualties']} "
                      f"nearcas={e['nearest_casualty_wu']} "
                      f"{e['vessel']}")

        sub = [e for e in ag if e["land"] == top]
        onshore = [e for e in sub if (e["onshore_kn"] or 0) > 0]
        rescuers = [e for e in sub if e["was_rescuer"]]
        chained = [e for e in sub
                   if e["nearest_casualty_wu"] is not None
                   and e["nearest_casualty_wu"] <= 15.0]
        print(f"\n  wind onshore at grounding : {len(onshore)}/{len(sub)} "
              f"({100.0*len(onshore)/max(1,len(sub)):.0f}%)")
        print(f"  vessel was a dispatched rescuer/diverted (player_commanded): "
              f"{len(rescuers)}/{len(sub)} "
              f"({100.0*len(rescuers)/max(1,len(sub)):.0f}%)")
        print(f"  grounded within 15 wu of an existing casualty: "
              f"{len(chained)}/{len(sub)} "
              f"({100.0*len(chained)/max(1,len(sub)):.0f}%)")

        print("\n  --- destination safety at moment of grounding (ALL aground) ---")
        with_dest = [e for e in ag if e["dest_depth_m"] is not None]
        unsafe_dest = [e for e in with_dest if e["dest_unsafe"]]
        print(f"      steering toward water too shallow for own draft: "
              f"{len(unsafe_dest)}/{len(with_dest)} "
              f"({100.0*len(unsafe_dest)/max(1,len(with_dest)):.0f}%)")
        r_dest = [e for e in with_dest if e["was_rescuer"]]
        r_unsafe = [e for e in r_dest if e["dest_unsafe"]]
        print(f"      ... restricted to dispatched rescuers: "
              f"{len(r_unsafe)}/{len(r_dest)} "
              f"({100.0*len(r_unsafe)/max(1,len(r_dest)):.0f}%)")

        print("\n  --- primary vs rescuer vs re-ground (ALL aground) ---")
        prim = [e for e in ag if not e["was_rescuer"]]
        resc_all = [e for e in ag if e["was_rescuer"]]
        # Re-ground = same vessel, within 2 wu of a spot it already grounded on.
        seen_spots = defaultdict(list)
        regrounds = 0
        for e in sorted(ag, key=lambda x: (x["seed"], x["sim_h"])):
            key = (e["seed"], e["vessel"])
            if any(math.hypot(p[0] - e["pos"][0], p[1] - e["pos"][1]) < 2.0
                   for p in seen_spots[key]):
                regrounds += 1
            seen_spots[key].append(e["pos"])
        print(f"      on own scheduled route (not commanded): {len(prim):4d}")
        print(f"      dispatched rescuer / diverted          : {len(resc_all):4d}")
        print(f"      re-grounds on a spot already hit       : {regrounds:4d}"
              f"  ({100.0*regrounds/max(1,len(ag)):.0f}% of all)")

        print("\n  --- route autopsy (aground on top landmass) ---")
        legs = Counter()
        for e in sub:
            r, idx = e["route"], e["route_idx"]
            if r and idx is not None and len(r) > 1:
                prev = tuple(r[(idx - 1) % len(r)])
                cur = tuple(r[idx % len(r)])
                legs[f"{prev} -> {cur}"] += 1
            else:
                legs[f"(no route) -> {e['dest']}"] += 1
        for leg, n in legs.most_common():
            print(f"      {n:3d}x  {leg}")

    print("\n  --- all events, chronological ---")
    for e in sorted(all_ev, key=lambda x: (x["seed"], x["sim_h"])):
        print(f"    s{e['seed']} t={e['sim_h']:8.2f}h {e['kind']:<14} "
              f"{e['vessel']:<20} ({e['pos'][0]:6.1f},{e['pos'][1]:6.1f}) "
              f"{e['land']:<24} d={e['land_dist_wu']:6.2f} {e['face']:<3} "
              f"resc={str(e['was_rescuer'])[0]}")


def report_emergency(runs):
    """Emergency-lifecycle report: every state, not just aground/adrift.

    The original harness counted only v.distress, so MEDICAL diverts, MOB
    searches, rescuer duty and the engine-failure/fuel-exhaustion split were all
    invisible -- which is how a fleet-wide emergency ratchet shipped through six
    verified commits.
    """
    days = sum(r["sim_days"] for r in runs)
    nv = runs[0]["n_vessels"]
    vessel_days = days * nv
    all_eps = [e for r in runs for e in r["em_eps"]]
    entries = Counter()
    for r in runs:
        entries.update(r["em_entries"])

    print("\n" + "=" * 74)
    print("EMERGENCY LIFECYCLE — all states")
    print("=" * 74)
    print(f"  seeds={len(runs)}  vessel-days={vessel_days:,.0f}\n")
    print(f"  {'state':<14} {'fires':>6} {'/vessel-day':>12} {'resolved':>9} "
          f"{'NEVER':>6} {'median h':>9} {'max h':>8}")
    for st in EMERG_STATES:
        eps = [e for e in all_eps if e["state"] == st]
        closed = [e for e in eps if e["end_h"] is not None]
        never = len(eps) - len(closed)
        durs = sorted(e["end_h"] - e["start_h"] for e in closed)
        med = f"{durs[len(durs)//2]:9.2f}" if durs else f"{'-':>9}"
        mx = f"{durs[-1]:8.2f}" if durs else f"{'-':>8}"
        print(f"  {st:<14} {entries[st]:6d} {entries[st]/max(1e-9,vessel_days):12.3f} "
              f"{len(closed):9d} {never:6d} {med} {mx}")
    print("\n  NEVER = episode still open when the run ended (no resolution path")
    print("  reached in the remaining sim time).")

    # --- simultaneous-emergency distribution -------------------------------
    census = [c for r in runs for c in r["em_census"]]
    if not census:
        return
    print("\n  --- simultaneous emergencies (as the fleet panel paints them) ---")
    print("  'displayed' = vessels showing MOB/ENG FAIL/DISTRESS/MEDICAL, i.e.")
    print("  the count a viewer reads off the screen.")
    hist = Counter(c["displayed"] for c in census)
    ns = len(census)
    for k in sorted(hist):
        bar = "#" * int(60.0 * hist[k] / ns)
        print(f"      {k:2d}/{nv}  {100.0*hist[k]/ns:5.1f}%  {bar}")
    disp = sorted(c["displayed"] for c in census)
    print(f"      median={disp[ns//2]}  p90={disp[int(ns*0.9)]}  max={disp[-1]}")

    # --- rescuer pool over time --------------------------------------------
    print("\n  --- eligible-rescuer pool (dispatch candidates fleet-wide) ---")
    elig = sorted(c["eligible"] for c in census)
    zero = sum(1 for c in census if c["eligible"] == 0)
    print(f"      median={elig[ns//2]}  p10={elig[int(ns*0.1)]}  min={elig[0]}  "
          f"max={elig[-1]}")
    print(f"      samples with ZERO eligible rescuer: {zero}/{ns} "
          f"({100.0*zero/ns:.1f}%)")
    stale = [c["stale"] for c in census]
    print(f"      casualties holding a dead rescuer pointer: "
          f"mean={sum(stale)/ns:.2f}  max={max(stale)}")

    print("\n  --- per sim-day trend (mean over each day, all seeds pooled) ---")
    print(f"      {'day':>4} {'displayed':>10} {'eligible':>9} {'stale':>6} "
          f"{'aground':>8} {'eng_fail':>9} {'medical':>8} {'rescuer':>8}")
    per_day = defaultdict(list)
    for c in census:
        per_day[int(c["sim_h"] // 24)].append(c)
    for d in sorted(per_day):
        cs = per_day[d]
        n = len(cs)
        def _m(key):
            return sum(c[key] for c in cs) / n
        print(f"      {d:4d} {_m('displayed'):10.2f} {_m('eligible'):9.2f} "
              f"{_m('stale'):6.2f} {_m('aground'):8.2f} {_m('eng_fail'):9.2f} "
              f"{_m('medical'):8.2f} {_m('rescuer'):8.2f}")

    # --- refloat -> re-ground flapping -------------------------------------
    gaps = sorted(g for r in runs for g in r["reground_gaps"])
    print("\n  --- refloat -> re-ground flapping (KNOWN_ISSUES #11) ---")
    if gaps:
        fast = [g for g in gaps if g <= 1.0 / 60.0]     # within one sim-minute
        hour = [g for g in gaps if g <= 1.0]
        print(f"      re-groundings after a refloat : {len(gaps):4d}")
        print(f"      ... within 1 sim-MINUTE       : {len(fast):4d}  "
              f"({100.0*len(fast)/len(gaps):.0f}%)")
        print(f"      ... within 1 sim-hour         : {len(hour):4d}  "
              f"({100.0*len(hour)/len(gaps):.0f}%)")
        print(f"      median gap                    : {gaps[len(gaps)//2]*60:6.2f} sim-min")
    else:
        print("      none observed")


def static_corridor_scan():
    """Independent static check: how close does each scheduled route leg pass
    to land, versus the depth needed by the vessel using it?"""
    from engine.world import World
    from data.world_data import populate_world
    import data.world_data as wd
    w = World()
    populate_world(w)

    print("\n" + "=" * 74)
    print("STATIC ROUTE-CORRIDOR SCAN (no sim) — min clearance per leg")
    print("=" * 74)
    print("  grounding radius = (draft + 0.5 - tide) / 4.0 wu  [DEPTH_COASTAL_SLOPE=4]")
    print(f"  e.g. draft 8.0 m @ low tide (-3 m): "
          f"{(8.0 + DRAFT_SAFETY_MARGIN_M + 3.0)/DEPTH_COASTAL_SLOPE:.2f} wu\n")

    routes = {n: getattr(wd, n) for n in dir(wd)
              if n.startswith("VESSEL_ROUTE_") and isinstance(getattr(wd, n), list)}
    rows = []
    for name, route in sorted(routes.items()):
        for i in range(len(route)):
            a = tuple(route[i])
            b = tuple(route[(i + 1) % len(route)])
            worst, worst_land, worst_pt = float("inf"), None, None
            for k in range(201):
                t = k / 200.0
                p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                land, d = nearest_land(w, p)
                if d < worst:
                    worst, worst_land, worst_pt = d, land, p
            rows.append((worst, name, a, b, worst_land, worst_pt))
    rows.sort()
    for worst, name, a, b, land, pt in rows[:14]:
        print(f"   {worst:6.2f} wu  depth~{worst*DEPTH_COASTAL_SLOPE:5.1f} m  "
              f"{name.replace('VESSEL_ROUTE_',''):<12} {a} -> {b}")
        print(f"{'':16}nearest: {land} at ({pt[0]:.0f},{pt[1]:.0f})")


def leeway_probe():
    """Controlled causal test of the leeway hypothesis on the pinch leg.

    One cargo vessel on the ORIGINAL pinch leg (500,565) -> (640,500), steered by
    the exact same pure-pursuit line main.py uses.  Wind is held FROM 060 deg so
    the hull push (bearing + 180 = 240 deg, i.e. west-and-north in screen axes
    where +y is south) sets the vessel onto Carrow's S/SW rim.  Sweep wind speed
    and record the closest approach to land: if clearance shrinks with wind,
    uncompensated leeway is the mechanism.

    NOTE: the coordinates here are hard-coded to the pre-fix geometry on purpose
    — this is the baseline measurement that motivated moving _WP_S_ISLANDS, so
    it must keep reproducing the old numbers rather than track the live route.
    """
    from engine.world import World
    from engine.ship import Vessel
    from engine.environment import Environment
    from data.world_data import populate_world

    print("\n" + "=" * 74)
    print("LEEWAY PROBE — pinch leg (500,565) -> (640,500), draft 8.0 m cargo")
    print("=" * 74)
    print("  steering = main.py pure pursuit (turn_toward(bearing_to(dest)))")
    print("  wind held FROM 060 deg (NE) => pushes SW/NW, onto Carrow's S/SW rim\n")
    print(f"  {'wind kn':>8} {'min clear wu':>13} {'min depth m':>12} "
          f"{'grounds?':>9}  {'closest pt':>16}")

    for wind_kn in (0, 5, 10, 15, 20, 25, 30):
        w = World()
        populate_world(w)
        env = Environment()
        env.weather_drift_enabled = False
        env.wind_speed = float(wind_kn)
        env.wind_direction = 60.0
        env.current_speed = 0.0        # isolate wind
        env.tide_level = -3.0          # low water (worst case)
        v = Vessel(name="probe", vessel_type="cargo", position=(500.0, 565.0),
                   heading=math.degrees(math.atan2(-65, 140)) % 360.0,
                   target_speed=9.0, current_speed=9.0, max_speed=12.0,
                   acceleration=2.0, deceleration=1.0, turn_rate=10.0, length_m=150.0,
                   beam_m=25.0, draft_m=8.0, fuel=1e9, fuel_capacity=1e9,
                   fuel_consumption_rate=0.0, destination=(640.0, 500.0))
        worst, worst_pt, worst_depth = float("inf"), None, float("inf")
        for _ in range(20000):
            v.turn_toward(v.bearing_to(v.destination), SIM_TIMESTEP)
            v.update_speed(SIM_TIMESTEP, env)
            v.move(SIM_TIMESTEP, env)
            _, d = nearest_land(w, v.position)
            dep = w.water_depth_at(v.position, env.tide_level)
            if d < worst:
                worst, worst_pt, worst_depth = d, v.position, dep
            if math.hypot(v.position[0] - 640, v.position[1] - 500) < 2.0:
                break
        grounds = worst_depth < 8.0 + DRAFT_SAFETY_MARGIN_M
        print(f"  {wind_kn:8d} {worst:13.2f} {worst_depth:12.2f} "
              f"{('GROUND' if grounds else 'ok'):>9}  "
              f"({worst_pt[0]:6.1f},{worst_pt[1]:6.1f})")
    print("\n  (tide is 0 here; at low water -3 m every row loses 3 m of depth,")
    print("   i.e. the grounding threshold moves out to 2.88 wu of clearance)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=14.0)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--static-only", action="store_true")
    ap.add_argument("--probe-only", action="store_true")
    args = ap.parse_args()

    if args.probe_only:
        leeway_probe()
        sys.exit(0)

    static_corridor_scan()
    leeway_probe()
    if args.static_only:
        sys.exit(0)

    runs = []
    for s in range(args.seeds):
        seed = 20260719 + s * 977
        print(f"\n[run] seed={seed} days={args.days}")
        runs.append(run(args.days, seed))
    out = os.path.join(tempfile.gettempdir(), "vela_diag_events.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(runs, fh, indent=1)
    print(f"\n[raw events written to {out}]")
    report(runs)
    report_emergency(runs)
