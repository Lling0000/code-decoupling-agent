from __future__ import annotations

import ast
from collections import defaultdict

from models.schema import RepoContext


def scan_env_usage(context: RepoContext) -> dict[str, object]:
    reads: list[dict[str, object]] = []
    variable_index: defaultdict[str, set[str]] = defaultdict(set)

    for parsed in context.files:
        os_aliases, getenv_aliases, environ_aliases = _collect_os_aliases(parsed.tree)

        for node in ast.walk(parsed.tree):
            env_name: str | None = None
            access_type: str | None = None

            if isinstance(node, ast.Call):
                if _matches_os_getenv(node.func, os_aliases, getenv_aliases):
                    env_name = _string_argument(node)
                    access_type = "getenv"
                elif _matches_os_environ_get(node.func, os_aliases, environ_aliases):
                    env_name = _string_argument(node)
                    access_type = "environ.get"
            elif isinstance(node, ast.Subscript):
                if _matches_environ_container(node.value, os_aliases, environ_aliases):
                    env_name = _string_literal(node.slice)
                    access_type = "environ[]"

            if not env_name:
                continue

            reads.append(
                {
                    "file": parsed.relative_path,
                    "module": parsed.module_name,
                    "variable": env_name,
                    "access_type": access_type,
                    "line": getattr(node, "lineno", None),
                }
            )
            variable_index[env_name].add(parsed.relative_path)

    variables = [
        {
            "name": name,
            "files": sorted(files),
            "file_count": len(files),
            "read_count": sum(1 for read in reads if read["variable"] == name),
        }
        for name, files in sorted(variable_index.items())
    ]

    return {
        "reads": sorted(reads, key=lambda item: (item["file"], item["line"] or 0, item["variable"])),
        "variables": variables,
    }


def _collect_os_aliases(
    tree: ast.AST,
) -> tuple[set[str], set[str], set[str]]:
    os_aliases = {"os"}
    getenv_aliases: set[str] = set()
    environ_aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                if alias.name == "getenv":
                    getenv_aliases.add(alias.asname or alias.name)
                elif alias.name == "environ":
                    environ_aliases.add(alias.asname or alias.name)

    return os_aliases, getenv_aliases, environ_aliases


def _matches_os_getenv(
    func: ast.AST,
    os_aliases: set[str],
    getenv_aliases: set[str],
) -> bool:
    if isinstance(func, ast.Name):
        return func.id in getenv_aliases
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "getenv"
        and isinstance(func.value, ast.Name)
        and func.value.id in os_aliases
    )


def _matches_os_environ_get(
    func: ast.AST,
    os_aliases: set[str],
    environ_aliases: set[str],
) -> bool:
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "get"
        and _matches_environ_container(func.value, os_aliases, environ_aliases)
    )


def _matches_environ_container(
    node: ast.AST,
    os_aliases: set[str],
    environ_aliases: set[str],
) -> bool:
    if isinstance(node, ast.Name):
        return node.id in environ_aliases
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id in os_aliases
    )


def _string_argument(node: ast.Call, index: int = 0) -> str | None:
    if len(node.args) > index:
        return _string_literal(node.args[index])
    return None


def _string_literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None
