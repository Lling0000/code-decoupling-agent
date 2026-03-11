from __future__ import annotations

import unittest
from os import environ
from pathlib import Path
from unittest.mock import patch

from agents.module_report_agent import (
    build_module_deep_reviews,
    build_module_heavyweight_cards,
    build_module_inventory,
    build_module_lightweight_cards,
    build_module_priority_groups,
)
from agents.tool_runner import run_deterministic_toolchain
from agents.validator_agent import run_validator_agent
from llm.catalog import build_model_routing
from llm.env import clear_env_cache
from scanner import build_repo_context


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD_REPO = PROJECT_ROOT / "tests" / "fixtures" / "repos" / "gold_repo"


class ModuleReportTests(unittest.TestCase):
    def test_module_inventory_prioritizes_hot_modules(self) -> None:
        context = build_repo_context(GOLD_REPO)
        tool_results = run_deterministic_toolchain(context)

        with patch.dict(environ, {"ENABLE_LIVE_AGENTS": "0"}, clear=False):
            clear_env_cache()
            model_routing = build_model_routing()
            validated_findings = run_validator_agent(
                findings_artifact=tool_results["findings"],
                context=context,
                model_routing=model_routing,
            )["validated_findings"]
            clear_env_cache()

        module_inventory = build_module_inventory(
            context=context,
            tool_results=tool_results,
            validated_findings=validated_findings,
        )
        module_priorities = build_module_priority_groups(module_inventory)

        self.assertEqual(module_inventory["summary"]["total_modules"], 12)
        self.assertEqual(module_inventory["summary"]["p0"], 2)
        p0_modules = {item["module"] for item in module_priorities["groups"]["P0"]}
        self.assertEqual(p0_modules, {"app.routes", "app.state"})

        routes_entry = next(item for item in module_inventory["modules"] if item["module"] == "app.routes")
        self.assertEqual(routes_entry["priority"], "P0")
        self.assertEqual(routes_entry["layer"], "interface")
        self.assertGreater(routes_entry["metrics"]["db_signal_count"], 0)

    def test_lightweight_and_heavyweight_cards_render_expected_sections(self) -> None:
        context = build_repo_context(GOLD_REPO)
        tool_results = run_deterministic_toolchain(context)

        with patch.dict(environ, {"ENABLE_LIVE_AGENTS": "0"}, clear=False):
            clear_env_cache()
            model_routing = build_model_routing()
            validated_findings = run_validator_agent(
                findings_artifact=tool_results["findings"],
                context=context,
                model_routing=model_routing,
            )["validated_findings"]
            clear_env_cache()

        module_inventory = build_module_inventory(
            context=context,
            tool_results=tool_results,
            validated_findings=validated_findings,
        )
        module_deep_reviews = build_module_deep_reviews(
            module_inventory=module_inventory,
            model_routing=model_routing,
        )
        light_cards = build_module_lightweight_cards(module_inventory)
        heavy_cards = build_module_heavyweight_cards(module_inventory, module_deep_reviews)

        self.assertEqual(len(light_cards), 12)
        self.assertEqual(len(heavy_cards), 5)
        self.assertIn("app.routes", light_cards)
        self.assertIn("app.routes", heavy_cards)
        self.assertIn("## 优先级原因", light_cards["app.routes"])

        heavy_report = heavy_cards["app.routes"]
        self.assertIn("## 1. 模块职责", heavy_report)
        self.assertIn("## 4. 耦合分析", heavy_report)
        self.assertIn("## 5. 深审增强", heavy_report)
        self.assertIn("### Validator 复核", heavy_report)
        self.assertIn("### Planner 建议", heavy_report)
        self.assertIn("### Critic 审查", heavy_report)
        self.assertIn("控制层直接接触数据库或 ORM 信号", heavy_report)

    def test_module_deep_reviews_can_use_mocked_llm_clients_for_top_modules(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.calls = 0

            def chat_json(self, **_: object) -> dict[str, object]:
                self.calls += 1
                if self.calls % 3 == 1:
                    return {
                        "json": {
                            "confirmation_status": "confirmed",
                            "confidence": "high",
                            "summary": "模块值得优先治理。",
                            "key_evidence": ["接口层直接接触数据库信号"],
                        }
                    }
                if self.calls % 3 == 2:
                    return {
                        "json": {
                            "recommend_change": "yes",
                            "priority": "high",
                            "actions": ["下沉依赖", "补测试"],
                            "test_recommendations": ["补边界回归测试"],
                            "summary": "建议先处理边界问题。",
                        }
                    }
                return {
                    "json": {
                        "review_status": "needs_review",
                        "risk_level": "high",
                        "concerns": ["高扇入模块，改动面较大。"],
                        "summary": "建议小步推进。",
                    }
                }

        context = build_repo_context(GOLD_REPO)
        tool_results = run_deterministic_toolchain(context)
        client = FakeClient()

        with patch.dict(
            environ,
            {
                "ENABLE_LIVE_AGENTS": "1",
                "DASHSCOPE_API_KEY": "fake-key",
                "PLANNER_MODEL": "deepseek-v3.2",
            },
            clear=False,
        ):
            clear_env_cache()
            model_routing = build_model_routing()
            validated_findings = run_validator_agent(
                findings_artifact=tool_results["findings"],
                context=context,
                model_routing=model_routing,
            )["validated_findings"]
            module_inventory = build_module_inventory(
                context=context,
                tool_results=tool_results,
                validated_findings=validated_findings,
            )
            with patch("agents.module_report_agent.build_bailian_client", return_value=client):
                module_deep_reviews = build_module_deep_reviews(
                    module_inventory=module_inventory,
                    model_routing=model_routing,
                )
            clear_env_cache()

        self.assertEqual(module_deep_reviews["summary"]["reviewed_modules"], 5)
        self.assertEqual(module_deep_reviews["summary"]["llm_reviewed_modules"], 5)
        first_review = module_deep_reviews["modules"][0]
        self.assertEqual(first_review["generation"]["mode"], "llm")
        self.assertEqual(first_review["validator_review"]["confidence"], "high")
        self.assertEqual(first_review["planner_review"]["recommend_change"], "yes")
        self.assertEqual(first_review["critic_review"]["review_status"], "needs_review")


if __name__ == "__main__":
    unittest.main()
