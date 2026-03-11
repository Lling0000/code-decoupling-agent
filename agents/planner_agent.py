from __future__ import annotations

from collections import Counter

from agents.contracts import PlanStep, TriageItem
from llm.client import build_bailian_client, provider_request_error
from models.schema import to_jsonable

FINDING_RULE_CONFIG = {
    "RULE_A": {
        "category": "architecture_boundary",
        "owner": "Refactor Agent",
        "title": "将数据库访问从请求层抽离出去",
        "success_criteria": [
            "handler/controller 文件中不再直接出现数据库访问操作。",
            "数据库访问被收敛到显式的 service 或 repository 边界之后。",
        ],
        "rollback_conditions": [
            "接口行为出现未预期变化。",
            "相关接口测试或集成测试失败。",
        ],
        "deterministic_tools": ["pytest", "ruff"],
    },
    "RULE_B": {
        "category": "configuration_centralization",
        "owner": "Planner Agent",
        "title": "集中管理环境变量读取",
        "success_criteria": [
            "共享环境变量只在一个配置模块中读取。",
            "业务模块依赖配置对象，而不是直接读取环境变量。",
        ],
        "rollback_conditions": [
            "默认配置或启动行为出现未预期变化。",
        ],
        "deterministic_tools": ["pytest"],
    },
    "RULE_C": {
        "category": "shared_dependency_cleanup",
        "owner": "Refactor Agent",
        "title": "拆分过载的共享工具依赖",
        "success_criteria": [
            "高扇入工具模块被拆成更聚焦的领域模块。",
            "共享 helper 模块的 import 扇入明显下降。",
        ],
        "rollback_conditions": [
            "跨模块依赖不降反升。",
        ],
        "deterministic_tools": ["pytest", "ruff"],
    },
    "RULE_D": {
        "category": "state_isolation",
        "owner": "Refactor Agent",
        "title": "隔离模块级可变状态",
        "success_criteria": [
            "可变全局状态被迁移到显式对象或工厂中。",
            "共享状态的访问路径清晰且可测试。",
        ],
        "rollback_conditions": [
            "初始化顺序或共享缓存语义出现未预期变化。",
        ],
        "deterministic_tools": ["pytest"],
    },
    "RULE_E": {
        "category": "dependency_breakup",
        "owner": "Planner Agent",
        "title": "通过提取接口或边界打破循环依赖",
        "success_criteria": [
            "import graph 中的简单循环依赖被消除。",
            "共享契约被提取到稳定的中间模块。",
        ],
        "rollback_conditions": [
            "为打破循环而引入超出预期的大范围改动。",
        ],
        "deterministic_tools": ["pytest", "ruff"],
    },
}

SEVERITY_SCORE = {"high": 90, "medium": 60, "low": 30}
PLAN_WINDOW = 5
MANDATORY_GUARDS = ["Policy Engine", "Critic Agent", "Tool Runner"]
ALLOWED_PRIORITIES = {"P0", "P1", "P2"}


def build_triage(findings_artifact: dict[str, object]) -> dict[str, object]:
    items: list[TriageItem] = []

    for finding in findings_artifact.get("findings", []):
        config = FINDING_RULE_CONFIG.get(
            finding["rule_id"],
            {
                "category": "general",
                "owner": "Planner Agent",
            },
        )
        score = SEVERITY_SCORE.get(finding["severity"], 20) + min(len(finding["files"]) * 5, 20)
        priority = _priority_for_score(score)
        items.append(
            TriageItem(
                finding_rule=finding["rule_id"],
                rule_name=finding["rule_name"],
                category=config["category"],
                priority=priority,
                severity=finding["severity"],
                score=score,
                files=finding["files"],
                rationale=finding["explanation"],
                recommended_owner=config["owner"],
            )
        )

    items.sort(key=lambda item: (-item.score, item.finding_rule, item.files))
    summary = Counter(item.priority for item in items)
    return {
        "items": [to_jsonable(item) for item in items],
        "summary": {
            "total": len(items),
            "p0": summary.get("P0", 0),
            "p1": summary.get("P1", 0),
            "p2": summary.get("P2", 0),
        },
    }


def build_action_plan(triage_artifact: dict[str, object]) -> dict[str, object]:
    steps: list[PlanStep] = []

    for index, item in enumerate(triage_artifact.get("items", [])[:PLAN_WINDOW], start=1):
        config = FINDING_RULE_CONFIG.get(item["finding_rule"], FINDING_RULE_CONFIG["RULE_B"])
        steps.append(
            PlanStep(
                step_id=f"STEP-{index:02d}",
                title=config["title"],
                category=item["category"],
                priority=item["priority"],
                owner=config["owner"],
                files=item["files"],
                finding_rule=item["finding_rule"],
                rationale=item["rationale"],
                success_criteria=config["success_criteria"],
                rollback_conditions=config["rollback_conditions"],
                deterministic_tools=config["deterministic_tools"],
                guarded_by=MANDATORY_GUARDS,
            )
        )

    backlog = [
        {
            "finding_rule": item["finding_rule"],
            "rule_name": item["rule_name"],
            "priority": item["priority"],
        }
        for item in triage_artifact.get("items", [])[PLAN_WINDOW:]
    ]
    return {
        "strategy": "多 Agent 规划，确定性工具负责执行约束",
        "plan_window": PLAN_WINDOW,
        "steps": [to_jsonable(step) for step in steps],
        "backlog": backlog,
    }


def run_planner_agent(
    *,
    repo_inventory: dict[str, object],
    findings_artifact: dict[str, object],
    triage_artifact: dict[str, object],
    deterministic_action_plan: dict[str, object],
    model_routing: dict[str, object],
    repo_files: list[str],
) -> dict[str, object]:
    assignment = _find_assignment(model_routing, "planner_triage_review")
    triage_with_generation = dict(triage_artifact)
    triage_with_generation["generation"] = {
        "mode": "deterministic",
        "source": "rule_engine",
    }
    fallback_action_plan = dict(deterministic_action_plan)
    fallback_action_plan["generation"] = {
        "mode": "deterministic",
        "source": "planner_fallback",
    }

    client = build_bailian_client()
    if client is None or assignment is None:
        return {
            "triage": triage_with_generation,
            "action_plan": fallback_action_plan,
            "planner_agent": _planner_runtime(
                assignment=assignment,
                mode="deterministic_fallback",
                used_live_llm=False,
                error=None,
                response_id=None,
            ),
        }

    payload = {
        "repo_inventory": repo_inventory,
        "findings": findings_artifact,
        "triage": triage_artifact,
        "deterministic_action_plan": deterministic_action_plan,
        "constraints": {
            "max_steps": PLAN_WINDOW,
            "available_files": repo_files,
            "mandatory_guards": MANDATORY_GUARDS,
            "non_goals": [
                "不要执行代码修改",
                "不要提出自动合并",
                "不要绕过确定性策略或工具检查",
            ],
        },
    }

    try:
        response = client.chat_json(
            model=assignment["api_model"],
            system_prompt=_planner_system_prompt(),
            user_payload=payload,
            temperature=0.1,
            max_tokens=1800,
        )
        action_plan = _sanitize_action_plan(
            response["json"],
            deterministic_action_plan=deterministic_action_plan,
            triage_artifact=triage_artifact,
            repo_files=set(repo_files),
        )
        action_plan["generation"] = {
            "mode": "llm",
            "provider": assignment["provider"],
            "model": assignment["api_model"],
        }
        return {
            "triage": triage_with_generation,
            "action_plan": action_plan,
            "planner_agent": _planner_runtime(
                assignment=assignment,
                mode="llm",
                used_live_llm=True,
                error=None,
                response_id=response["id"],
            ),
        }
    except Exception as exc:
        return {
            "triage": triage_with_generation,
            "action_plan": fallback_action_plan,
            "planner_agent": _planner_runtime(
                assignment=assignment,
                mode="deterministic_fallback",
                used_live_llm=False,
                error=provider_request_error(exc),
                response_id=None,
            ),
        }


def _priority_for_score(score: int) -> str:
    if score >= 90:
        return "P0"
    if score >= 60:
        return "P1"
    return "P2"


def _find_assignment(model_routing: dict[str, object], role: str) -> dict[str, object] | None:
    for item in model_routing.get("assignments", []):
        if item.get("role") == role:
            return item
    return None


def _planner_runtime(
    *,
    assignment: dict[str, object] | None,
    mode: str,
    used_live_llm: bool,
    error: str | None,
    response_id: str | None,
) -> dict[str, object]:
    return {
        "role": "planner_triage_review",
        "mode": mode,
        "used_live_llm": used_live_llm,
        "provider": assignment["provider"] if assignment else None,
        "model": assignment["api_model"] if assignment else None,
        "response_id": response_id,
        "error": error,
    }


def _planner_system_prompt() -> str:
    return (
        "You are the Planner Agent in a technical-debt cleanup system.\n"
        "Use only the repository evidence provided by the user payload.\n"
        "Return JSON only.\n"
        "All natural-language string fields must be written in Simplified Chinese.\n"
        "Do not propose automatic code execution.\n"
        "Keep the plan bounded, concrete, and file-scoped.\n"
        "Use only files from the provided available_files list.\n"
        "Output shape:\n"
        "{\n"
        '  "strategy": string,\n'
        '  "steps": [\n'
        "    {\n"
        '      "title": string,\n'
        '      "category": string,\n'
        '      "priority": "P0" | "P1" | "P2",\n'
        '      "owner": string,\n'
        '      "files": [string],\n'
        '      "finding_rule": string,\n'
        '      "rationale": string,\n'
        '      "success_criteria": [string],\n'
        '      "rollback_conditions": [string],\n'
        '      "deterministic_tools": [string],\n'
        '      "guarded_by": [string]\n'
        "    }\n"
        "  ],\n"
        '  "backlog": [\n'
        '    {"finding_rule": string, "rule_name": string, "priority": "P0" | "P1" | "P2"}\n'
        "  ]\n"
        "}"
    )


def _sanitize_action_plan(
    llm_output: dict[str, object],
    *,
    deterministic_action_plan: dict[str, object],
    triage_artifact: dict[str, object],
    repo_files: set[str],
) -> dict[str, object]:
    deterministic_steps = deterministic_action_plan.get("steps", [])
    triage_map = {item["finding_rule"]: item for item in triage_artifact.get("items", [])}
    steps: list[dict[str, object]] = []

    raw_steps = llm_output.get("steps")
    if isinstance(raw_steps, list):
        for index, raw_step in enumerate(raw_steps[:PLAN_WINDOW], start=1):
            if not isinstance(raw_step, dict):
                continue
            step = _sanitize_step(
                raw_step,
                index=index,
                triage_map=triage_map,
                deterministic_steps=deterministic_steps,
                repo_files=repo_files,
            )
            if step:
                steps.append(step)

    if not steps:
        steps = deterministic_steps

    raw_backlog = llm_output.get("backlog")
    if isinstance(raw_backlog, list):
        backlog = [
            {
                "finding_rule": item.get("finding_rule"),
                "rule_name": item.get("rule_name"),
                "priority": item.get("priority") if item.get("priority") in ALLOWED_PRIORITIES else "P2",
            }
            for item in raw_backlog
            if isinstance(item, dict) and item.get("finding_rule") and item.get("rule_name")
        ]
    else:
        backlog = deterministic_action_plan.get("backlog", [])

    strategy = llm_output.get("strategy")
    if not isinstance(strategy, str) or not strategy.strip():
        strategy = deterministic_action_plan.get("strategy", "LLM 辅助规划")

    return {
        "strategy": strategy.strip(),
        "plan_window": len(steps),
        "steps": steps,
        "backlog": backlog,
    }


def _sanitize_step(
    raw_step: dict[str, object],
    *,
    index: int,
    triage_map: dict[str, dict[str, object]],
    deterministic_steps: list[dict[str, object]],
    repo_files: set[str],
) -> dict[str, object] | None:
    finding_rule = raw_step.get("finding_rule")
    if not isinstance(finding_rule, str) or finding_rule not in triage_map:
        if index - 1 < len(deterministic_steps):
            finding_rule = deterministic_steps[index - 1]["finding_rule"]
        else:
            return None

    triage_item = triage_map[finding_rule]
    config = FINDING_RULE_CONFIG.get(finding_rule, FINDING_RULE_CONFIG["RULE_B"])
    fallback_step = next(
        (item for item in deterministic_steps if item.get("finding_rule") == finding_rule),
        _config_to_step(config, triage_item, index),
    )

    raw_files = raw_step.get("files")
    if isinstance(raw_files, list):
        files = [file for file in raw_files if isinstance(file, str) and file in repo_files]
    else:
        files = []
    if not files:
        files = fallback_step["files"]

    priority = raw_step.get("priority")
    if priority not in ALLOWED_PRIORITIES:
        priority = triage_item["priority"]

    return {
        "step_id": f"STEP-{index:02d}",
        "title": _non_empty_text(raw_step.get("title"), fallback_step["title"]),
        "category": _non_empty_text(raw_step.get("category"), triage_item["category"]),
        "priority": priority,
        "owner": _non_empty_text(raw_step.get("owner"), fallback_step["owner"]),
        "files": files,
        "finding_rule": finding_rule,
        "rationale": _non_empty_text(raw_step.get("rationale"), triage_item["rationale"]),
        "success_criteria": _string_list(raw_step.get("success_criteria"), fallback_step["success_criteria"]),
        "rollback_conditions": _string_list(
            raw_step.get("rollback_conditions"),
            fallback_step["rollback_conditions"],
        ),
        "deterministic_tools": _string_list(
            raw_step.get("deterministic_tools"),
            fallback_step["deterministic_tools"],
        ),
        "guarded_by": _merge_guards(raw_step.get("guarded_by")),
    }


def _config_to_step(config: dict[str, object], triage_item: dict[str, object], index: int) -> dict[str, object]:
    return {
        "step_id": f"STEP-{index:02d}",
        "title": config["title"],
        "category": triage_item["category"],
        "priority": triage_item["priority"],
        "owner": config["owner"],
        "files": triage_item["files"],
        "finding_rule": triage_item["finding_rule"],
        "rationale": triage_item["rationale"],
        "success_criteria": config["success_criteria"],
        "rollback_conditions": config["rollback_conditions"],
        "deterministic_tools": config["deterministic_tools"],
        "guarded_by": MANDATORY_GUARDS,
    }


def _non_empty_text(value: object, fallback: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _string_list(value: object, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return items or fallback


def _merge_guards(value: object) -> list[str]:
    guards = _string_list(value, [])
    return list(dict.fromkeys([*MANDATORY_GUARDS, *guards]))
