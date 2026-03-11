from __future__ import annotations

import ast
from pathlib import Path

from models.schema import ParsedFile, RepoContext, ScanError

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
}


def build_repo_context(repo_root: Path) -> RepoContext:
    files: list[ParsedFile] = []
    scan_errors: list[ScanError] = []
    module_index: dict[str, str] = {}

    for path in sorted(repo_root.rglob("*.py")):
        if should_skip_path(path):
            continue
        relative_path = path.relative_to(repo_root).as_posix()
        source = path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            scan_errors.append(
                ScanError(
                    file=relative_path,
                    message=exc.msg,
                    line=exc.lineno,
                )
            )
            continue

        module_name = path_to_module(relative_path)
        package_name = package_for_module(module_name, path.name == "__init__.py")
        files.append(
            ParsedFile(
                path=path,
                relative_path=relative_path,
                module_name=module_name,
                package_name=package_name,
                source=source,
                tree=tree,
            )
        )
        module_index.setdefault(module_name, relative_path)

    return RepoContext(
        root=repo_root,
        files=files,
        module_index=module_index,
        scan_errors=scan_errors,
    )


def should_skip_path(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def path_to_module(relative_path: str) -> str:
    module = relative_path[:-3].replace("/", ".")
    if module.endswith(".__init__"):
        module = module[: -len(".__init__")]
    return module or "__init__"


def package_for_module(module_name: str, is_package_init: bool) -> str:
    if is_package_init:
        return "" if module_name == "__init__" else module_name
    if "." not in module_name:
        return ""
    return module_name.rsplit(".", 1)[0]
