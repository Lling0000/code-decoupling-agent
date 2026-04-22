from __future__ import annotations

import unittest
from os import environ
from pathlib import Path
import tempfile
from unittest.mock import patch

from agents.critic_agent import build_deterministic_review
from agents.planner_agent import build_action_plan, build_triage
from agents.scanner_agent import build_repo_inventory
from agents.tool_runner import run_deterministic_toolchain
from agents.validator_agent import actionable_findings_artifact, run_validator_agent
from llm.catalog import build_model_routing
from llm.env import clear_env_cache
from report.renderer import render_summary
from scanner import build_repo_context


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD_REPO = PROJECT_ROOT / "tests" / "fixtures" / "repos" / "gold_repo"


class ReportingTests(unittest.TestCase):
    def test_summary_includes_validation_status_and_confidence(self) -> None:
        context = build_repo_context(GOLD_REPO)
        artifacts = run_deterministic_toolchain(context)
        repo_inventory = build_repo_inventory(context, artifacts)

        with patch.dict(environ, {"ENABLE_LIVE_AGENTS": "0"}, clear=False):
            clear_env_cache()
            model_routing = build_model_routing()
            validated_findings = run_validator_agent(
                findings_artifact=artifacts["findings"],
                context=context,
                model_routing=model_routing,
            )["validated_findings"]
            clear_env_cache()

        triage = build_triage(actionable_findings_artifact(validated_findings))
        action_plan = build_action_plan(triage)
        action_plan["generation"] = {"mode": "deterministic_fallback"}
        critic_review, _ = build_deterministic_review(action_plan, repo_inventory)
        critic_review["generation"] = {"mode": "deterministic_fallback"}
        planner_agent = {"mode": "deterministic_fallback"}
        critic_agent = {"mode": "deterministic_fallback"}

        summary = render_summary(
            repo_root=GOLD_REPO,
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

        self.assertIn("## 扫描概览", summary)
        self.assertIn("## Findings", summary)
        self.assertIn("确认状态", summary)
        self.assertIn("置信度", summary)
        self.assertIn("Validator 生成方式", summary)
        self.assertIn("疑似可变全局状态", summary)

    def test_summary_marks_non_product_global_state_as_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            tests_dir = repo / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_state.py").write_text("ITEMS = []\n", encoding="utf-8")
            context = build_repo_context(repo)

            summary = render_summary(
                repo_root=repo,
                context=context,
                import_graph={"files": [], "cycles": []},
                definitions={"totals": {"classes": 0, "functions": 0, "methods": 0}},
                call_graph={"edges": []},
                env_usage={"variables": []},
                db_usage={"files": []},
                utils_usage={"modules": []},
                global_state={"files": [{"file": "tests/test_state.py", "risk_count": 1}]},
                findings={"counts": {"total": 0}},
                validated_findings={
                    "summary": {"actionable_finding_count": 0, "confirmed": 0, "needs_review": 0, "rejected": 0},
                    "generation": {"mode": "deterministic_fallback"},
                    "findings": [],
                },
                repo_inventory={"hotspots": []},
                triage={"summary": {"total": 0}},
                action_plan={"steps": []},
                critic_review={
                    "status": "approved",
                    "risk_level": "low",
                    "summary": "ok",
                    "required_checks": ["pytest"],
                    "generation": {"mode": "deterministic_fallback"},
                    "concerns": [],
                },
                planner_agent={"mode": "deterministic_fallback"},
                critic_agent={"mode": "deterministic_fallback"},
                model_routing={"assignments": [], "providers": []},
            )

            self.assertIn("这些路径默认不进入 findings", summary)


if __name__ == "__main__":
    unittest.main()
