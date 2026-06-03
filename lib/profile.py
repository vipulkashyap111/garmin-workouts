"""Fitness profile management — goals, training plan, and progress check-ins.

Data lives outside the public repo. Resolution order for the profile directory:
  1. GARMIN_WORKOUTS_PROFILE env var
  2. ./profile/ in the current working directory (dev override)
  3. ~/.garmin-workouts/profile/ (default user home location)
"""

import json
import os
from datetime import datetime
from pathlib import Path


def _resolve_profile_dir() -> Path:
    env = os.getenv("GARMIN_WORKOUTS_PROFILE")
    if env:
        return Path(env).expanduser()
    local = Path.cwd() / "profile"
    if local.exists():
        return local
    return Path.home() / ".garmin-workouts" / "profile"


PROFILE_DIR = _resolve_profile_dir()


def _ensure_dir() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)


def _load(filename: str) -> dict:
    path = PROFILE_DIR / filename
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(filename: str, data: dict) -> None:
    _ensure_dir()
    path = PROFILE_DIR / filename
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# --- Goals ---

def get_goals() -> dict:
    return _load("goals.json")


def set_goals(short_term: list[dict] = None, long_term: list[dict] = None) -> dict:
    goals = get_goals()
    if short_term is not None:
        goals["shortTerm"] = short_term
    if long_term is not None:
        goals["longTerm"] = long_term
    goals["updatedAt"] = datetime.now().isoformat()
    _save("goals.json", goals)
    return goals


# --- Training Plan ---

def get_plan() -> dict:
    return _load("plan.json")


def set_plan(plan: dict) -> dict:
    plan["updatedAt"] = datetime.now().isoformat()
    _save("plan.json", plan)
    return plan


# --- Check-ins ---

def get_checkins(limit: int = 10) -> list[dict]:
    data = _load("checkins.json")
    checkins = data.get("checkins", [])
    return checkins[-limit:]


def add_checkin(summary: str, metrics: dict = None, notes: str = "") -> dict:
    data = _load("checkins.json")
    checkins = data.get("checkins", [])
    entry = {
        "date": datetime.now().isoformat(),
        "summary": summary,
        "metrics": metrics or {},
        "notes": notes,
    }
    checkins.append(entry)
    _save("checkins.json", {"checkins": checkins})
    return entry
