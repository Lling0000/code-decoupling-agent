from __future__ import annotations


def _normalized_parts(relative_path: str) -> list[str]:
    return [part for part in relative_path.replace("\\", "/").split("/") if part]


def is_test_file(relative_path: str) -> bool:
    file_name = relative_path.rsplit("/", 1)[-1]
    return (
        relative_path.startswith("tests/")
        or file_name.startswith("test_")
        or file_name.endswith("_test.py")
    )


def is_docs_file(relative_path: str) -> bool:
    parts = _normalized_parts(relative_path)
    return any(part in {"docs", "doc"} for part in parts[:-1])


def is_non_product_file(relative_path: str) -> bool:
    return is_test_file(relative_path) or is_docs_file(relative_path)


def find_assignment(model_routing: dict[str, object], role: str) -> dict[str, object] | None:
    for item in model_routing.get("assignments", []):
        if item.get("role") == role:
            return item
    return None


def string_list(value: object, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return items or fallback


def non_empty_text(value: object, fallback: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback
