from __future__ import annotations

from agents.contracts import RepoInventory
from models.schema import RepoContext, to_jsonable


def build_repo_inventory(
    context: RepoContext,
    tool_results: dict[str, object],
) -> dict[str, object]:
    import_counts = {
        item["file"]: len(item["imports"])
        for item in tool_results["import_graph"]["files"]
    }
    db_counts = {
        item["file"]: item["signal_count"]
        for item in tool_results["db_usage"]["files"]
    }
    global_counts = {
        item["file"]: item["risk_count"]
        for item in tool_results["global_state"]["files"]
    }
    env_counts: dict[str, int] = {}
    for item in tool_results["env_usage"]["reads"]:
        env_counts[item["file"]] = env_counts.get(item["file"], 0) + 1

    hotspot_files: list[dict[str, object]] = []
    for parsed in context.files:
        score = (
            import_counts.get(parsed.relative_path, 0)
            + env_counts.get(parsed.relative_path, 0)
            + (db_counts.get(parsed.relative_path, 0) * 2)
            + (global_counts.get(parsed.relative_path, 0) * 2)
        )
        hotspot_files.append(
            {
                "file": parsed.relative_path,
                "module": parsed.module_name,
                "score": score,
                "import_count": import_counts.get(parsed.relative_path, 0),
                "env_read_count": env_counts.get(parsed.relative_path, 0),
                "db_signal_count": db_counts.get(parsed.relative_path, 0),
                "global_risk_count": global_counts.get(parsed.relative_path, 0),
            }
        )

    inventory = RepoInventory(
        scanned_files=len(context.files),
        parse_errors=len(context.scan_errors),
        finding_count=tool_results["findings"]["counts"]["total"],
        has_tests=any(_is_test_file(parsed.relative_path) for parsed in context.files),
        hotspots=sorted(hotspot_files, key=lambda item: item["score"], reverse=True)[:10],
    )
    return to_jsonable(inventory)


def _is_test_file(relative_path: str) -> bool:
    file_name = relative_path.rsplit("/", 1)[-1]
    return relative_path.startswith("tests/") or file_name.startswith("test_") or file_name.endswith("_test.py")
