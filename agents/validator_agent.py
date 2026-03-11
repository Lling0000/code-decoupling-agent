from __future__ import annotations

import re
from collections import Counter

from common.helpers import find_assignment
from common.log import get_logger
from llm.client import build_bailian_client, provider_request_error

log = get_logger("decoupling.validator")

CONFIRMATION_STATUS = {"confirmed", "needs_review", "rejected"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
SNIPPET_CONTEXT_LINES = 3
SNIPPET_FALLBACK_LINES = 18
SNIPPET_MAX_BLOCKS = 2


def run_validator_agent(
    *,
    findings_artifact: dict[str, object],
    context: object,
    model_routing: dict[str, object],
) -> dict[str, object]:
    assignment = find_assignment(model_routing, "finding_validation")
    prepared_findings = _prepare_findings(findings_artifact, context)
    deterministic_items = [_deterministic_validation(item) for item in prepared_findings]

    client = build_bailian_client()
    if client is None or assignment is None:
        log.info("Validator running in deterministic fallback mode")
        validated_findings = _build_validated_artifact(
            deterministic_items,
            raw_finding_count=findings_artifact["counts"]["total"],
            generation={
                "mode": "deterministic_fallback",
                "source": "validator_fallback",
            },
        )
        return {
            "validated_findings": validated_findings,
        }

    validated_items: list[dict[str, object]] = []
    llm_successes = 0
    errors: list[str] = []

    for prepared_item, deterministic_item in zip(prepared_findings, deterministic_items, strict=False):
        try:
            response = client.chat_json(
                model=assignment["api_model"],
                system_prompt=_validator_system_prompt(),
                user_payload={
                    "finding": prepared_item["finding"],
                    "file_snippets": prepared_item["file_snippets"],
                },
                temperature=0,
                max_tokens=900,
            )
            validated_items.append(
                _merge_validation(
                    deterministic_item,
                    _sanitize_validation_response(response["json"], deterministic_item),
                    validation_source="llm",
                    validation_model=assignment["api_model"],
                )
            )
            llm_successes += 1
        except Exception as exc:
            errors.append(provider_request_error(exc))
            validated_items.append(
                _merge_validation(
                    deterministic_item,
                    {},
                    validation_source="deterministic_fallback",
                    validation_model=assignment["api_model"],
                )
            )

    generation_mode = (
        "llm"
        if llm_successes == len(prepared_findings)
        else "hybrid"
        if llm_successes > 0
        else "deterministic_fallback"
    )
    validated_findings = _build_validated_artifact(
        validated_items,
        raw_finding_count=findings_artifact["counts"]["total"],
        generation={
            "mode": generation_mode,
            "source": "validator_agent",
            "provider": assignment["provider"],
            "model": assignment["api_model"],
            "errors": errors,
        },
    )
    return {
        "validated_findings": validated_findings,
    }


def actionable_findings_artifact(validated_findings: dict[str, object]) -> dict[str, object]:
    actionable = [
        _strip_validation_fields(item)
        for item in validated_findings.get("findings", [])
        if item.get("confirmation_status") in {"confirmed", "needs_review"}
    ]
    counts = Counter(item["severity"] for item in actionable)
    return {
        "findings": actionable,
        "counts": {
            "high": counts.get("high", 0),
            "medium": counts.get("medium", 0),
            "low": counts.get("low", 0),
            "total": len(actionable),
        },
    }


def _prepare_findings(findings_artifact: dict[str, object], context: object) -> list[dict[str, object]]:
    file_map = {parsed.relative_path: parsed for parsed in context.files}
    prepared = []
    for finding in findings_artifact.get("findings", []):
        prepared.append(
            {
                "finding": finding,
                "file_snippets": _collect_file_snippets(finding, file_map),
            }
        )
    return prepared


def _collect_file_snippets(
    finding: dict[str, object],
    file_map: dict[str, object],
) -> list[dict[str, object]]:
    snippets: list[dict[str, object]] = []
    line_numbers = _line_numbers_from_evidence(finding.get("evidence", []))

    for file_path in finding.get("files", []):
        parsed = file_map.get(file_path)
        if parsed is None:
            continue
        source_lines = parsed.source.splitlines()
        ranges = _snippet_ranges(source_lines, line_numbers)
        rendered_blocks = [
            {
                "start_line": start,
                "end_line": end,
                "snippet": _render_snippet(source_lines, start, end),
            }
            for start, end in ranges[:SNIPPET_MAX_BLOCKS]
        ]
        snippets.append(
            {
                "file": file_path,
                "module": parsed.module_name,
                "blocks": rendered_blocks,
            }
        )
    return snippets


def _line_numbers_from_evidence(evidence: list[str]) -> list[int]:
    line_numbers: set[int] = set()
    for item in evidence:
        if not isinstance(item, str):
            continue
        for match in re.finditer(r"(?:line|第)\s*(\d+)", item, re.IGNORECASE):
            line_numbers.add(int(match.group(1)))
    return sorted(line_numbers)


def _snippet_ranges(source_lines: list[str], line_numbers: list[int]) -> list[tuple[int, int]]:
    if not source_lines:
        return []
    if not line_numbers:
        return [(1, min(len(source_lines), SNIPPET_FALLBACK_LINES))]

    ranges: list[tuple[int, int]] = []
    for line_number in line_numbers[:SNIPPET_MAX_BLOCKS]:
        start = max(1, line_number - SNIPPET_CONTEXT_LINES)
        end = min(len(source_lines), line_number + SNIPPET_CONTEXT_LINES)
        ranges.append((start, end))
    return ranges


def _render_snippet(source_lines: list[str], start_line: int, end_line: int) -> str:
    rendered = []
    for line_number in range(start_line, end_line + 1):
        rendered.append(f"{line_number}: {source_lines[line_number - 1]}")
    return "\n".join(rendered)


def _deterministic_validation(prepared_item: dict[str, object]) -> dict[str, object]:
    finding = dict(prepared_item["finding"])
    confidence = _deterministic_confidence(finding)
    status = "confirmed" if confidence in {"high", "medium"} else "needs_review"
    if not finding.get("evidence") or not finding.get("files"):
        status = "rejected"
        confidence = "low"

    reason = _deterministic_reason(finding, status)
    return {
        **finding,
        "confirmation_status": status,
        "confidence": confidence,
        "validation_reason": reason,
        "file_snippets": prepared_item["file_snippets"],
        "validation_source": "deterministic_fallback",
        "validation_model": None,
        "needs_human_review": status != "confirmed" or confidence == "low",
    }


def _deterministic_confidence(finding: dict[str, object]) -> str:
    rule_id = finding["rule_id"]
    evidence = finding.get("evidence", [])
    file_count = len(finding.get("files", []))

    if rule_id == "RULE_A":
        return "high" if any("高" in item or "high" in item for item in evidence) else "medium"
    if rule_id == "RULE_B":
        return "high" if file_count >= 4 else "medium"
    if rule_id == "RULE_C":
        return "medium" if file_count >= 5 else "low"
    if rule_id == "RULE_D":
        return "high" if any("变更次数=" in item or "mutations=" in item for item in evidence) else "medium"
    if rule_id == "RULE_E":
        return "medium"
    return "low"


def _deterministic_reason(finding: dict[str, object], status: str) -> str:
    if status == "rejected":
        return "当前 finding 缺少稳定证据，建议先人工复核原始扫描结果。"

    reasons = {
        "RULE_A": "路径命中请求层关键词，且存在数据库访问操作证据。",
        "RULE_B": "同一环境变量在多个业务文件中被直接读取，具备稳定配置分散信号。",
        "RULE_C": "共享工具模块的依赖范围跨越多个文件或包，存在横向耦合迹象。",
        "RULE_D": "模块级可变对象在函数作用域内被修改，共享状态风险较高。",
        "RULE_E": "Import 图中存在强连通组件，循环依赖证据明确。",
    }
    return reasons.get(finding["rule_id"], "finding 已被规则和证据初步支持，但仍建议结合代码上下文确认。")


def _validator_system_prompt() -> str:
    return (
        "You are the Finding Validator Agent in a technical-debt diagnosis system.\n"
        "Validate whether the finding is sufficiently supported by the provided evidence and file snippets.\n"
        "Return JSON only.\n"
        "All natural-language string fields must be written in Simplified Chinese.\n"
        "Do not invent files or evidence that are not present in the payload.\n"
        "Output shape:\n"
        "{\n"
        '  "confirmation_status": "confirmed" | "needs_review" | "rejected",\n'
        '  "confidence": "high" | "medium" | "low",\n'
        '  "reason": string\n'
        "}"
    )


def _sanitize_validation_response(
    llm_output: dict[str, object],
    deterministic_item: dict[str, object],
) -> dict[str, object]:
    status = llm_output.get("confirmation_status")
    if status not in CONFIRMATION_STATUS:
        status = deterministic_item["confirmation_status"]

    confidence = llm_output.get("confidence")
    if confidence not in CONFIDENCE_LEVELS:
        confidence = deterministic_item["confidence"]

    reason = llm_output.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = deterministic_item["validation_reason"]

    return {
        "confirmation_status": status,
        "confidence": confidence,
        "validation_reason": reason.strip(),
    }


def _merge_validation(
    deterministic_item: dict[str, object],
    llm_validation: dict[str, object],
    *,
    validation_source: str,
    validation_model: str | None,
) -> dict[str, object]:
    merged = dict(deterministic_item)
    merged.update(llm_validation)
    merged["validation_source"] = validation_source
    merged["validation_model"] = validation_model if validation_source == "llm" else None
    merged["needs_human_review"] = (
        merged["confirmation_status"] != "confirmed" or merged["confidence"] == "low"
    )
    return merged


def _build_validated_artifact(
    validated_items: list[dict[str, object]],
    *,
    raw_finding_count: int,
    generation: dict[str, object],
) -> dict[str, object]:
    status_counts = Counter(item["confirmation_status"] for item in validated_items)
    confidence_counts = Counter(item["confidence"] for item in validated_items)
    actionable_count = sum(
        1 for item in validated_items if item["confirmation_status"] in {"confirmed", "needs_review"}
    )
    return {
        "findings": validated_items,
        "summary": {
            "raw_finding_count": raw_finding_count,
            "validated_finding_count": len(validated_items),
            "actionable_finding_count": actionable_count,
            "confirmed": status_counts.get("confirmed", 0),
            "needs_review": status_counts.get("needs_review", 0),
            "rejected": status_counts.get("rejected", 0),
            "high_confidence": confidence_counts.get("high", 0),
            "medium_confidence": confidence_counts.get("medium", 0),
            "low_confidence": confidence_counts.get("low", 0),
        },
        "generation": generation,
    }


def _strip_validation_fields(item: dict[str, object]) -> dict[str, object]:
    stripped = dict(item)
    stripped.pop("confirmation_status", None)
    stripped.pop("confidence", None)
    stripped.pop("validation_reason", None)
    stripped.pop("file_snippets", None)
    stripped.pop("validation_source", None)
    stripped.pop("validation_model", None)
    stripped.pop("needs_human_review", None)
    return stripped


