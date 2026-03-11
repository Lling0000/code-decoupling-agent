from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agents.governor import run_governed_analysis
from iteration.gate_runner import decision_exit_code, run_iteration_gates
from llm.health import run_llm_health_check
from models.schema import to_jsonable
from report.renderer import render_summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose coupling signals in a local Python repository.")
    parser.add_argument("--repo", help="Path to the Python repository to analyze.")
    parser.add_argument("--output", help="Directory for generated reports and artifacts.")
    parser.add_argument(
        "--check-llm-config",
        action="store_true",
        help="Run LLM configuration self-check and model health probes.",
    )
    parser.add_argument(
        "--run-gates",
        action="store_true",
        help="Run iteration gates after analysis and emit agent/human gate reports.",
    )
    parser.add_argument(
        "--system-test-command",
        help="Override the command used for the system test gate.",
    )
    parser.add_argument(
        "--golden-test-command",
        help="Override the command used for the golden regression gate.",
    )
    parser.add_argument(
        "--target-test-command",
        action="append",
        default=[],
        help="Target repository regression test command. Repeat to pass multiple commands.",
    )
    parser.add_argument(
        "--runtime-command",
        action="append",
        default=[],
        help="Target repository runtime smoke command. Repeat to pass multiple commands.",
    )
    args = parser.parse_args(argv)
    if args.check_llm_config:
        return args
    if not args.repo or not args.output:
        parser.error("--repo and --output are required unless --check-llm-config is used.")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.check_llm_config:
        return _run_llm_check(args)

    repo_root = Path(args.repo).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()

    if not repo_root.exists() or not repo_root.is_dir():
        print(f"Repository path does not exist or is not a directory: {repo_root}", file=sys.stderr)
        return 1

    run_result = run_governed_analysis(repo_root)
    context = run_result["context"]
    artifacts = run_result["artifacts"]
    validated_findings = run_result["validated_findings"]
    module_inventory = run_result["module_inventory"]
    module_priorities = run_result["module_priorities"]
    module_deep_reviews = run_result["module_deep_reviews"]
    module_lightweight_cards = run_result["module_lightweight_cards"]
    module_heavyweight_cards = run_result["module_heavyweight_cards"]
    repo_inventory = run_result["repo_inventory"]
    triage = run_result["triage"]
    action_plan = run_result["action_plan"]
    critic_review = run_result["critic_review"]
    planner_agent = run_result["planner_agent"]
    critic_agent = run_result["critic_agent"]
    model_routing = run_result["model_routing"]

    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    _write_json(artifacts_dir / "import_graph.json", artifacts["import_graph"])
    _write_json(artifacts_dir / "definitions.json", artifacts["definitions"])
    _write_json(artifacts_dir / "call_graph.json", artifacts["call_graph"])
    _write_json(artifacts_dir / "env_usage.json", artifacts["env_usage"])
    _write_json(artifacts_dir / "db_usage.json", artifacts["db_usage"])
    _write_json(artifacts_dir / "utils_usage.json", artifacts["utils_usage"])
    _write_json(artifacts_dir / "global_state.json", artifacts["global_state"])
    _write_json(artifacts_dir / "findings.json", artifacts["findings"])
    _write_json(artifacts_dir / "validated_findings.json", validated_findings)
    _write_json(artifacts_dir / "module_inventory.json", module_inventory)
    _write_json(artifacts_dir / "module_priorities.json", module_priorities)
    _write_json(artifacts_dir / "module_deep_reviews.json", module_deep_reviews)
    _write_json(artifacts_dir / "repo_inventory.json", repo_inventory)
    _write_json(artifacts_dir / "triage.json", triage)
    _write_json(artifacts_dir / "action_plan.json", action_plan)
    _write_json(artifacts_dir / "critic_review.json", critic_review)
    _write_json(artifacts_dir / "planner_agent.json", planner_agent)
    _write_json(artifacts_dir / "critic_agent.json", critic_agent)
    _write_json(artifacts_dir / "model_routing.json", model_routing)

    summary = render_summary(
        repo_root=repo_root,
        context=context,
        import_graph=artifacts["import_graph"],
        definitions=artifacts["definitions"],
        call_graph=artifacts["call_graph"],
        env_usage=artifacts["env_usage"],
        db_usage=artifacts["db_usage"],
        utils_usage=artifacts["utils_usage"],
        global_state=artifacts["global_state"],
        findings=artifacts["findings"],
        validated_findings=validated_findings,
        repo_inventory=repo_inventory,
        triage=triage,
        action_plan=action_plan,
        critic_review=critic_review,
        planner_agent=planner_agent,
        critic_agent=critic_agent,
        model_routing=model_routing,
    )
    (output_dir / "summary.md").write_text(summary, encoding="utf-8")
    lightweight_dir = output_dir / "module_reports" / "lightweight"
    heavyweight_dir = output_dir / "module_reports" / "heavyweight"
    lightweight_dir.mkdir(parents=True, exist_ok=True)
    heavyweight_dir.mkdir(parents=True, exist_ok=True)
    for module_name, report_text in module_lightweight_cards.items():
        report_path = lightweight_dir / f"{_safe_module_report_name(module_name)}.md"
        report_path.write_text(report_text, encoding="utf-8")
    for module_name, report_text in module_heavyweight_cards.items():
        report_path = heavyweight_dir / f"{_safe_module_report_name(module_name)}.md"
        report_path.write_text(report_text, encoding="utf-8")

    print(f"Scanned {len(context.files)} Python files")
    print(f"Generated {artifacts['findings']['counts']['total']} findings")
    print(f"Validated {validated_findings['summary']['actionable_finding_count']} actionable findings")
    print(f"Profiled {module_inventory['summary']['total_modules']} modules")
    print(f"Generated {len(module_heavyweight_cards)} heavyweight module cards")
    print(f"Output written to {output_dir}")

    if not args.run_gates:
        return 0

    gate_report = run_iteration_gates(
        repo_root=repo_root,
        output_dir=output_dir,
        action_plan=action_plan,
        critic_review=critic_review,
        system_test_command=args.system_test_command,
        golden_test_command=args.golden_test_command,
        target_test_commands=list(args.target_test_command),
        runtime_commands=list(args.runtime_command),
    )
    print(f"Gate decision: {gate_report['decision']}")
    print(f"Agent gate report: {output_dir / 'artifacts' / 'iteration_agent_report.json'}")
    print(f"Human gate report: {output_dir / 'iteration_human_report.md'}")
    return decision_exit_code(gate_report["decision"])


def _run_llm_check(args: argparse.Namespace) -> int:
    health_check = run_llm_health_check()
    if args.output:
        output_dir = Path(args.output).expanduser().resolve()
        artifacts_dir = output_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        _write_json(artifacts_dir / "llm_health_check.json", health_check)

    print(json.dumps(to_jsonable(health_check), indent=2, ensure_ascii=False))
    return 0 if health_check["summary"]["ok"] else 1


def _write_json(path: Path, data: object) -> None:
    path.write_text(
        json.dumps(to_jsonable(data), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _safe_module_report_name(module_name: str) -> str:
    return module_name.replace("/", "_").replace("\\", "_").replace(".", "__")


if __name__ == "__main__":
    raise SystemExit(main())
