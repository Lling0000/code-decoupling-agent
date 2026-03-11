from __future__ import annotations

from models.schema import RepoContext
from rules_engine.engine import detect_import_cycles, run_rules
from scanner.calls import scan_calls
from scanner.db_usage import scan_db_usage
from scanner.definitions import scan_definitions
from scanner.envs import scan_env_usage
from scanner.globals import scan_global_state
from scanner.imports import scan_imports
from scanner.utils_usage import scan_utils_usage


def run_deterministic_toolchain(context: RepoContext) -> dict[str, object]:
    import_graph = scan_imports(context)
    definitions = scan_definitions(context)
    call_graph = scan_calls(context)
    env_usage = scan_env_usage(context)
    db_usage = scan_db_usage(context)
    utils_usage = scan_utils_usage(import_graph)
    global_state = scan_global_state(context)
    cycles = detect_import_cycles(import_graph)
    import_graph["cycles"] = cycles
    findings = run_rules(
        import_graph=import_graph,
        env_usage=env_usage,
        db_usage=db_usage,
        utils_usage=utils_usage,
        global_state=global_state,
        cycles=cycles,
        definitions=definitions,
    )

    return {
        "import_graph": import_graph,
        "definitions": definitions,
        "call_graph": call_graph,
        "env_usage": env_usage,
        "db_usage": db_usage,
        "utils_usage": utils_usage,
        "global_state": global_state,
        "findings": findings,
    }
