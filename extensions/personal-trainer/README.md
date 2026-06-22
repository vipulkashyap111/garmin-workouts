# personal-trainer extension

A [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-copilot-cli) extension that turns Copilot into a personal fitness coach driven by your Garmin Connect data.

## What it does

When you mention fitness topics in chat (workout, training, badminton, HRV, recovery, etc.), the extension:

1. **Injects coaching context** — turns the model into a trainer that follows date-awareness, weekly-review, and programming protocols.
2. **Provides `trainer_*` tools** — read activities/recovery/lifts, set goals/plan, log check-ins, push workouts to your watch. All tools wrap `workout.py` so behavior stays consistent with the CLI.
3. **Personalizes** — reads a `trainer-profile.json` from your local (gitignored) profile directory and substitutes your name, device, sport focus, weekly schedule, and personal training rules into the coach's context.

The extension only works inside Copilot CLI — it uses the `@github/copilot-sdk/extension` API.

## Install

The Copilot CLI looks for extensions at `~/.copilot/extensions/<name>/extension.mjs`. Pick one:

### Option A — Symlink (recommended, auto-syncs with `git pull`)

```powershell
# Windows (requires Developer Mode or admin)
New-Item -ItemType SymbolicLink `
  -Path "$HOME\.copilot\extensions\personal-trainer" `
  -Target "$HOME\Repos\garmin-workouts\extensions\personal-trainer"
```

```bash
# macOS / Linux
ln -s ~/Repos/garmin-workouts/extensions/personal-trainer ~/.copilot/extensions/personal-trainer
```

### Option B — Copy

```powershell
Copy-Item -Recurse `
  "$HOME\Repos\garmin-workouts\extensions\personal-trainer" `
  "$HOME\.copilot\extensions\personal-trainer"
```

Then restart the Copilot CLI. The extension needs to be granted permission once per working directory the first time it loads.

## Configure your profile

Copy the example into your private profile directory:

```bash
mkdir -p ~/.garmin-workouts/profile
cp extensions/personal-trainer/trainer-profile.example.json \
   ~/.garmin-workouts/profile/trainer-profile.json
# edit ~/.garmin-workouts/profile/trainer-profile.json to taste
```

If you've set `$GARMIN_WORKOUTS_PROFILE` to point elsewhere (per the main repo README), the extension reads `trainer-profile.json` from there instead. You can also override with `$GARMIN_TRAINER_PROFILE`.

If no profile is found, the coach still loads — but it will use generic defaults and remind you to create one.

## Configure repo location

By default the extension assumes it lives at `<garmin-workouts-checkout>/extensions/personal-trainer/extension.mjs` and shells out to `python workout.py` from two directories up. Override with:

```bash
export GARMIN_WORKOUTS_DIR=~/path/to/garmin-workouts
```

This is only necessary if you installed via Option B (copy) into a different location, or you keep the workouts repo somewhere unusual.

## How it interacts with your data

| Layer | What's there | Where |
|---|---|---|
| Coaching behavior | Date/review protocols, universal programming rules | `extension.mjs` (this repo) |
| Personal context | Name, device, sport, typical week, personal rules | `~/.garmin-workouts/profile/trainer-profile.json` (local, gitignored) |
| Training data | Goals, plan, check-ins | `~/.garmin-workouts/profile/*.json` (local) |
| Activity data | Workouts, sleep, HRV, readiness, strength sets | Garmin Connect (cloud) |

Nothing personal is ever read into the repo. The extension is pure logic + tool wiring.

## Customizing the coach

Add lessons you've learned to your `personalRules` array — they're injected verbatim into every fitness prompt. Examples:

```json
"personalRules": [
  "Default rebuild depth is -5%, not -10% — my body absorbs 95% loads fine.",
  "Skip box jumps in weeks with 3+ court days — knees can't take it.",
  "Sleep <7h means downgrade the day's intensity by one RPE level.",
  "Always include calf raises in lower sessions — my Achilles needs it."
]
```

If you find yourself correcting the coach for the same thing repeatedly, that's a candidate for a new rule.

## Disclaimer

This is a tool for personal training planning. It is not medical advice. If you have any pain, illness, or medical condition, consult a healthcare professional, not an AI coach.
