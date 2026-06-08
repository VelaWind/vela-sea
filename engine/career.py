"""Career system: wallet, reputation, and job board for the player vessel.

Pure Python — no Pygame imports. All state lives here; render/panels.py reads it.
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Optional

from config import (
    PLAYER_STARTING_MONEY, PLAYER_STARTING_REPUTATION,
    HULL_REPAIR_COST_PER_POINT, CONTRACT_PENALTY,
    NM_PER_WORLD_UNIT,
)


@dataclass
class Contract:
    """A single job available on or accepted from the job board."""
    contract_id: str
    job_type: str               # "delivery" | "rescue_assist" | "patrol"
    from_port: str
    to_port: str
    payout: float
    deadline_sim_hours: float
    reputation_required: int
    status: str = "available"   # "available" | "active" | "completed" | "failed"
    accepted_at_sim_s: float = 0.0


# (job_type, payout_rate_per_nm, reputation_required)
_CONTRACT_TEMPLATES = [
    ("delivery",      80.0,  0),
    ("delivery",      80.0,  0),   # weighted: delivery is most common
    ("rescue_assist", 150.0, 10),
    ("patrol",        60.0,  25),
]


class PlayerCareer:
    """Persistent career state: money, reputation, and cumulative statistics."""

    def __init__(self) -> None:
        self.money: float = PLAYER_STARTING_MONEY
        self.reputation: int = PLAYER_STARTING_REPUTATION
        self.total_deliveries: int = 0
        self.total_distance_nm: float = 0.0
        self.fines_paid: float = 0.0
        self.hull_repairs_paid: float = 0.0
        self._history: List[str] = []   # capped at 20 entries

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

    def add_reputation(self, delta: int) -> None:
        self.reputation = max(0, min(100, self.reputation + delta))

    def _record(self, text: str) -> None:
        self._history.append(text)
        if len(self._history) > 20:
            self._history.pop(0)


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
        port_names = [p.name for p in world.ports]
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
        career.spend(CONTRACT_PENALTY, f"Missed deadline {c.contract_id}")
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
        deadline_hours = random.randint(4, 12)

        return Contract(
            contract_id=cid,
            job_type=job_type,
            from_port=from_port,
            to_port=to_port,
            payout=float(payout),
            deadline_sim_hours=float(deadline_hours),
            reputation_required=rep_req,
        )
