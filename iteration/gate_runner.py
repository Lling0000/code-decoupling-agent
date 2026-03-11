from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from policy.engine import evaluate_plan

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GATE_SPEC_PATH = PROJECT_ROOT / "config" / "gate_spec.json"
AGENT_REPORT_FILENAME = "iteration_agent_report.json"
HUMAN_REPORT_FILENAME = "iteration_human_report.md"
REQUIRED_OUTPUTS = (
    "summary.md",
    "artifacts/findings.json",
    "artifacts/validated_findings.json",
    "artifacts/action_plan.json",
    "artifacts/critic_review.json",
)


def load_gate_spec(path: Path | None = None) -> dict[str, object]:
    spec_path = path or DEFAULT_GATE_SPEC_PATH
    return json.loads(spec_path.read_text(encoding="utf-8"))


def run_iteration_gates(
    *,
    repo_root: Path,
    output_dir: Path,
    action_plan: dict[str, object],
    critic_review: dict[str, object],
    gate_spec_path: Path | None = None,
    system_test_command: str | None = None,
    golden_test_command: str | None = None,
    target_test_commands: list[str] | None = None,
    runtime_commands: list[str] | None = None,
) -> dict[str, object]:
    spec = load_gate_spec(gate_spec_path)
    gates_by_id = {item["gate_id"]: item for item in spec["gates"]}
    target_test_commands = target_test_commands or []
    runtime_commands = runtime_commands or []
    policy_result = evaluate_plan(action_plan)

    gates = [
        _run_test_gate(
            gate_spec=gates_by_id["test_gate"],
            repo_root=repo_root,
            system_test_command=system_test_command or f"{sys.executable} -m unittest -v",
            golden_test_command=golden_test_command or f"{sys.executable} -m unittest -v tests.test_goldens",
            target_test_commands=target_test_commands,
        ),
        _run_policy_gate(
            gate_spec=gates_by_id["policy_gate"],
            action_plan=action_plan,
            critic_review=critic_review,
            policy_result=policy_result,
        ),
        _run_runtime_gate(
            gate_spec=gates_by_id["runtime_gate"],
            repo_root=repo_root,
            output_dir=output_dir,
            runtime_commands=runtime_commands,
        ),
    ]

    decision = _decide_iteration(gates)
    agent_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": repo_root.as_posix(),
        "output_dir": output_dir.as_posix(),
        "gate_spec_path": str(gate_spec_path or DEFAULT_GATE_SPEC_PATH),
        "decision": decision,
        "summary": {
            "passed_gates": sum(1 for gate in gates if gate["status"] == "passed"),
            "failed_gates": sum(1 for gate in gates if gate["status"] == "failed"),
            "manual_review_gates": sum(1 for gate in gates if gate["status"] == "manual_review"),
        },
        "gates": gates,
        "policy_result": policy_result,
        "critic_status": critic_review.get("status"),
    }

    _write_agent_report(output_dir, agent_report)
    _write_human_report(output_dir, agent_report)
    return agent_report


def decision_exit_code(decision: str) -> int:
    if decision == "allow_next_iteration":
        return 0
    if decision == "hold_for_review":
        return 2
    return 1


def _run_test_gate(
    *,
    gate_spec: dict[str, object],
    repo_root: Path,
    system_test_command: str,
    golden_test_command: str,
    target_test_commands: list[str],
) -> dict[str, object]:
    checks = [
        _execute_command_check(
            check_id="system_test_suite",
            owner="Tool Runner",
            command=system_test_command,
            workdir=PROJECT_ROOT,
        ),
        _execute_command_check(
            check_id="golden_regression_suite",
            owner="Tool Runner",
            command=golden_test_command,
            workdir=PROJECT_ROOT,
        ),
    ]

    if target_test_commands:
        checks.append(
            _execute_multi_command_check(
                check_id="target_repo_regression_suite",
                owner="Verifier",
                commands=target_test_commands,
                workdir=repo_root,
            )
        )
    else:
        checks.append(
            _manual_review_check(
                check_id="target_repo_regression_suite",
                owner="Verifier",
                reason="未提供目标仓库测试命令，无法自动确认回归状态。",
            )
        )

    return _finalize_gate(gate_spec=gate_spec, checks=checks)


def _run_policy_gate(
    *,
    gate_spec: dict[str, object],
    action_plan: dict[str, object],
    critic_review: dict[str, object],
    policy_result: dict[str, object],
) -> dict[str, object]:
    checks = [
        {
            "check_id": "protected_path_check",
            "owner": "Policy Engine",
            "status": "failed" if policy_result["protected_files"] else "passed",
            "details": {
                "protected_files": policy_result["protected_files"],
            },
            "message": (
                f"检测到受保护路径：{', '.join(policy_result['protected_files'])}"
                if policy_result["protected_files"]
                else "未检测到受保护路径。"
            ),
        },
        {
            "check_id": "step_scope_check",
            "owner": "Policy Engine",
            "status": "failed" if policy_result["oversized_steps"] else "passed",
            "details": {
                "oversized_steps": policy_result["oversized_steps"],
                "max_files_per_step": policy_result["max_files_per_step"],
            },
            "message": (
                f"存在超范围 step：{', '.join(policy_result['oversized_steps'])}"
                if policy_result["oversized_steps"]
                else "所有 step 范围均在当前阈值内。"
            ),
        },
        {
            "check_id": "no_auto_execution_check",
            "owner": "Critic Agent",
            "status": "passed" if _plan_is_non_executing(action_plan) else "failed",
            "details": {
                "critic_status": critic_review.get("status"),
                "blocked": critic_review.get("blocked"),
            },
            "message": (
                "当前计划仍然是受控 patch plan，不会自动落盘执行。"
                if _plan_is_non_executing(action_plan)
                else "检测到疑似自动执行字段，违反受控执行边界。"
            ),
        },
    ]

    gate = _finalize_gate(gate_spec=gate_spec, checks=checks)
    if gate["status"] == "passed" and critic_review.get("status") == "needs_review":
        gate["status"] = "manual_review"
        gate["message"] = "策略检查通过，但 Critic 要求人工复核。"
    if critic_review.get("status") == "blocked":
        gate["status"] = "failed"
        gate["message"] = "Critic 已阻断当前计划，禁止进入下一轮。"
    return gate


def _run_runtime_gate(
    *,
    gate_spec: dict[str, object],
    repo_root: Path,
    output_dir: Path,
    runtime_commands: list[str],
) -> dict[str, object]:
    checks = [
        _artifact_completeness_check(output_dir),
    ]

    if runtime_commands:
        checks.append(
            _execute_command_check(
                check_id="target_repo_entrypoint_smoke_run",
                owner="Verifier",
                command=runtime_commands[0],
                workdir=repo_root,
            )
        )
        if len(runtime_commands) > 1:
            checks.append(
                _execute_command_check(
                    check_id="target_repo_core_command_check",
                    owner="Verifier",
                    command=runtime_commands[1],
                    workdir=repo_root,
                )
            )
        else:
            checks.append(
                _manual_review_check(
                    check_id="target_repo_core_command_check",
                    owner="Verifier",
                    reason="只提供了一个运行命令，缺少第二个核心路径 smoke check。",
                )
            )
    else:
        checks.extend(
            [
                _manual_review_check(
                    check_id="target_repo_entrypoint_smoke_run",
                    owner="Verifier",
                    reason="未提供目标仓库运行命令，无法自动验证入口是否可运行。",
                ),
                _manual_review_check(
                    check_id="target_repo_core_command_check",
                    owner="Verifier",
                    reason="未提供目标仓库核心命令，无法自动验证关键路径。",
                ),
            ]
        )

    return _finalize_gate(gate_spec=gate_spec, checks=checks)


def _artifact_completeness_check(output_dir: Path) -> dict[str, object]:
    missing = [path for path in REQUIRED_OUTPUTS if not (output_dir / path).exists()]
    return {
        "check_id": "artifact_completeness_check",
        "owner": "CLI",
        "status": "failed" if missing else "passed",
        "details": {
            "missing_outputs": missing,
        },
        "message": (
            f"缺少输出：{', '.join(missing)}"
            if missing
            else "summary 和关键 artifacts 已完整生成。"
        ),
    }


def _execute_multi_command_check(
    *,
    check_id: str,
    owner: str,
    commands: list[str],
    workdir: Path,
) -> dict[str, object]:
    results = [_execute_command(command=command, workdir=workdir) for command in commands]
    failed = [item for item in results if item["returncode"] != 0]
    return {
        "check_id": check_id,
        "owner": owner,
        "status": "failed" if failed else "passed",
        "details": {
            "commands": results,
        },
        "message": "目标仓库测试通过。" if not failed else "目标仓库测试失败。",
    }


def _execute_command_check(
    *,
    check_id: str,
    owner: str,
    command: str,
    workdir: Path,
) -> dict[str, object]:
    result = _execute_command(command=command, workdir=workdir)
    return {
        "check_id": check_id,
        "owner": owner,
        "status": "passed" if result["returncode"] == 0 else "failed",
        "details": result,
        "message": "命令执行成功。" if result["returncode"] == 0 else "命令执行失败。",
    }


def _manual_review_check(*, check_id: str, owner: str, reason: str) -> dict[str, object]:
    return {
        "check_id": check_id,
        "owner": owner,
        "status": "manual_review",
        "details": {
            "reason": reason,
        },
        "message": reason,
    }


def _execute_command(*, command: str, workdir: Path) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=workdir,
        shell=True,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": command,
        "workdir": workdir.as_posix(),
        "returncode": completed.returncode,
        "stdout_preview": completed.stdout[-1200:],
        "stderr_preview": completed.stderr[-1200:],
    }


def _finalize_gate(*, gate_spec: dict[str, object], checks: list[dict[str, object]]) -> dict[str, object]:
    failed = [item for item in checks if item["status"] == "failed"]
    manual_review = [item for item in checks if item["status"] == "manual_review"]

    if failed:
        status = "failed"
        message = "存在失败检查，当前 gate 不通过。"
    elif manual_review:
        status = "manual_review"
        message = "当前 gate 需要人工补充证据或复核。"
    else:
        status = "passed"
        message = "当前 gate 已通过。"

    return {
        "gate_id": gate_spec["gate_id"],
        "display_name": gate_spec["display_name"],
        "status": status,
        "message": message,
        "checks": checks,
    }


def _decide_iteration(gates: list[dict[str, object]]) -> str:
    if any(gate["status"] == "failed" for gate in gates):
        return "blocked"
    if all(gate["status"] == "passed" for gate in gates):
        return "allow_next_iteration"
    return "hold_for_review"


def _plan_is_non_executing(action_plan: dict[str, object]) -> bool:
    forbidden_keys = {"apply_patch", "write_files", "execute", "commit_changes"}
    for step in action_plan.get("steps", []):
        if forbidden_keys.intersection(step):
            return False
    return True


def _write_agent_report(output_dir: Path, agent_report: dict[str, object]) -> None:
    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / AGENT_REPORT_FILENAME).write_text(
        json.dumps(agent_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_human_report(output_dir: Path, agent_report: dict[str, object]) -> None:
    lines = [
        "# 迭代门禁报告",
        "",
        f"- 决策：{_decision_label(agent_report['decision'])}",
        f"- 仓库路径：`{agent_report['repo_root']}`",
        f"- 输出目录：`{agent_report['output_dir']}`",
        "",
        "## 总结",
        "",
        f"- 通过 Gate 数：{agent_report['summary']['passed_gates']}",
        f"- 失败 Gate 数：{agent_report['summary']['failed_gates']}",
        f"- 待人工复核 Gate 数：{agent_report['summary']['manual_review_gates']}",
        f"- Critic 状态：{agent_report.get('critic_status')}",
        "",
    ]

    for gate in agent_report["gates"]:
        lines.extend(
            [
                f"## {gate['display_name']}",
                "",
                f"- 状态：{_gate_status_label(gate['status'])}",
                f"- 说明：{gate['message']}",
                "",
            ]
        )
        for check in gate["checks"]:
            lines.append(f"- `{check['check_id']}`：{_gate_status_label(check['status'])}，{check['message']}")
        lines.append("")

    lines.extend(
        [
            "## 结论",
            "",
            _decision_summary(agent_report["decision"]),
            "",
        ]
    )

    (output_dir / HUMAN_REPORT_FILENAME).write_text("\n".join(lines), encoding="utf-8")


def _decision_label(decision: str) -> str:
    labels = {
        "allow_next_iteration": "允许进入下一轮",
        "hold_for_review": "暂停，等待人工复核",
        "blocked": "阻断",
    }
    return labels.get(decision, decision)


def _gate_status_label(status: str) -> str:
    labels = {
        "passed": "通过",
        "failed": "失败",
        "manual_review": "待人工复核",
    }
    return labels.get(status, status)


def _decision_summary(decision: str) -> str:
    if decision == "allow_next_iteration":
        return "本轮已同时满足测试、策略和运行门禁，可以进入下一轮。"
    if decision == "hold_for_review":
        return "本轮没有硬失败，但仍缺少关键证据或存在人工复核项，暂不允许自动进入下一轮。"
    return "本轮存在门禁失败项，必须先修复或回滚后再继续。"
