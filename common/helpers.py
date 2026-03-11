from __future__ import annotations


def is_test_file(relative_path: str) -> bool:
    file_name = relative_path.rsplit("/", 1)[-1]
    return (
        relative_path.startswith("tests/")
        or file_name.startswith("test_")
        or file_name.endswith("_test.py")
    )


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
