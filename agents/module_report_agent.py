from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

from common.helpers import find_assignment, is_test_file, non_empty_text, string_list
from common.log import get_logger
from llm.client import build_bailian_client, provider_request_error
from models.schema import RepoContext

log = get_logger("decoupling.module_report")
GIT_SUBPROCESS_TIMEOUT = 30
PRIORITY_WEIGHTS_PATH = Path(__file__).resolve().parents[1] / "config" / "priority_weights.json"

GIT_HOTNESS_COMMIT_LIMIT = 200
MAX_DETAILED_MODULE_REPORTS = 5
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}
VALIDATOR_STATUSES = {"confirmed", "needs_review", "rejected"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
PLANNER_PRIORITIES = {"high", "medium", "low"}
CRITIC_STATUSES = {"approved", "needs_review", "blocked"}
RISK_LEVELS = {"high", "medium", "low"}


def build_module_inventory(
    *,
    context: RepoContext,
    tool_results: dict[str, object],
    validated_findings: dict[str, object],
) -> dict[str, object]:
    import_counts = {
        item["file"]: len(item["imports"])
        for item in tool_results["import_graph"]["files"]
    }
    definition_counts = {
        item["file"]: len(item["definitions"])
        for item in tool_results["definitions"]["files"]
    }
    db_counts = {
        item["file"]: item["signal_count"]
        for item in tool_results["db_usage"]["files"]
    }
    global_counts = {
        item["file"]: item["risk_count"]
        for item in tool_results["global_state"]["files"]
    }
    env_counts: dict[str, int] = {}
    for item in tool_results["env_usage"]["reads"]:
        env_counts[item["file"]] = env_counts.get(item["file"], 0) + 1

    file_to_module: dict[str, str] = {}
    modules: dict[str, dict[str, object]] = {}
    for parsed in context.files:
        module_name = _module_bucket(parsed.relative_path, parsed.package_name, parsed.module_name)
        file_to_module[parsed.relative_path] = module_name
        module_entry = modules.setdefault(
            module_name,
            {
                "module": module_name,
                "layer": _classify_layer(module_name, parsed.relative_path),
                "files": [],
                "metrics": Counter(),
                "upstream_modules": set(),
                "downstream_modules": set(),
                "cross_layer_dependencies": set(),
                "matching_test_files": set(),
                "related_findings": [],
            },
        )
        module_entry["files"].append(parsed.relative_path)
        module_entry["metrics"]["file_count"] += 1
        module_entry["metrics"]["import_count"] += import_counts.get(parsed.relative_path, 0)
        module_entry["metrics"]["definition_count"] += definition_counts.get(parsed.relative_path, 0)
        module_entry["metrics"]["env_read_count"] += env_counts.get(parsed.relative_path, 0)
        module_entry["metrics"]["db_signal_count"] += db_counts.get(parsed.relative_path, 0)
        module_entry["metrics"]["global_risk_count"] += global_counts.get(parsed.relative_path, 0)
        if is_test_file(parsed.relative_path):
            module_entry["metrics"]["test_file_count"] += 1

    for parsed in context.files:
        if not is_test_file(parsed.relative_path):
            continue
        for module_name, module_entry in modules.items():
            if _looks_like_matching_test(module_name, parsed.relative_path):
                module_entry["matching_test_files"].add(parsed.relative_path)

    for edge in tool_results["import_graph"].get("local_edges", []):
        source_module = file_to_module.get(edge["source"])
        target_module = file_to_module.get(edge["target"])
        if not source_module or not target_module or source_module == target_module:
            continue
        modules[source_module]["downstream_modules"].add(target_module)
        modules[target_module]["upstream_modules"].add(source_module)
        if modules[source_module]["layer"] != modules[target_module]["layer"]:
            modules[source_module]["cross_layer_dependencies"].add(target_module)

    for finding in validated_findings.get("findings", []):
        for file_path in finding.get("files", []):
            module_name = file_to_module.get(file_path)
            if module_name is None:
                continue
            modules[module_name]["related_findings"].append(
                {
                    "rule_id": finding["rule_id"],
                    "rule_name": finding["rule_name"],
                    "severity": finding["severity"],
                    "confirmation_status": finding["confirmation_status"],
                    "confidence": finding["confidence"],
                    "files": finding["files"],
                    "evidence": finding["evidence"],
                }
            )

    git_hotness = _collect_git_hotness(context.root)
    inventory_items: list[dict[str, object]] = []
    for module_name, module_entry in sorted(modules.items()):
        hotness = sum(git_hotness.get(file_path, 0) for file_path in module_entry["files"])
        metrics = module_entry["metrics"]
        metrics["upstream_count"] = len(module_entry["upstream_modules"])
        metrics["downstream_count"] = len(module_entry["downstream_modules"])
        metrics["cross_layer_dependency_count"] = len(module_entry["cross_layer_dependencies"])
        metrics["matching_test_file_count"] = len(module_entry["matching_test_files"])
        metrics["git_change_count_last_200_commits"] = hotness
        metrics["finding_count"] = len(module_entry["related_findings"])
        metrics["priority_score"] = _priority_score(metrics)

        priority, reasons = _priority_level(module_entry["layer"], metrics, module_entry["related_findings"])
        inventory_items.append(
            {
                "module": module_name,
                "layer": module_entry["layer"],
                "files": sorted(module_entry["files"]),
                "metrics": dict(metrics),
                "upstream_modules": sorted(module_entry["upstream_modules"]),
                "downstream_modules": sorted(module_entry["downstream_modules"]),
                "cross_layer_dependencies": sorted(module_entry["cross_layer_dependencies"]),
                "matching_test_files": sorted(module_entry["matching_test_files"]),
                "related_findings": module_entry["related_findings"],
                "priority": priority,
                "priority_reasons": reasons,
            }
        )

    inventory_items.sort(
        key=lambda item: (
            PRIORITY_ORDER.get(item["priority"], 99),
            -item["metrics"]["priority_score"],
            item["module"],
        )
    )
    priority_counts = Counter(item["priority"] for item in inventory_items)
    return {
        "modules": inventory_items,
        "summary": {
            "total_modules": len(inventory_items),
            "p0": priority_counts.get("P0", 0),
            "p1": priority_counts.get("P1", 0),
            "p2": priority_counts.get("P2", 0),
        },
    }


def build_module_priority_groups(module_inventory: dict[str, object]) -> dict[str, object]:
    groups = {"P0": [], "P1": [], "P2": []}
    for item in module_inventory.get("modules", []):
        groups.setdefault(item["priority"], []).append(
            {
                "module": item["module"],
                "layer": item["layer"],
                "priority_score": item["metrics"]["priority_score"],
                "priority_reasons": item["priority_reasons"],
            }
        )
    return {
        "groups": groups,
        "summary": module_inventory["summary"],
    }


def build_module_lightweight_cards(module_inventory: dict[str, object]) -> dict[str, str]:
    return {
        item["module"]: _render_lightweight_card(item)
        for item in module_inventory.get("modules", [])
    }


def build_module_deep_reviews(
    *,
    module_inventory: dict[str, object],
    model_routing: dict[str, object],
) -> dict[str, object]:
    modules = _detailed_modules(module_inventory)
    client = build_bailian_client()
    validator_assignment = find_assignment(model_routing, "finding_validation")
    planner_assignment = find_assignment(model_routing, "planner_triage_review")
    critic_assignment = find_assignment(model_routing, "critic_review")

    reviewed_modules: list[dict[str, object]] = []
    llm_reviewed = 0
    for module_entry in modules:
        deterministic = _deterministic_deep_review(module_entry)
        if client is None or not validator_assignment or not planner_assignment or not critic_assignment:
            reviewed_modules.append(deterministic)
            continue

        errors: list[str] = []
        validator_review = deterministic["validator_review"]
        planner_review = deterministic["planner_review"]
        critic_review = deterministic["critic_review"]
        llm_successes = 0
        payload = _module_payload(module_entry)

        try:
            response = client.chat_json(
                model=validator_assignment["api_model"],
                system_prompt=_module_validator_prompt(),
                user_payload=payload,
                temperature=0,
                max_tokens=900,
            )
            validator_review = _sanitize_module_validator_review(response["json"], validator_review)
            llm_successes += 1
        except Exception as exc:
            errors.append(provider_request_error(exc))

        try:
            response = client.chat_json(
                model=planner_assignment["api_model"],
                system_prompt=_module_planner_prompt(),
                user_payload=payload,
                temperature=0.1,
                max_tokens=1100,
            )
            planner_review = _sanitize_module_planner_review(response["json"], planner_review)
            llm_successes += 1
        except Exception as exc:
            errors.append(provider_request_error(exc))

        try:
            response = client.chat_json(
                model=critic_assignment["api_model"],
                system_prompt=_module_critic_prompt(),
                user_payload=payload,
                temperature=0.1,
                max_tokens=900,
            )
            critic_review = _sanitize_module_critic_review(response["json"], critic_review)
            llm_successes += 1
        except Exception as exc:
            errors.append(provider_request_error(exc))

        mode = "llm" if llm_successes == 3 else "hybrid" if llm_successes > 0 else "deterministic_fallback"
        reviewed_modules.append(
            {
                "module": module_entry["module"],
                "priority": module_entry["priority"],
                "layer": module_entry["layer"],
                "validator_review": validator_review,
                "planner_review": planner_review,
                "critic_review": critic_review,
                "generation": {
                    "mode": mode,
                    "validator_model": validator_assignment["api_model"],
                    "planner_model": planner_assignment["api_model"],
                    "critic_model": critic_assignment["api_model"],
                    "errors": errors,
                },
            }
        )
        if mode != "deterministic_fallback":
            llm_reviewed += 1

    return {
        "modules": reviewed_modules,
        "summary": {
            "reviewed_modules": len(reviewed_modules),
            "llm_reviewed_modules": llm_reviewed,
            "deterministic_modules": len(reviewed_modules) - llm_reviewed,
        },
    }


def build_module_heavyweight_cards(
    module_inventory: dict[str, object],
    module_deep_reviews: dict[str, object],
) -> dict[str, str]:
    review_map = {item["module"]: item for item in module_deep_reviews.get("modules", [])}
    return {
        item["module"]: _render_heavyweight_card(item, review_map.get(item["module"]))
        for item in _detailed_modules(module_inventory)
    }


def build_module_reports(
    module_inventory: dict[str, object],
    module_deep_reviews: dict[str, object] | None = None,
) -> dict[str, str]:
    return build_module_heavyweight_cards(module_inventory, module_deep_reviews or {"modules": []})


def _render_lightweight_card(module_entry: dict[str, object]) -> str:
    metrics = module_entry["metrics"]
    recommendation = _module_recommendation(module_entry)
    lines = [
        f"# {module_entry['module']} 轻量卡",
        "",
        f"- 优先级：{module_entry['priority']}",
        f"- 所属层：{module_entry['layer']}",
        f"- 文件数：{metrics['file_count']}",
        f"- priority score：{metrics['priority_score']}",
        f"- import 数：{metrics['import_count']}",
        f"- finding 数：{metrics['finding_count']}",
        f"- 跨层依赖数：{metrics['cross_layer_dependency_count']}",
        f"- 测试映射文件数：{metrics['matching_test_file_count']}",
        f"- 建议动作：{', '.join(recommendation['recommended_actions'])}",
        "",
        "## 优先级原因",
        "",
    ]
    for reason in module_entry["priority_reasons"]:
        lines.append(f"- {reason}")
    lines.append("")
    return "\n".join(lines)


def _render_heavyweight_card(
    module_entry: dict[str, object],
    deep_review: dict[str, object] | None,
) -> str:
    metrics = module_entry["metrics"]
    related_findings = module_entry["related_findings"]
    coupling_types = _coupling_types(module_entry)
    recommendation = _module_recommendation(module_entry)
    validator_review = deep_review["validator_review"] if deep_review else _deterministic_validator_review(module_entry)
    planner_review = deep_review["planner_review"] if deep_review else _deterministic_planner_review(module_entry)
    critic_review = deep_review["critic_review"] if deep_review else _deterministic_critic_review(module_entry)
    generation_mode = deep_review["generation"]["mode"] if deep_review else "deterministic_fallback"

    lines = [
        f"# {module_entry['module']} 模块诊断卡",
        "",
        "## 1. 模块职责",
        "",
        f"- 所属层：{module_entry['layer']}",
        f"- 主要职责：{_responsibility_text(module_entry)}",
        f"- 核心入口：{_core_entry(module_entry['files']) or '未识别到明确入口'}",
        "",
        "## 2. 关键组成",
        "",
    ]
    for file_path in module_entry["files"][:10]:
        lines.append(f"- `{file_path}`")
    if len(module_entry["files"]) > 10:
        lines.append(f"- 其余 {len(module_entry['files']) - 10} 个文件已省略")

    lines.extend(
        [
            "",
            "## 3. 依赖关系",
            "",
            f"- 上游模块数：{metrics['upstream_count']}",
            f"- 下游模块数：{metrics['downstream_count']}",
            f"- 跨层依赖数：{metrics['cross_layer_dependency_count']}",
            f"- 环境变量接触点：{metrics['env_read_count']}",
            f"- 数据库/ORM 接触点：{metrics['db_signal_count']}",
            f"- 全局状态风险点：{metrics['global_risk_count']}",
            "",
        ]
    )
    if module_entry["upstream_modules"]:
        lines.append(f"- 上游依赖：{', '.join(module_entry['upstream_modules'][:8])}")
    if module_entry["downstream_modules"]:
        lines.append(f"- 下游依赖：{', '.join(module_entry['downstream_modules'][:8])}")

    lines.extend(
        [
            "",
            "## 4. 耦合分析",
            "",
        ]
    )
    if coupling_types:
        for item in coupling_types:
            lines.append(f"- {item}")
    else:
        lines.append("- 当前没有识别到明显的高风险耦合模式。")

    lines.extend(
        [
            "",
            "## 5. 深审增强",
            "",
            f"- 深审生成方式：{generation_mode}",
            "",
            "### Validator 复核",
            "",
            f"- 确认状态：{validator_review['confirmation_status']}",
            f"- 置信度：{validator_review['confidence']}",
            f"- 结论：{validator_review['summary']}",
        ]
    )
    for item in validator_review["key_evidence"]:
        lines.append(f"- 证据：{item}")

    lines.extend(
        [
            "",
            "### Planner 建议",
            "",
            f"- 是否建议修改：{planner_review['recommend_change']}",
            f"- 调整优先级：{planner_review['priority']}",
            f"- 总结：{planner_review['summary']}",
        ]
    )
    for item in planner_review["actions"]:
        lines.append(f"- 推荐改法：{item}")
    for item in planner_review["test_recommendations"]:
        lines.append(f"- 测试建议：{item}")

    lines.extend(
        [
            "",
            "### Critic 审查",
            "",
            f"- 审查状态：{critic_review['review_status']}",
            f"- 变更风险：{critic_review['risk_level']}",
            f"- 审查结论：{critic_review['summary']}",
        ]
    )
    for item in critic_review["concerns"]:
        lines.append(f"- 风险点：{item}")

    lines.extend(
        [
            "",
            "## 6. 修改建议",
            "",
            f"- 是否建议修改：{recommendation['should_change']}",
            f"- 修改优先级：{module_entry['priority']}",
            f"- 推荐改法：{', '.join(recommendation['recommended_actions'])}",
            f"- 修改风险：{recommendation['change_risk']}",
            "",
            "## 7. 证据",
            "",
            f"- priority score：{metrics['priority_score']}",
            f"- 定义数：{metrics['definition_count']}",
            f"- import 数：{metrics['import_count']}",
            f"- 近 200 次提交改动热度：{metrics['git_change_count_last_200_commits']}",
            f"- 匹配测试文件数：{metrics['matching_test_file_count']}",
        ]
    )
    if related_findings:
        lines.append("- 相关 findings：")
        for finding in related_findings[:6]:
            lines.append(
                f"  - {finding['rule_name']} / {finding['severity']} / "
                f"{finding['confirmation_status']} / {finding['confidence']}"
            )
    else:
        lines.append("- 相关 findings：无直接命中")

    lines.append("")
    return "\n".join(lines)


def _deterministic_deep_review(module_entry: dict[str, object]) -> dict[str, object]:
    return {
        "module": module_entry["module"],
        "priority": module_entry["priority"],
        "layer": module_entry["layer"],
        "validator_review": _deterministic_validator_review(module_entry),
        "planner_review": _deterministic_planner_review(module_entry),
        "critic_review": _deterministic_critic_review(module_entry),
        "generation": {
            "mode": "deterministic_fallback",
            "errors": [],
        },
    }


def _deterministic_validator_review(module_entry: dict[str, object]) -> dict[str, object]:
    metrics = module_entry["metrics"]
    if module_entry["priority"] == "P0":
        status = "confirmed"
        confidence = "high"
    elif metrics["finding_count"] > 0:
        status = "confirmed"
        confidence = "medium"
    else:
        status = "needs_review"
        confidence = "medium"

    evidence = []
    if metrics["db_signal_count"]:
        evidence.append(f"数据库/ORM 接触点 {metrics['db_signal_count']} 个")
    if metrics["global_risk_count"]:
        evidence.append(f"全局状态风险点 {metrics['global_risk_count']} 个")
    if metrics["cross_layer_dependency_count"]:
        evidence.append(f"跨层依赖 {metrics['cross_layer_dependency_count']} 个")
    if not evidence:
        evidence.append("当前主要依赖综合风险分排序进入重点观察队列")

    return {
        "confirmation_status": status,
        "confidence": confidence,
        "summary": "当前模块已具备进入重点审查的证据。"
        if status == "confirmed"
        else "当前模块值得继续观察，但仍建议结合更多上下文确认。",
        "key_evidence": evidence,
    }


def _deterministic_planner_review(module_entry: dict[str, object]) -> dict[str, object]:
    recommendation = _module_recommendation(module_entry)
    return {
        "recommend_change": "yes" if recommendation["should_change"] == "是" else "defer",
        "priority": "high" if module_entry["priority"] == "P0" else "medium" if module_entry["priority"] == "P1" else "low",
        "actions": recommendation["recommended_actions"],
        "test_recommendations": _test_recommendations(module_entry),
        "summary": "建议优先针对模块边界和测试薄弱点做受控治理。"
        if recommendation["should_change"] == "是"
        else "当前模块可先保持观察，暂不进入立即改造。",
    }


def _deterministic_critic_review(module_entry: dict[str, object]) -> dict[str, object]:
    concerns = []
    metrics = module_entry["metrics"]
    if metrics["matching_test_file_count"] == 0:
        concerns.append("测试映射较弱，改动前应先补最小回归测试。")
    if metrics["cross_layer_dependency_count"] > 0:
        concerns.append("跨层依赖存在，拆分时要避免新一轮边界回流。")
    if metrics["upstream_count"] >= 4:
        concerns.append("高扇入模块，改动影响面较大。")

    review_status = "needs_review" if concerns else "approved"
    risk_level = "high" if module_entry["priority"] == "P0" else "medium" if module_entry["priority"] == "P1" else "low"
    return {
        "review_status": review_status,
        "risk_level": risk_level,
        "concerns": concerns or ["当前模块没有额外阻断项，但仍应保持小步改动。"],
        "summary": "当前模块值得推进，但必须保持小范围、可验证的改动。"
        if review_status == "needs_review"
        else "当前模块可以进入下一步设计或重构计划阶段。",
    }


def _module_payload(module_entry: dict[str, object]) -> dict[str, object]:
    metrics = module_entry["metrics"]
    return {
        "module": module_entry["module"],
        "priority": module_entry["priority"],
        "layer": module_entry["layer"],
        "files": module_entry["files"][:12],
        "metrics": {
            "file_count": metrics["file_count"],
            "import_count": metrics["import_count"],
            "definition_count": metrics["definition_count"],
            "env_read_count": metrics["env_read_count"],
            "db_signal_count": metrics["db_signal_count"],
            "global_risk_count": metrics["global_risk_count"],
            "upstream_count": metrics["upstream_count"],
            "downstream_count": metrics["downstream_count"],
            "cross_layer_dependency_count": metrics["cross_layer_dependency_count"],
            "matching_test_file_count": metrics["matching_test_file_count"],
            "priority_score": metrics["priority_score"],
        },
        "priority_reasons": module_entry["priority_reasons"],
        "related_findings": module_entry["related_findings"][:6],
        "coupling_types": _coupling_types(module_entry),
        "recommended_actions": _module_recommendation(module_entry)["recommended_actions"],
    }


def _module_validator_prompt() -> str:
    return (
        "You are the Validator Agent for module review.\n"
        "Confirm whether this module deserves priority attention based only on the supplied payload.\n"
        "Return JSON only. All natural-language fields must be Simplified Chinese.\n"
        "Output shape:\n"
        "{\n"
        '  "confirmation_status": "confirmed" | "needs_review" | "rejected",\n'
        '  "confidence": "high" | "medium" | "low",\n'
        '  "summary": string,\n'
        '  "key_evidence": [string]\n'
        "}"
    )


def _module_planner_prompt() -> str:
    return (
        "You are the Planner Agent for module review.\n"
        "Given the module payload, propose bounded refactor directions without editing code.\n"
        "Return JSON only. All natural-language fields must be Simplified Chinese.\n"
        "Output shape:\n"
        "{\n"
        '  "recommend_change": "yes" | "defer",\n'
        '  "priority": "high" | "medium" | "low",\n'
        '  "actions": [string],\n'
        '  "test_recommendations": [string],\n'
        '  "summary": string\n'
        "}"
    )


def _module_critic_prompt() -> str:
    return (
        "You are the Critic Agent for module review.\n"
        "Review the suggested attention level and flag risks before any change.\n"
        "Return JSON only. All natural-language fields must be Simplified Chinese.\n"
        "Output shape:\n"
        "{\n"
        '  "review_status": "approved" | "needs_review" | "blocked",\n'
        '  "risk_level": "high" | "medium" | "low",\n'
        '  "concerns": [string],\n'
        '  "summary": string\n'
        "}"
    )


def _sanitize_module_validator_review(
    llm_output: dict[str, object],
    fallback: dict[str, object],
) -> dict[str, object]:
    status = llm_output.get("confirmation_status")
    confidence = llm_output.get("confidence")
    summary = llm_output.get("summary")
    key_evidence = llm_output.get("key_evidence")
    return {
        "confirmation_status": status if status in VALIDATOR_STATUSES else fallback["confirmation_status"],
        "confidence": confidence if confidence in CONFIDENCE_LEVELS else fallback["confidence"],
        "summary": non_empty_text(summary, fallback["summary"]),
        "key_evidence": string_list(key_evidence, fallback["key_evidence"]),
    }


def _sanitize_module_planner_review(
    llm_output: dict[str, object],
    fallback: dict[str, object],
) -> dict[str, object]:
    recommend_change = llm_output.get("recommend_change")
    priority = llm_output.get("priority")
    return {
        "recommend_change": recommend_change if recommend_change in {"yes", "defer"} else fallback["recommend_change"],
        "priority": priority if priority in PLANNER_PRIORITIES else fallback["priority"],
        "actions": string_list(llm_output.get("actions"), fallback["actions"]),
        "test_recommendations": string_list(
            llm_output.get("test_recommendations"),
            fallback["test_recommendations"],
        ),
        "summary": non_empty_text(llm_output.get("summary"), fallback["summary"]),
    }


def _sanitize_module_critic_review(
    llm_output: dict[str, object],
    fallback: dict[str, object],
) -> dict[str, object]:
    review_status = llm_output.get("review_status")
    risk_level = llm_output.get("risk_level")
    return {
        "review_status": review_status if review_status in CRITIC_STATUSES else fallback["review_status"],
        "risk_level": risk_level if risk_level in RISK_LEVELS else fallback["risk_level"],
        "concerns": string_list(llm_output.get("concerns"), fallback["concerns"]),
        "summary": non_empty_text(llm_output.get("summary"), fallback["summary"]),
    }


def _test_recommendations(module_entry: dict[str, object]) -> list[str]:
    recommendations = []
    metrics = module_entry["metrics"]
    if metrics["matching_test_file_count"] == 0:
        recommendations.append("先补最小 characterization tests。")
    if metrics["db_signal_count"] > 0:
        recommendations.append("补接口层到服务层边界的回归测试。")
    if metrics["global_risk_count"] > 0:
        recommendations.append("补共享状态行为测试和并发/顺序测试。")
    if not recommendations:
        recommendations.append("保持现有测试覆盖，并补充一个模块级 smoke case。")
    return recommendations


def _priority_score(metrics: Counter) -> int:
    w = _load_priority_weights()
    return (
        metrics["file_count"] * w["file_count"]
        + metrics["import_count"] * w["import_count"]
        + metrics["definition_count"] * w["definition_count"]
        + metrics["upstream_count"] * w["upstream_count"]
        + metrics["downstream_count"] * w["downstream_count"]
        + metrics["cross_layer_dependency_count"] * w["cross_layer_dependency_count"]
        + metrics["db_signal_count"] * w["db_signal_count"]
        + metrics["global_risk_count"] * w["global_risk_count"]
        + metrics["env_read_count"] * w["env_read_count"]
        + min(metrics["git_change_count_last_200_commits"], w["git_change_cap"])
        + (w["no_test_penalty"] if metrics["matching_test_file_count"] == 0 else 0)
        + metrics["finding_count"] * w["finding_count"]
    )


_CACHED_WEIGHTS: dict[str, int] | None = None


def _load_priority_weights() -> dict[str, int]:
    global _CACHED_WEIGHTS
    if _CACHED_WEIGHTS is not None:
        return _CACHED_WEIGHTS

    defaults = {
        "file_count": 1, "import_count": 1, "definition_count": 1,
        "upstream_count": 2, "downstream_count": 1, "cross_layer_dependency_count": 2,
        "db_signal_count": 3, "global_risk_count": 3, "env_read_count": 1,
        "git_change_cap": 10, "no_test_penalty": 4, "finding_count": 2,
    }
    if PRIORITY_WEIGHTS_PATH.exists():
        try:
            raw = json.loads(PRIORITY_WEIGHTS_PATH.read_text(encoding="utf-8"))
            loaded = raw.get("weights", {})
            for key in defaults:
                if key in loaded and isinstance(loaded[key], (int, float)):
                    defaults[key] = int(loaded[key])
        except (OSError, json.JSONDecodeError):
            log.warning("Failed to load priority weights, using defaults")

    _CACHED_WEIGHTS = defaults
    return _CACHED_WEIGHTS


def _priority_level(
    layer: str,
    metrics: Counter,
    related_findings: list[dict[str, object]],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    high_severity_count = sum(1 for item in related_findings if item["severity"] == "high")
    if high_severity_count:
        reasons.append(f"存在 {high_severity_count} 个高严重度 finding")
    if metrics["db_signal_count"] and layer == "interface":
        reasons.append("接口层直接接触数据库信号")
    if metrics["cross_layer_dependency_count"] >= 2:
        reasons.append("跨层依赖较重")
    if metrics["matching_test_file_count"] == 0:
        reasons.append("测试映射较弱")
    if metrics["git_change_count_last_200_commits"] >= 5:
        reasons.append("最近改动热度较高")

    if high_severity_count or (metrics["db_signal_count"] and layer == "interface") or metrics["priority_score"] >= 18:
        return "P0", reasons or ["综合风险分较高"]
    if metrics["priority_score"] >= 9 or metrics["finding_count"] >= 1:
        return "P1", reasons or ["建议进入重点诊断队列"]
    return "P2", reasons or ["当前风险较低，暂时挂起"]


def _detailed_modules(module_inventory: dict[str, object]) -> list[dict[str, object]]:
    return [
        item
        for item in module_inventory.get("modules", [])
        if item["priority"] in {"P0", "P1"}
    ][:MAX_DETAILED_MODULE_REPORTS]


def _module_bucket(relative_path: str, package_name: str, module_name: str) -> str:
    if is_test_file(relative_path):
        return package_name or module_name
    if package_name:
        return package_name
    if "." in module_name:
        return module_name.rsplit(".", 1)[0]
    return module_name


def _classify_layer(module_name: str, relative_path: str) -> str:
    lower = f"{module_name} {relative_path}".lower()
    if is_test_file(relative_path):
        return "test"
    if any(keyword in lower for keyword in ("route", "router", "handler", "controller", "view", "api")):
        return "interface"
    if any(keyword in lower for keyword in ("service", "usecase", "workflow")):
        return "service"
    if any(keyword in lower for keyword in ("repo", "repository", "dao", "model", "orm", "db")):
        return "data_access"
    if any(keyword in lower for keyword in ("config", "settings", "env")):
        return "configuration"
    if any(keyword in lower for keyword in ("utils", "common", "helper")):
        return "shared"
    if any(keyword in lower for keyword in ("state", "cache", "store")):
        return "state"
    return "domain"


def _looks_like_matching_test(module_name: str, test_path: str) -> bool:
    tail = module_name.rsplit(".", 1)[-1].lower()
    return bool(tail) and tail in test_path.lower()


def _responsibility_text(module_entry: dict[str, object]) -> str:
    layer_to_text = {
        "interface": "对外暴露请求处理或控制层能力。",
        "service": "承接业务编排或用例层逻辑。",
        "data_access": "负责数据访问、模型或持久化接触点。",
        "configuration": "负责配置、环境变量或启动参数边界。",
        "shared": "提供共享工具或跨模块复用能力。",
        "state": "管理缓存、共享状态或模块级存储。",
        "test": "承载测试或验证逻辑。",
        "domain": "承载领域逻辑或一般模块能力。",
    }
    return layer_to_text.get(module_entry["layer"], "承载一般模块能力。")


def _core_entry(files: list[str]) -> str | None:
    for file_path in files:
        lower = file_path.lower()
        if lower.endswith(("main.py", "app.py", "api.py")) or "__init__.py" not in lower:
            return file_path
    return files[0] if files else None


def _coupling_types(module_entry: dict[str, object]) -> list[str]:
    metrics = module_entry["metrics"]
    coupling: list[str] = []
    if module_entry["layer"] == "interface" and metrics["db_signal_count"] > 0:
        coupling.append("控制层直接接触数据库或 ORM 信号，边界下沉不够。")
    if metrics["cross_layer_dependency_count"] > 0:
        coupling.append(f"存在 {metrics['cross_layer_dependency_count']} 个跨层依赖，模块边界较重。")
    if metrics["global_risk_count"] > 0:
        coupling.append("存在共享状态或可变全局风险。")
    if metrics["env_read_count"] > 1:
        coupling.append("环境变量读取较分散，配置边界不清。")
    if module_entry["layer"] == "shared" and metrics["downstream_count"] >= 3:
        coupling.append("共享模块扇入较高，可能反向承载了业务能力。")
    if metrics["upstream_count"] >= 4:
        coupling.append("高扇入模块，修改可能带来较大影响面。")
    if metrics["downstream_count"] >= 4:
        coupling.append("高扇出模块，说明编排职责或依赖范围较重。")
    return coupling


def _module_recommendation(module_entry: dict[str, object]) -> dict[str, object]:
    priority = module_entry["priority"]
    metrics = module_entry["metrics"]
    actions: list[str] = []
    if metrics["db_signal_count"] and module_entry["layer"] == "interface":
        actions.append("下沉依赖")
    if metrics["cross_layer_dependency_count"] > 0:
        actions.append("拆职责")
    if metrics["env_read_count"] > 1:
        actions.append("提取配置")
    if metrics["matching_test_file_count"] == 0:
        actions.append("补测试")
    if metrics["global_risk_count"] > 0:
        actions.append("隔离状态")
    if not actions:
        actions.append("暂缓")

    return {
        "should_change": "是" if priority in {"P0", "P1"} else "暂缓",
        "recommended_actions": actions,
        "change_risk": "高" if priority == "P0" else "中" if priority == "P1" else "低",
    }




def _collect_git_hotness(repo_root: Path) -> dict[str, int]:
    if not (repo_root / ".git").exists():
        return {}
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "log",
                f"--max-count={GIT_HOTNESS_COMMIT_LIMIT}",
                "--pretty=format:",
                "--name-only",
                "--",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_SUBPROCESS_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        log.warning("git log command failed or timed out for %s", repo_root)
        return {}
    if completed.returncode != 0:
        return {}

    counts: dict[str, int] = {}
    for line in completed.stdout.splitlines():
        normalized = line.strip().replace("\\", "/")
        if normalized.endswith(".py"):
            counts[normalized] = counts.get(normalized, 0) + 1
    return counts


