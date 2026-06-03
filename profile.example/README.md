# Profile (Example Templates)

These are **empty schema templates**. Your real profile data should live **outside this repo**, either:

- In a separate private repo (recommended), or
- In `~/.garmin-workouts/profile/` (default fallback)

## Setup

```bash
# Option A: separate private repo, point env var at it
git clone git@github.com:<you>/garmin-workouts-private.git ~/garmin-data
export GARMIN_WORKOUTS_PROFILE=~/garmin-data/profile

# Option B: default home location
mkdir -p ~/.garmin-workouts/profile
cp profile.example/*.json ~/.garmin-workouts/profile/

# Option C: local override (will be picked up if ./profile/ exists in CWD)
cp -r profile.example profile   # this folder is gitignored
```

## Files

| File | Purpose |
|------|---------|
| `goals.json` | Short/long-term goals + 12-week KPIs |
| `plan.json`  | Current weekly training plan |
| `checkins.json` | Weekly review log (auto-appended by `workout.py checkin add`) |
| `retests.json` | Athletic re-test battery results (auto-created by `workout.py retest add`) |
