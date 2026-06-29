// Extension: personal-trainer
// Generic Copilot CLI fitness coach for the garmin-workouts toolkit.
//
// Reads athlete-specific profile from one of (in order):
//   1. $GARMIN_TRAINER_PROFILE
//   2. $GARMIN_WORKOUTS_PROFILE/trainer-profile.json
//   3. ~/.garmin-workouts/profile/trainer-profile.json
//
// If no profile is found, the coach still works with generic defaults but
// without personalized rules. See trainer-profile.example.json for the schema.

import { joinSession } from "@github/copilot-sdk/extension";
import { execFile } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";

// ── Configuration ────────────────────────────────────────────────────────────
// Point WORKOUT_DIR at the garmin-workouts checkout. Defaults assume the
// extension lives at <repo>/extensions/personal-trainer/extension.mjs.
const __dirname = dirname(fileURLToPath(import.meta.url));
const WORKOUT_DIR = process.env.GARMIN_WORKOUTS_DIR
    || join(__dirname, "..", "..");

// ── Profile loading ──────────────────────────────────────────────────────────
function resolveProfilePath() {
    if (process.env.GARMIN_TRAINER_PROFILE) return process.env.GARMIN_TRAINER_PROFILE;
    if (process.env.GARMIN_WORKOUTS_PROFILE) {
        return join(process.env.GARMIN_WORKOUTS_PROFILE, "trainer-profile.json");
    }
    return join(homedir(), ".garmin-workouts", "profile", "trainer-profile.json");
}

function loadProfile() {
    const path = resolveProfilePath();
    if (!existsSync(path)) return null;
    try {
        return JSON.parse(readFileSync(path, "utf-8"));
    } catch (err) {
        console.error(`[personal-trainer] Failed to parse ${path}: ${err.message}`);
        return null;
    }
}

const PROFILE = loadProfile();

// ── Context builder ──────────────────────────────────────────────────────────
function buildAthleteIntro(p) {
    if (!p) {
        return `You are acting as the user's personal fitness trainer. You have access to trainer_* tools to read their Garmin Connect data, manage fitness goals, create workouts, and track progress. Use these tools proactively when discussing fitness topics. Be encouraging but direct. Base recommendations on their actual activity data.

NOTE: No trainer-profile.json was found. Coaching will use generic defaults. To personalize, create a profile at ~/.garmin-workouts/profile/trainer-profile.json — see extensions/personal-trainer/trainer-profile.example.json in the repo.`;
    }

    const name = p.name || "the athlete";
    const device = p.device ? ` Their Garmin device is a ${p.device}.` : "";
    const sport = p.primarySport ? ` Their primary sport is ${p.primarySport}.` : "";
    const focus = (p.secondaryFocus && p.secondaryFocus.length)
        ? ` They train for: ${p.secondaryFocus.join(", ")}.`
        : "";

    return `You are acting as ${name}'s personal fitness trainer. You have access to trainer_* tools to read their Garmin Connect data, manage fitness goals, create workouts, and track progress. Use these tools proactively when discussing fitness topics. Be encouraging but direct. Base recommendations on their actual activity data.${device}${sport}${focus}`;
}

function buildPersonalRulesBlock(p) {
    if (!p || !p.personalRules || !p.personalRules.length) return "";
    const lines = p.personalRules.map((r, i) => `${i + 1}. ${r}`).join("\n");
    return `\n\nPERSONAL RULES (athlete-specific, learned from their data):\n${lines}`;
}

function buildTypicalWeekBlock(p) {
    if (!p || !p.typicalWeek) return "";
    const w = p.typicalWeek;
    const parts = [];
    if (w.courtDays != null) parts.push(`${w.courtDays} court day(s)`);
    if (w.strengthSessions != null) parts.push(`${w.strengthSessions} strength session(s)`);
    if (w.activeRecoveryDays != null) parts.push(`${w.activeRecoveryDays} active recovery day(s)`);
    if (w.restDays != null) parts.push(`${w.restDays} rest day(s)`);
    if (!parts.length) return "";
    return `\n\nTYPICAL WEEK: ${parts.join(" + ")}. Factor this into all programming — assume the schedule is already full and avoid stacking new load on top.`;
}

const UNIVERSAL_RULES = `
DATE AWARENESS (CRITICAL): Before responding to ANY fitness/workout/recovery query, check the current date and day-of-week from the <current_datetime> tag in the user's message (or call out if missing). Use it to:
- Compute the correct date ranges for "today", "yesterday", "this week" (Mon-Sun of current week), "last week" (prior Mon-Sun), "midweek", "weekend"
- Pick the right day from the weeklySchedule when discussing what's planned/done
- Frame recovery and activity windows correctly when calling trainer_recovery (start_date/end_date) and interpreting trainer_activities timestamps
- State the date you're reasoning from at the start of any review (e.g., "Today is Mon May 4 — reviewing last week Apr 27 to May 3").
Never assume a date from prior turns; always recheck.

WEEKLY REVIEW PROTOCOL: When asked to review a week or assess progress, ALWAYS:
1. Pull activities (trainer_activities) for workout data
2. Pull recovery data (trainer_recovery) for sleep, readiness, HRV
3. Pull actual lift data (trainer_lifts) for any strength sessions in the review window — sets, reps, top weights. Do NOT prescribe next week's loads from memory or from the prior plan; derive them from what was actually completed last week.
4. Cross-reference: correlate sleep quality/readiness scores with workout effectiveness
5. Identify patterns: did good sleep predict better workouts? Is HRV trending up (adapting) or down (overtraining)? Are unplanned court/cardio sessions on rest days correlating with readiness collapses?
6. Check-in (trainer_checkin) to record the review
7. Plan next week factoring in recovery state AND actual recent loads — if readiness is low or HRV declining, reduce volume or add rest days. When proposing strength loads, cite the specific recent session ("Wed 6/24 Upper Rebuild: OHP 34kg×5×4 completed") rather than abstract percentages.

LOAD PROGRESSION RULE: Never prescribe weights/reps without first inspecting the athlete's actual last completed session for that lift. "100% of W11 loads" is meaningless unless you confirm what those loads were and what was actually executed since. If the lift data tool fails or returns nothing, say so explicitly and ask the athlete before guessing.

UNIVERSAL PROGRAMMING RULES:

REP RANGES: Do NOT prescribe 3-rep sets at sub-max loads (≤89% 1RM) — they produce no real stimulus and feel pointless. Low reps (1-3) only earn their place at ≥90% 1RM (strength test) or with explicit explosive/dynamic-effort intent. For rebuild/maintenance weeks, default top sets are 5-8 reps at 80-88% 1RM (RPE 7-8). For deload weeks, drop intensity to 60-75% 1RM but keep reps in the 5-8 range so the movement pattern stays primed.

REBUILD vs DELOAD: Always distinguish "rebuild" (95-100% of recent loads, RPE 7, no PR attempts) from "deload" (-10% loads, RPE 5-6, recovery focus). Default back-off weeks to rebuild depth; reserve true deloads for every 4-5 weeks or when HRV is acutely suppressed (multiple days <35ms). Never call a 95% week a "reload".

HRV INTERPRETATION: Multi-week HRV trends matter more than any single day's reading. A 2+ week declining trend is a yellow flag for cumulative fatigue even if individual days look acceptable.

DON'T LECTURE: When data later shows a planned-rest violation didn't break the athlete (next-day readiness rebounded), acknowledge it honestly instead of doubling down on "mistake" framing. Calibrate confidence to evidence, not narrative.`;

function buildContext() {
    return buildAthleteIntro(PROFILE)
         + buildTypicalWeekBlock(PROFILE)
         + buildPersonalRulesBlock(PROFILE)
         + "\n" + UNIVERSAL_RULES;
}

const CONTEXT = buildContext();

// ── Subprocess helpers ───────────────────────────────────────────────────────
function runWorkoutCli(args) {
    return new Promise((resolve) => {
        execFile(
            "python",
            ["workout.py", ...args],
            { cwd: WORKOUT_DIR, timeout: 30000 },
            (err, stdout, stderr) => {
                if (err) resolve(`Error: ${stderr || err.message}`);
                else resolve(stdout);
            }
        );
    });
}

function runPython(code) {
    return new Promise((resolve) => {
        execFile(
            "python",
            ["-c", code],
            { cwd: WORKOUT_DIR, timeout: 30000 },
            (err, stdout, stderr) => {
                if (err) resolve(`Error: ${stderr || err.message}`);
                else resolve(stdout);
            }
        );
    });
}

// ── Session ──────────────────────────────────────────────────────────────────
const FITNESS_KEYWORDS = [
    "workout", "training", "fitness", "exercise", "gym",
    "strength", "hiit", "cardio", "badminton", "tennis", "running",
    "goal", "plan", "progress", "check-in", "checkin", "garmin",
    "lift", "squat", "deadlift", "bench", "press", "sleep", "recovery",
    "readiness", "hrv",
];

const session = await joinSession({
    hooks: {
        onUserPromptSubmitted: async (input) => {
            const prompt = input.prompt.toLowerCase();
            const isFitness = FITNESS_KEYWORDS.some(k => prompt.includes(k));
            if (isFitness) {
                return { additionalContext: CONTEXT };
            }
        },
    },
    tools: [
        {
            name: "trainer_activities",
            description: "Get recent completed activities from Garmin Connect. Returns activity name, type, duration, calories, date.",
            skipPermission: true,
            parameters: {
                type: "object",
                properties: {
                    limit: { type: "number", description: "Number of activities (default 20)" },
                },
            },
            handler: async (args) => {
                const limit = args.limit || 20;
                return await runWorkoutCli(["activities", "--limit", String(limit), "--json-output"]);
            },
        },
        {
            name: "trainer_lifts",
            description: "Get strength lift history — actual completed sets/reps/weights and 1RM estimates from recent Garmin strength_training activities. CRITICAL: call this before prescribing next week's loads, so prescriptions are anchored to what the athlete actually lifted (not memory or prior plan).",
            skipPermission: true,
            parameters: {
                type: "object",
                properties: {
                    weeks: { type: "number", description: "Weeks of history to analyze (default 4)" },
                    filter: { type: "string", description: "all | upper | lower" },
                },
            },
            handler: async (args) => {
                const cli = ["lifts", "--json-output"];
                if (args.weeks) cli.push("--weeks", String(args.weeks));
                if (args.filter) cli.push("--filter", args.filter);
                return await runWorkoutCli(cli);
            },
        },
        {
            name: "trainer_stats",
            description: "Get weekly workout statistics — volume, frequency, duration, types. Use to assess training consistency and progress.",
            skipPermission: true,
            parameters: {
                type: "object",
                properties: {
                    weeks: { type: "number", description: "Number of weeks to analyze (default 4)" },
                },
            },
            handler: async (args) => {
                const weeks = args.weeks || 4;
                return await runWorkoutCli(["stats", "--weeks", String(weeks), "--json-output"]);
            },
        },
        {
            name: "trainer_recovery",
            description: "Get recovery report (sleep hours/score/deep, training readiness, HRV trend) for a date range. Use for weekly reviews and planning. Correlate with workout performance to identify patterns.",
            skipPermission: true,
            parameters: {
                type: "object",
                properties: {
                    start_date: { type: "string", description: "Start date YYYY-MM-DD (typically Monday)" },
                    end_date: { type: "string", description: "End date YYYY-MM-DD (typically Sunday)" },
                },
                required: ["start_date", "end_date"],
            },
            handler: async (args) => {
                return await runWorkoutCli(["recovery", args.start_date, args.end_date, "--json-output"]);
            },
        },
        {
            name: "trainer_goals",
            description: "Get current short-term and long-term fitness goals.",
            skipPermission: true,
            parameters: { type: "object", properties: {} },
            handler: async () => {
                return await runWorkoutCli(["goals", "--json-output"]);
            },
        },
        {
            name: "trainer_set_goals",
            description: "Update fitness goals. Provide shortTerm and/or longTerm arrays of goal objects.",
            skipPermission: true,
            parameters: {
                type: "object",
                properties: {
                    shortTerm: {
                        type: "array",
                        description: "Short-term goals (weeks/months)",
                        items: {
                            type: "object",
                            properties: {
                                goal: { type: "string" },
                                target: { type: "string" },
                                done: { type: "boolean" },
                            },
                            required: ["goal"],
                        },
                    },
                    longTerm: {
                        type: "array",
                        description: "Long-term goals (quarterly/yearly)",
                        items: {
                            type: "object",
                            properties: {
                                goal: { type: "string" },
                                target: { type: "string" },
                            },
                            required: ["goal"],
                        },
                    },
                },
            },
            handler: async (args) => {
                const code = `
import json, sys
sys.path.insert(0, '.')
from lib.profile import set_goals
result = set_goals(
    short_term=${JSON.stringify(args.shortTerm || "None").replace('"None"', 'None')},
    long_term=${JSON.stringify(args.longTerm || "None").replace('"None"', 'None')},
)
print(json.dumps(result, indent=2, default=str))
`;
                return await runPython(code);
            },
        },
        {
            name: "trainer_plan",
            description: "Get current training plan and weekly schedule.",
            skipPermission: true,
            parameters: { type: "object", properties: {} },
            handler: async () => {
                return await runWorkoutCli(["plan", "--json-output"]);
            },
        },
        {
            name: "trainer_set_plan",
            description: "Update the training plan. Provide currentPlan description and weeklySchedule.",
            skipPermission: true,
            parameters: {
                type: "object",
                properties: {
                    currentPlan: { type: "string", description: "Description of the current training plan" },
                    weeklySchedule: {
                        type: "object",
                        description: "Weekly schedule mapping day names to workout descriptions",
                    },
                },
                required: ["currentPlan"],
            },
            handler: async (args) => {
                const code = `
import json, sys
sys.path.insert(0, '.')
from lib.profile import set_plan
result = set_plan(${JSON.stringify(args)})
print(json.dumps(result, indent=2, default=str))
`;
                return await runPython(code);
            },
        },
        {
            name: "trainer_checkin",
            description: "Record a progress check-in with summary and optional metrics/notes.",
            skipPermission: true,
            parameters: {
                type: "object",
                properties: {
                    summary: { type: "string", description: "Brief progress summary" },
                    metrics: { type: "object", description: "Key metrics (e.g., weight, reps, times)" },
                    notes: { type: "string", description: "Additional notes" },
                },
                required: ["summary"],
            },
            handler: async (args) => {
                const metricsStr = args.metrics ? JSON.stringify(args.metrics) : "{}";
                const code = `
import json, sys
sys.path.insert(0, '.')
from lib.profile import add_checkin
result = add_checkin(
    summary=${JSON.stringify(args.summary)},
    metrics=json.loads('${metricsStr.replace(/'/g, "\\'")}'),
    notes=${JSON.stringify(args.notes || "")},
)
print(json.dumps(result, indent=2, default=str))
`;
                return await runPython(code);
            },
        },
        {
            name: "trainer_checkins",
            description: "Get recent progress check-ins.",
            skipPermission: true,
            parameters: {
                type: "object",
                properties: {
                    limit: { type: "number", description: "Number of check-ins (default 5)" },
                },
            },
            handler: async () => {
                return await runWorkoutCli(["checkins", "--json-output"]);
            },
        },
        {
            name: "trainer_create_workout",
            description: "Save a workout JSON file to the workouts/ directory. The workout JSON must follow Garmin's native format with sportType, workoutSegments, workoutSteps.",
            skipPermission: true,
            parameters: {
                type: "object",
                properties: {
                    filename: { type: "string", description: "Filename (without path, e.g. 'leg_day.json')" },
                    workout: { type: "object", description: "Complete workout JSON in Garmin format" },
                },
                required: ["filename", "workout"],
            },
            handler: async (args) => {
                const fs = await import("node:fs");
                const path = await import("node:path");
                const filepath = path.default.join(WORKOUT_DIR, "workouts", args.filename);
                fs.default.writeFileSync(filepath, JSON.stringify(args.workout, null, 2));
                return `Workout saved to workouts/${args.filename}`;
            },
        },
        {
            name: "trainer_push_workout",
            description: "Upload a workout JSON file to Garmin Connect so it syncs to the watch.",
            skipPermission: true,
            parameters: {
                type: "object",
                properties: {
                    filename: { type: "string", description: "Filename in workouts/ directory" },
                },
                required: ["filename"],
            },
            handler: async (args) => {
                const filepath = `workouts\\${args.filename}`;
                return await runWorkoutCli(["push", filepath]);
            },
        },
        {
            name: "trainer_list_workouts",
            description: "List all workouts currently on Garmin Connect.",
            skipPermission: true,
            parameters: { type: "object", properties: {} },
            handler: async () => {
                return await runWorkoutCli(["list"]);
            },
        },
    ],
});
