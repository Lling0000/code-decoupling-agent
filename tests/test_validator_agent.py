from __future__ import annotations

import unittest
from os import environ
from pathlib import Path
from unittest.mock import patch

from agents.tool_runner import run_deterministic_toolchain
from agents.validator_agent import actionable_findings_artifact, run_validator_agent
from llm.catalog import build_model_routing
from llm.env import clear_env_cache
from scanner import build_repo_context


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD_REPO = PROJECT_ROOT / "tests" / "fixtures" / "repos" / "gold_repo"


class ValidatorAgentTests(unittest.TestCase):
    def test_validator_fallback_adds_status_confidence_and_snippets(self) -> None:
        context = build_repo_context(GOLD_REPO)
        findings_artifact = run_deterministic_toolchain(context)["findings"]

        with patch.dict(environ, {"ENABLE_LIVE_AGENTS": "0"}, clear=False):
            clear_env_cache()
            model_routing = build_model_routing()
            result = run_validator_agent(
                findings_artifact=findings_artifact,
                context=context,
                model_routing=model_routing,
            )
            clear_env_cache()

        validated = result["validated_findings"]
        self.assertEqual(validated["generation"]["mode"], "deterministic_fallback")
        self.assertEqual(validated["summary"]["raw_finding_count"], findings_artifact["counts"]["total"])
        self.assertEqual(validated["summary"]["validated_finding_count"], len(validated["findings"]))
        self.assertEqual(
            validated["summary"]["confirmed"]
            + validated["summary"]["needs_review"]
            + validated["summary"]["rejected"],
            len(validated["findings"]),
        )

        rule_map = {item["rule_id"]: item for item in validated["findings"]}
        self.assertEqual(set(rule_map), {"RULE_A", "RULE_B", "RULE_C", "RULE_D", "RULE_E"})
        self.assertEqual(rule_map["RULE_A"]["confirmation_status"], "confirmed")
        self.assertEqual(rule_map["RULE_D"]["confidence"], "high")
        self.assertIn("session.execute", rule_map["RULE_A"]["file_snippets"][0]["blocks"][0]["snippet"])

        for item in validated["findings"]:
            self.assertIn(item["confirmation_status"], {"confirmed", "needs_review", "rejected"})
            self.assertIn(item["confidence"], {"high", "medium", "low"})
            self.assertIn("validation_reason", item)
            self.assertIn("file_snippets", item)

    def test_actionable_findings_filters_rejected_items_and_strips_validation_fields(self) -> None:
        validated_findings = {
            "findings": [
                {
                    "rule_id": "RULE_A",
                    "rule_name": "Handler/Controller 直接访问数据库",
                    "severity": "high",
                    "files": ["app/routes/user_handler.py"],
                    "evidence": ["session.execute（第 5 行，置信度=高）"],
                    "explanation": "请求层直接访问数据库。",
                    "suggestion": "抽到 service。",
                    "confirmation_status": "confirmed",
                    "confidence": "high",
                    "validation_reason": "证据充分。",
                    "file_snippets": [],
                    "validation_source": "llm",
                    "validation_model": "deepseek-v3.2",
                    "needs_human_review": False,
                },
                {
                    "rule_id": "RULE_C",
                    "rule_name": "共享 Utils 模块被过度依赖",
                    "severity": "medium",
                    "files": ["app/common/helpers.py"],
                    "evidence": ["helpers 被多个文件依赖"],
                    "explanation": "共享模块过载。",
                    "suggestion": "按领域拆分。",
                    "confirmation_status": "rejected",
                    "confidence": "low",
                    "validation_reason": "证据不足。",
                    "file_snippets": [],
                    "validation_source": "deterministic_fallback",
                    "validation_model": None,
                    "needs_human_review": True,
                },
                {
                    "rule_id": "RULE_D",
                    "rule_name": "疑似可变全局状态",
                    "severity": "medium",
                    "files": ["app/state/cache.py"],
                    "evidence": ["CACHE（第 1 行，变更次数=1）"],
                    "explanation": "共享状态会放大副作用。",
                    "suggestion": "封装成显式对象。",
                    "confirmation_status": "needs_review",
                    "confidence": "medium",
                    "validation_reason": "需要补更多上下文。",
                    "file_snippets": [],
                    "validation_source": "llm",
                    "validation_model": "deepseek-v3.2",
                    "needs_human_review": True,
                },
            ],
            "summary": {},
            "generation": {"mode": "hybrid"},
        }

        actionable = actionable_findings_artifact(validated_findings)

        self.assertEqual(actionable["counts"]["total"], 2)
        self.assertEqual(actionable["counts"]["high"], 1)
        self.assertEqual(actionable["counts"]["medium"], 1)
        self.assertEqual({item["rule_id"] for item in actionable["findings"]}, {"RULE_A", "RULE_D"})
        for item in actionable["findings"]:
            self.assertNotIn("confirmation_status", item)
            self.assertNotIn("confidence", item)
            self.assertNotIn("validation_reason", item)
            self.assertNotIn("file_snippets", item)

    def test_validator_llm_path_uses_mocked_client(self) -> None:
        class FakeValidatorClient:
            def __init__(self) -> None:
                self.calls = 0

            def chat_json(self, **_: object) -> dict[str, object]:
                self.calls += 1
                return {
                    "json": {
                        "confirmation_status": "needs_review",
                        "confidence": "low",
                        "reason": "证据不足，建议人工复核。",
                    },
                    "id": f"validator-{self.calls}",
                }

        context = build_repo_context(GOLD_REPO)
        findings_artifact = run_deterministic_toolchain(context)["findings"]
        client = FakeValidatorClient()

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
            with patch("agents.validator_agent.build_bailian_client", return_value=client):
                result = run_validator_agent(
                    findings_artifact=findings_artifact,
                    context=context,
                    model_routing=model_routing,
                )
            clear_env_cache()

        validated = result["validated_findings"]
        self.assertEqual(validated["generation"]["mode"], "llm")
        self.assertEqual(client.calls, findings_artifact["counts"]["total"])
        for item in validated["findings"]:
            self.assertEqual(item["validation_source"], "llm")
            self.assertEqual(item["validation_model"], "deepseek-v3.2")
            self.assertEqual(item["confirmation_status"], "needs_review")
            self.assertEqual(item["confidence"], "low")


if __name__ == "__main__":
    unittest.main()
