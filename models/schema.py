from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ParsedFile:
    path: Path
    relative_path: str
    module_name: str
    package_name: str
    source: str
    tree: ast.Module


@dataclass(slots=True)
class ScanError:
    file: str
    message: str
    line: int | None = None


@dataclass(slots=True)
class RepoContext:
    root: Path
    files: list[ParsedFile]
    module_index: dict[str, str]
    scan_errors: list[ScanError]


@dataclass(slots=True)
class Finding:
    rule_id: str
    rule_name: str
    severity: str
    files: list[str]
    evidence: list[str]
    explanation: str
    suggestion: str


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    return value
