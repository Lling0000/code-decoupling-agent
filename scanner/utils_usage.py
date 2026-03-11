from __future__ import annotations

from collections import defaultdict

from rules.config import UTILS_MODULE_KEYWORDS, UTILS_OVERUSE_THRESHOLD


def scan_utils_usage(import_graph: dict[str, object]) -> dict[str, object]:
    dependencies: list[dict[str, object]] = []
    module_to_files: defaultdict[str, set[str]] = defaultdict(set)
    module_to_consumer_packages: defaultdict[str, set[str]] = defaultdict(set)
    seen: set[tuple[str, str, int]] = set()

    for file_entry in import_graph.get("files", []):
        source_file = file_entry["file"]
        source_module = file_entry["module"]
        consumer_package = _consumer_package(source_module)
        for item in file_entry["imports"]:
            modules = item["resolved_local_modules"]
            if not modules:
                continue
            for module_name in modules:
                if not _matches_utils_name(module_name):
                    continue
                key = (source_file, module_name, item["line"])
                if key in seen:
                    continue
                seen.add(key)
                dependencies.append(
                    {
                        "file": source_file,
                        "module": module_name,
                        "line": item["line"],
                        "consumer_package": consumer_package,
                    }
                )
                module_to_files[module_name].add(source_file)
                module_to_consumer_packages[module_name].add(consumer_package)

    modules = [
        {
            "module": module_name,
            "files": sorted(files),
            "file_count": len(files),
            "consumer_packages": sorted(module_to_consumer_packages[module_name]),
            "consumer_package_count": len(module_to_consumer_packages[module_name]),
            "overuse_threshold": UTILS_OVERUSE_THRESHOLD,
        }
        for module_name, files in sorted(module_to_files.items())
    ]

    return {
        "dependencies": sorted(dependencies, key=lambda item: (item["module"], item["file"])),
        "modules": modules,
        "threshold": UTILS_OVERUSE_THRESHOLD,
    }


def _matches_utils_name(module_name: str) -> bool:
    parts = [part.lower() for part in module_name.split(".")]
    for part in parts:
        if part in UTILS_MODULE_KEYWORDS:
            return True
        # Also match underscore-separated names like "myapp_utils" or "common_tools".
        segments = part.split("_")
        if any(seg in UTILS_MODULE_KEYWORDS for seg in segments):
            return True
    return False


def _consumer_package(module_name: str) -> str:
    if "." not in module_name:
        return module_name
    return module_name.rsplit(".", 1)[0]
