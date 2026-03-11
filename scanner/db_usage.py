from __future__ import annotations

import ast

from models.schema import RepoContext
from rules.config import (
    DB_IMPORTED_CALL_NAMES,
    DB_IMPORT_KEYWORDS,
    DB_OPERATION_METHODS,
    DB_ROOT_NAME_HINTS,
)
from scanner.calls import extract_call_name


def scan_db_usage(context: RepoContext) -> dict[str, object]:
    files_artifact: list[dict[str, object]] = []
    files_with_signals = 0
    signal_count = 0

    for parsed in context.files:
        db_context = _collect_db_context(parsed.tree)
        signals: list[dict[str, object]] = []
        seen: set[tuple[str, int, str]] = set()

        for node in ast.walk(parsed.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _matches_import(alias.name):
                        _append_signal(
                            signals,
                            seen,
                            kind="import",
                            signal=alias.name,
                            line=node.lineno,
                            confidence="high",
                        )
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                if _matches_import(module_name):
                    _append_signal(
                        signals,
                        seen,
                        kind="import",
                        signal=module_name,
                        line=node.lineno,
                        confidence="high",
                    )
            elif isinstance(node, ast.Call):
                call_name = extract_call_name(node.func)
                confidence = _classify_db_call(call_name, db_context)
                if confidence:
                    _append_signal(
                        signals,
                        seen,
                        kind="call",
                        signal=call_name or "<unknown>",
                        line=node.lineno,
                        confidence=confidence,
                    )
            elif isinstance(node, ast.Attribute):
                attr_name = extract_call_name(node)
                confidence = _classify_db_attribute(attr_name, db_context)
                if confidence:
                    _append_signal(
                        signals,
                        seen,
                        kind="attribute",
                        signal=attr_name or "<unknown>",
                        line=node.lineno,
                        confidence=confidence,
                    )

        if signals:
            files_with_signals += 1
            signal_count += len(signals)

        files_artifact.append(
            {
                "file": parsed.relative_path,
                "module": parsed.module_name,
                "signals": sorted(signals, key=lambda item: (item["line"], item["signal"])),
                "signal_count": len(signals),
            }
        )

    return {
        "files": sorted(files_artifact, key=lambda item: item["file"]),
        "files_with_signals": files_with_signals,
        "signal_count": signal_count,
    }


def _append_signal(
    signals: list[dict[str, object]],
    seen: set[tuple[str, int, str]],
    *,
    kind: str,
    signal: str,
    line: int,
    confidence: str,
) -> None:
    key = (kind, line, signal)
    if key in seen:
        return
    seen.add(key)
    signals.append(
        {
            "kind": kind,
            "signal": signal,
            "line": line,
            "confidence": confidence,
        }
    )


def _matches_import(module_name: str) -> bool:
    module_name = module_name.lower()
    return any(keyword in module_name for keyword in DB_IMPORT_KEYWORDS)


def _collect_db_context(tree: ast.AST) -> dict[str, object]:
    module_aliases: set[str] = set()
    symbol_aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _matches_import(alias.name):
                    continue
                module_aliases.add((alias.asname or alias.name.split(".")[0]).lower())
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            if not _matches_import(module_name):
                continue
            for alias in node.names:
                symbol_aliases.add((alias.asname or alias.name).lower())

    return {
        "has_db_imports": bool(module_aliases or symbol_aliases),
        "module_aliases": module_aliases,
        "symbol_aliases": symbol_aliases,
    }


def _classify_db_call(name: str | None, db_context: dict[str, object]) -> str | None:
    if not name:
        return None

    if _looks_like_model_query(name):
        return "high"

    normalized = name.lower()
    root_name = _root_name(normalized)
    last_segment = _last_segment(normalized)

    if "db.session" in normalized or "model.query" in normalized:
        return "high"
    if normalized in db_context["symbol_aliases"] and normalized in DB_IMPORTED_CALL_NAMES:
        return "medium"
    if root_name in db_context["module_aliases"]:
        if last_segment in DB_IMPORTED_CALL_NAMES:
            return "high"
        if last_segment in DB_OPERATION_METHODS:
            return "medium"
    if root_name in db_context["symbol_aliases"] and last_segment in DB_OPERATION_METHODS:
        return "medium"
    if db_context["has_db_imports"] and root_name in DB_ROOT_NAME_HINTS and last_segment in DB_OPERATION_METHODS:
        return "medium"
    return None


def _classify_db_attribute(name: str | None, db_context: dict[str, object]) -> str | None:
    if not name:
        return None

    if _looks_like_model_query(name):
        return "high"

    normalized = name.lower()
    if "db.session" in normalized or "model.query" in normalized:
        return "high"
    if db_context["has_db_imports"] and _root_name(normalized) in DB_ROOT_NAME_HINTS:
        if _last_segment(normalized) in {"session", "query"}:
            return "medium"
    return None


def _looks_like_model_query(name: str) -> bool:
    parts = name.split(".")
    return len(parts) == 2 and parts[1] == "query" and parts[0][:1].isupper()


def _root_name(name: str) -> str:
    return name.split(".", 1)[0].replace("()", "").replace("[]", "")


def _last_segment(name: str) -> str:
    return name.rsplit(".", 1)[-1].replace("()", "").replace("[]", "")
