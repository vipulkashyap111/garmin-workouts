"""Workout JSON builder helpers for Garmin Connect.

Builds workout payloads in Garmin's native format for:
- Strength training (exercises, sets, reps, weight, rest)
- HIIT (timed intervals with work/rest periods)
- Cardio (steady-state or zone-based time blocks)

Reference: https://github.com/n1t3k/garmin-strength-api
"""

# --- Sport Types ---
SPORT_STRENGTH = {"sportTypeId": 5, "sportTypeKey": "strength_training"}
SPORT_CARDIO = {"sportTypeId": 3, "sportTypeKey": "training"}
SPORT_HIIT = {"sportTypeId": 62, "sportTypeKey": "hiit"}
SPORT_RUNNING = {"sportTypeId": 1, "sportTypeKey": "running"}

# --- Step Types ---
STEP_WARMUP = {"stepTypeId": 1, "stepTypeKey": "warmup"}
STEP_COOLDOWN = {"stepTypeId": 2, "stepTypeKey": "cooldown"}
STEP_INTERVAL = {"stepTypeId": 3, "stepTypeKey": "interval"}
STEP_RECOVERY = {"stepTypeId": 4, "stepTypeKey": "recovery"}
STEP_REST = {"stepTypeId": 5, "stepTypeKey": "rest"}
STEP_REPEAT = {"stepTypeId": 6, "stepTypeKey": "repeat"}

# --- Condition Types ---
COND_TIME = {"conditionTypeId": 2, "conditionTypeKey": "time"}
COND_ITERATIONS = {"conditionTypeId": 7, "conditionTypeKey": "iterations"}
COND_REPS = {"conditionTypeId": 10, "conditionTypeKey": "reps"}
COND_LAP_BUTTON = {"conditionTypeId": 1, "conditionTypeKey": "lap.button"}

# --- Weight Units ---
UNIT_KG = {"unitId": 8, "unitKey": "kilogram", "factor": 1000.0}
UNIT_LB = {"unitId": 9, "unitKey": "pound", "factor": 453.592}


def build_workout(name: str, sport_type: dict, steps: list, description: str = "") -> dict:
    """Build a complete workout payload."""
    workout = {
        "workoutName": name,
        "description": description,
        "sportType": sport_type,
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": sport_type,
                "workoutSteps": _number_steps(steps),
            }
        ],
    }
    return workout


def exercise_set(
    category: str,
    exercise_name: str,
    sets: int,
    reps: int,
    weight_kg: float | None = None,
    rest_seconds: int = 60,
    skip_last_rest: bool = True,
) -> dict:
    """Build a strength exercise group (sets × reps with rest between sets).

    Args:
        category: Garmin exercise category (e.g., "SQUAT", "BENCH_PRESS", "PLANK")
        exercise_name: Garmin exercise name (e.g., "GOBLET_SQUAT", "PUSH_UP")
        sets: Number of sets
        reps: Number of reps per set
        weight_kg: Optional weight in kilograms
        rest_seconds: Rest between sets in seconds
        skip_last_rest: Whether to skip rest after the final set
    """
    work_step = {
        "type": "ExecutableStepDTO",
        "stepType": STEP_INTERVAL,
        "endCondition": COND_REPS,
        "endConditionValue": float(reps),
        "category": category,
        "exerciseName": exercise_name,
    }
    if weight_kg is not None:
        work_step["weightValue"] = float(weight_kg)
        work_step["weightUnit"] = UNIT_KG

    rest_step = {
        "type": "ExecutableStepDTO",
        "stepType": STEP_REST,
        "endCondition": COND_TIME,
        "endConditionValue": float(rest_seconds),
    }

    return {
        "type": "RepeatGroupDTO",
        "stepType": STEP_REPEAT,
        "numberOfIterations": sets,
        "endCondition": COND_ITERATIONS,
        "endConditionValue": float(sets),
        "skipLastRestStep": skip_last_rest,
        "workoutSteps": [work_step, rest_step],
    }


def timed_step(
    duration_seconds: int,
    step_type: dict = STEP_INTERVAL,
    description: str = "",
) -> dict:
    """Build a time-based step (for HIIT/cardio intervals)."""
    step = {
        "type": "ExecutableStepDTO",
        "stepType": step_type,
        "endCondition": COND_TIME,
        "endConditionValue": float(duration_seconds),
    }
    if description:
        step["description"] = description
    return step


def rest_step(duration_seconds: int) -> dict:
    """Build a rest step."""
    return timed_step(duration_seconds, step_type=STEP_REST)


def warmup_step(duration_seconds: int = 300) -> dict:
    """Build a warmup step (default 5 minutes)."""
    return timed_step(duration_seconds, step_type=STEP_WARMUP)


def cooldown_step(duration_seconds: int = 300) -> dict:
    """Build a cooldown step (default 5 minutes)."""
    return timed_step(duration_seconds, step_type=STEP_COOLDOWN)


def lap_button_step(step_type: dict = STEP_INTERVAL, description: str = "") -> dict:
    """Build a step that ends on lap button press."""
    step = {
        "type": "ExecutableStepDTO",
        "stepType": step_type,
        "endCondition": COND_LAP_BUTTON,
    }
    if description:
        step["description"] = description
    return step


def repeat_group(steps: list, iterations: int, skip_last_rest: bool = True) -> dict:
    """Build a repeat group (e.g., HIIT circuits)."""
    return {
        "type": "RepeatGroupDTO",
        "stepType": STEP_REPEAT,
        "numberOfIterations": iterations,
        "endCondition": COND_ITERATIONS,
        "endConditionValue": float(iterations),
        "skipLastRestStep": skip_last_rest,
        "workoutSteps": steps,
    }


def _number_steps(steps: list, start: int = 1) -> list:
    """Recursively assign stepOrder to all steps."""
    order = start
    result = []
    for step in steps:
        step_copy = dict(step)
        step_copy["stepOrder"] = order
        order += 1
        if "workoutSteps" in step_copy:
            inner, order = _number_steps_inner(step_copy["workoutSteps"], order)
            step_copy["workoutSteps"] = inner
        result.append(step_copy)
    return result


def _number_steps_inner(steps: list, start: int) -> tuple[list, int]:
    """Inner recursive step numbering."""
    order = start
    result = []
    for step in steps:
        step_copy = dict(step)
        step_copy["stepOrder"] = order
        order += 1
        if "workoutSteps" in step_copy:
            inner, order = _number_steps_inner(step_copy["workoutSteps"], order)
            step_copy["workoutSteps"] = inner
        result.append(step_copy)
    return result, order
