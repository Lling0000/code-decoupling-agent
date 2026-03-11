from __future__ import annotations

import json
from pathlib import Path

from llm.client import live_agent_runtime_enabled
from llm.env import env_value, env_value_with_aliases

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "agent_models.json"
DEFAULT_CONFIG = {
    "provider": {
        "provider_id": "bailian",
        "display_name": "Alibaba Cloud Bailian / DashScope Compatible API",
        "api_key_env": "DASHSCOPE_API_KEY",
        "base_url_env": "DASHSCOPE_BASE_URL",
        "base_url_env_aliases": ["BAILIAN_BASE_URL"],
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    "models": {
        "planner": "deepseek-v3.2",
        "validator": "deepseek-v3.2",
        "critic": "deepseek-v3.2",
        "coder": "qwen3-coder-flash",
        "summary": "qwen3.5-flash",
        "embedding": "text-embedding-v4",
        "rerank": "qwen3-rerank",
    },
}


def build_model_routing() -> dict[str, object]:
    config = load_agent_model_config()
    provider_config = config["provider"]
    model_defaults = config["models"]
    validator_default = model_defaults.get("validator", model_defaults["planner"])
    provider = _provider(
        provider_id=provider_config["provider_id"],
        display_name=provider_config["display_name"],
        api_key_env=provider_config["api_key_env"],
        base_url_env=provider_config["base_url_env"],
        base_url_env_aliases=provider_config["base_url_env_aliases"],
        default_base_url=provider_config["default_base_url"],
        notes=(
            "Single provider blueprint for multi-model routing. "
            "Planner and coder roles can be switched independently via environment variables."
        ),
    )
    live_enabled = live_agent_runtime_enabled() and provider["configured"]

    assignments = [
        {
            "role": "governor_orchestration",
            "provider": provider["provider_id"],
            "logical_model": _resolve_model("PLANNER_MODEL", model_defaults["planner"]),
            "api_model": _resolve_model("PLANNER_MODEL", model_defaults["planner"]),
            "model_env": "PLANNER_MODEL",
            "mode": "thinking",
            "responsibilities": [
                "task orchestration",
                "bounded planning",
                "finding triage",
                "critic review",
            ],
            "why": "High-leverage reasoning work benefits from a dedicated planner model override.",
        },
        {
            "role": "planner_triage_review",
            "provider": provider["provider_id"],
            "logical_model": _resolve_model("PLANNER_MODEL", model_defaults["planner"]),
            "api_model": _resolve_model("PLANNER_MODEL", model_defaults["planner"]),
            "model_env": "PLANNER_MODEL",
            "mode": "thinking",
            "responsibilities": [
                "priority scoring",
                "risk evaluation",
                "step planning",
                "review comments",
            ],
            "why": "Planning and critique need stronger structured reasoning than raw code emission.",
        },
        {
            "role": "finding_validation",
            "provider": provider["provider_id"],
            "logical_model": _resolve_model("PLANNER_MODEL", validator_default),
            "api_model": _resolve_model("PLANNER_MODEL", validator_default),
            "model_env": "PLANNER_MODEL",
            "mode": "thinking",
            "responsibilities": [
                "finding confirmation",
                "confidence scoring",
                "false-positive filtering",
                "evidence validation",
            ],
            "why": "Finding validation benefits from the same strong reasoning tier used for planning and critique.",
        },
        {
            "role": "critic_review",
            "provider": provider["provider_id"],
            "logical_model": _resolve_model("PLANNER_MODEL", model_defaults["critic"]),
            "api_model": _resolve_model("PLANNER_MODEL", model_defaults["critic"]),
            "model_env": "PLANNER_MODEL",
            "mode": "thinking",
            "responsibilities": [
                "plan review",
                "risk assessment",
                "guardrail critique",
                "required-check recommendations",
            ],
            "why": "Critique should use the same high-reasoning model family unless split later.",
        },
        {
            "role": "refactor_and_test_fix",
            "provider": provider["provider_id"],
            "logical_model": _resolve_model("CODER_MODEL", model_defaults["coder"]),
            "api_model": _resolve_model("CODER_MODEL", model_defaults["coder"]),
            "model_env": "CODER_MODEL",
            "mode": "coding",
            "responsibilities": [
                "small bug fixes",
                "multi-file edits",
                "test generation",
                "patch drafting",
            ],
            "why": "Fast coding model is a better cost/performance fit for code-editing loops.",
        },
        {
            "role": "summary_and_pr_copy",
            "provider": provider["provider_id"],
            "logical_model": _resolve_general_model(model_defaults["summary"]),
            "api_model": _resolve_general_model(model_defaults["summary"]),
            "model_env": "DASHSCOPE_MODEL",
            "model_env_aliases": ["BAILIAN_MODEL"],
            "mode": "fast_generation",
            "responsibilities": [
                "scan result explanation",
                "PR descriptions",
                "cheap summaries",
            ],
            "why": "Low-cost summarization should not consume premium reasoning capacity.",
        },
        {
            "role": "embedding",
            "provider": provider["provider_id"],
            "logical_model": model_defaults["embedding"],
            "api_model": model_defaults["embedding"],
            "model_env": None,
            "mode": "retrieval",
            "responsibilities": [
                "vector indexing",
                "semantic recall",
            ],
            "why": "Current embedding tier supports code and multilingual retrieval use cases.",
        },
        {
            "role": "rerank",
            "provider": provider["provider_id"],
            "logical_model": model_defaults["rerank"],
            "api_model": model_defaults["rerank"],
            "model_env": None,
            "mode": "retrieval",
            "responsibilities": [
                "candidate reranking",
                "retrieval precision boost",
            ],
            "why": "Cheap rerank improves recall precision without moving all work to a larger generation model.",
        },
    ]

    return {
        "config_path": str(CONFIG_PATH),
        "providers": [provider],
        "assignments": assignments,
        "policy": {
            "external_llm_calls_enabled": live_enabled,
            "status": "live_enabled" if live_enabled else "disabled",
            "explanation": (
                "This repository stores DashScope-compatible model routing defaults in config/agent_models.json, "
                "and live Planner/Critic agent calls run when provider config is available."
            ),
        },
    }


def load_agent_model_config() -> dict[str, dict[str, object]]:
    if not CONFIG_PATH.exists():
        return _copy_default_config()

    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _copy_default_config()

    provider_raw = raw.get("provider", {})
    models_raw = raw.get("models", {})
    provider = {
        "provider_id": _pick_text(provider_raw.get("provider_id"), DEFAULT_CONFIG["provider"]["provider_id"]),
        "display_name": _pick_text(provider_raw.get("display_name"), DEFAULT_CONFIG["provider"]["display_name"]),
        "api_key_env": _pick_text(provider_raw.get("api_key_env"), DEFAULT_CONFIG["provider"]["api_key_env"]),
        "base_url_env": _pick_text(provider_raw.get("base_url_env"), DEFAULT_CONFIG["provider"]["base_url_env"]),
        "base_url_env_aliases": _pick_string_list(
            provider_raw.get("base_url_env_aliases"),
            DEFAULT_CONFIG["provider"]["base_url_env_aliases"],
        ),
        "default_base_url": _pick_text(
            provider_raw.get("default_base_url"),
            DEFAULT_CONFIG["provider"]["default_base_url"],
        ),
    }
    models = {
        "planner": _pick_text(models_raw.get("planner"), DEFAULT_CONFIG["models"]["planner"]),
        "validator": _pick_text(models_raw.get("validator"), DEFAULT_CONFIG["models"]["validator"]),
        "critic": _pick_text(models_raw.get("critic"), DEFAULT_CONFIG["models"]["critic"]),
        "coder": _pick_text(models_raw.get("coder"), DEFAULT_CONFIG["models"]["coder"]),
        "summary": _pick_text(models_raw.get("summary"), DEFAULT_CONFIG["models"]["summary"]),
        "embedding": _pick_text(models_raw.get("embedding"), DEFAULT_CONFIG["models"]["embedding"]),
        "rerank": _pick_text(models_raw.get("rerank"), DEFAULT_CONFIG["models"]["rerank"]),
    }
    return {
        "provider": provider,
        "models": models,
    }


def _provider(
    *,
    provider_id: str,
    display_name: str,
    api_key_env: str,
    base_url_env: str,
    base_url_env_aliases: list[str],
    default_base_url: str,
    notes: str,
) -> dict[str, object]:
    base_url, base_url_name = env_value_with_aliases(base_url_env, base_url_env_aliases, default_base_url)
    return {
        "provider_id": provider_id,
        "display_name": display_name,
        "api_key_env": api_key_env,
        "base_url_env": base_url_env,
        "base_url_env_aliases": base_url_env_aliases,
        "base_url_env_resolved_from": base_url_name or "default",
        "base_url": base_url,
        "configured": bool(env_value(api_key_env)),
        "configured_model_envs": {
            "DASHSCOPE_MODEL": env_value("DASHSCOPE_MODEL"),
            "BAILIAN_MODEL": env_value("BAILIAN_MODEL"),
            "CODER_MODEL": env_value("CODER_MODEL"),
            "PLANNER_MODEL": env_value("PLANNER_MODEL"),
        },
        "notes": notes,
    }


def _resolve_general_model(default_model: str) -> str:
    model, _ = env_value_with_aliases("DASHSCOPE_MODEL", ["BAILIAN_MODEL"], default_model)
    return model or default_model


def _resolve_model(env_name: str, default_model: str) -> str:
    general_model, _ = env_value_with_aliases("DASHSCOPE_MODEL", ["BAILIAN_MODEL"])
    return env_value(env_name) or general_model or default_model


def _copy_default_config() -> dict[str, dict[str, object]]:
    provider = dict(DEFAULT_CONFIG["provider"])
    provider["base_url_env_aliases"] = list(DEFAULT_CONFIG["provider"]["base_url_env_aliases"])
    models = dict(DEFAULT_CONFIG["models"])
    return {
        "provider": provider,
        "models": models,
    }


def _pick_text(value: object, fallback: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _pick_string_list(value: object, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return items or list(fallback)
