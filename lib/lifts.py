"""Strength lift history — pulls per-set data from Garmin activities,
computes top sets and Epley-estimated 1RM per lift, output in lbs.

Garmin stores weights in grams. We convert to lbs throughout.
"""

from datetime import datetime
from collections import defaultdict
from lib.client import _get_api, get_activities

ACTIVITY_API = "https://connect.garmin.com/gc-api/activity-service"

# Categories we treat as trackable strength lifts (others ignored)
TRACKED_CATEGORIES = {
    "BENCH_PRESS",
    "ROW",
    "SHOULDER_PRESS",
    "CURL",
    "TRICEPS_EXTENSION",
    "SQUAT",
    "DEADLIFT",
    "LUNGE",
    "HIP_RAISE",
    "CALF_RAISE",
    "PLYO",          # power output (med ball etc.)
    "LEG_RAISE",
    "PULL_UP",
    "SHRUG",
}

LOWER_BODY_CATS = {"SQUAT", "DEADLIFT", "LUNGE", "HIP_RAISE", "CALF_RAISE"}
UPPER_BODY_CATS = {"BENCH_PRESS", "ROW", "SHOULDER_PRESS", "CURL", "TRICEPS_EXTENSION", "PULL_UP", "SHRUG"}


def grams_to_lbs(g):
    if g is None:
        return None
    return round(g / 1000.0 * 2.20462, 1)


def epley_1rm(weight_lbs, reps):
    """Epley 1RM estimate. Caps at reps>=12 (formula becomes unreliable)."""
    if not weight_lbs or not reps or reps <= 0:
        return None
    if reps > 12:
        return None  # too high-rep for reliable 1RM estimate
    return round(weight_lbs * (1 + reps / 30.0), 1)


def get_exercise_sets(activity_id):
    """Fetch per-set data for a single strength activity."""
    api = _get_api()
    resp = api.get(f"{ACTIVITY_API}/activity/{activity_id}/exerciseSets")
    return resp.get("exerciseSets", []) if isinstance(resp, dict) else []


def extract_top_sets(sets):
    """Given raw exerciseSets, return dict: (category, exercise_name) -> top set.

    Top set = the one with highest Epley 1RM estimate (across all working sets).
    """
    top = {}
    for s in sets:
        if s.get("setType") != "ACTIVE":
            continue
        exercises = s.get("exercises") or []
        if not exercises:
            continue
        # Use highest-probability exercise label
        ex = max(exercises, key=lambda e: e.get("probability") or 0)
        cat = ex.get("category")
        if cat not in TRACKED_CATEGORIES:
            continue
        name = ex.get("name") or cat
        prob = ex.get("probability", 0)
        weight_lbs = grams_to_lbs(s.get("weight"))
        reps = s.get("repetitionCount")
        if reps is None or reps == 0:
            continue
        # Bodyweight (weight=None or 0) handled — skip 1RM calc, but track reps
        e1rm = epley_1rm(weight_lbs, reps) if weight_lbs else None
        key = (cat, name)
        cur = top.get(key)
        if cur is None:
            top[key] = {
                "category": cat,
                "exercise": name,
                "weight_lbs": weight_lbs,
                "reps": reps,
                "e1rm_lbs": e1rm,
                "probability": prob,
                "total_sets": 1,
            }
        else:
            cur["total_sets"] += 1
            # Replace top if new e1rm higher (or current was bodyweight and new has weight)
            if e1rm is not None and (cur["e1rm_lbs"] is None or e1rm > cur["e1rm_lbs"]):
                cur["weight_lbs"] = weight_lbs
                cur["reps"] = reps
                cur["e1rm_lbs"] = e1rm
                cur["probability"] = prob
            elif cur["e1rm_lbs"] is None and weight_lbs is None and reps > cur["reps"]:
                # Bodyweight: track highest reps
                cur["reps"] = reps
    return top


def get_lifts_history(weeks=12, activity_limit=120):
    """Pull strength sessions over the last N weeks and extract top sets.

    Returns:
        {
            "sessions": [ {date, activity_id, name, lifts: {...}} ],
            "lift_timeline": { (cat, name): [ {date, weight_lbs, reps, e1rm_lbs} ] },
            "best_1rm": { (cat, name): {weight_lbs, reps, e1rm_lbs, date} },
        }
    """
    acts = get_activities(limit=activity_limit)
    cutoff_days = weeks * 7
    now = datetime.now()

    strength = []
    for a in acts:
        if (a.get("activityType") or {}).get("typeKey") != "strength_training":
            continue
        start = a.get("startTimeLocal", "")
        if not start:
            continue
        try:
            dt = datetime.fromisoformat(start.replace("Z", ""))
        except (ValueError, TypeError):
            continue
        if (now - dt).days > cutoff_days:
            continue
        strength.append(a)

    sessions = []
    lift_timeline = defaultdict(list)
    best_1rm = {}

    for a in strength:
        try:
            raw_sets = get_exercise_sets(a["activityId"])
        except Exception:
            continue
        top = extract_top_sets(raw_sets)
        if not top:
            continue
        date = a["startTimeLocal"][:10]
        session = {
            "date": date,
            "activity_id": a["activityId"],
            "name": a.get("activityName", ""),
            "lifts": top,
        }
        sessions.append(session)
        for key, d in top.items():
            lift_timeline[key].append({
                "date": date,
                "weight_lbs": d["weight_lbs"],
                "reps": d["reps"],
                "e1rm_lbs": d["e1rm_lbs"],
            })
            cur_best = best_1rm.get(key)
            if d["e1rm_lbs"] is not None and (cur_best is None or d["e1rm_lbs"] > cur_best["e1rm_lbs"]):
                best_1rm[key] = {
                    "weight_lbs": d["weight_lbs"],
                    "reps": d["reps"],
                    "e1rm_lbs": d["e1rm_lbs"],
                    "date": date,
                    "activity_id": a["activityId"],
                }

    # Sort timeline ascending by date
    for k in lift_timeline:
        lift_timeline[k].sort(key=lambda x: x["date"])

    sessions.sort(key=lambda x: x["date"], reverse=True)
    return {
        "sessions": sessions,
        "lift_timeline": dict(lift_timeline),
        "best_1rm": best_1rm,
        "period_weeks": weeks,
    }


def detect_prs(history):
    """Mark sessions where a lift hit a new 1RM-est PR at the time of that session."""
    prs = []
    seen_best = {}
    sessions_asc = sorted(history["sessions"], key=lambda s: s["date"])
    for s in sessions_asc:
        for key, d in s["lifts"].items():
            e = d["e1rm_lbs"]
            if e is None:
                continue
            prev = seen_best.get(key)
            if prev is None or e > prev:
                seen_best[key] = e
                if prev is not None:  # not the very first occurrence
                    prs.append({
                        "date": s["date"],
                        "category": d["category"],
                        "exercise": d["exercise"],
                        "weight_lbs": d["weight_lbs"],
                        "reps": d["reps"],
                        "e1rm_lbs": e,
                        "prev_best_e1rm": prev,
                        "delta_lbs": round(e - prev, 1),
                    })
    return prs
