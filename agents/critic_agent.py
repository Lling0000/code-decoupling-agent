from __future__ import annotations

from agents.contracts import CriticReview
from common.helpers import find_assignment, non_empty_text, string_list
from common.log import get_logger
from llm.client import build_bailian_client, provider_request_error
from models.schema import to_jsonable
from policy.engine import evaluate_plan

log = get_logger("decoupling.critic")

ALLOWED_STATUS = {"approved", "needs_review", "blocked"}
ALLOWED_RISK = {"low", "medium", "high"}


def build_deterministic_review(
    action_plan: dict[str, object],
    repo_inventory: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    policy_result = evaluate_plan(action_plan)
    concerns: list[str] = []
    required_checks = {"python -m unittest"}

    if policy_result["protected_files"]:
        concerns.append("计划涉及受保护或高风险路径，不应自动执行。")
    if policy_result["oversized_steps"]:
        concerns.append("部分步骤涉及文件范围过大，执行前应进一步拆分。")
    if repo_inventory["parse_errors"] > 0:
        concerns.append("存在无法解析的 Python 文件，当前规划结论可信度会下降。")
    if not repo_inventory["has_tests"] and action_plan.get("steps"):
        concerns.append("仓库缺少明显测试，任何重构计划都应先补 characterization tests。")

    if any(step["finding_rule"] in {"RULE_A", "RULE_D", "RULE_E"} for step in action_plan.get("steps", [])):
        required_checks.add("targeted regression tests")

    blocked = bool(policy_result["protected_files"])
    if blocked:
        status = "blocked"
        risk_level = "high"
    elif concerns:
        status = "needs_review"
        risk_level = "high" if any(step["priority"] == "P0" for step in action_plan.get("steps", [])) else "medium"
    else:
        status = "approved"
        risk_level = "medium" if action_plan.get("steps") else "low"

    summary = (
        "计划被策略规则阻断。"
        if blocked
        else "计划在执行前需要人工复核。"
        if concerns
        else "计划位于当前确定性约束范围内。"
    )
    review = CriticReview(
        status=status,
        blocked=blocked,
        risk_level=risk_level,
        concerns=concerns,
        required_checks=sorted(required_checks),
        protected_files=policy_result["protected_files"],
        summary=summary,
    )
    return to_jsonable(review), policy_result


def run_critic_agent(
    *,
    action_plan: dict[str, object],
    repo_inventory: dict[str, object],
    model_routing: dict[str, object],
) -> dict[str, object]:
    deterministic_review, policy_result = build_deterministic_review(action_plan, repo_inventory)
    deterministic_review["generation"] = {
        "mode": "deterministic",
        "source": "critic_fallback",
    }

    assignment = find_assignment(model_routing, "critic_review")
    client = build_bailian_client()
    if client is None or assignment is None:
        log.info("Critic running in deterministic fallback mode")
        return {
            "critic_review": deterministic_review,
            "critic_agent": _critic_runtime(
                assignment=assignment,
                mode="deterministic_fallback",
                used_live_llm=False,
                error=None,
                response_id=None,
            ),
        }

    payload = {
        "repo_inventory": repo_inventory,
        "action_plan": action_plan,
        "deterministic_review": deterministic_review,
        "policy_result": policy_result,
        "constraints": {
            "allowed_status": sorted(ALLOWED_STATUS),
            "allowed_risk_levels": sorted(ALLOWED_RISK),
            "must_respect_policy_result": True,
            "must_keep_no_auto_execution": True,
        },
    }

    try:
        response = client.chat_json(
            model=assignment["api_model"],
            system_prompt=_critic_system_prompt(),
            user_payload=payload,
            temperature=0.1,
            max_tokens=1200,
        )
        critic_review = _sanitize_critic_review(
            response["json"],
            deterministic_review=deterministic_review,
            policy_result=policy_result,
        )
        critic_review["generation"] = {
            "mode": "llm",
            "provider": assignment["provider"],
            "model": assignment["api_model"],
        }
        return {
            "critic_review": critic_review,
            "critic_agent": _critic_runtime(
                assignment=assignment,
                mode="llm",
                used_live_llm=True,
                error=None,
                response_id=response["id"],
            ),
        }
    except Exception as exc:
        return {
            "critic_review": deterministic_review,
            "critic_agent": _critic_runtime(
                assignment=assignment,
                mode="deterministic_fallback",
                used_live_llm=False,
                error=provider_request_error(exc),
                response_id=None,
            ),
        }


def _critic_runtime(
    *,
    assignment: dict[str, object] | None,
    mode: str,
    used_live_llm: bool,
    error: str | None,
    response_id: str | None,
) -> dict[str, object]:
    return {
        "role": "critic_review",
        "mode": mode,
        "used_live_llm": used_live_llm,
        "provider": assignment["provider"] if assignment else None,
        "model": assignment["api_model"] if assignment else None,
        "response_id": response_id,
        "error": error,
    }


def _critic_system_prompt() -> str:
    return (
        "You are the Critic Agent in a technical-debt cleanup system.\n"
        "Review the action plan, but respect deterministic policy constraints.\n"
        "Return JSON only.\n"
        "All natural-language string fields must be written in Simplified Chinese.\n"
        "Do not authorize automatic code execution.\n"
        "Output shape:\n"
        "{\n"
        '  "status": "approved" | "needs_review" | "blocked",\n'
        '  "blocked": boolean,\n'
        '  "risk_level": "low" | "medium" | "high",\n'
        '  "concerns": [string],\n'
        '  "required_checks": [string],\n'
        '  "summary": string\n'
        "}"
    )


def _sanitize_critic_review(
    llm_output: dict[str, object],
    *,
    deterministic_review: dict[str, object],
    policy_result: dict[str, object],
) -> dict[str, object]:
    status = llm_output.get("status")
    if status not in ALLOWED_STATUS:
        status = deterministic_review["status"]

    blocked = bool(llm_output.get("blocked"))
    if policy_result["protected_files"]:
        blocked = True
        status = "blocked"

    risk_level = llm_output.get("risk_level")
    if risk_level not in ALLOWED_RISK:
        risk_level = deterministic_review["risk_level"]
    if blocked:
        risk_level = "high"

    concerns = string_list(llm_output.get("concerns"), deterministic_review["concerns"])
    required_checks = sorted(
        set(string_list(llm_output.get("required_checks"), deterministic_review["required_checks"]))
        | set(deterministic_review["required_checks"])
    )
    summary = non_empty_text(llm_output.get("summary"), deterministic_review["summary"])

    return {
        "status": status,
        "blocked": blocked,
        "risk_level": risk_level,
        "concerns": concerns,
        "required_checks": required_checks,
        "protected_files": policy_result["protected_files"],
        "summary": summary,
    }


