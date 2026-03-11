from __future__ import annotations

import ast

from models.schema import RepoContext


def scan_definitions(context: RepoContext) -> dict[str, object]:
    files_artifact: list[dict[str, object]] = []
    totals = {"functions": 0, "classes": 0, "methods": 0}

    for parsed in context.files:
        collector = _DefinitionCollector(parsed.module_name)
        collector.visit(parsed.tree)
        files_artifact.append(
            {
                "file": parsed.relative_path,
                "module": parsed.module_name,
                "definitions": collector.records,
            }
        )
        for key in totals:
            totals[key] += collector.counts[key]

    return {
        "files": sorted(files_artifact, key=lambda item: item["file"]),
        "totals": totals,
    }


class _DefinitionCollector(ast.NodeVisitor):
    def __init__(self, module_name: str) -> None:
        self.module_name = module_name
        self.records: list[dict[str, object]] = []
        self.scope_stack: list[tuple[str, str]] = []
        self.counts = {"functions": 0, "classes": 0, "methods": 0}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = self._qualified_name(node.name)
        self.records.append(
            {
                "name": node.name,
                "qualified_name": qualified_name,
                "type": "class",
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
            }
        )
        self.counts["classes"] += 1
        self.scope_stack.append(("class", node.name))
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        kind = "method" if any(scope_type == "class" for scope_type, _ in self.scope_stack) else "function"
        qualified_name = self._qualified_name(node.name)
        self.records.append(
            {
                "name": node.name,
                "qualified_name": qualified_name,
                "type": kind,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
            }
        )
        self.counts["methods" if kind == "method" else "functions"] += 1
        self.scope_stack.append(("function", node.name))
        self.generic_visit(node)
        self.scope_stack.pop()

    def _qualified_name(self, name: str) -> str:
        scope_names = [scope_name for _, scope_name in self.scope_stack]
        pieces = [piece for piece in [self.module_name, *scope_names, name] if piece]
        return ".".join(pieces)
