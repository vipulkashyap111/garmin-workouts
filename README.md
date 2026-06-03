# Garmin Workout CLI

A lightweight Python CLI to create, upload, and manage custom workouts on Garmin Connect — plus helpers for pulling recovery / HRV / activity data and tracking strength PRs, athletic re-tests, bodyweight, goals, plans, and weekly check-ins. Workouts sync automatically to your Garmin watch.

## Privacy by design

Source code (this repo) is intentionally separate from personal training data. Your data — goals, check-ins, plans, re-tests, personal workouts — lives **outside** this repo, in a directory you control. See [Profile setup](#profile-setup).

## Setup

```bash
cd Repos/garmin-workouts
pip install -r requirements.txt
```

## Authentication

Login once — session persists for hours, full re-login is occasional:

```bash
python workout.py login    # opens browser, log in to Garmin Connect once
```

Or via environment variables:

```bash
set GARMIN_EMAIL=you@example.com
set GARMIN_PASSWORD=your_password
```

Tokens / cookies are stored at `~/.garminconnect/` — **never** inside the repo.

## Profile setup

Personal data (goals, check-ins, plan, re-tests, bodyweight history references) lives **outside** this repo. The CLI resolves the profile directory in this order:

1. `GARMIN_WORKOUTS_PROFILE` env var, if set
2. `./profile/` in the current working directory (local dev override — gitignored)
3. `~/.garmin-workouts/profile/` (default fallback)

Recommended: keep your personal data in a separate (private) git repo and point the env var at it.

```bash
# Bootstrap from templates
mkdir -p ~/.garmin-workouts/profile
cp profile.example/*.json ~/.garmin-workouts/profile/

# Or use a private repo
git clone git@github.com:<you>/garmin-workouts-private.git ~/garmin-data
set GARMIN_WORKOUTS_PROFILE=C:\Users\you\garmin-data\profile
```

See [`profile.example/README.md`](profile.example/README.md) for the schemas.

## Usage

```bash
# Workouts
python workout.py list                              # list workouts on your account
python workout.py push examples/hiit_badminton.json # upload a single workout
python workout.py sync workouts/                    # upload all in a directory
python workout.py schedule <workout_id> 2026-06-10  # schedule on Garmin calendar (or use day name: mon, tue, ...)
python workout.py delete <workout_id>
python workout.py show examples/strength_upper.json

# Data pulls
python workout.py activities --limit 10
python workout.py recovery 2026-06-01 2026-06-07
python workout.py stats 2026-06-01 2026-06-07

# Performance tracking
python workout.py lifts --weeks 16                  # strength history + estimated 1RMs + PRs
python workout.py retest add --vertical 22 --broad 78 --shuttle 4.9 --hop-l 65 --hop-r 64 --bodyweight 165
python workout.py retest list
python workout.py retest compare                    # last two re-tests, delta report
python workout.py weight log 165.4                  # log bodyweight to Garmin
python workout.py weight list --weeks 12

# Profile (lives outside repo, see above)
python workout.py goals                             # show current goals
python workout.py plan                              # show current weekly plan
python workout.py checkin add "Week 10 review" ...  # append a check-in
python workout.py checkins                          # list recent check-ins
```

## Creating Workouts

Workout files are JSON in Garmin's native format. See `examples/` for templates:

| File | Type | Description |
|------|------|-------------|
| `examples/strength_upper.json` | Strength | DB bench, rows, shoulder press, curls, triceps |
| `examples/hiit_badminton.json` | HIIT | Court shuttles, lateral lunges, shadow badminton, jump squats |
| `examples/cardio_steady.json`  | Cardio | 30 min steady-state with warmup/cooldown |

Additional ready-to-use templates live in `workouts/` (z2 walks, plyo, footwork, recovery, etc.).

### Workout JSON Structure

```json
{
  "workoutName": "My Workout",
  "sportType": { "sportTypeId": 5, "sportTypeKey": "strength_training" },
  "workoutSegments": [{
    "segmentOrder": 1,
    "sportType": { "sportTypeId": 5, "sportTypeKey": "strength_training" },
    "workoutSteps": [...]
  }]
}
```

### Sport Types

| Sport | sportTypeId | sportTypeKey |
|-------|------------|--------------|
| Strength | 5 | `strength_training` |
| Cardio | 3 | `training` |
| HIIT | 62 | `hiit` |
| Running | 1 | `running` |

### Builder Module

Use `lib/builder.py` programmatically to generate workout JSONs:

```python
from lib.builder import *
import json

workout = build_workout("Leg Day", SPORT_STRENGTH, [
    exercise_set("SQUAT", "GOBLET_SQUAT", sets=4, reps=10, weight_kg=16, rest_seconds=90),
    exercise_set("LUNGE", "DUMBBELL_LUNGES", sets=3, reps=12, rest_seconds=60),
    exercise_set("CALF_RAISE", "STANDING_CALF_RAISE", sets=3, reps=15, rest_seconds=45),
])

with open("workouts/leg_day.json", "w") as f:
    json.dump(workout, f, indent=2)
```

## Exercise Reference

Exercise names and categories follow Garmin's FIT SDK. Common examples:

| Category | Exercises |
|----------|-----------|
| SQUAT | GOBLET_SQUAT, BARBELL_BACK_SQUAT, DUMBBELL_SQUAT |
| BENCH_PRESS | DUMBBELL_BENCH_PRESS, BARBELL_BENCH_PRESS, PUSH_UP |
| ROW | DUMBBELL_ROW, BARBELL_ROW, SEATED_CABLE_ROW |
| SHOULDER_PRESS | DUMBBELL_SHOULDER_PRESS, BARBELL_OVERHEAD_PRESS |
| CURL | DUMBBELL_BICEPS_CURL, BARBELL_CURL, HAMMER_CURL |
| PLANK | PLANK, SIDE_PLANK |
| LUNGE | DUMBBELL_LUNGES, WALKING_LUNGE |

Full catalog: [garmin-strength-api exercise catalog](https://github.com/n1t3k/garmin-strength-api/blob/main/docs/exercise-catalog.md)
