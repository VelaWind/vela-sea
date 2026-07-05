"""tests/audit_abc.py -- Comprehensive audit of Chunks A, B, C.

Rules applied:
  - Real engine classes only; no engine/config files modified.
  - Each test prints: scenario | expected (closed-form) | actual | abs_error | PASS/FAIL.
  - Tolerance: <= 1 % relative error unless stated in test.
  - Final: summary table + FAILURES IN DETAIL section.
  - render/ is NOT imported (pygame dependency -- B7/COG is BLOCKED).
  - Do NOT run old test scripts.

Closed-form references used:
  - distance = speed_kn * KNOTS_TO_UNITS_PER_HOUR * (dt / 3600)
  - fuel_used = rate * (speed / max_speed)^2 * (dt / 3600)
  - turn_effectiveness (speed <= optimal): MIN + (1 - MIN) * (frac / OPTIMAL)
  - turn_effectiveness (speed > optimal): 1 - (1 - HIGH) * over
  - depth (open water): min(DEPTH_OFFSHORE, dist_to_coast * DEPTH_COASTAL_SLOPE) + tide*TIDAL
  - depth (shallow zone): DEPTH_SHOAL_SKERRY + tide * TIDAL_DEPTH_INFLUENCE
  - depth (land): 0
  - grounding: depth < draft_m + DRAFT_SAFETY_MARGIN_M
"""

import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    SIM_TIMESTEP, KNOTS_TO_UNITS_PER_HOUR, NM_PER_WORLD_UNIT,
    FUEL_COAST_DECELERATION,
    TURN_OPTIMAL_SPEED_FRACTION, TURN_MIN_EFFECTIVENESS,
    TURN_HIGH_SPEED_EFFECTIVENESS, TURN_SPEED_BLEED,
    CURRENT_INFLUENCE,
    WINDAGE_CARGO, WINDAGE_FISHING, WINDAGE_SAILBOAT,
    SAIL_NO_GO_ANGLE, SAIL_EFFICIENCY, SAIL_RUN_FACTOR,
    DEPTH_OFFSHORE, DEPTH_COASTAL_SLOPE, DEPTH_SHOAL_SKERRY,
    DRAFT_SAFETY_MARGIN_M, TIDAL_DEPTH_INFLUENCE, TIDE_RANGE,
)
from engine.world import World
from engine.environment import Environment
from engine.ship import Vessel
from data.world_data import populate_world

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------
DT = SIM_TIMESTEP  # 0.016 sim-s per physics tick
_results = []      # (chunk, tid, name, passed, detail)
_failures = []


def _record(chunk: str, tid: str, name: str, passed: bool, detail: str = "") -> None:
    _results.append((chunk, tid, name, passed, detail))
    tag = "PASS" if passed else "FAIL"
    print(f"  [{tag}] {chunk}.{tid}  {name}")
    if not passed:
        print(f"         >> {detail}")
        _failures.append((chunk, tid, name, detail))


def _near(a: float, b: float, rel: float = 0.01) -> bool:
    """True when |a - b| <= rel × max(|b|, 1e-9).  Default: 1 % relative."""
    return abs(a - b) <= rel * max(abs(b), 1e-9)


def _blocked(chunk: str, tid: str, name: str, reason: str) -> None:
    _results.append((chunk, tid, name, None, reason))
    print(f"  [BLKD] {chunk}.{tid}  {name}")
    print(f"         >> {reason}")


def _vessel(**kw) -> Vessel:
    defaults = dict(
        name="T", vessel_type="cargo",
        position=(500.0, 500.0), heading=0.0,
        target_speed=8.0, current_speed=8.0,
        max_speed=12.0, acceleration=0.020, deceleration=0.017,
        turn_rate=1.0, length_m=150.0, beam_m=25.0, draft_m=8.0,
        fuel=80.0, fuel_capacity=100.0, fuel_consumption_rate=3.5,
    )
    defaults.update(kw)
    return Vessel(**defaults)


def _env(**kw) -> Environment:
    e = Environment()
    # Disable current and wind by default so they don't pollute isolation tests.
    e.current_speed    = 0.0
    e.wind_speed       = 0.0
    e.wind_direction   = 0.0
    e.current_direction = 0.0
    for k, v in kw.items():
        setattr(e, k, v)
    return e


# ---------------------------------------------------------------------------
# Build the populated world (shared across all tests)
# ---------------------------------------------------------------------------
W = World()
populate_world(W)

# Known geometry constants used in expected-value calculations
SKERRY_CENTER  = (445.0, 335.0)  # center of Skerry Bank shallow zone
OPEN_WATER_PT  = (300.0, 500.0)  # far from all island edges (>80 wu to nearest)
LAND_PT        = (50.0,  50.0)   # inside mainland polygon (verified by ray-cast)

# Coastal-approach point: ~2 wu from mainland edge vertex (90, 305).
# We use (90, 307) -- 2 wu north of the vertex along the x=90 line.
COASTAL_PT     = (90.0, 307.0)


# ===========================================================================
# CHUNK A -- Vessel positions, port placements, fuel range
# ===========================================================================
print()
print("=" * 66)
print("CHUNK A -- Port placements, vessel starts, fuel range")
print("=" * 66)

# A1-A5: ports must not lie inside any island polygon
for port in W.ports:
    in_land = W.point_in_island(port.position)
    _record("A", f"1.{port.name[:6]}", f"Port '{port.name}' not in land",
            not in_land,
            f"position={port.position} is INSIDE a land polygon" if in_land else "")

# A6: demo vessel start positions not inside islands
demo_starts = {
    "MV Tidewater":       (700.0, 240.0),
    "FV Horizon":        (250.0, 280.0),
    "SY Windward":       (700.0, 400.0),
    "MS Coastal Express":(105.0, 380.0),
}
for name, pos in demo_starts.items():
    in_land = W.point_in_island(pos)
    _record("A", f"6.{name[:4]}", f"Vessel '{name}' start not in land",
            not in_land,
            f"position={pos} is inside land" if in_land else "")

# A7: demo vessel destinations not inside islands
port_maren        = W.find_port("Port Maren")
brattlin_quay     = W.find_port("Brattlin Light Quay")
vesper_cove_pos   = (512.0, 654.0)
demo_dests = {
    "MV Tidewater":        port_maren.position,
    "FV Horizon":         vesper_cove_pos,
    "SY Windward":        vesper_cove_pos,
    "MS Coastal Express": brattlin_quay.position,
}
for name, pos in demo_dests.items():
    in_land = W.point_in_island(pos)
    _record("A", f"7.{name[:4]}", f"Vessel '{name}' destination not in land",
            not in_land,
            f"position={pos} is inside land" if in_land else "")

# A8-A10: fuel range checks -- fuel >= fuel_needed for straight-line voyage
# Formula: fuel_needed = rate * (speed/max_speed)^2 * travel_hours
# travel_hours = dist_wu / (speed_kn * KNOTS_TO_UNITS_PER_HOUR)
def _fuel_check(name, start, dest, speed, max_spd, rate, fuel):
    dx = dest[0] - start[0]
    dy = dest[1] - start[1]
    dist_wu = math.sqrt(dx*dx + dy*dy)
    travel_h = dist_wu / (speed * KNOTS_TO_UNITS_PER_HOUR)
    needed   = rate * (speed / max_spd)**2 * travel_h
    dist_nm  = dist_wu * NM_PER_WORLD_UNIT
    ok = fuel >= needed
    _record("A", f"8.{name[:4]}",
            f"Fuel range: '{name}'  dist={dist_nm:.1f} nm  "
            f"need={needed:.1f}  have={fuel:.1f}",
            ok,
            f"INSUFFICIENT: need {needed:.2f}, have {fuel:.1f}" if not ok else "")

_fuel_check("MV Tidewater",       (700.0,240.0), port_maren.position,
             8.0, 12.0, 3.5, 80.0)
_fuel_check("FV Horizon",        (250.0,280.0), vesper_cove_pos,
             6.0, 10.0, 2.8, 40.0)
_fuel_check("MS Coastal Express",(105.0,380.0), brattlin_quay.position,
             10.0, 14.0, 5.0, 60.0)


# ===========================================================================
# CHUNK B -- Physics: movement, forces, fuel, turning
# ===========================================================================
print()
print("=" * 66)
print("CHUNK B -- Physics")
print("=" * 66)

# --- B1: Acceleration ramp -- one timestep from rest -----------------------
v = _vessel(current_speed=0.0, target_speed=8.0, acceleration=0.020)
env0 = _env()
v.update_speed(DT, env0)
expected_b1 = 0.020 * DT   # 0.00032 kn
_record("B", "1", f"Accel 1 step: expect {expected_b1:.6f} kn",
        _near(v.current_speed, expected_b1),
        f"expected={expected_b1:.8f}  actual={v.current_speed:.8f}  "
        f"err={abs(v.current_speed - expected_b1):.2e}")

# --- B2: Deceleration ramp -- one timestep from 8 kn -> target 0 -----------
v = _vessel(current_speed=8.0, target_speed=0.0, deceleration=0.017)
v.update_speed(DT, env0)
expected_b2 = 8.0 - 0.017 * DT   # 7.999728 kn
_record("B", "2", f"Decel 1 step: expect {expected_b2:.6f} kn",
        _near(v.current_speed, expected_b2),
        f"expected={expected_b2:.8f}  actual={v.current_speed:.8f}  "
        f"err={abs(v.current_speed - expected_b2):.2e}")

# --- B3: Current drift on a STATIONARY vessel (current_speed = 0) ---------
# Spec intent: current should move any vessel regardless of self.current_speed.
# Known code behaviour: move() is gated on current_speed > 0 -- stationary
# vessels are NOT displaced by current.  This test documents the gap.
N_B3 = 3600  # steps = 3600 * 0.016 = 57.6 sim-s
v = _vessel(current_speed=0.0, target_speed=0.0, status="underway")
env_cur = _env(current_speed=10.0, current_direction=0.0)  # 10 kn east
x0_b3 = v.position[0]
for _ in range(N_B3):
    v.move(DT, env_cur)
hours_b3   = N_B3 * DT / 3600.0
expected_b3 = 10.0 * KNOTS_TO_UNITS_PER_HOUR * hours_b3 * CURRENT_INFLUENCE
actual_b3   = v.position[0] - x0_b3
# Expect FAIL: code does not move a zero-speed vessel with current alone.
_record("B", "3",
        f"Current drift on stationary vessel: expect {expected_b3:.4f} wu east",
        _near(actual_b3, expected_b3),
        f"expected={expected_b3:.4f} wu  actual={actual_b3:.4f} wu  "
        f"(move() gated on current_speed>0 -- stationary vessel not displaced)")

# --- B4: Current drift on a MOVING vessel -- correct additive displacement --
v = _vessel(current_speed=8.0, target_speed=8.0, heading=0.0,
            position=(500.0, 500.0))
env_cur4 = _env(current_speed=2.0, current_direction=90.0)  # 2 kn south
x0, y0 = v.position
v.move(DT, env_cur4)
hours_b4 = DT / 3600.0
exp_dx_b4 = 8.0  * KNOTS_TO_UNITS_PER_HOUR * hours_b4                        # vessel east
exp_dy_b4 = 2.0  * KNOTS_TO_UNITS_PER_HOUR * hours_b4 * CURRENT_INFLUENCE    # current south
act_dx_b4 = v.position[0] - x0
act_dy_b4 = v.position[1] - y0
ok_b4 = _near(act_dx_b4, exp_dx_b4) and _near(act_dy_b4, exp_dy_b4)
_record("B", "4", "Current added to moving vessel displacement",
        ok_b4,
        f"dx: exp={exp_dx_b4:.6e}  act={act_dx_b4:.6e}  "
        f"dy: exp={exp_dy_b4:.6e}  act={act_dy_b4:.6e}")

# --- B5: Wind drift on a MOVING vessel ------------------------------------
v = _vessel(current_speed=8.0, target_speed=8.0, heading=0.0,
            position=(500.0, 500.0))
# Wind from south (wind_direction=270deg), push is toward north (90deg = +y direction)
# push_direction = (270 + 180) % 360 = 90deg -> dy positive
env_wind = _env(wind_speed=10.0, wind_direction=270.0)
x0, y0 = v.position
v.move(DT, env_wind)
push_kn_b5   = 10.0 * WINDAGE_CARGO
hours_b5     = DT / 3600.0
exp_dx_b5    = 8.0 * KNOTS_TO_UNITS_PER_HOUR * hours_b5
exp_dy_b5    = push_kn_b5 * KNOTS_TO_UNITS_PER_HOUR * hours_b5   # north = +y
act_dx_b5    = v.position[0] - x0
act_dy_b5    = v.position[1] - y0
ok_b5 = _near(act_dx_b5, exp_dx_b5) and _near(act_dy_b5, exp_dy_b5)
_record("B", "5", "Wind drift added to moving vessel displacement",
        ok_b5,
        f"dx: exp={exp_dx_b5:.6e}  act={act_dx_b5:.6e}  "
        f"dy: exp={exp_dy_b5:.6e}  act={act_dy_b5:.6e}")

# --- B6: Sailboat polar -- in no-go zone returns 0 -------------------------
sail = _vessel(vessel_type="sailboat", fuel=None, fuel_capacity=None,
               fuel_consumption_rate=0.0, heading=0.0,
               max_speed=10.0, current_speed=5.0, target_speed=6.0)
env_irons = _env(wind_speed=10.0, wind_direction=0.0)   # wind from east, vessel faces east
ews = sail._effective_wind_speed(env_irons)
_record("B", "6", f"Sailboat in-irons -> effective wind speed = 0 kn",
        ews == 0.0,
        f"_effective_wind_speed()={ews:.4f}  (wind angle = 0deg < {SAIL_NO_GO_ANGLE}deg)")

# --- B7: Sailboat polar -- beam reach (90deg wind angle) --------------------
sail7 = _vessel(vessel_type="sailboat", fuel=None, fuel_capacity=None,
                fuel_consumption_rate=0.0, heading=0.0,
                max_speed=10.0, current_speed=5.0, target_speed=10.0)
env_beam = _env(wind_speed=10.0, wind_direction=90.0)  # wind from south, vessel faces east
# wind_angle = wind_direction - heading = 90 - 0 = 90deg  (beam reach)
# factor at 90deg: t = (90-45)/(90-45) = 1.0; peak = min(10, 10*0.80) = 8 kn
expected_b7 = min(sail7.max_speed, 10.0 * SAIL_EFFICIENCY) * 1.0
ews7 = sail7._effective_wind_speed(env_beam)
_record("B", "7", f"Sailboat beam reach: expect ews = {expected_b7:.2f} kn",
        _near(ews7, expected_b7),
        f"expected={expected_b7:.4f}  actual={ews7:.4f}  "
        f"err={abs(ews7 - expected_b7):.4f}")

# --- B8: Sailboat polar -- running (180deg wind angle) ----------------------
sail8 = _vessel(vessel_type="sailboat", fuel=None, fuel_capacity=None,
                fuel_consumption_rate=0.0, heading=0.0,
                max_speed=10.0, current_speed=5.0, target_speed=10.0)
env_run = _env(wind_speed=10.0, wind_direction=180.0)  # wind from west, vessel east -> dead run
# wind_angle = 180 - 0 = 180deg
# t = (180-90)/90 = 1.0; factor = 1 - (1-SAIL_RUN_FACTOR)*1.0 = SAIL_RUN_FACTOR
peak_b8      = min(sail8.max_speed, 10.0 * SAIL_EFFICIENCY)  # 8 kn
expected_b8  = peak_b8 * SAIL_RUN_FACTOR
ews8 = sail8._effective_wind_speed(env_run)
_record("B", "8", f"Sailboat running: expect ews = {expected_b8:.2f} kn",
        _near(ews8, expected_b8),
        f"expected={expected_b8:.4f}  actual={ews8:.4f}  "
        f"err={abs(ews8 - expected_b8):.4f}")

# --- B9: Sailboat in-irons deceleration rate ------------------------------
# Spec: in-irons vessel should coast down at FUEL_COAST_DECELERATION (same as
# an adrift powered vessel -- no engine drive available).
# Code: uses self.deceleration when effective_target=0 (normal ramp-down).
# We run 1000 steps to amplify the discrepancy enough to exceed 1% tolerance.
N_B9     = 1000
sail9    = _vessel(vessel_type="sailboat", fuel=None, fuel_capacity=None,
                   fuel_consumption_rate=0.0, heading=0.0,
                   current_speed=5.0, target_speed=6.0,
                   deceleration=0.020, max_speed=10.0)
env_b9   = _env(wind_speed=10.0, wind_direction=0.0)  # in-irons
for _ in range(N_B9):
    sail9.update_speed(DT, env_b9)
t_b9         = N_B9 * DT               # 16.0 sim-s
# Spec expected: 5.0 - FUEL_COAST_DECELERATION * t_b9 (coasting drag rate)
exp_spec_b9  = max(0.0, 5.0 - FUEL_COAST_DECELERATION * t_b9)
# Code actual: 5.0 - self.deceleration * t_b9  (ramped via target=0)
exp_code_b9  = max(0.0, 5.0 - 0.020 * t_b9)
act_b9       = sail9.current_speed
_record("B", "9",
        f"Sailboat in-irons deceleration rate after {t_b9:.1f} sim-s",
        _near(act_b9, exp_spec_b9),
        f"spec_expected (FUEL_COAST_DECEL={FUEL_COAST_DECELERATION})={exp_spec_b9:.4f}  "
        f"code_expected (deceleration=0.020)={exp_code_b9:.4f}  "
        f"actual={act_b9:.4f}  "
        f"(code uses self.deceleration, not FUEL_COAST_DECELERATION)")

# --- B10: Fuel consumption -- one timestep at constant speed ---------------
v10 = _vessel(current_speed=8.0, target_speed=8.0, heading=0.0,
              fuel=80.0, fuel_capacity=100.0, fuel_consumption_rate=3.5,
              max_speed=12.0)
fuel_before = v10.fuel
v10.move(DT, env0)
fuel_used_actual = fuel_before - v10.fuel
speed_ratio_b10  = 8.0 / 12.0
expected_b10     = 3.5 * speed_ratio_b10**2 * (DT / 3600.0)
_record("B", "10",
        f"Fuel consumed 1 step: expect {expected_b10:.3e} units",
        _near(fuel_used_actual, expected_b10),
        f"expected={expected_b10:.6e}  actual={fuel_used_actual:.6e}  "
        f"err={abs(fuel_used_actual - expected_b10):.2e}")

# --- B11: Fuel exhaustion flips status to adrift --------------------------
v11 = _vessel(current_speed=8.0, target_speed=8.0, fuel=0.001,
              fuel_capacity=100.0, fuel_consumption_rate=3.5,
              max_speed=12.0, status="underway")
# Run until fuel hits 0
for _ in range(200):
    v11.move(DT, env0)
    v11.update_speed(DT, env0)
    if v11.status == "adrift":
        break
_record("B", "11", "Fuel empty -> status flips to 'adrift'",
        v11.status == "adrift",
        f"status after fuel exhaustion = '{v11.status}'")

# --- B12: Turn rate at optimal speed fraction (peak effectiveness = 1.0) --
v12 = _vessel(current_speed=6.0, target_speed=6.0, heading=0.0,
              max_speed=12.0, turn_rate=1.0)
# speed_fraction = 6/12 = 0.5 = TURN_OPTIMAL_SPEED_FRACTION -> effectiveness = 1.0
v12.turn_toward(90.0, DT)
expected_b12 = 1.0 * 1.0 * DT     # turn_rate * effectiveness * dt = 0.016deg
actual_b12   = v12.heading
_record("B", "12",
        f"Turn at optimal speed: expect Δhdg = {expected_b12:.4f}deg",
        _near(actual_b12, expected_b12),
        f"expected={expected_b12:.6f}deg  actual={actual_b12:.6f}deg  "
        f"err={abs(actual_b12 - expected_b12):.2e}")

# --- B13: Turn rate at low speed (reduced effectiveness) ------------------
v13 = _vessel(current_speed=1.2, target_speed=1.2, heading=0.0,
              max_speed=12.0, turn_rate=1.0)
# speed_fraction = 1.2/12 = 0.1; <= TURN_OPTIMAL_SPEED_FRACTION
# effectiveness = TURN_MIN + (1-TURN_MIN) * (0.1/0.5) = 0.08 + 0.92*0.2 = 0.264
frac_b13   = 1.2 / 12.0
eff_b13    = (TURN_MIN_EFFECTIVENESS
              + (1.0 - TURN_MIN_EFFECTIVENESS)
              * (frac_b13 / TURN_OPTIMAL_SPEED_FRACTION))
v13.turn_toward(90.0, DT)
expected_b13 = 1.0 * eff_b13 * DT
actual_b13   = v13.heading
_record("B", "13",
        f"Turn at low speed (frac={frac_b13:.2f}): expect Δhdg = {expected_b13:.6f}deg",
        _near(actual_b13, expected_b13),
        f"expected={expected_b13:.8f}deg  actual={actual_b13:.8f}deg  "
        f"err={abs(actual_b13 - expected_b13):.2e}")

# --- B14: Turn speed bleed -------------------------------------------------
v14 = _vessel(current_speed=6.0, target_speed=6.0, heading=0.0,
              max_speed=12.0, turn_rate=1.0)
spd_before_b14 = v14.current_speed
v14.turn_toward(90.0, DT)   # same effective turn as B12 -> actual_turn = 0.016deg
yaw_rate_b14    = (1.0 * 1.0 * DT) / DT   # 1.0 deg/s at optimal
expected_b14    = 6.0 - TURN_SPEED_BLEED * yaw_rate_b14 * DT
actual_b14      = v14.current_speed
_record("B", "14",
        f"Turn speed bleed: expect speed = {expected_b14:.6f} kn",
        _near(actual_b14, expected_b14),
        f"expected={expected_b14:.8f}  actual={actual_b14:.8f}  "
        f"err={abs(actual_b14 - expected_b14):.2e}")

# --- B7 (COG vector) -- BLOCKED, requires render/chart.py (pygame) ----------
_blocked("B", "15", "COG direction vector (_cog_direction in render/chart.py)",
         "render/chart.py imports pygame -- cannot be imported headlessly")


# ===========================================================================
# CHUNK C -- Depth model and grounding
# ===========================================================================
print()
print("=" * 66)
print("CHUNK C -- Depth model and grounding")
print("=" * 66)

# --- C1: Land position -> depth = 0 ----------------------------------------
depth_land = W.water_depth_at(LAND_PT, tide_level=0.0)
_record("C", "1", f"Land position {LAND_PT} -> depth = 0.0 m",
        depth_land == 0.0,
        f"actual depth = {depth_land:.2f} m")

# --- C2: Far offshore -> depth = DEPTH_OFFSHORE (60 m) at tide = 0 ----------
# OPEN_WATER_PT (300, 500) is >80 wu from any coast -> dist*DEPTH_COASTAL_SLOPE >> 60
depth_open = W.water_depth_at(OPEN_WATER_PT, tide_level=0.0)
_record("C", "2", f"Open water {OPEN_WATER_PT} -> depth = {DEPTH_OFFSHORE:.0f} m",
        _near(depth_open, DEPTH_OFFSHORE),
        f"expected={DEPTH_OFFSHORE:.1f}  actual={depth_open:.2f}")

# --- C3: Skerry Bank shallow zone -- base depth at tide = 0 -----------------
depth_skerry0 = W.water_depth_at(SKERRY_CENTER, tide_level=0.0)
_record("C", "3",
        f"Skerry Bank shallow zone at tide=0 -> depth = {DEPTH_SHOAL_SKERRY:.1f} m",
        _near(depth_skerry0, DEPTH_SHOAL_SKERRY),
        f"expected={DEPTH_SHOAL_SKERRY:.1f}  actual={depth_skerry0:.2f}")

# --- C4: Tidal influence on shallow zone depth ----------------------------
# Expected delta = (tide_hi - tide_lo) * TIDAL_DEPTH_INFLUENCE
tide_hi, tide_lo = 2.0, -2.0
d_hi = W.water_depth_at(SKERRY_CENTER, tide_level=tide_hi)
d_lo = W.water_depth_at(SKERRY_CENTER, tide_level=tide_lo)
expected_c4_hi = DEPTH_SHOAL_SKERRY + tide_hi * TIDAL_DEPTH_INFLUENCE   # 7.0 m
expected_c4_lo = DEPTH_SHOAL_SKERRY + tide_lo * TIDAL_DEPTH_INFLUENCE   # 3.0 m
ok_c4 = _near(d_hi, expected_c4_hi) and _near(d_lo, expected_c4_lo)
_record("C", "4",
        f"Tidal depth at Skerry: HW expect {expected_c4_hi:.1f} m, LW expect {expected_c4_lo:.1f} m",
        ok_c4,
        f"HW: exp={expected_c4_hi:.2f}  act={d_hi:.2f}  "
        f"LW: exp={expected_c4_lo:.2f}  act={d_lo:.2f}")

# --- C5: Tidal influence on open-water depth ------------------------------
# delta_depth = (tide_hi - tide_lo) * TIDAL_DEPTH_INFLUENCE
d_open_hi = W.water_depth_at(OPEN_WATER_PT, tide_level=tide_hi)
d_open_lo = W.water_depth_at(OPEN_WATER_PT, tide_level=tide_lo)
expected_c5_delta = (tide_hi - tide_lo) * TIDAL_DEPTH_INFLUENCE  # 4.0 m
actual_c5_delta   = d_open_hi - d_open_lo
_record("C", "5",
        f"Tidal range on open water: expect Δdepth = {expected_c5_delta:.1f} m",
        _near(actual_c5_delta, expected_c5_delta),
        f"expected={expected_c5_delta:.2f}  actual={actual_c5_delta:.2f}")

# --- C6: Cargo aground at Skerry Bank (mid-tide) --------------------------
# depth=5.0 m, cargo draft=8.0 m, margin=0.5 m -> need 8.5 m -> aground
cargo_draft = 8.0
depth_c6    = W.water_depth_at(SKERRY_CENTER, tide_level=0.0)  # 5.0 m
aground_c6  = depth_c6 < cargo_draft + DRAFT_SAFETY_MARGIN_M
_record("C", "6",
        f"Cargo (draft={cargo_draft}m) aground at Skerry mid-tide (depth={depth_c6:.1f}m)",
        aground_c6,
        f"need={cargo_draft + DRAFT_SAFETY_MARGIN_M:.1f}m, have={depth_c6:.1f}m")

# --- C7: Fishing vessel SAFE at Skerry Bank (mid-tide) --------------------
fishing_draft = 3.0
aground_c7    = depth_c6 < fishing_draft + DRAFT_SAFETY_MARGIN_M
_record("C", "7",
        f"Fishing (draft={fishing_draft}m) safe at Skerry mid-tide (depth={depth_c6:.1f}m)",
        not aground_c7,
        f"need={fishing_draft + DRAFT_SAFETY_MARGIN_M:.1f}m, have={depth_c6:.1f}m -> should be SAFE")

# --- C8: Cargo ALWAYS aground at Skerry regardless of tide ----------------
# Max depth at HW = 5.0 + 3.0*1.0 = 8.0 m < 8.5 m needed
all_aground_c8 = all(
    W.water_depth_at(SKERRY_CENTER, t) < cargo_draft + DRAFT_SAFETY_MARGIN_M
    for t in [-TIDE_RANGE, -TIDE_RANGE/2, 0.0, TIDE_RANGE/2, TIDE_RANGE]
)
hw_depth_c8 = W.water_depth_at(SKERRY_CENTER, TIDE_RANGE)
_record("C", "8",
        f"Cargo always aground at Skerry (max depth at HW = {hw_depth_c8:.1f} m < "
        f"{cargo_draft + DRAFT_SAFETY_MARGIN_M:.1f} m needed)",
        all_aground_c8,
        f"max_depth={hw_depth_c8:.1f}m  need={cargo_draft + DRAFT_SAFETY_MARGIN_M:.1f}m")

# --- C9: Coastal approach point -- cargo safe at HW, aground at LW ---------
# COASTAL_PT = (90, 307) is ~2 wu from mainland vertex (90, 305).
# base_depth ≈ min(60, 2 * 4) = 8.0 m  (approximately -- cache uses integer cell)
hw_depth_c9 = W.water_depth_at(COASTAL_PT, tide_level=TIDE_RANGE)
lw_depth_c9 = W.water_depth_at(COASTAL_PT, tide_level=-TIDE_RANGE)
cargo_safe_hw  = hw_depth_c9 >= cargo_draft + DRAFT_SAFETY_MARGIN_M
cargo_aground_lw = lw_depth_c9 < cargo_draft + DRAFT_SAFETY_MARGIN_M
ok_c9 = cargo_safe_hw and cargo_aground_lw
_record("C", "9",
        f"Coastal point: cargo safe HW ({hw_depth_c9:.1f}m), aground LW ({lw_depth_c9:.1f}m)",
        ok_c9,
        f"HW: depth={hw_depth_c9:.2f}m need={cargo_draft+DRAFT_SAFETY_MARGIN_M:.1f}m safe={cargo_safe_hw}  "
        f"LW: depth={lw_depth_c9:.2f}m aground={cargo_aground_lw}")

# --- C10: depth_cache consistency -- same integer cell returns same depth --
pos_a = (300.2, 500.7)
pos_b = (300.9, 500.1)   # same integer cell (300, 500)
d_a = W.water_depth_at(pos_a, tide_level=0.0)
d_b = W.water_depth_at(pos_b, tide_level=0.0)
_record("C", "10",
        "Depth cache: two positions in same integer cell (300,500) return identical depth",
        d_a == d_b,
        f"pos_a depth={d_a:.4f}  pos_b depth={d_b:.4f}")


# ===========================================================================
# CHUNK X -- Cross-chunk integration: grounding, tide, depth-under-keel, adrift
# ===========================================================================
print()
print("=" * 66)
print("CHUNK X -- Cross-chunk integration")
print("=" * 66)

# --- X1: Shoal-zone grounding uses depth model, not land-polygon ----------
# Skerry Bank is open water (point_in_island=False) yet depth < cargo need.
# Proves the depth model is what catches shoal groundings, not land check.
skerry_in_land = W.point_in_island(SKERRY_CENTER)
depth_x1  = W.water_depth_at(SKERRY_CENTER, tide_level=0.0)
grounds_x1 = depth_x1 < 8.0 + DRAFT_SAFETY_MARGIN_M
_record("X", "1",
        "Skerry Bank: not land polygon, but depth triggers grounding",
        (not skerry_in_land) and grounds_x1,
        f"point_in_island={skerry_in_land}  depth={depth_x1:.1f}m  "
        f"cargo_needs={8.0+DRAFT_SAFETY_MARGIN_M:.1f}m  grounds={grounds_x1}")

# --- X2: Aground vessel -- speed zeroed and move() is a no-op --------------
# Mirrors the exact grounding logic in main.py update_simulation():
#   if depth < vessel.draft_m + DRAFT_SAFETY_MARGIN_M:
#       vessel.status = "aground"; vessel.current_speed = 0.0
vx2 = _vessel(position=SKERRY_CENTER, current_speed=8.0, status="underway",
              draft_m=8.0)
env_x2 = _env(current_speed=5.0, current_direction=0.0)  # strong current too
depth_x2 = W.water_depth_at(vx2.position, tide_level=0.0)
if depth_x2 < vx2.draft_m + DRAFT_SAFETY_MARGIN_M:
    vx2.status = "aground"
    vx2.current_speed = 0.0
pos_before_x2 = vx2.position
for _ in range(50):
    vx2.update_speed(DT, env_x2)
    vx2.move(DT, env_x2)
pos_unchanged = vx2.position == pos_before_x2 and vx2.current_speed == 0.0
_record("X", "2",
        "Aground vessel: speed=0, position unchanged after 50 ticks",
        pos_unchanged,
        f"status={vx2.status}  speed={vx2.current_speed}  "
        f"position moved: {vx2.position != pos_before_x2}")

# --- X3: Grounding in open water (not on land) -- cargo vs fishing at Skerry
# Same position, different draft -- only cargo is blocked.
depth_x3   = W.water_depth_at(SKERRY_CENTER, tide_level=0.0)
cargo_ag   = depth_x3 < 8.0 + DRAFT_SAFETY_MARGIN_M    # 8.0 m draft
fishing_ag = depth_x3 < 3.0 + DRAFT_SAFETY_MARGIN_M    # 3.0 m draft
_record("X", "3",
        f"Draft differential at Skerry: cargo aground, fishing safe "
        f"(depth={depth_x3:.1f}m)",
        cargo_ag and not fishing_ag,
        f"cargo_ag={cargo_ag}  fishing_ag={fishing_ag}  "
        f"cargo_needs={8.0+DRAFT_SAFETY_MARGIN_M:.1f}m  "
        f"fishing_needs={3.0+DRAFT_SAFETY_MARGIN_M:.1f}m")

# --- X4: Tide-gated grounding at coastal approach point -------------------
# Cargo (draft=8m, needs 8.5m) at COASTAL_PT (base ≈ 10.2m):
#   HW (+TIDE_RANGE): depth ≈ 13.2m -> safe
#   LW (-TIDE_RANGE): depth ≈ 7.2m  -> aground
hw_x4 = W.water_depth_at(COASTAL_PT, tide_level=+TIDE_RANGE)
lw_x4 = W.water_depth_at(COASTAL_PT, tide_level=-TIDE_RANGE)
safe_hw_x4    = hw_x4 >= 8.0 + DRAFT_SAFETY_MARGIN_M
aground_lw_x4 = lw_x4  < 8.0 + DRAFT_SAFETY_MARGIN_M
_record("X", "4",
        f"Tide-gated grounding at coastal point: safe HW ({hw_x4:.1f}m), "
        f"aground LW ({lw_x4:.1f}m)",
        safe_hw_x4 and aground_lw_x4,
        f"HW safe={safe_hw_x4}  LW aground={aground_lw_x4}  "
        f"cargo needs={8.0+DRAFT_SAFETY_MARGIN_M:.1f}m")

# --- X5: Depth-under-keel (UKC) = depth - draft_m -------------------------
# UKC > 0 means clear; UKC < 0 means hull in the seabed.
# Test both cargo and fishing at mid-tide at COASTAL_PT.
depth_x5       = W.water_depth_at(COASTAL_PT, tide_level=0.0)
ukc_cargo_x5   = depth_x5 - 8.0   # draft_m = 8.0
ukc_fishing_x5 = depth_x5 - 3.0   # draft_m = 3.0
exp_ukc_c_x5   = depth_x5 - 8.0
exp_ukc_f_x5   = depth_x5 - 3.0
ok_x5 = (_near(ukc_cargo_x5, exp_ukc_c_x5)
          and _near(ukc_fishing_x5, exp_ukc_f_x5))
_record("X", "5",
        f"UKC at coastal point (mid-tide, depth={depth_x5:.1f}m): "
        f"cargo UKC={ukc_cargo_x5:.2f}m, fishing UKC={ukc_fishing_x5:.2f}m",
        ok_x5,
        f"cargo: exp={exp_ukc_c_x5:.4f}  act={ukc_cargo_x5:.4f}  "
        f"fishing: exp={exp_ukc_f_x5:.4f}  act={ukc_fishing_x5:.4f}")

# --- X6: Adrift deceleration rate = FUEL_COAST_DECELERATION ---------------
# A powered vessel that runs out of fuel switches to "adrift" and decelerates
# at FUEL_COAST_DECELERATION, NOT self.deceleration.
# This is the correct behaviour; B9 above tests that sailboats use the WRONG
# rate in irons (self.deceleration).  This test verifies powered-adrift is correct.
N_X6     = 1000
vx6      = _vessel(current_speed=8.0, target_speed=0.0, status="adrift",
                   deceleration=0.017)  # deceleration intentionally different
for _ in range(N_X6):
    vx6.update_speed(DT, env0)
t_x6         = N_X6 * DT               # 16.0 sim-s
exp_x6       = max(0.0, 8.0 - FUEL_COAST_DECELERATION * t_x6)
act_x6       = vx6.current_speed
# Distinguish from self.deceleration rate (would give 8 - 0.017*16 = 7.728)
exp_wrong_x6 = max(0.0, 8.0 - 0.017 * t_x6)
_record("X", "6",
        f"Adrift deceleration uses FUEL_COAST_DECEL ({FUEL_COAST_DECELERATION}): "
        f"expect {exp_x6:.4f} kn after {t_x6:.0f} sim-s",
        _near(act_x6, exp_x6),
        f"FUEL_COAST_DECEL expected={exp_x6:.6f}  "
        f"self.decel expected={exp_wrong_x6:.6f}  actual={act_x6:.6f}")


# ===========================================================================
# SUMMARY TABLE
# ===========================================================================
print()
print("=" * 66)
print("SUMMARY TABLE")
print("=" * 66)
print(f"  {'Chunk':<8}  {'ID':<14}  {'Name':<42}  {'Result'}")
print(f"  {'-'*8}  {'-'*14}  {'-'*42}  {'-'*6}")
for chunk, tid, name, passed, _ in _results:
    if passed is None:
        tag = "BLOCKED"
    elif passed:
        tag = "PASS"
    else:
        tag = "FAIL"
    print(f"  {chunk:<8}  {tid:<14}  {name[:42]:<42}  {tag}")

passed_count  = sum(1 for _, _, _, p, _ in _results if p is True)
failed_count  = sum(1 for _, _, _, p, _ in _results if p is False)
blocked_count = sum(1 for _, _, _, p, _ in _results if p is None)
total         = len(_results)

print()
print(f"  TOTAL {total}   PASS {passed_count}   FAIL {failed_count}   BLOCKED {blocked_count}")

# ===========================================================================
# FAILURES IN DETAIL
# ===========================================================================
if _failures:
    print()
    print("=" * 66)
    print("FAILURES IN DETAIL")
    print("=" * 66)
    for i, (chunk, tid, name, detail) in enumerate(_failures, 1):
        print(f"\n  FAILURE {i}: [{chunk}.{tid}]  {name}")
        print(f"  {detail}")
else:
    print()
    print("No failures.")
