from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main as main_module
from iteration.gate_runner import run_iteration_gates


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_required_outputs(output_dir: Path) -> None:
    (output_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.md").write_text("# summary\n", encoding="utf-8")
    for rel_path in (
        "artifacts/findings.json",
        "artifacts/validated_findings.json",
        "artifacts/action_plan.json",
        "artifacts/critic_review.json",
    ):
        (output_dir / rel_path).write_text("{}\n", encoding="utf-8")


def _passing_command_result(*, command: str, workdir: Path) -> dict[str, object]:
    return {
        "command": command,
        "workdir": workdir.as_posix(),
        "returncode": 0,
        "stdout_preview": "OK",
        "stderr_preview": "",
    }


class GateRunnerTests(unittest.TestCase):
    def test_gate_runner_allows_next_iteration_when_all_checks_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            output_dir = Path(tmp) / "out"
            repo_root.mkdir()
            _write_required_outputs(output_dir)

            action_plan = {
                "steps": [
                    {
                        "step_id": "STEP-01",
                        "files": ["app/service.py"],
                        "guarded_by": ["Policy Engine", "Tool Runner"],
                    }
                ]
            }
            critic_review = {"status": "approved", "blocked": False}

            with patch("iteration.gate_runner._execute_command", side_effect=_passing_command_result):
                report = run_iteration_gates(
                    repo_root=repo_root,
                    output_dir=output_dir,
                    action_plan=action_plan,
                    critic_review=critic_review,
                    system_test_command="sys-tests",
                    golden_test_command="gold-tests",
                    target_test_commands=["repo-tests"],
                    runtime_commands=["repo-run", "repo-smoke"],
                )

            self.assertEqual(report["decision"], "allow_next_iteration")
            self.assertTrue((output_dir / "artifacts" / "iteration_agent_report.json").exists())
            self.assertTrue((output_dir / "iteration_human_report.md").exists())
            human_report = (output_dir / "iteration_human_report.md").read_text(encoding="utf-8")
            self.assertIn("允许进入下一轮", human_report)

    def test_gate_runner_holds_for_review_when_runtime_or_target_tests_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            output_dir = Path(tmp) / "out"
            repo_root.mkdir()
            _write_required_outputs(output_dir)

            with patch("iteration.gate_runner._execute_command", side_effect=_passing_command_result):
                report = run_iteration_gates(
                    repo_root=repo_root,
                    output_dir=output_dir,
                    action_plan={"steps": []},
                    critic_review={"status": "approved", "blocked": False},
                    system_test_command="sys-tests",
                    golden_test_command="gold-tests",
                    target_test_commands=[],
                    runtime_commands=[],
                )

            self.assertEqual(report["decision"], "hold_for_review")
            gate_map = {item["gate_id"]: item for item in report["gates"]}
            self.assertEqual(gate_map["test_gate"]["status"], "manual_review")
            self.assertEqual(gate_map["runtime_gate"]["status"], "manual_review")

    def test_gate_runner_blocks_when_policy_gate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            output_dir = Path(tmp) / "out"
            repo_root.mkdir()
            _write_required_outputs(output_dir)

            action_plan = {
                "steps": [
                    {
                        "step_id": "STEP-01",
                        "files": ["app/settings.py"],
                        "guarded_by": ["Policy Engine", "Tool Runner"],
                    }
                ]
            }

            with patch("iteration.gate_runner._execute_command", side_effect=_passing_command_result):
                report = run_iteration_gates(
                    repo_root=repo_root,
                    output_dir=output_dir,
                    action_plan=action_plan,
                    critic_review={"status": "approved", "blocked": False},
                    system_test_command="sys-tests",
                    golden_test_command="gold-tests",
                    target_test_commands=["repo-tests"],
                    runtime_commands=["repo-run", "repo-smoke"],
                )

            self.assertEqual(report["decision"], "blocked")
            gate_map = {item["gate_id"]: item for item in report["gates"]}
            self.assertEqual(gate_map["policy_gate"]["status"], "failed")

    def test_main_run_gates_writes_reports_and_returns_gate_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            out = Path(tmp) / "out"
            repo.mkdir()
            (repo / "main.py").write_text("def run():\n    return 'ok'\n", encoding="utf-8")

            with patch("iteration.gate_runner._execute_command", side_effect=_passing_command_result):
                exit_code = main_module.main(
                    [
                        "--repo",
                        str(repo),
                        "--output",
                        str(out),
                        "--run-gates",
                        "--system-test-command",
                        "sys-tests",
                        "--golden-test-command",
                        "gold-tests",
                        "--target-test-command",
                        "repo-tests",
                        "--runtime-command",
                        "repo-run",
                        "--runtime-command",
                        "repo-smoke",
                    ]
                )

            self.assertEqual(exit_code, 0)
            report_path = out / "artifacts" / "iteration_agent_report.json"
            self.assertTrue(report_path.exists())
            agent_report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(agent_report["decision"], "allow_next_iteration")
            self.assertTrue((out / "iteration_human_report.md").exists())


if __name__ == "__main__":
    unittest.main()
