"""Athletic re-test battery storage — vertical jump, broad jump, shuttle, etc.

Stored as retests.json inside the resolved profile directory (see lib/profile.py).
Manual entry (Garmin can't auto-measure these).
"""

import json
from datetime import datetime
from pathlib import Path

from .profile import PROFILE_DIR

RETESTS_FILE = PROFILE_DIR / "retests.json"

# Canonical test schema. Values stored in their natural units; UI converts if needed.
TEST_DEFINITIONS = {
    "vertical_jump": {"label": "Vertical Jump", "unit": "in", "higher_is_better": True},
    "broad_jump": {"label": "Broad Jump", "unit": "in", "higher_is_better": True},
    "shuttle_5_10_5": {"label": "5-10-5 Pro-Agility Shuttle", "unit": "s", "higher_is_better": False},
    "single_leg_hop_l": {"label": "Single-Leg Hop (Left)", "unit": "in", "higher_is_better": True},
    "single_leg_hop_r": {"label": "Single-Leg Hop (Right)", "unit": "in", "higher_is_better": True},
    "mile_time": {"label": "1-Mile Run", "unit": "mm:ss", "higher_is_better": False},
    "bodyweight_lbs": {"label": "Bodyweight", "unit": "lb", "higher_is_better": None},
}


def _load() -> dict:
    if not RETESTS_FILE.exists():
        return {"retests": []}
    return json.loads(RETESTS_FILE.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    RETESTS_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def add_retest(date: str, results: dict, notes: str = "") -> dict:
    """Add a re-test entry.

    Args:
        date: YYYY-MM-DD
        results: dict of test_key -> value (e.g. {"vertical_jump": 22.5, "shuttle_5_10_5": 5.1})
        notes: free-text notes
    """
    data = _load()
    # Validate test keys
    unknown = [k for k in results if k not in TEST_DEFINITIONS]
    if unknown:
        raise ValueError(f"Unknown test keys: {unknown}. Valid: {list(TEST_DEFINITIONS.keys())}")
    entry = {
        "date": date,
        "results": results,
        "notes": notes,
        "loggedAt": datetime.now().isoformat(),
    }
    data.setdefault("retests", []).append(entry)
    # Keep sorted by date
    data["retests"].sort(key=lambda x: x["date"])
    _save(data)
    return entry


def list_retests() -> list:
    return _load().get("retests", [])


def compare_last_two() -> dict:
    """Compare the two most recent re-tests and report deltas."""
    retests = list_retests()
    if len(retests) < 2:
        return {"error": "Need at least 2 re-tests to compare. Found: " + str(len(retests))}
    prev, curr = retests[-2], retests[-1]
    deltas = {}
    for key, val in curr["results"].items():
        prev_val = prev["results"].get(key)
        if prev_val is None or key not in TEST_DEFINITIONS:
            continue
        # Skip non-numeric (e.g. "mile_time" stored as string)
        try:
            d = float(val) - float(prev_val)
        except (TypeError, ValueError):
            continue
        td = TEST_DEFINITIONS[key]
        improved = None
        if td["higher_is_better"] is True:
            improved = d > 0
        elif td["higher_is_better"] is False:
            improved = d < 0
        deltas[key] = {
            "label": td["label"],
            "unit": td["unit"],
            "previous": prev_val,
            "current": val,
            "delta": round(d, 2),
            "improved": improved,
        }
    return {
        "previous_date": prev["date"],
        "current_date": curr["date"],
        "deltas": deltas,
    }
