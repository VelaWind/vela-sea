"""Career system: wallet, reputation, and job board for the player vessel.

Pure Python — no Pygame imports. All state lives here; render/panels.py reads it.
"""

import json
import math
import os
import random
from dataclasses import dataclass, field
from typing import List, Optional

from config import (
    PLAYER_STARTING_MONEY, PLAYER_STARTING_REPUTATION,
    HULL_REPAIR_COST_PER_POINT, CONTRACT_PENALTY,
    NM_PER_WORLD_UNIT,
    GAME_VERSION, SAVE_FILEPATH,
    HAZMAT_RATE_MULT, HAZMAT_REP_REQUIRED, HAZMAT_DEADLINE_RANGE_H,
    CHARTER_RATE_PER_NM, CHARTER_DEADLINE_RANGE_H,
    CONTRACT_DEADLINE_RANGE_H,
    REP_TIER_2, REP_TIER_4, REP_TIER_TABLE, VIP_CHARTER_RATE_MULT,
)


@dataclass
class Contract:
    """A single job available on or accepted from the job board."""
    contract_id: str
    job_type: str               # "delivery" | "rescue_assist" | "patrol" | "hazmat" | "charter"
    from_port: str
    to_port: str
    payout: float
    deadline_sim_hours: float
    reputation_required: int
    status: str = "available"   # "available" | "active" | "completed" | "failed"
    accepted_at_sim_s: float = 0.0
    description: str = ""       # special-requirement text shown on the panel


# (job_type, payout_rate_per_nm, reputation_required)
_CONTRACT_TEMPLATES = [
    ("delivery",      80.0,  0),
    ("delivery",      80.0,  0),   # weighted: delivery is most common
    ("rescue_assist", 150.0, REP_TIER_2),   # Tier 2 (First Mate) privilege
    ("patrol",        60.0,  25),
    ("hazmat",        80.0 * HAZMAT_RATE_MULT, HAZMAT_REP_REQUIRED),
    ("charter",       CHARTER_RATE_PER_NM, 0),
    ("vip_charter",   80.0 * VIP_CHARTER_RATE_MULT, REP_TIER_4),  # Tier 4 exclusive
]

# Per-type deadline windows (sim-hours); types not listed use the default.
_DEADLINE_RANGES = {
    "hazmat":  HAZMAT_DEADLINE_RANGE_H,
    "charter": CHARTER_DEADLINE_RANGE_H,
}

# Special-requirement text surfaced on the career panel.
_JOB_DESCRIPTIONS = {
    "hazmat":      "Hazardous cargo — avoid restricted zones or double fine",
    "charter":     "Passenger charter — must maintain speed ≤ 10 kn in all zones",
    "vip_charter": "Exclusive VIP charter — Master Mariner clientele only",
}


# Canonical achievement list: (name, how to earn it).  The award logic lives
# in main.py; this table drives the CareerPanel display and the save format.
ACHIEVEMENT_DEFS = [
    ("First Delivery", "Complete 1 contract"),
    ("Storm Sailor",   "Complete a contract during a storm"),
    ("Clean Record",   "Complete 5 contracts with zero fines"),
    ("Lucky Escape",   "Survive grounding with hull > 10%"),
]


def reputation_tier_name(reputation: int) -> str:
    """Map a reputation score to its rank title via the config tier table."""
    for threshold, name in REP_TIER_TABLE:
        if reputation >= threshold:
            return name
    return REP_TIER_TABLE[-1][1]


class PlayerCareer:
    """Persistent career state: money, reputation, and cumulative statistics."""

    def __init__(self) -> None:
        self.money: float = PLAYER_STARTING_MONEY
        self.reputation: int = PLAYER_STARTING_REPUTATION
        self.total_deliveries: int = 0
        self.total_distance_nm: float = 0.0
        self.fines_paid: float = 0.0
        self.hull_repairs_paid: float = 0.0
        self.achievements: set = set()  # unlocked achievement names
        self._history: List[str] = []   # capped at 20 entries

    @property
    def tier_name(self) -> str:
        """Current rank title (Deckhand → Master Mariner)."""
        return reputation_tier_name(self.reputation)

    def earn(self, amount: float, reason: str) -> None:
        self.money += amount
        self._record(f"+£{amount:.0f}  {reason}")

    def spend(self, amount: float, reason: str) -> bool:
        """Deduct amount. Returns False (no-op) when funds are insufficient."""
        if self.money < amount:
            return False
        self.money -= amount
        self._record(f"-£{amount:.0f}  {reason}")
        return True

    def force_spend(self, amount: float, reason: str) -> None:
        """Forcibly deduct amount even if it drives the balance negative.

        Use for mandatory penalties (zone fines, contract penalties) where the
        player cannot simply choose not to pay.
        """
        self.money -= amount
        self._record(f"-£{amount:.0f}  {reason}")

    def add_reputation(self, delta: int) -> None:
        self.reputation = max(0, min(100, self.reputation + delta))

    def _record(self, text: str) -> None:
        self._history.append(text)
        if len(self._history) > 20:
            self._history.pop(0)


# ---------------------------------------------------------------------------
# Save / load — JSON persistence for career state between sessions
# ---------------------------------------------------------------------------

# Every field a valid save must contain.  Checked on load so a truncated or
# hand-edited file is rejected as a whole rather than half-restoring state.
_SAVE_FIELDS = (
    "money", "reputation", "total_deliveries", "total_distance_nm",
    "fines_paid", "hull_repairs_paid", "hull_integrity", "achievements",
)


def save_career(career: "PlayerCareer", filepath: str = SAVE_FILEPATH,
                hull_integrity: float = 1.0) -> None:
    """Write career state (plus the player vessel's hull) to a JSON file.

    hull_integrity is passed in rather than read from a vessel so this module
    stays decoupled from ship.py — the caller owns that relationship.
    """
    data = {
        "version": GAME_VERSION,
        "money": career.money,
        "reputation": career.reputation,
        "total_deliveries": career.total_deliveries,
        "total_distance_nm": career.total_distance_nm,
        "fines_paid": career.fines_paid,
        "hull_repairs_paid": career.hull_repairs_paid,
        "hull_integrity": hull_integrity,
        # Sorted for a stable file diff; restored as a set on load.
        "achievements": sorted(career.achievements),
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_career(filepath: str = SAVE_FILEPATH) -> Optional[dict]:
    """Read a save file. Returns the field dict, or None when the file is
    missing, unparseable, the wrong version, or missing any required field.

    Returning the raw dict (not a PlayerCareer) lets the caller restore both
    the career object and the player vessel's hull in one place.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != GAME_VERSION:
        return None
    if any(k not in data for k in _SAVE_FIELDS):
        return None
    return data


def delete_save(filepath: str = SAVE_FILEPATH) -> None:
    """Remove the save file if present; silently ignore a missing file.

    Called on game over so a lost run cannot be continued.
    """
    try:
        os.remove(filepath)
    except OSError:
        pass


class JobBoard:
    """Maintains up to 4 available contracts; refreshed each time the player docks."""

    SLOT_COUNT = 4

    def __init__(self) -> None:
        self._contracts: List[Contract] = []
        self._id_counter: int = 0
        self._active: Optional[Contract] = None

    # ------------------------------------------------------------------ public

    def refresh_jobs(self, world) -> None:
        """Replace all *available* contracts with fresh ones. The active stays."""
        # Draft-restricted ports (e.g. Kessock Anchorage) are excluded so the
        # board never offers a destination the player's hull can't berth at.
        port_names = [p.name for p in world.ports
                      if getattr(p, "max_draft_m", None) is None]
        if len(port_names) < 2:
            return
        self._contracts = [c for c in self._contracts if c.status == "active"]
        while len(self._contracts) < self.SLOT_COUNT:
            self._contracts.append(self._generate(port_names, world))

    def accept_job(self, contract_id: str, career: "PlayerCareer",
                   sim_elapsed_s: float) -> bool:
        """Mark a contract active. Only one active contract at a time."""
        if self._active is not None:
            return False
        for c in self._contracts:
            if c.contract_id == contract_id and c.status == "available":
                if career.reputation < c.reputation_required:
                    return False
                c.status = "active"
                c.accepted_at_sim_s = sim_elapsed_s
                self._active = c
                return True
        return False

    def complete_job(self, port_name: str, career: "PlayerCareer") -> Optional[Contract]:
        """Call when player docks. Completes active contract if destination matches."""
        if self._active is None:
            return None
        c = self._active
        if c.to_port == port_name:
            c.status = "completed"
            career.earn(c.payout, f"Contract {c.contract_id}")
            career.add_reputation(5)
            career.total_deliveries += 1
            self._active = None
            self._contracts = [x for x in self._contracts if x is not c]
            return c
        return None

    def check_deadline(self, sim_elapsed_s: float) -> Optional[Contract]:
        """Return the active contract if its deadline has passed, else None."""
        if self._active is None:
            return None
        deadline_s = self._active.accepted_at_sim_s + self._active.deadline_sim_hours * 3600.0
        if sim_elapsed_s > deadline_s:
            return self._active
        return None

    def fail_active(self, career: "PlayerCareer") -> Optional[Contract]:
        """Mark active contract failed and apply the penalty."""
        if self._active is None:
            return None
        c = self._active
        c.status = "failed"
        career.force_spend(CONTRACT_PENALTY, f"Missed deadline {c.contract_id}")
        career.add_reputation(-10)
        self._active = None
        self._contracts = [x for x in self._contracts if x is not c]
        return c

    @property
    def active(self) -> Optional[Contract]:
        return self._active

    @property
    def available(self) -> List[Contract]:
        return [c for c in self._contracts if c.status == "available"]

    # ----------------------------------------------------------------- private

    def _generate(self, port_names: List[str], world) -> Contract:
        self._id_counter += 1
        cid = f"C{self._id_counter:04d}"

        job_type, rate, rep_req = random.choice(_CONTRACT_TEMPLATES)
        from_port, to_port = random.sample(port_names, 2)

        fp = next((p for p in world.ports if p.name == from_port), None)
        tp = next((p for p in world.ports if p.name == to_port), None)
        if fp and tp:
            dx = tp.position[0] - fp.position[0]
            dy = tp.position[1] - fp.position[1]
            dist_nm = math.hypot(dx, dy) * NM_PER_WORLD_UNIT
        else:
            dist_nm = 50.0

        payout = round(dist_nm * rate)
        dl_min, dl_max = _DEADLINE_RANGES.get(job_type, CONTRACT_DEADLINE_RANGE_H)
        deadline_hours = random.randint(dl_min, dl_max)

        return Contract(
            contract_id=cid,
            job_type=job_type,
            from_port=from_port,
            to_port=to_port,
            payout=float(payout),
            deadline_sim_hours=float(deadline_hours),
            reputation_required=rep_req,
            description=_JOB_DESCRIPTIONS.get(job_type, ""),
        )
