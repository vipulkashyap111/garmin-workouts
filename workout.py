"""Garmin Workout CLI — create, upload, and manage workouts on Garmin Connect."""

import json
import os
import sys

# Ensure UTF-8 output even when spawned by Node.js on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import click

from lib.browser_auth import browser_login
from lib.client import (
    delete_workout,
    get_activities,
    get_weekly_recovery,
    get_weekly_stats,
    get_weight_history,
    list_workouts,
    log_weight_to_garmin,
    push_workout_file,
    schedule_workout,
    sync_directory,
)
from lib.profile import (
    add_checkin,
    get_checkins,
    get_goals,
    get_plan,
    set_goals,
    set_plan,
)
from lib.lifts import get_lifts_history, detect_prs, LOWER_BODY_CATS, UPPER_BODY_CATS
from lib.retests import add_retest, list_retests, compare_last_two, TEST_DEFINITIONS


@click.group()
def cli():
    """Garmin Workout CLI — manage workouts on Garmin Connect."""
    pass


@cli.command("login")
def browser_login_cmd():
    """Login via browser and save session cookies."""
    browser_login()


@cli.command("list")
def list_cmd():
    """List all workouts on your Garmin Connect account."""
    workouts = list_workouts()

    if not workouts:
        print("No workouts found.")
        return

    print(f"\n{'ID':<14} {'Sport':<20} {'Name'}")
    print("-" * 60)
    for w in workouts:
        wid = w.get("workoutId", "?")
        name = w.get("workoutName", "Untitled") or "Untitled"
        sport = (w.get("sportType") or {}).get("sportTypeKey", "?") or "?"
        print(f"{wid:<14} {sport:<20} {name}")
    print(f"\n{len(workouts)} workout(s) total.")


@cli.command()
@click.argument("filepath", type=click.Path(exists=True))
def push(filepath):
    """Upload a single workout JSON file to Garmin Connect."""
    print(f"Uploading {filepath}...")
    result = push_workout_file(filepath)
    name = result.get("workoutName", "?")
    wid = result.get("workoutId", "?")
    print(f"✅ Uploaded: {name} (ID: {wid})")


@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
def sync(directory):
    """Upload all .json workout files from a directory."""
    print(f"Syncing workouts from {directory}...")
    results = sync_directory(directory)
    success = sum(1 for _, r in results if "error" not in r)
    print(f"\nDone: {success}/{len(results)} uploaded successfully.")


@cli.command()
@click.argument("workout_id")
def delete(workout_id):
    """Delete a workout from Garmin Connect by ID."""
    if not click.confirm(f"Delete workout {workout_id}?"):
        return
    delete_workout(workout_id)
    print(f"🗑️  Deleted workout {workout_id}.")


@cli.command()
@click.argument("workout_id")
@click.argument("date", metavar="YYYY-MM-DD or day name (mon, tue, wed...)")
def schedule(workout_id, date):
    """Schedule a workout on your Garmin calendar.

    DATE can be YYYY-MM-DD or a day name (mon, tue, wed, thu, fri, sat, sun).
    Day names resolve to the next occurrence of that day (today if it matches).
    """
    from datetime import datetime, timedelta
    day_names = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    if date.lower()[:3] in day_names:
        target_day = day_names[date.lower()[:3]]
        today = datetime.now()
        days_ahead = (target_day - today.weekday()) % 7
        resolved = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        print(f"  {date} → {resolved} ({today.strftime('%A %b %d')} is today)")
        date = resolved
    schedule_workout(workout_id, date)
    print(f"📅 Scheduled workout {workout_id} for {date}.")


# --- Activity & Stats Commands ---

@cli.command()
@click.option("--limit", default=20, help="Number of activities to show")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def activities(limit, as_json):
    """Show recent completed activities from Garmin Connect."""
    acts = get_activities(limit=limit)
    if as_json:
        print(json.dumps(acts, indent=2, default=str))
        return
    if not acts:
        print("No activities found.")
        return
    print(f"\n{'Date':<12} {'Type':<20} {'Duration':<10} {'Calories':<10} {'Name'}")
    print("-" * 75)
    for a in acts:
        date = (a.get("startTimeLocal", "")[:10]) or "?"
        atype = (a.get("activityType") or {}).get("typeKey", "?") or "?"
        dur_s = a.get("duration", 0) or 0
        mins = int(dur_s // 60)
        cal = a.get("calories", 0) or 0
        name = a.get("activityName", "Untitled") or "Untitled"
        print(f"{date:<12} {atype:<20} {mins}min{'':<5} {cal:<10} {name}")
    print(f"\n{len(acts)} activity(ies) shown.")


@cli.command()
@click.option("--weeks", default=4, help="Number of weeks to analyze")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def stats(weeks, as_json):
    """Show weekly workout statistics."""
    data = get_weekly_stats(weeks=weeks)
    if as_json:
        print(json.dumps(data, indent=2, default=str))
        return
    s = data["summary"]
    print(f"\n📊 Fitness Stats ({s['periodWeeks']} weeks)")
    print(f"   Total workouts: {s['totalWorkouts']}")
    print(f"   Total duration: {s['totalDurationMin']}min")
    print(f"   Avg/week: {s['avgWorkoutsPerWeek']}")
    print()
    for week, w in data["weeks"].items():
        types = ", ".join(set(w["types"])) if w["types"] else "none"
        print(f"   {week}: {w['count']} workouts, {w['duration_min']}min, {w['calories']}cal — {types}")


@cli.command()
@click.argument("start_date")
@click.argument("end_date")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def recovery(start_date, end_date, as_json):
    """Get recovery report (sleep, readiness, HRV) for a date range. Dates: YYYY-MM-DD."""
    data = get_weekly_recovery(start_date, end_date)
    if as_json:
        print(json.dumps(data, indent=2, default=str))
        return
    s = data["summary"]
    print(f"\n🛌 Recovery Report ({start_date} to {end_date})")
    print(f"   Avg sleep: {s['avgSleepHours']}h | Avg score: {s['avgSleepScore']}")
    print(f"   Avg readiness: {s['avgReadiness']} | Avg HRV: {s['avgHRV']}ms ({s['hrvTrend']})")
    print()
    for d in data["days"]:
        sl = f"{d.get('sleepHours', '?')}h" if d.get("sleepHours") else "—"
        sc = d.get("sleepScore", "—") or "—"
        deep = f"{d.get('deepSleepMin', '?')}m" if d.get("deepSleepMin") else "—"
        rd = d.get("readinessScore", "—") or "—"
        rl = (d.get("readinessLevel", "") or "")[:3]
        hrv = d.get("nightlyAvg", "—") or "—"
        print(f"   {d['date']}: sleep={sl} score={sc} deep={deep} | readiness={rd} ({rl}) | HRV={hrv}ms")


# --- Profile Commands ---

@cli.command()
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def goals(as_json):
    """Show current fitness goals."""
    g = get_goals()
    if as_json:
        print(json.dumps(g, indent=2))
        return
    print("\n🎯 Fitness Goals")
    if g.get("updatedAt"):
        print(f"   Updated: {g['updatedAt'][:10]}")
    print("\n   Short-term:")
    for goal in g.get("shortTerm", []):
        status = "✅" if goal.get("done") else "⬜"
        print(f"   {status} {goal.get('goal', '?')}")
    if not g.get("shortTerm"):
        print("   (none set)")
    print("\n   Long-term:")
    for goal in g.get("longTerm", []):
        print(f"   🔵 {goal.get('goal', '?')}")
    if not g.get("longTerm"):
        print("   (none set)")


@cli.command("set-goals")
@click.argument("goals_json", type=click.Path(exists=True))
def set_goals_cmd(goals_json):
    """Update fitness goals from a JSON file."""
    with open(goals_json, "r") as f:
        data = json.load(f)
    result = set_goals(
        short_term=data.get("shortTerm"),
        long_term=data.get("longTerm"),
    )
    print(f"✅ Goals updated ({len(result.get('shortTerm', []))} short-term, {len(result.get('longTerm', []))} long-term)")


@cli.command()
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def plan(as_json):
    """Show current training plan."""
    p = get_plan()
    if as_json:
        print(json.dumps(p, indent=2))
        return
    print("\n📋 Training Plan")
    current = p.get("currentPlan") or p.get("current_plan")
    if current:
        print(f"   {current}")
    else:
        print("   (no plan set)")
    schedule = p.get("weeklySchedule") or p.get("weekly_schedule")
    if schedule:
        print("\n   Weekly schedule:")
        for day, workout in schedule.items():
            print(f"   {day}: {workout}")


@cli.command()
@click.option("--limit", default=5, help="Number of check-ins to show")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def checkins(limit, as_json):
    """Show recent progress check-ins."""
    entries = get_checkins(limit=limit)
    if as_json:
        print(json.dumps(entries, indent=2))
        return
    if not entries:
        print("No check-ins yet.")
        return
    print(f"\n📝 Recent Check-ins ({len(entries)})")
    for e in entries:
        date = e.get("date", "?")[:10]
        print(f"\n   {date}: {e.get('summary', '')}")
        if e.get("notes"):
            print(f"   Notes: {e['notes']}")


@cli.command()
@click.argument("filepath", type=click.Path(exists=True))
def show(filepath):
    """Pretty-print a workout JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        workout = json.load(f)

    print(f"\n📋 {workout.get('workoutName', 'Untitled')}")
    sport = workout.get("sportType", {}).get("sportTypeKey", "?")
    print(f"   Sport: {sport}")
    if workout.get("description"):
        print(f"   Description: {workout['description']}")

    segments = workout.get("workoutSegments", [])
    for seg in segments:
        steps = seg.get("workoutSteps", [])
        _print_steps(steps, indent=3)


def _print_steps(steps: list, indent: int = 0):
    """Recursively print workout steps."""
    prefix = " " * indent
    for step in steps:
        step_type = step.get("stepType", {}).get("stepTypeKey", "?")
        stype = step.get("type", "")

        if stype == "RepeatGroupDTO":
            iters = step.get("numberOfIterations", "?")
            inner = step.get("workoutSteps", [])
            exercise = ""
            for s in inner:
                if s.get("exerciseName"):
                    exercise = f" — {s['exerciseName'].replace('_', ' ').title()}"
                    break
            print(f"{prefix}🔁 {iters}× repeat{exercise}")
            _print_steps(inner, indent + 3)
        else:
            cond = step.get("endCondition", {}).get("conditionTypeKey", "")
            val = step.get("endConditionValue", "")
            desc = step.get("description", "")

            if cond == "reps":
                label = f"{int(val)} reps"
            elif cond == "time":
                mins, secs = divmod(int(val), 60)
                label = f"{mins}:{secs:02d}" if mins else f"{int(val)}s"
            elif cond == "lap.button":
                label = "lap button"
            else:
                label = str(val) if val else ""

            exercise = step.get("exerciseName", "")
            if exercise:
                exercise = exercise.replace("_", " ").title()
                label = f"{exercise} — {label}"

            weight = step.get("weightValue")
            if weight:
                label += f" @ {weight}kg"

            icon = {"warmup": "🟡", "cooldown": "🔵", "rest": "⏸️", "interval": "🟢", "recovery": "⏸️"}.get(step_type, "▪️")
            if desc:
                label = f"{desc} ({label})" if label else desc
            print(f"{prefix}{icon} {step_type}: {label}")


# --- Lifts & Re-tests ---

@cli.command()
@click.option("--weeks", default=12, help="Weeks of history to analyze")
@click.option("--filter", "filt", default="all", type=click.Choice(["all", "upper", "lower"]), help="Filter lifts")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def lifts(weeks, filt, as_json):
    """Show strength lift history and 1RM estimates (lbs) from Garmin data."""
    history = get_lifts_history(weeks=weeks)
    if as_json:
        out = {
            "sessions": history["sessions"],
            "best_1rm": {f"{k[0]}::{k[1]}": v for k, v in history["best_1rm"].items()},
            "lift_timeline": {f"{k[0]}::{k[1]}": v for k, v in history["lift_timeline"].items()},
            "period_weeks": history["period_weeks"],
            "prs": detect_prs(history),
        }
        print(json.dumps(out, indent=2, default=str))
        return

    sessions = history["sessions"]
    best = history["best_1rm"]
    if not sessions:
        print(f"No strength sessions found in the last {weeks} weeks.")
        return

    cat_filter = None
    if filt == "upper":
        cat_filter = UPPER_BODY_CATS
    elif filt == "lower":
        cat_filter = LOWER_BODY_CATS

    print(f"\n💪 Strength History — last {weeks} weeks ({len(sessions)} sessions)")
    print("=" * 75)

    print("\n🏆 Best 1RM estimate per lift (Epley)")
    print(f"   {'Exercise':<34} {'Top set':<14} {'1RM est':<10} {'Date'}")
    print(f"   {'-'*34} {'-'*14} {'-'*10} {'-'*10}")
    items = []
    for (cat, name), d in best.items():
        if cat_filter and cat not in cat_filter:
            continue
        items.append((cat, name, d))
    items.sort(key=lambda x: -(x[2]["e1rm_lbs"] or 0))
    for cat, name, d in items:
        exname = name.replace("_", " ").title()
        top_set = f"{d['weight_lbs']}lb x {d['reps']}"
        e1rm = f"{d['e1rm_lbs']} lb"
        print(f"   {exname:<34} {top_set:<14} {e1rm:<10} {d['date']}")

    prs = detect_prs(history)
    if prs:
        if cat_filter:
            prs = [p for p in prs if p["category"] in cat_filter]
        if prs:
            print(f"\n📈 PRs hit in this period ({len(prs)})")
            for p in prs[-10:]:
                exname = p["exercise"].replace("_", " ").title()
                print(f"   {p['date']}  {exname:<32} {p['weight_lbs']}lb x {p['reps']}  -> {p['e1rm_lbs']}lb 1RM  (+{p['delta_lbs']}lb)")

    print(f"\n📋 Recent sessions")
    for s in sessions[:5]:
        print(f"\n   {s['date']} — {s['name']}")
        for (cat, name), d in s["lifts"].items():
            if cat_filter and cat not in cat_filter:
                continue
            exname = name.replace("_", " ").title()
            wt = f"{d['weight_lbs']}lb" if d['weight_lbs'] else "BW"
            e1rm = f"-> {d['e1rm_lbs']}lb 1RM" if d['e1rm_lbs'] else ""
            sets_info = f"({d['total_sets']} set{'s' if d['total_sets']>1 else ''})"
            print(f"     {exname:<32} {wt:>8} x {d['reps']:<3} {sets_info}  {e1rm}")


@cli.group()
def retest():
    """Manage athletic re-test battery (vertical jump, shuttle, etc.)."""
    pass


@retest.command("add")
@click.option("--date", default=None, help="Date YYYY-MM-DD (defaults to today)")
@click.option("--vertical", type=float, help="Vertical jump (inches)")
@click.option("--broad", type=float, help="Broad jump (inches)")
@click.option("--shuttle", type=float, help="5-10-5 pro-agility shuttle (seconds)")
@click.option("--hop-l", type=float, help="Single-leg hop left (inches)")
@click.option("--hop-r", type=float, help="Single-leg hop right (inches)")
@click.option("--mile", type=str, help="1-mile time (mm:ss)")
@click.option("--bodyweight", type=float, help="Bodyweight (lbs)")
@click.option("--notes", default="", help="Free-text notes")
def retest_add(date, vertical, broad, shuttle, hop_l, hop_r, mile, bodyweight, notes):
    """Log a new re-test result set."""
    from datetime import datetime as _dt
    date = date or _dt.now().strftime("%Y-%m-%d")
    results = {}
    if vertical is not None: results["vertical_jump"] = vertical
    if broad is not None: results["broad_jump"] = broad
    if shuttle is not None: results["shuttle_5_10_5"] = shuttle
    if hop_l is not None: results["single_leg_hop_l"] = hop_l
    if hop_r is not None: results["single_leg_hop_r"] = hop_r
    if mile: results["mile_time"] = mile
    if bodyweight is not None: results["bodyweight_lbs"] = bodyweight
    if not results:
        print("No results provided. Use --vertical, --broad, --shuttle, --hop-l, --hop-r, --mile, --bodyweight.")
        return
    entry = add_retest(date, results, notes)
    print(f"✅ Logged re-test for {date}")
    for k, v in entry["results"].items():
        td = TEST_DEFINITIONS[k]
        print(f"   {td['label']}: {v} {td['unit']}")
    if notes:
        print(f"   Notes: {notes}")


@retest.command("list")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def retest_list(as_json):
    """Show all re-test entries."""
    retests = list_retests()
    if as_json:
        print(json.dumps(retests, indent=2, default=str))
        return
    if not retests:
        print("No re-tests logged yet. Run: python workout.py retest add --vertical 22 --broad 80 ...")
        return
    print(f"\n🏃 Re-test history ({len(retests)} entries)")
    print("=" * 75)
    for r in retests:
        print(f"\n   📅 {r['date']}")
        for k, v in r["results"].items():
            td = TEST_DEFINITIONS.get(k, {"label": k, "unit": ""})
            print(f"     {td['label']:<28} {v} {td['unit']}")
        if r.get("notes"):
            print(f"     Notes: {r['notes']}")


@retest.command("compare")
def retest_compare():
    """Compare the two most recent re-tests."""
    result = compare_last_two()
    if "error" in result:
        print(f"⚠️  {result['error']}")
        return
    print(f"\n📊 Re-test comparison: {result['previous_date']} → {result['current_date']}")
    print("=" * 75)
    for key, d in result["deltas"].items():
        arrow = "↑" if d["improved"] else ("↓" if d["improved"] is False else "→")
        sign = "+" if d["delta"] > 0 else ""
        print(f"   {d['label']:<28} {d['previous']} → {d['current']} {d['unit']}  ({sign}{d['delta']}) {arrow}")


# --- Bodyweight (Garmin-native) ---

@cli.group()
def weight():
    """Log and view bodyweight (stored in Garmin Connect)."""
    pass


@weight.command("log")
@click.argument("weight_lbs", type=float)
@click.option("--date", default=None, help="Date YYYY-MM-DD (defaults to today)")
def weight_log(weight_lbs, date):
    """Log a bodyweight entry to Garmin Connect (lbs)."""
    result = log_weight_to_garmin(weight_lbs, date)
    print(f"✅ Logged {weight_lbs} lbs to Garmin for {date or 'today'}")
    if isinstance(result, dict) and result:
        print(f"   {json.dumps(result, indent=2, default=str)[:300]}")


@weight.command("list")
@click.option("--weeks", default=12, help="Weeks of history to show")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def weight_list(weeks, as_json):
    """Show bodyweight history from Garmin."""
    from datetime import datetime, timedelta
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
    entries = get_weight_history(start, end)
    if as_json:
        print(json.dumps(entries, indent=2, default=str))
        return
    if not entries:
        print(f"No weigh-ins logged in last {weeks} weeks. Run: python workout.py weight log <lbs>")
        return
    print(f"\n⚖️  Bodyweight history ({len(entries)} entries, last {weeks} weeks)")
    print("=" * 60)
    G_TO_LB = 2.20462 / 1000
    weights = []
    for e in entries:
        # Garmin returns weight in grams
        cdate = e.get("calendarDate") or e.get("date") or "?"
        w_g = e.get("weight")
        w_lb = round(w_g * G_TO_LB, 1) if w_g else None
        bmi = e.get("bmi")
        bf = e.get("bodyFat")
        if w_lb:
            weights.append(w_lb)
        extras = []
        if bmi: extras.append(f"BMI {bmi}")
        if bf: extras.append(f"BF {bf}%")
        extra_str = f"  ({', '.join(extras)})" if extras else ""
        print(f"   {cdate}   {w_lb} lb{extra_str}")
    if len(weights) >= 2:
        delta = round(weights[-1] - weights[0], 1)
        sign = "+" if delta > 0 else ""
        print(f"\n   Trend: {weights[0]} → {weights[-1]} ({sign}{delta} lb over {len(weights)} entries)")


if __name__ == "__main__":
    cli()
