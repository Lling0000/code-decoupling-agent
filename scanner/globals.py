from __future__ import annotations

import ast

from models.schema import RepoContext
from rules.config import GLOBAL_STATE_IGNORED_NAMES, GLOBAL_STATE_MUTATION_METHODS
from scanner.calls import extract_call_name


def scan_global_state(context: RepoContext) -> dict[str, object]:
    files_artifact: list[dict[str, object]] = []
    files_with_risk = 0
    risk_count = 0

    for parsed in context.files:
        candidates = _collect_module_candidates(parsed.tree)
        interactions = _collect_function_interactions(parsed.tree, set(candidates))
        globals_found: list[dict[str, object]] = []

        for name, candidate in sorted(candidates.items(), key=lambda item: (item[1]["line"], item[0])):
            interaction = interactions.get(name, _empty_interaction())
            mutation_lines = sorted(interaction["mutation_lines"])
            read_lines = sorted(interaction["read_lines"])
            shared_access = bool(mutation_lines or read_lines)
            finding_candidate = bool(mutation_lines or candidate["kind"] == "augmented_assignment")

            if not finding_candidate:
                continue

            risk = "high" if mutation_lines else "medium"
            detail = candidate["detail"]
            if mutation_lines:
                detail = f"{detail}; mutated from function scope"

            globals_found.append(
                {
                    "name": name,
                    "line": candidate["line"],
                    "kind": candidate["kind"],
                    "mutable": candidate["mutable"],
                    "risk": risk,
                    "detail": detail,
                    "shared_access": shared_access,
                    "read_lines": read_lines,
                    "mutation_lines": mutation_lines,
                    "read_count": len(read_lines),
                    "mutation_count": len(mutation_lines),
                    "finding_candidate": True,
                }
            )

        if globals_found:
            files_with_risk += 1
            risk_count += len(globals_found)

        files_artifact.append(
            {
                "file": parsed.relative_path,
                "module": parsed.module_name,
                "globals": globals_found,
                "risk_count": len(globals_found),
            }
        )

    return {
        "files": sorted(files_artifact, key=lambda item: item["file"]),
        "files_with_risk": files_with_risk,
        "risk_count": risk_count,
    }


def _collect_module_candidates(tree: ast.Module) -> dict[str, dict[str, object]]:
    candidates: dict[str, dict[str, object]] = {}

    for node in tree.body:
        if isinstance(node, ast.Assign):
            classification = _classify_global_value(node.value)
            if not classification:
                continue
            for target in node.targets:
                for name in _target_names(target):
                    if _should_ignore_name(name):
                        continue
                    candidates[name] = {
                        "line": node.lineno,
                        **classification,
                    }
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            classification = _classify_global_value(node.value)
            if not classification or _should_ignore_name(node.target.id):
                continue
            candidates[node.target.id] = {
                "line": node.lineno,
                **classification,
            }
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            if _should_ignore_name(node.target.id):
                continue
            candidates[node.target.id] = {
                "line": node.lineno,
                "kind": "augmented_assignment",
                "mutable": True,
                "detail": "module-level augmented assignment may represent shared state",
            }

    return candidates


def _classify_global_value(value: ast.AST | None) -> dict[str, object] | None:
    if value is None:
        return None
    if isinstance(value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
        return {
            "kind": "mutable_literal",
            "mutable": True,
            "detail": "module-level mutable collection",
        }
    if isinstance(value, ast.Call):
        call_name = extract_call_name(value.func) or "<call>"
        normalized = call_name.lower()
        if normalized in {"list", "dict", "set", "defaultdict", "deque"}:
            return {
                "kind": "mutable_factory",
                "mutable": True,
                "detail": f"module-level mutable container created by {call_name}",
            }
        if "cache" in normalized or "registry" in normalized or "state" in normalized:
            return {
                "kind": "stateful_object",
                "mutable": True,
                "detail": f"module-level stateful object created by {call_name}",
            }
    return None


def _collect_function_interactions(tree: ast.AST, candidate_names: set[str]) -> dict[str, dict[str, set[int]]]:
    interactions = {name: _empty_interaction() for name in candidate_names}

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        declared_global: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Global):
                declared_global.update(name for name in child.names if name in candidate_names)

        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load) and child.id in candidate_names:
                interactions[child.id]["read_lines"].add(child.lineno)
            elif isinstance(child, ast.Call):
                call_name = extract_call_name(child.func)
                root_name = _root_name(call_name)
                method_name = _last_segment(call_name)
                if root_name in candidate_names and method_name in GLOBAL_STATE_MUTATION_METHODS:
                    interactions[root_name]["mutation_lines"].add(child.lineno)
            elif isinstance(child, ast.Assign):
                _record_target_mutations(child.targets, candidate_names, declared_global, child.lineno, interactions)
            elif isinstance(child, ast.AnnAssign):
                _record_target_mutations([child.target], candidate_names, declared_global, child.lineno, interactions)
            elif isinstance(child, ast.AugAssign):
                _record_target_mutations([child.target], candidate_names, declared_global, child.lineno, interactions)

    return interactions


def _record_target_mutations(
    targets: list[ast.AST],
    candidate_names: set[str],
    declared_global: set[str],
    line: int,
    interactions: dict[str, dict[str, set[int]]],
) -> None:
    for target in targets:
        for name in _mutated_candidate_names(target, candidate_names, declared_global):
            interactions[name]["mutation_lines"].add(line)


def _mutated_candidate_names(
    target: ast.AST,
    candidate_names: set[str],
    declared_global: set[str],
) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id} if target.id in candidate_names and target.id in declared_global else set()
    if isinstance(target, ast.Subscript):
        root_name = _root_name(extract_call_name(target.value))
        return {root_name} if root_name in candidate_names else set()
    if isinstance(target, ast.Attribute):
        root_name = _root_name(extract_call_name(target.value))
        return {root_name} if root_name in candidate_names else set()
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for item in target.elts:
            names.update(_mutated_candidate_names(item, candidate_names, declared_global))
        return names
    return set()


def _target_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for item in target.elts:
            names.extend(_target_names(item))
        return names
    return []


def _should_ignore_name(name: str) -> bool:
    return name in GLOBAL_STATE_IGNORED_NAMES


def _empty_interaction() -> dict[str, set[int]]:
    return {
        "read_lines": set(),
        "mutation_lines": set(),
    }


def _root_name(name: str | None) -> str:
    if not name:
        return ""
    return name.split(".", 1)[0].replace("()", "").replace("[]", "")


def _last_segment(name: str | None) -> str:
    if not name:
        return ""
    return name.rsplit(".", 1)[-1].replace("()", "").replace("[]", "")
