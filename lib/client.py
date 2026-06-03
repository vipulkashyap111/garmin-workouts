"""Garmin Connect API client.

Uses headless Edge browser with saved cookies for API calls —
bypasses Cloudflare TLS fingerprint checks that block plain HTTP clients.
Falls back to garminconnect library if OAuth tokens are available.
"""

import json
from pathlib import Path

from lib.browser_auth import (
    get_cookie_path,
    get_garmin_client,
    has_saved_session,
    load_session_token,
)

BASE_URL = "https://connect.garmin.com"
GC_API = f"{BASE_URL}/gc-api"
WORKOUT_API = f"{GC_API}/workout-service"
ACTIVITY_API = f"{GC_API}/activitylist-service"


class BrowserAPI:
    """Headless Edge browser for Garmin Connect API calls."""

    def __init__(self):
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._csrf = None

    def _ensure_started(self):
        if self._page is not None:
            return
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            channel="msedge", headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
        )
        # Load saved cookies
        cookie_file = get_cookie_path()
        if cookie_file.exists():
            cookies = json.loads(cookie_file.read_text())
            self._context.add_cookies(cookies)
        # Load CSRF token
        token_data = load_session_token()
        self._csrf = token_data.get("csrf", "")
        self._page = self._context.new_page()

    def get(self, url: str, params: dict = None) -> dict:
        self._ensure_started()
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{qs}"
        headers = {"NK": "NT", "Accept": "application/json"}
        if self._csrf:
            headers["connect-csrf-token"] = self._csrf
        result = self._page.evaluate("""
            async ([url, headers]) => {
                const resp = await fetch(url, { headers, credentials: 'include' });
                const text = await resp.text();
                return { status: resp.status, body: text };
            }
        """, [url, headers])
        if result["status"] >= 400:
            raise RuntimeError(f"API error {result['status']}: {url}")
        try:
            return json.loads(result["body"])
        except json.JSONDecodeError:
            return result["body"]

    def post(self, url: str, json_data: dict = None) -> dict:
        self._ensure_started()
        headers = {
            "NK": "NT",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._csrf:
            headers["connect-csrf-token"] = self._csrf
        result = self._page.evaluate("""
            async ([url, headers, body]) => {
                const resp = await fetch(url, {
                    method: 'POST', headers, credentials: 'include',
                    body: body ? JSON.stringify(body) : undefined,
                });
                const text = await resp.text();
                return { status: resp.status, body: text };
            }
        """, [url, headers, json_data])
        if result["status"] >= 400:
            raise RuntimeError(f"API error {result['status']}: {url}")
        try:
            return json.loads(result["body"]) if result["body"] else {}
        except json.JSONDecodeError:
            return {}

    def delete(self, url: str) -> None:
        self._ensure_started()
        headers = {"NK": "NT", "Accept": "application/json"}
        if self._csrf:
            headers["connect-csrf-token"] = self._csrf
        result = self._page.evaluate("""
            async ([url, headers]) => {
                const resp = await fetch(url, { method: 'DELETE', headers, credentials: 'include' });
                return { status: resp.status };
            }
        """, [url, headers])
        if result["status"] >= 400:
            raise RuntimeError(f"API error {result['status']}: {url}")

    def close(self):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._pw = None


# Singleton browser API
_browser_api = None

def _get_api() -> BrowserAPI:
    global _browser_api
    if _browser_api is None:
        if not has_saved_session():
            raise RuntimeError("No saved session. Run 'python workout.py login' first.")
        _browser_api = BrowserAPI()
        # Navigate to connect once to establish session
        _browser_api._ensure_started()
        _browser_api._page.goto("https://connect.garmin.com/modern/", wait_until="domcontentloaded")
        _browser_api._page.wait_for_timeout(2000)
    return _browser_api


def list_workouts() -> list[dict]:
    """List all workouts on Garmin Connect."""
    client = get_garmin_client()
    if client:
        try:
            return client.get_workouts()
        except Exception:
            pass
    api = _get_api()
    return api.get(f"{WORKOUT_API}/workouts", {"myWorkoutsOnly": "true", "sharedWorkoutsOnly": "false", "includeAtp": "false"})


def push_workout(workout: dict) -> dict:
    """Upload a workout JSON to Garmin Connect."""
    client = get_garmin_client()
    if client:
        try:
            return client.save_workout(workout)
        except Exception:
            pass
    api = _get_api()
    return api.post(f"{WORKOUT_API}/workout", workout)


def push_workout_file(filepath: str) -> dict:
    """Upload a workout from a JSON file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Workout file not found: {filepath}")
    if path.suffix != ".json":
        raise ValueError(f"Expected .json file, got: {path.suffix}")

    with open(path, "r", encoding="utf-8") as f:
        workout = json.load(f)

    return push_workout(workout)


def delete_workout(workout_id: str) -> None:
    """Delete a workout from Garmin Connect by ID."""
    client = get_garmin_client()
    if client:
        try:
            client.delete_workout(workout_id)
            return
        except Exception:
            pass
    api = _get_api()
    api.delete(f"{WORKOUT_API}/workout/{workout_id}")


def schedule_workout(workout_id: str, date: str) -> dict:
    """Schedule a workout on the Garmin Connect calendar."""
    client = get_garmin_client()
    if client:
        try:
            return client.schedule_workout(workout_id, date)
        except Exception:
            pass
    api = _get_api()
    return api.post(f"{WORKOUT_API}/schedule/{workout_id}", {"date": date})


def sync_directory(directory: str) -> list[tuple]:
    """Upload all .json workout files from a directory."""
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    results = []
    json_files = sorted(dir_path.glob("*.json"))
    if not json_files:
        print(f"No .json files found in {directory}")
        return results

    for filepath in json_files:
        try:
            result = push_workout_file(str(filepath))
            results.append((filepath.name, result))
            workout_name = result.get("workoutName", filepath.stem)
            print(f"  ✅ {workout_name}")
        except Exception as e:
            results.append((filepath.name, {"error": str(e)}))
            print(f"  ❌ {filepath.name}: {e}")

    return results


# --- Activities ---

def get_activities(limit: int = 20, start: int = 0) -> list[dict]:
    """Get recent completed activities from Garmin Connect."""
    client = get_garmin_client()
    if client:
        try:
            return client.get_activities(start, limit)
        except Exception:
            pass
    api = _get_api()
    return api.get(f"{ACTIVITY_API}/activities/search/activities", {"limit": limit, "start": start})


def get_weekly_stats(weeks: int = 4) -> dict:
    """Compute weekly workout stats from recent activities."""
    from collections import defaultdict
    from datetime import datetime, timedelta

    activities = get_activities(limit=weeks * 10)

    now = datetime.now()
    week_start = now - timedelta(days=now.weekday())
    weekly = defaultdict(lambda: {"count": 0, "duration_min": 0, "calories": 0, "types": []})

    for act in activities:
        start_time = act.get("startTimeLocal", "")
        if not start_time:
            continue
        try:
            act_date = datetime.fromisoformat(start_time.replace("Z", ""))
        except (ValueError, TypeError):
            continue

        days_ago = (now - act_date).days
        week_num = days_ago // 7
        if week_num >= weeks:
            continue

        week_label = (week_start - timedelta(weeks=week_num)).strftime("%Y-%m-%d")
        w = weekly[week_label]
        w["count"] += 1
        w["duration_min"] += round(act.get("duration", 0) / 60, 1)
        w["calories"] += act.get("calories", 0) or 0
        act_type = act.get("activityType", {}).get("typeKey", "unknown")
        w["types"].append(act_type)

    total_workouts = sum(w["count"] for w in weekly.values())
    total_duration = sum(w["duration_min"] for w in weekly.values())
    avg_per_week = round(total_workouts / max(weeks, 1), 1)

    return {
        "weeks": dict(sorted(weekly.items(), reverse=True)),
        "summary": {
            "totalWorkouts": total_workouts,
            "totalDurationMin": round(total_duration, 1),
            "avgWorkoutsPerWeek": avg_per_week,
            "periodWeeks": weeks,
        },
    }


def get_weight_history(start_date: str, end_date: str) -> list[dict]:
    """Get bodyweight log entries from Garmin in a date range (YYYY-MM-DD)."""
    api = _get_api()
    data = api.get(f"{GC_API}/weight-service/weight/dateRange",
                   {"startDate": start_date, "endDate": end_date})
    return data.get("dateWeightList", []) if isinstance(data, dict) else []


def log_weight_to_garmin(weight_lbs: float, date: str = None) -> dict:
    """POST a weigh-in to Garmin. weight_lbs in pounds. date YYYY-MM-DD (defaults to today)."""
    from datetime import datetime, timezone
    api = _get_api()
    if date:
        dt_local = datetime.fromisoformat(date).replace(hour=8, minute=0, second=0).astimezone()
    else:
        dt_local = datetime.now().astimezone()
    dt_gmt = dt_local.astimezone(timezone.utc)
    # Garmin format: YYYY-MM-DDTHH:MM:SS.S (ms precision implied)
    def fmt(d):
        return d.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    payload = {
        "dateTimestamp": fmt(dt_local.replace(tzinfo=None)),
        "gmtTimestamp": fmt(dt_gmt.replace(tzinfo=None)),
        "unitKey": "lbs",
        "sourceType": "MANUAL",
        "value": float(weight_lbs),
    }
    return api.post(f"{GC_API}/weight-service/user-weight", payload)


# --- Wellness & Recovery ---

def get_sleep_data(date: str) -> dict:
    """Get sleep data for a specific date (YYYY-MM-DD)."""
    api = _get_api()
    return api.get(f"{GC_API}/sleep-service/sleep/dailySleepData", {"date": date, "nonSleepBufferMinutes": 60})


def get_training_readiness(date: str) -> dict:
    """Get training readiness score for a specific date."""
    api = _get_api()
    return api.get(f"{GC_API}/metrics-service/metrics/trainingreadiness/{date}")


def get_hrv_data(start_date: str, end_date: str) -> dict:
    """Get HRV daily data for a date range."""
    api = _get_api()
    return api.get(f"{GC_API}/hrv-service/hrv/daily/{start_date}/{end_date}")


def get_weekly_recovery(start_date: str, end_date: str) -> dict:
    """Get a combined recovery report: sleep, readiness, HRV for a date range.

    Args:
        start_date: Start date (YYYY-MM-DD), typically Monday
        end_date: End date (YYYY-MM-DD), typically Sunday
    """
    from datetime import datetime, timedelta

    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    api = _get_api()

    # HRV for the range
    hrv_raw = {}
    try:
        hrv_raw = get_hrv_data(start_date, end_date)
    except Exception:
        pass

    hrv_by_date = {}
    summaries = []
    if isinstance(hrv_raw, dict):
        summaries = hrv_raw.get("hrvSummaries", [])
    elif isinstance(hrv_raw, list):
        summaries = hrv_raw
    for entry in summaries:
        d = entry.get("calendarDate", "")
        hrv_by_date[d] = {
            "nightlyAvg": entry.get("lastNightAvg"),
            "weeklyAvg": entry.get("weeklyAvg"),
            "status": entry.get("status"),
        }

    # Day-by-day sleep + readiness
    days = []
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        day = {"date": date_str}

        # Sleep
        try:
            sleep = get_sleep_data(date_str)
            dto = sleep.get("dailySleepDTO", {})
            day["sleepHours"] = round((dto.get("sleepTimeSeconds", 0) or 0) / 3600, 1)
            day["sleepScore"] = (dto.get("sleepScores") or {}).get("overall", {}).get("value")
            day["deepSleepMin"] = round((dto.get("deepSleepSeconds", 0) or 0) / 60)
            day["remSleepMin"] = round((dto.get("remSleepSeconds", 0) or 0) / 60)
        except Exception:
            day["sleepHours"] = None

        # Readiness
        try:
            readiness = get_training_readiness(date_str)
            if isinstance(readiness, list) and readiness:
                day["readinessScore"] = readiness[0].get("score")
                day["readinessLevel"] = readiness[0].get("level")
            elif isinstance(readiness, dict):
                day["readinessScore"] = readiness.get("score")
                day["readinessLevel"] = readiness.get("level")
        except Exception:
            pass

        # HRV
        if date_str in hrv_by_date:
            day.update(hrv_by_date[date_str])

        days.append(day)
        current += timedelta(days=1)

    # Compute summary
    sleep_scores = [d["sleepScore"] for d in days if d.get("sleepScore")]
    readiness_scores = [d["readinessScore"] for d in days if d.get("readinessScore")]
    sleep_hours = [d["sleepHours"] for d in days if d.get("sleepHours")]
    hrv_vals = [d["nightlyAvg"] for d in days if d.get("nightlyAvg")]

    return {
        "days": days,
        "summary": {
            "avgSleepHours": round(sum(sleep_hours) / len(sleep_hours), 1) if sleep_hours else None,
            "avgSleepScore": round(sum(sleep_scores) / len(sleep_scores)) if sleep_scores else None,
            "avgReadiness": round(sum(readiness_scores) / len(readiness_scores)) if readiness_scores else None,
            "avgHRV": round(sum(hrv_vals) / len(hrv_vals)) if hrv_vals else None,
            "hrvTrend": "declining" if hrv_vals and hrv_vals[-1] < hrv_vals[0] else "improving" if hrv_vals and hrv_vals[-1] > hrv_vals[0] else "stable",
        },
    }
