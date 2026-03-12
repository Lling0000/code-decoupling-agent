from __future__ import annotations

from collections import Counter, defaultdict

from common.log import get_logger
from models.schema import Finding, to_jsonable
from rules.config import (
    ENV_RULE_EXCLUDED_PATH_KEYWORDS,
    HANDLER_PATH_KEYWORDS,
    OVERSIZED_CLASS_METHOD_THRESHOLD,
    OVERSIZED_FILE_LINE_THRESHOLD,
    UTILS_CONSUMER_PACKAGE_THRESHOLD,
    UTILS_OVERUSE_THRESHOLD,
)

CONFIDENCE_LABELS = {"high": "高", "medium": "中", "low": "低"}

log = get_logger("decoupling.rules_engine")


def detect_import_cycles(import_graph: dict[str, object]) -> list[list[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in import_graph.get("local_edges", []):
        source = edge["source"]
        target = edge["target"]
        if source == target:
            continue
        adjacency[source].add(target)
        adjacency.setdefault(target, set())

    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    components: list[list[str]] = []

    def strongconnect(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in adjacency.get(node, set()):
            if neighbor not in indices:
                strongconnect(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])

        if lowlinks[node] != indices[node]:
            return

        component: list[str] = []
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        if len(component) > 1:
            components.append(sorted(component))

    for node in sorted(adjacency):
        if node not in indices:
            strongconnect(node)

    return sorted(components, key=lambda item: (len(item), item))


def run_rules(
    import_graph: dict[str, object],
    env_usage: dict[str, object],
    db_usage: dict[str, object],
    utils_usage: dict[str, object],
    global_state: dict[str, object],
    cycles: list[list[str]] | None = None,
    definitions: dict[str, object] | None = None,
) -> dict[str, object]:
    findings: list[Finding] = []
    cycles = cycles if cycles is not None else detect_import_cycles(import_graph)

    findings.extend(_handler_db_findings(db_usage))
    findings.extend(_shared_env_findings(env_usage))
    findings.extend(_utils_overuse_findings(utils_usage))
    findings.extend(_global_state_findings(global_state))
    findings.extend(_cycle_findings(cycles))
    findings.extend(_oversized_file_findings(definitions))
    findings.extend(_cross_layer_db_findings(db_usage, import_graph))

    severity_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda item: (severity_order.get(item.severity, 99), item.rule_id, item.files))
    counts = Counter(finding.severity for finding in findings)

    log.info("rules engine: %d findings generated (high=%d, medium=%d, low=%d)",
             len(findings), counts.get("high", 0), counts.get("medium", 0), counts.get("low", 0))

    return {
        "findings": [to_jsonable(finding) for finding in findings],
        "counts": {
            "high": counts.get("high", 0),
            "medium": counts.get("medium", 0),
            "low": counts.get("low", 0),
            "total": len(findings),
        },
    }


def _handler_db_findings(db_usage: dict[str, object]) -> list[Finding]:
    findings: list[Finding] = []

    for file_entry in db_usage.get("files", []):
        file_path = file_entry["file"]
        if not _is_handler_path(file_path):
            continue

        operational_signals = [
            signal
            for signal in file_entry.get("signals", [])
            if signal["kind"] in {"call", "attribute"} and signal["confidence"] in {"medium", "high"}
        ]
        if not operational_signals:
            continue

        severity = "high" if any(signal["confidence"] == "high" for signal in operational_signals) else "medium"
        evidence = [
            f'{signal["signal"]}（第 {signal["line"]} 行，置信度={CONFIDENCE_LABELS.get(signal["confidence"], signal["confidence"]) }）'
            for signal in operational_signals[:3]
        ]
        findings.append(
            Finding(
                rule_id="RULE_A",
                rule_name="Handler/Controller 直接访问数据库",
                severity=severity,
                files=[file_path],
                evidence=evidence,
                explanation=(
                    "请求层文件中直接出现数据库或 ORM 操作，通常说明业务边界和数据访问边界没有被清晰隔离。"
                ),
                suggestion=(
                    "建议把数据库访问下沉到显式的 service 或 repository 层，让 handler/controller 只负责请求编排。"
                ),
            )
        )

    return findings


def _shared_env_findings(env_usage: dict[str, object]) -> list[Finding]:
    findings: list[Finding] = []

    for variable in env_usage.get("variables", []):
        business_files = [file for file in variable["files"] if _is_business_path(file)]
        excluded_files = [file for file in variable["files"] if file not in business_files]
        if len(business_files) <= 1:
            continue

        severity = "high" if len(business_files) >= 4 else "medium"
        evidence = [f'{variable["name"]} 在 {len(business_files)} 个业务文件中被直接读取']
        if excluded_files:
            evidence.append(f"已忽略 {len(excluded_files)} 个配置或测试文件中的读取")
        findings.append(
            Finding(
                rule_id="RULE_B",
                rule_name="同一环境变量在多个文件中被直接读取",
                severity=severity,
                files=business_files,
                evidence=evidence,
                explanation=(
                    "同一个环境变量在多个业务文件中被直接读取，会让配置入口分散，增加修改和排查时的耦合成本。"
                ),
                suggestion=(
                    "建议把环境变量读取集中到专门的配置模块，再把配置对象传入业务代码。"
                ),
            )
        )

    return findings


def _utils_overuse_findings(utils_usage: dict[str, object]) -> list[Finding]:
    findings: list[Finding] = []

    for module in utils_usage.get("modules", []):
        if module["file_count"] < UTILS_OVERUSE_THRESHOLD:
            continue
        if module.get("consumer_package_count", 0) < UTILS_CONSUMER_PACKAGE_THRESHOLD:
            continue

        severity = "high" if module["file_count"] >= UTILS_OVERUSE_THRESHOLD + 3 else "medium"
        findings.append(
            Finding(
                rule_id="RULE_C",
                rule_name="共享 Utils 模块被过度依赖",
                severity=severity,
                files=module["files"],
                evidence=[
                    (
                        f'{module["module"]} 被 {module["file_count"]} 个文件依赖，覆盖 {module["consumer_package_count"]} 个包'
                    )
                ],
                explanation=(
                    "共享 utils/common/helper 模块被多个包横向依赖，通常意味着跨领域的隐式耦合正在累积。"
                ),
                suggestion=(
                    "建议按领域边界拆分共享工具模块，把真正通用的能力和领域能力分开。"
                ),
            )
        )

    return findings


def _global_state_findings(global_state: dict[str, object]) -> list[Finding]:
    findings: list[Finding] = []

    for file_entry in global_state.get("files", []):
        actionable_globals = [
            item for item in file_entry.get("globals", []) if item.get("finding_candidate")
        ]
        if not actionable_globals:
            continue

        severity = "high" if any(item["risk"] == "high" for item in actionable_globals) else "medium"
        evidence = [
            (
                f'{item["name"]} ({item["kind"]}，第 {item["line"]} 行，变更次数={item["mutation_count"]})'
            )
            for item in actionable_globals[:3]
        ]
        findings.append(
            Finding(
                rule_id="RULE_D",
                rule_name="疑似可变全局状态",
                severity=severity,
                files=[file_entry["file"]],
                evidence=evidence,
                explanation=(
                    "模块级可变对象在函数作用域中被修改，说明共享状态正在跨函数传播，副作用会更难追踪。"
                ),
                suggestion=(
                    "建议把共享状态封装到显式对象、工厂或依赖注入边界中，让写入路径更清晰、更易测试。"
                ),
            )
        )

    return findings


def _cycle_findings(cycles: list[list[str]]) -> list[Finding]:
    findings: list[Finding] = []

    for cycle in cycles:
        severity = "high" if len(cycle) >= 4 else "medium"
        findings.append(
            Finding(
                rule_id="RULE_E",
                rule_name="检测到简单循环 Import",
                severity=severity,
                files=cycle,
                evidence=[" -> ".join(cycle)],
                explanation=(
                    "发现了强连通的 import 组件。循环依赖通常会增加初始化脆弱性，并让模块边界更难维护。"
                ),
                suggestion=(
                    "建议提取稳定的共享接口或中间边界模块，把双向依赖重新拆回单向依赖。"
                ),
            )
        )

    return findings


def _oversized_file_findings(definitions: dict[str, object] | None) -> list[Finding]:
    if definitions is None:
        return []

    findings: list[Finding] = []
    for file_entry in definitions.get("files", []):
        file_path = file_entry["file"]
        line_count = file_entry.get("line_count", 0)
        if line_count < OVERSIZED_FILE_LINE_THRESHOLD:
            continue

        oversized_classes = [
            defn
            for defn in file_entry.get("definitions", [])
            if defn.get("type") == "class" and defn.get("method_count", 0) >= OVERSIZED_CLASS_METHOD_THRESHOLD
        ]

        evidence = [f"文件共 {line_count} 行，超过 {OVERSIZED_FILE_LINE_THRESHOLD} 行阈值"]
        for cls in oversized_classes[:2]:
            evidence.append(f"类 {cls['name']} 包含 {cls['method_count']} 个方法")

        findings.append(
            Finding(
                rule_id="RULE_F",
                rule_name="文件或类规模过大",
                severity="medium",
                files=[file_path],
                evidence=evidence,
                explanation=(
                    "单文件行数过多或单个类方法数过多，通常说明职责不够聚焦，难以测试和维护。"
                ),
                suggestion=(
                    "建议按职责边界拆分大文件，将大类中可独立的方法组提取为单独的模块或服务类。"
                ),
            )
        )

    return findings


def _cross_layer_db_findings(db_usage: dict[str, object], import_graph: dict[str, object]) -> list[Finding]:
    """Detect non-handler files in service/domain layers that directly access DB."""
    findings: list[Finding] = []

    for file_entry in db_usage.get("files", []):
        file_path = file_entry["file"]
        # Skip handlers (already covered by RULE_A) and obvious data-access layers.
        if _is_handler_path(file_path):
            continue
        if _is_data_access_path(file_path):
            continue

        high_signals = [
            signal
            for signal in file_entry.get("signals", [])
            if signal["kind"] in {"call", "attribute"} and signal["confidence"] == "high"
        ]
        if len(high_signals) < 2:
            continue

        evidence = [
            f'{signal["signal"]}（第 {signal["line"]} 行）'
            for signal in high_signals[:3]
        ]
        findings.append(
            Finding(
                rule_id="RULE_G",
                rule_name="非数据层文件直接执行数据库操作",
                severity="medium",
                files=[file_path],
                evidence=evidence,
                explanation=(
                    "服务层或领域层文件直接包含多个高置信度数据库操作，说明数据访问没有被下沉到独立的数据访问层。"
                ),
                suggestion=(
                    "建议把数据库操作收敛到 repository/dao 层，让业务逻辑通过抽象接口访问数据。"
                ),
            )
        )

    return findings


def _is_handler_path(file_path: str) -> bool:
    lower_path = file_path.lower()
    return any(keyword in lower_path for keyword in HANDLER_PATH_KEYWORDS)


def _is_data_access_path(file_path: str) -> bool:
    lower_path = file_path.lower()
    return any(keyword in lower_path for keyword in ("repo", "repository", "dao", "model", "orm", "db"))


def _is_business_path(file_path: str) -> bool:
    lower_path = file_path.lower().replace("\\", "/")
    parts = lower_path.split("/")
    filename = parts[-1]
    # Strip .py extension for filename checks.
    filename_stem = filename[:-3] if filename.endswith(".py") else filename
    for keyword in ENV_RULE_EXCLUDED_PATH_KEYWORDS:
        if keyword.endswith(".py"):
            # Exact filename match for entries like "conftest.py" or "manage.py".
            if filename == keyword:
                return False
        elif keyword in parts[:-1]:
            # Directory component match (e.g. "tests" in path).
            return False
        elif filename_stem == keyword:
            # Exact stem match (e.g. filename is "config.py" and keyword is "config").
            return False
        elif filename_stem.startswith(f"{keyword}_") and keyword in ("test", "tests"):
            # Only exclude "test_*" prefixed filenames, not "config_helper" etc.
            return False
    return True
