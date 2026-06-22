# Installation

Copilot CLI looks for extensions under `~/.copilot/extensions/<name>/`. There's no install command — you make the directory visible to the CLI by symlinking or copying.

## Quick install (Windows PowerShell)

```powershell
# Symlink — auto-syncs with git pull (requires Developer Mode or admin shell)
$repo = "$HOME\Repos\garmin-workouts"   # adjust if your checkout is elsewhere
New-Item -ItemType SymbolicLink `
  -Path "$HOME\.copilot\extensions\personal-trainer" `
  -Target "$repo\extensions\personal-trainer"
```

If you can't create symlinks, copy instead:

```powershell
$repo = "$HOME\Repos\garmin-workouts"
Copy-Item -Recurse `
  "$repo\extensions\personal-trainer" `
  "$HOME\.copilot\extensions\personal-trainer"
```

## Quick install (macOS / Linux)

```bash
repo=~/Repos/garmin-workouts   # adjust if needed
ln -s "$repo/extensions/personal-trainer" ~/.copilot/extensions/personal-trainer
```

## Create your profile

```bash
mkdir -p ~/.garmin-workouts/profile
cp extensions/personal-trainer/trainer-profile.example.json \
   ~/.garmin-workouts/profile/trainer-profile.json
# Then edit ~/.garmin-workouts/profile/trainer-profile.json
```

## Verify it loaded

1. Restart the Copilot CLI.
2. Inside the CLI, run `/env` — `personal-trainer` should appear under extensions.
3. The first time you trigger a fitness prompt in a new directory, the CLI may ask permission to load the extension. Allow it.
4. Ask the CLI something fitness-related — `trainer_*` tools should appear in tool listings.

## Troubleshooting

**Extension doesn't appear in `/env`:**
- Check `~/.copilot/logs/extensions/user-personal-trainer-*.log` for load errors.
- Permissions: extensions need approval per working directory. Look in `~/.copilot/permissions-config.json` for an `extension-permission-access` entry naming `user:personal-trainer`.

**`Error: spawn python ENOENT`:**
- Python must be on `PATH`. Test with `python --version`.

**`Error: ... workout.py: file not found`:**
- The extension defaults to `../..` from its own location. If you copied (not symlinked) into a non-standard place, set `GARMIN_WORKOUTS_DIR` to point at the checkout.

**Tools work but coach lacks personalization:**
- Check that `trainer-profile.json` exists at one of the resolved paths (see README). The extension logs a warning to stderr if it fails to parse.
