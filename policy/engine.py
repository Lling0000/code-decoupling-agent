from __future__ import annotations

import json
from pathlib import Path

from common.log import get_logger

log = get_logger("decoupling.policy")

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "policy_config.json"

_DEFAULT_PROTECTED_PATH_KEYWORDS = (
    "auth",
    "security",
    "schema",
    "migration",
    "migrations",
    "settings",
    "secret",
    "credential",
    "permission",
)

_DEFAULT_MAX_FILES_PER_STEP = 8
_DEFAULT_MAX_PLAN_WINDOW = 5


def load_policy_config() -> dict[str, object]:
    if not _CONFIG_PATH.exists():
        return _default_config()
    try:
        raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("Failed to load policy config from %s, using defaults", _CONFIG_PATH)
        return _default_config()

    keywords = raw.get("protected_path_keywords")
    if not isinstance(keywords, list):
        keywords = list(_DEFAULT_PROTECTED_PATH_KEYWORDS)
    user_paths = raw.get("user_protected_paths")
    if not isinstance(user_paths, list):
        user_paths = []

    return {
        "protected_path_keywords": tuple(str(k).lower() for k in keywords),
        "user_protected_paths": [str(p) for p in user_paths],
        "max_files_per_step": int(raw.get("max_files_per_step", _DEFAULT_MAX_FILES_PER_STEP)),
        "max_plan_window": int(raw.get("max_plan_window", _DEFAULT_MAX_PLAN_WINDOW)),
    }


def evaluate_plan(action_plan: dict[str, object]) -> dict[str, object]:
    config = load_policy_config()
    protected_path_keywords = config["protected_path_keywords"]
    user_protected_paths = config["user_protected_paths"]
    max_files_per_step = config["max_files_per_step"]
    max_plan_window = config["max_plan_window"]

    protected_files: list[str] = []
    oversized_steps: list[str] = []

    for step in action_plan.get("steps", []):
        files = step["files"]
        if len(files) > max_files_per_step:
            oversized_steps.append(step["step_id"])
        for file_path in files:
            lower_path = file_path.lower()
            if any(keyword in lower_path for keyword in protected_path_keywords):
                protected_files.append(file_path)
            if any(file_path == protected or file_path.startswith(f"{protected}/") for protected in user_protected_paths):
                protected_files.append(file_path)

    if protected_files:
        log.warning("Policy: detected %d protected files in plan", len(set(protected_files)))
    if oversized_steps:
        log.warning("Policy: %d oversized steps exceed %d files", len(oversized_steps), max_files_per_step)

    return {
        "protected_files": sorted(set(protected_files)),
        "oversized_steps": oversized_steps,
        "max_files_per_step": max_files_per_step,
        "max_plan_window": max_plan_window,
    }


def _default_config() -> dict[str, object]:
    return {
        "protected_path_keywords": _DEFAULT_PROTECTED_PATH_KEYWORDS,
        "user_protected_paths": [],
        "max_files_per_step": _DEFAULT_MAX_FILES_PER_STEP,
        "max_plan_window": _DEFAULT_MAX_PLAN_WINDOW,
    }
