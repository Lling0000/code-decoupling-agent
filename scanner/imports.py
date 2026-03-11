from __future__ import annotations

import ast
from typing import Iterable

from models.schema import ParsedFile, RepoContext


def scan_imports(context: RepoContext) -> dict[str, object]:
    files_artifact: list[dict[str, object]] = []
    edge_seen: set[tuple[str, str, str]] = set()
    local_edges: list[dict[str, str]] = []

    for parsed in context.files:
        collector = _ImportCollector(parsed, context.module_index)
        collector.visit(parsed.tree)

        for item in collector.imports:
            _append_edges(
                parsed.relative_path,
                item["resolved_local_modules"],
                context.module_index,
                collector.local_dependencies,
                edge_seen,
                local_edges,
            )

        files_artifact.append(
            {
                "file": parsed.relative_path,
                "module": parsed.module_name,
                "imports": sorted(collector.imports, key=lambda item: (item["line"], item["module"])),
                "local_dependencies": sorted(collector.local_dependencies),
            }
        )

    return {
        "files": sorted(files_artifact, key=lambda item: item["file"]),
        "local_edges": sorted(local_edges, key=lambda item: (item["source"], item["target"])),
    }


def _append_edges(
    source_file: str,
    resolved_modules: Iterable[str],
    module_index: dict[str, str],
    local_dependencies: set[str],
    edge_seen: set[tuple[str, str, str]],
    local_edges: list[dict[str, str]],
) -> None:
    for module_name in resolved_modules:
        target_file = module_index[module_name]
        local_dependencies.add(target_file)
        edge_key = (source_file, target_file, module_name)
        if edge_key in edge_seen:
            continue
        edge_seen.add(edge_key)
        local_edges.append(
            {
                "source": source_file,
                "target": target_file,
                "module": module_name,
            }
        )


def _resolve_from_import(
    node: ast.ImportFrom,
    parsed: ParsedFile,
    module_index: dict[str, str],
) -> list[str]:
    absolute_base = _absolute_from_base(parsed, node.module, node.level)
    resolved: set[str] = set()

    for alias in node.names:
        if alias.name == "*":
            match = _resolve_best_match(absolute_base, module_index)
            if match:
                resolved.add(match)
            continue

        if absolute_base:
            candidate = _resolve_best_match(f"{absolute_base}.{alias.name}", module_index)
            if candidate:
                resolved.add(candidate)
                continue

        match = _resolve_best_match(absolute_base or alias.name, module_index)
        if match:
            resolved.add(match)

    return sorted(resolved)


def _absolute_from_base(parsed: ParsedFile, module: str | None, level: int) -> str:
    if level <= 0:
        return module or ""

    package_parts = parsed.package_name.split(".") if parsed.package_name else []
    steps_up = max(level - 1, 0)
    if steps_up >= len(package_parts):
        base_parts: list[str] = []
    else:
        base_parts = package_parts[: len(package_parts) - steps_up]

    module_parts = module.split(".") if module else []
    return ".".join(part for part in [*base_parts, *module_parts] if part)


def _resolve_best_match(module_name: str, module_index: dict[str, str]) -> str | None:
    if not module_name:
        return None

    parts = module_name.split(".")
    for size in range(len(parts), 0, -1):
        candidate = ".".join(parts[:size])
        if candidate in module_index:
            return candidate
    return None


class _ImportCollector(ast.NodeVisitor):
    def __init__(self, parsed: ParsedFile, module_index: dict[str, str]) -> None:
        self.parsed = parsed
        self.module_index = module_index
        self.imports: list[dict[str, object]] = []
        self.local_dependencies: set[str] = set()

    def visit_If(self, node: ast.If) -> None:
        if _is_type_checking_guard(node.test):
            for child in node.orelse:
                self.visit(child)
            return
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            resolved_module = _resolve_best_match(alias.name, self.module_index)
            resolved_modules = [resolved_module] if resolved_module else []
            resolved_files = [self.module_index[module_name] for module_name in resolved_modules]
            self.imports.append(
                {
                    "kind": "import",
                    "module": alias.name,
                    "names": [alias.name],
                    "line": node.lineno,
                    "is_local": bool(resolved_modules),
                    "resolved_local_modules": resolved_modules,
                    "resolved_local_files": resolved_files,
                }
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module_label = "." * node.level + (node.module or "")
        resolved_modules = _resolve_from_import(node, self.parsed, self.module_index)
        resolved_files = [self.module_index[module_name] for module_name in resolved_modules]
        self.imports.append(
            {
                "kind": "from_import",
                "module": module_label or ".",
                "names": [alias.name for alias in node.names],
                "line": node.lineno,
                "is_local": bool(resolved_modules),
                "resolved_local_modules": resolved_modules,
                "resolved_local_files": resolved_files,
            }
        )


def _is_type_checking_guard(test: ast.AST) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return (
        isinstance(test, ast.Attribute)
        and test.attr == "TYPE_CHECKING"
        and isinstance(test.value, ast.Name)
        and test.value.id == "typing"
    )
