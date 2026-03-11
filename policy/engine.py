from __future__ import annotations

PROTECTED_PATH_KEYWORDS = (
    "auth",
    "security",
    "schema",
    "migration",
    "migrations",
    "settings",
    "secret",
)

MAX_FILES_PER_STEP = 8
MAX_PLAN_WINDOW = 5


def evaluate_plan(action_plan: dict[str, object]) -> dict[str, object]:
    protected_files: list[str] = []
    oversized_steps: list[str] = []

    for step in action_plan.get("steps", []):
        files = step["files"]
        if len(files) > MAX_FILES_PER_STEP:
            oversized_steps.append(step["step_id"])
        for file_path in files:
            lower_path = file_path.lower()
            if any(keyword in lower_path for keyword in PROTECTED_PATH_KEYWORDS):
                protected_files.append(file_path)

    return {
        "protected_files": sorted(set(protected_files)),
        "oversized_steps": oversized_steps,
        "max_files_per_step": MAX_FILES_PER_STEP,
        "max_plan_window": MAX_PLAN_WINDOW,
    }
