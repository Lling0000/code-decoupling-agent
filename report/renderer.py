from __future__ import annotations

from pathlib import Path

from models.schema import RepoContext

SEVERITY_LABELS = {"high": "高", "medium": "中", "low": "低"}
RISK_LABELS = {"high": "高", "medium": "中", "low": "低"}
STATUS_LABELS = {
    "approved": "通过",
    "needs_review": "需要人工复核",
    "blocked": "已阻断",
    "confirmed": "已确认",
    "rejected": "已驳回",
}
MODE_LABELS = {
    "llm": "LLM",
    "deterministic": "确定性",
    "deterministic_fallback": "确定性回退",
    "hybrid": "混合",
    "thinking": "推理",
    "coding": "编码",
    "fast_generation": "快速生成",
    "retrieval": "检索",
}
ROLE_LABELS = {
    "governor_orchestration": "总控编排",
    "planner_triage_review": "规划与分诊",
    "finding_validation": "Finding 复核",
    "critic_review": "审查",
    "refactor_and_test_fix": "重构与测试补全",
    "summary_and_pr_copy": "摘要与说明生成",
    "embedding": "向量召回",
    "rerank": "重排",
}
AGENT_LABELS = {
    "Refactor Agent": "重构 Agent",
    "Planner Agent": "规划 Agent",
    "Critic Agent": "审查 Agent",
    "Policy Engine": "策略引擎",
    "Tool Runner": "工具执行器",
}


def render_summary(
    repo_root: Path,
    context: RepoContext,
    import_graph: dict[str, object],
    definitions: dict[str, object],
    call_graph: dict[str, object],
    env_usage: dict[str, object],
    db_usage: dict[str, object],
    utils_usage: dict[str, object],
    global_state: dict[str, object],
    findings: dict[str, object],
    validated_findings: dict[str, object],
    repo_inventory: dict[str, object],
    triage: dict[str, object],
    action_plan: dict[str, object],
    critic_review: dict[str, object],
    planner_agent: dict[str, object],
    critic_agent: dict[str, object],
    model_routing: dict[str, object],
) -> str:
    lines: list[str] = [
        "# 代码解耦诊断报告",
        "",
        f"仓库路径：`{repo_root}`",
        "",
        "## 扫描概览",
        "",
        f"- 已扫描 Python 文件数：{len(context.files)}",
        f"- 跳过的解析失败文件数：{len(context.scan_errors)}",
        f"- 原始 findings 数：{findings['counts']['total']}",
        f"- 经 Validator 复核后的可行动 findings 数：{validated_findings['summary']['actionable_finding_count']}",
        f"- 生成热点清单数：{len(repo_inventory['hotspots'])}",
        "",
        "## Import 依赖概览",
        "",
    ]

    import_heavy = sorted(
        import_graph.get("files", []),
        key=lambda item: len(item["imports"]),
        reverse=True,
    )[:5]
    if import_heavy:
        for item in import_heavy:
            lines.append(f"- `{item['file']}` 共有 {len(item['imports'])} 个 import")
    else:
        lines.append("- 未发现 import 语句")

    cycles = import_graph.get("cycles", [])
    if cycles:
        lines.append(f"- 识别到简单循环依赖：{len(cycles)} 组")
    else:
        lines.append("- 未识别到简单循环依赖")

    lines.extend(
        [
            "",
            "## 定义与调用概览",
            "",
            f"- 类定义数：{definitions['totals']['classes']}",
            f"- 函数定义数：{definitions['totals']['functions']}",
            f"- 方法定义数：{definitions['totals']['methods']}",
            f"- 近似调用边数：{len(call_graph['edges'])}",
            "",
            "## 环境变量使用",
            "",
        ]
    )

    if env_usage.get("variables"):
        for item in env_usage["variables"][:10]:
            lines.append(
                f"- `{item['name']}` 在 {item['file_count']} 个文件中被读取，共 {item['read_count']} 次"
            )
    else:
        lines.append("- 未发现直接环境变量读取")

    lines.extend(
        [
            "",
            "## 数据库访问信号",
            "",
        ]
    )
    db_files = [item for item in db_usage.get("files", []) if item["signal_count"] > 0]
    db_files.sort(key=lambda item: item["signal_count"], reverse=True)
    if db_files:
        for item in db_files[:10]:
            lines.append(f"- `{item['file']}` 命中 {item['signal_count']} 个数据库/ORM 信号")
    else:
        lines.append("- 未发现数据库或 ORM 访问信号")

    lines.extend(
        [
            "",
            "## 共享 Utils 依赖",
            "",
        ]
    )
    if utils_usage.get("modules"):
        for item in utils_usage["modules"][:10]:
            lines.append(
                f"- `{item['module']}` 被 {item['file_count']} 个文件依赖，覆盖 {item.get('consumer_package_count', 0)} 个包"
            )
    else:
        lines.append("- 未发现共享 utils/common/helper 依赖")

    lines.extend(
        [
            "",
            "## 全局状态风险",
            "",
        ]
    )
    risky_files = [item for item in global_state.get("files", []) if item["risk_count"] > 0]
    risky_files.sort(key=lambda item: item["risk_count"], reverse=True)
    if risky_files:
        for item in risky_files[:10]:
            lines.append(f"- `{item['file']}` 命中 {item['risk_count']} 个疑似全局状态风险")
    else:
        lines.append("- 未发现疑似可变全局状态")

    lines.extend(
        [
            "",
            "## 仓库理解",
            "",
        ]
    )
    if repo_inventory.get("hotspots"):
        for item in repo_inventory["hotspots"][:5]:
            lines.append(
                f"- `{item['file']}` 热点分数 {item['score']} "
                f"(imports={item['import_count']}, db={item['db_signal_count']}, globals={item['global_risk_count']})"
            )
    else:
        lines.append("- 未识别到明显热点")

    lines.extend(
        [
            "",
            "## Findings",
            "",
        ]
    )
    lines.append(
        f"- Validator 生成方式：{_label(MODE_LABELS, validated_findings.get('generation', {}).get('mode', 'deterministic_fallback'))}"
    )
    lines.append(
        f"- 已确认：{validated_findings['summary']['confirmed']}，需复核：{validated_findings['summary']['needs_review']}，已驳回：{validated_findings['summary']['rejected']}"
    )
    lines.append("")
    if validated_findings.get("findings"):
        for finding in validated_findings["findings"]:
            lines.append(f"### {finding['rule_name']}")
            lines.append("")
            lines.append(f"- 严重级别：{_label(SEVERITY_LABELS, finding['severity'])}")
            lines.append(f"- 确认状态：{_label(STATUS_LABELS, finding['confirmation_status'])}")
            lines.append(f"- 置信度：{_label(SEVERITY_LABELS, finding['confidence'])}")
            lines.append(f"- 文件：{', '.join(finding['files'])}")
            lines.append(f"- 证据：{'; '.join(finding['evidence'])}")
            lines.append(f"- 解释：{finding['explanation']}")
            lines.append(f"- 建议：{finding['suggestion']}")
            lines.append(f"- 验证说明：{finding['validation_reason']}")
            lines.append("")
    else:
        lines.append("- 未生成 findings")
        lines.append("")

    lines.extend(
        [
            "## 行动计划",
            "",
        ]
    )
    if action_plan.get("steps"):
        lines.append(f"- 计划策略：{action_plan['strategy']}")
        lines.append(f"- 当前展开步骤数：{len(action_plan['steps'])}")
        lines.append(
            f"- Planner 生成方式：{_label(MODE_LABELS, action_plan.get('generation', {}).get('mode', planner_agent['mode']))}"
        )
        for step in action_plan["steps"]:
            lines.append(
                f"- {step['step_id']} [{step['priority']}] {step['title']} "
                f"负责人={_label(AGENT_LABELS, step['owner'])} 涉及文件数={len(step['files'])}"
            )
    else:
        lines.append("- 未生成行动计划")

    lines.extend(
        [
            "",
            "## 审查结果",
            "",
            f"- 状态：{_label(STATUS_LABELS, critic_review['status'])}",
            f"- 风险等级：{_label(RISK_LABELS, critic_review['risk_level'])}",
            f"- 总结：{critic_review['summary']}",
            f"- 必需检查：{', '.join(critic_review['required_checks'])}",
            f"- Critic 生成方式：{_label(MODE_LABELS, critic_review.get('generation', {}).get('mode', critic_agent['mode']))}",
        ]
    )
    if critic_review["concerns"]:
        for concern in critic_review["concerns"]:
            lines.append(f"- 风险点：{concern}")
    else:
        lines.append("- 风险点：无")

    lines.extend(
        [
            "",
            "## 模型路由",
            "",
        ]
    )
    for item in model_routing.get("assignments", []):
        lines.append(
            f"- `{_label(ROLE_LABELS, item['role'])}` -> `{item['api_model']}` "
            f"via `{item['provider']}` ({_label(MODE_LABELS, item['mode'])})"
        )
    for provider in model_routing.get("providers", []):
        status = "已配置" if provider["configured"] else "缺少 API Key"
        lines.append(
            f"- Provider `{provider['provider_id']}` 的环境变量 `{provider['api_key_env']}` 状态：{status}"
        )
        lines.append(f"- Provider Base URL：`{provider['base_url']}`")

    lines.extend(
        [
            "",
            "## 局限性",
            "",
            "- 当前分析基于 AST，属于有意保持轻量化的近似静态分析。",
            "- 动态 import、运行时 monkey patch、反射和间接调用目前都无法精确解析。",
            "- 数据库访问检测仍然是信号式识别，仍可能存在少量误报或漏报。",
            "- 环境变量检测目前主要覆盖字符串字面量形式的常见读取模式。",
            "- 目前只有 Planner 和 Critic 可以走 live LLM，扫描、规则和策略判断仍然是确定性链路。",
            "- Planner 和 Critic 输出受 schema 约束，调用失败时会回退到确定性结果。",
        ]
    )
    if context.scan_errors:
        lines.append(f"- 有 {len(context.scan_errors)} 个文件因解析失败被跳过。")
    if triage["summary"]["total"] > len(action_plan.get("steps", [])):
        lines.append("- 当前只展开最高优先级的计划窗口，剩余问题保留在 backlog。")

    lines.append("")
    return "\n".join(lines)


def _label(mapping: dict[str, str], value: str) -> str:
    return mapping.get(value, value)
