from __future__ import annotations

from datetime import datetime, timezone

from llm.catalog import build_model_routing
from llm.client import build_bailian_client, live_agent_runtime_enabled, provider_request_error

CHECKED_ROLES = (
    "planner_triage_review",
    "finding_validation",
    "critic_review",
    "refactor_and_test_fix",
    "summary_and_pr_copy",
)


def run_llm_health_check() -> dict[str, object]:
    model_routing = build_model_routing()
    provider = _first_provider(model_routing)
    runtime_flag_enabled = live_agent_runtime_enabled()
    client = build_bailian_client()
    roles = []
    probe_cache: dict[str, dict[str, object]] = {}

    for role_name in CHECKED_ROLES:
        assignment = _find_assignment(model_routing, role_name)
        if assignment is None:
            roles.append(
                {
                    "role": role_name,
                    "status": "missing_assignment",
                    "checked": False,
                    "provider": None,
                    "model": None,
                    "model_env": None,
                    "probe": None,
                }
            )
            continue

        model = assignment.get("api_model")
        role_result = {
            "role": role_name,
            "status": "skipped",
            "checked": False,
            "provider": assignment.get("provider"),
            "model": model,
            "model_env": assignment.get("model_env"),
            "probe": None,
        }

        if not runtime_flag_enabled:
            role_result["probe"] = {
                "status": "skipped",
                "reason": "live_agents_disabled",
            }
            roles.append(role_result)
            continue

        if not provider.get("configured"):
            role_result["probe"] = {
                "status": "skipped",
                "reason": "missing_api_key",
            }
            roles.append(role_result)
            continue

        if client is None:
            role_result["probe"] = {
                "status": "skipped",
                "reason": "client_unavailable",
            }
            roles.append(role_result)
            continue

        if not isinstance(model, str) or not model.strip():
            role_result["status"] = "failed"
            role_result["checked"] = True
            role_result["probe"] = {
                "status": "failed",
                "error": "No model resolved for role",
            }
            roles.append(role_result)
            continue

        if model not in probe_cache:
            probe_cache[model] = _probe_model(client, model)

        probe = dict(probe_cache[model])
        probe["cached"] = model in {item.get("model") for item in roles if item.get("checked")}
        role_result["checked"] = True
        role_result["status"] = probe["status"]
        role_result["probe"] = probe
        roles.append(role_result)

    passed = sum(1 for role in roles if role["status"] == "passed")
    failed = sum(1 for role in roles if role["status"] in {"failed", "missing_assignment"})
    skipped = sum(1 for role in roles if role["status"] == "skipped")

    if not runtime_flag_enabled:
        status = "disabled"
        ok = False
    elif not provider.get("configured"):
        status = "misconfigured"
        ok = False
    elif failed:
        status = "degraded"
        ok = False
    else:
        status = "healthy"
        ok = True

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "config_path": model_routing.get("config_path"),
        "provider": {
            "provider_id": provider.get("provider_id"),
            "display_name": provider.get("display_name"),
            "api_key_env": provider.get("api_key_env"),
            "api_key_configured": bool(provider.get("configured")),
            "base_url_env": provider.get("base_url_env"),
            "base_url_env_aliases": provider.get("base_url_env_aliases", []),
            "base_url_resolved_from": provider.get("base_url_env_resolved_from"),
            "base_url": provider.get("base_url"),
        },
        "runtime": {
            "live_agents_flag_enabled": runtime_flag_enabled,
            "external_llm_calls_enabled": bool(model_routing.get("policy", {}).get("external_llm_calls_enabled")),
            "policy_status": model_routing.get("policy", {}).get("status"),
        },
        "roles": roles,
        "summary": {
            "status": status,
            "ok": ok,
            "checked_roles": len(roles),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "unique_models_probed": len(probe_cache),
        },
    }


def _first_provider(model_routing: dict[str, object]) -> dict[str, object]:
    providers = model_routing.get("providers", [])
    if providers and isinstance(providers[0], dict):
        return providers[0]
    return {}


def _find_assignment(model_routing: dict[str, object], role_name: str) -> dict[str, object] | None:
    for assignment in model_routing.get("assignments", []):
        if assignment.get("role") == role_name:
            return assignment
    return None


def _probe_model(client: object, model: str) -> dict[str, object]:
    try:
        response = client.probe_model(model=model)
        return {
            "status": "passed",
            "response_id": response.get("id"),
            "response_model": response.get("response_model", model),
            "content_preview": response.get("content_preview", ""),
        }
    except Exception as exc:
        return {
            "status": "failed",
            "error": provider_request_error(exc),
        }
