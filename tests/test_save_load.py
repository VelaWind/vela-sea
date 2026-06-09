"""Headless round-trip tests for the career save/load system.

Pure engine — no pygame, no window.  Uses a temp directory so the real
save.json in the repo root is never touched.
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import json

from engine.career import PlayerCareer, save_career, load_career, delete_save
from config import GAME_VERSION


def _make_career() -> PlayerCareer:
    c = PlayerCareer()
    c.money             = 12345.67
    c.reputation        = 42
    c.total_deliveries  = 9
    c.total_distance_nm = 318.25
    c.fines_paid        = 650.0
    c.hull_repairs_paid = 1200.0
    return c


def test_round_trip_exact(tmp_path):
    """Save known values and load them back — every field must match exactly."""
    path = str(tmp_path / "save.json")
    career = _make_career()
    save_career(career, filepath=path, hull_integrity=0.85)

    data = load_career(filepath=path)
    assert data is not None
    assert data["version"]           == GAME_VERSION
    assert data["money"]             == 12345.67
    assert data["reputation"]        == 42
    assert data["total_deliveries"]  == 9
    assert data["total_distance_nm"] == 318.25
    assert data["fines_paid"]        == 650.0
    assert data["hull_repairs_paid"] == 1200.0
    assert data["hull_integrity"]    == 0.85


def test_load_missing_file_returns_none(tmp_path):
    assert load_career(filepath=str(tmp_path / "nope.json")) is None


def test_load_corrupt_file_returns_none(tmp_path):
    path = tmp_path / "save.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert load_career(filepath=str(path)) is None


def test_load_wrong_version_returns_none(tmp_path):
    path = tmp_path / "save.json"
    career = _make_career()
    save_career(career, filepath=str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = "0.0.1"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_career(filepath=str(path)) is None


def test_load_missing_field_returns_none(tmp_path):
    path = tmp_path / "save.json"
    career = _make_career()
    save_career(career, filepath=str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["money"]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_career(filepath=str(path)) is None


def test_delete_save(tmp_path):
    path = str(tmp_path / "save.json")
    save_career(_make_career(), filepath=path)
    assert os.path.exists(path)
    delete_save(filepath=path)
    assert not os.path.exists(path)
    # Deleting an already-missing file must not raise.
    delete_save(filepath=path)
