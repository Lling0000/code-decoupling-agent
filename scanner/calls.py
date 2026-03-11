from __future__ import annotations

import ast

from models.schema import RepoContext


def scan_calls(context: RepoContext) -> dict[str, object]:
    files_artifact: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []

    for parsed in context.files:
        collector = _CallCollector(parsed.module_name)
        collector.visit(parsed.tree)
        file_calls = sorted(collector.calls, key=lambda item: (item["line"], item["callee"]))
        files_artifact.append(
            {
                "file": parsed.relative_path,
                "module": parsed.module_name,
                "calls": file_calls,
            }
        )
        edges.extend(
            {
                "file": parsed.relative_path,
                "caller": call["caller"],
                "callee": call["callee"],
                "line": call["line"],
            }
            for call in file_calls
        )

    return {
        "files": sorted(files_artifact, key=lambda item: item["file"]),
        "edges": sorted(edges, key=lambda item: (item["file"], item["line"], item["callee"])),
    }


def extract_call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = extract_call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        base = extract_call_name(node.func)
        return f"{base}()" if base else None
    if isinstance(node, ast.Subscript):
        base = extract_call_name(node.value)
        return f"{base}[]" if base else None
    return None


class _CallCollector(ast.NodeVisitor):
    def __init__(self, module_name: str) -> None:
        self.module_name = module_name
        self.scope_stack: list[tuple[str, str]] = []
        self.current_caller: str | None = None
        self.calls: list[dict[str, object]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope_stack.append(("class", node.name))
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self.current_caller:
            callee = extract_call_name(node.func) or "<unknown>"
            self.calls.append(
                {
                    "caller": self.current_caller,
                    "callee": callee,
                    "line": node.lineno,
                }
            )
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope_stack.append(("function", node.name))
        previous_caller = self.current_caller
        self.current_caller = self._qualified_name()
        self.generic_visit(node)
        self.current_caller = previous_caller
        self.scope_stack.pop()

    def _qualified_name(self) -> str:
        scope_names = [name for _, name in self.scope_stack]
        pieces = [piece for piece in [self.module_name, *scope_names] if piece]
        return ".".join(pieces)
