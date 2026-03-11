from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from os import environ
from pathlib import Path
from unittest.mock import patch

import main as main_module
from agents.governor import run_governed_analysis
from llm.catalog import build_model_routing
from llm.env import clear_env_cache
from llm.health import run_llm_health_check
from rules_engine.engine import detect_import_cycles, run_rules
from scanner import build_repo_context
from scanner.db_usage import scan_db_usage
from scanner.envs import scan_env_usage
from scanner.globals import scan_global_state
from scanner.imports import scan_imports
from scanner.utils_usage import scan_utils_usage


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SmokeTests(unittest.TestCase):
    def test_import_scanner_resolves_local_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "pkg").mkdir()
            (repo / "pkg" / "__init__.py").write_text("", encoding="utf-8")
            (repo / "pkg" / "service.py").write_text("VALUE = 1\n", encoding="utf-8")
            (repo / "app.py").write_text(
                textwrap.dedent(
                    """
                    import pkg.service
                    from pkg import service
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            context = build_repo_context(repo)
            artifact = scan_imports(context)

            edges = {(item["source"], item["target"]) for item in artifact["local_edges"]}
            self.assertIn(("app.py", "pkg/service.py"), edges)

    def test_import_scanner_ignores_type_checking_only_imports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "pkg").mkdir()
            (repo / "pkg" / "__init__.py").write_text("", encoding="utf-8")
            (repo / "pkg" / "a.py").write_text(
                textwrap.dedent(
                    """
                    from typing import TYPE_CHECKING

                    if TYPE_CHECKING:
                        from pkg import b
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (repo / "pkg" / "b.py").write_text("from pkg import a\n", encoding="utf-8")

            context = build_repo_context(repo)
            artifact = scan_imports(context)
            cycles = detect_import_cycles(artifact)

            edges = {(item["source"], item["target"]) for item in artifact["local_edges"]}
            self.assertNotIn(("pkg/a.py", "pkg/b.py"), edges)
            self.assertEqual(cycles, [])

    def test_env_scanner_detects_common_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "config.py").write_text(
                textwrap.dedent(
                    """
                    import os
                    from os import getenv

                    API_KEY = os.getenv("API_KEY")
                    DB_URL = os.environ["DB_URL"]
                    FEATURE_FLAG = getenv("FEATURE_FLAG")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            context = build_repo_context(repo)
            artifact = scan_env_usage(context)

            variables = {item["name"] for item in artifact["variables"]}
            self.assertEqual(variables, {"API_KEY", "DB_URL", "FEATURE_FLAG"})

    def test_rule_engine_flags_handler_direct_db_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "routes").mkdir()
            (repo / "routes" / "user_handler.py").write_text(
                textwrap.dedent(
                    """
                    from sqlalchemy import select

                    def list_users(session):
                        return session.execute(select("users"))
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            context = build_repo_context(repo)
            import_graph = scan_imports(context)
            db_usage = scan_db_usage(context)
            utils_usage = scan_utils_usage(import_graph)
            global_state = scan_global_state(context)
            cycles = detect_import_cycles(import_graph)
            findings = run_rules(
                import_graph=import_graph,
                env_usage={"reads": [], "variables": []},
                db_usage=db_usage,
                utils_usage=utils_usage,
                global_state=global_state,
                cycles=cycles,
            )

            rule_ids = {item["rule_id"] for item in findings["findings"]}
            self.assertIn("RULE_A", rule_ids)

    def test_utils_scanner_ignores_external_utils_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "app.py").write_text(
                textwrap.dedent(
                    """
                    from torch.utils.data import Dataset

                    class LocalDataset(Dataset):
                        pass
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            context = build_repo_context(repo)
            import_graph = scan_imports(context)
            artifact = scan_utils_usage(import_graph)

            self.assertEqual(artifact["modules"], [])

    def test_governor_generates_plan_and_critic_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "routes").mkdir()
            (repo / "routes" / "user_handler.py").write_text(
                textwrap.dedent(
                    """
                    from sqlalchemy import select

                    CACHE = {}

                    def list_users(session):
                        CACHE["last"] = "users"
                        return session.execute(select("users"))
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            with patch.dict(environ, {"ENABLE_LIVE_AGENTS": "0"}, clear=False):
                clear_env_cache()
                result = run_governed_analysis(repo)
                clear_env_cache()

            self.assertTrue(result["action_plan"]["steps"])
            self.assertIn(result["critic_review"]["status"], {"approved", "needs_review", "blocked"})
            self.assertGreaterEqual(result["triage"]["summary"]["total"], 1)
            self.assertEqual(
                result["validated_findings"]["summary"]["raw_finding_count"],
                result["artifacts"]["findings"]["counts"]["total"],
            )
            self.assertIn(
                result["validated_findings"]["findings"][0]["confirmation_status"],
                {"confirmed", "needs_review", "rejected"},
            )
            self.assertEqual(result["planner_agent"]["mode"], "deterministic_fallback")
            self.assertEqual(result["critic_agent"]["mode"], "deterministic_fallback")

    def test_model_routing_uses_bailian_env_overrides(self) -> None:
        overrides = {
            "DASHSCOPE_API_KEY": "test-key",
            "DASHSCOPE_BASE_URL": "https://example.invalid/compatible/v1",
            "DASHSCOPE_MODEL": "qwen3.5-flash",
            "CODER_MODEL": "qwen3-coder-flash",
            "PLANNER_MODEL": "deepseek-v3.2",
            "ENABLE_LIVE_AGENTS": "1",
        }
        with patch.dict(environ, overrides, clear=False):
            clear_env_cache()
            routing = build_model_routing()
            clear_env_cache()

        provider = routing["providers"][0]
        assignments = {item["role"]: item for item in routing["assignments"]}

        self.assertEqual(provider["provider_id"], "bailian")
        self.assertEqual(provider["base_url"], overrides["DASHSCOPE_BASE_URL"])
        self.assertEqual(provider["base_url_env"], "DASHSCOPE_BASE_URL")
        self.assertTrue(provider["configured"])
        self.assertEqual(assignments["planner_triage_review"]["api_model"], "deepseek-v3.2")
        self.assertEqual(assignments["refactor_and_test_fix"]["api_model"], "qwen3-coder-flash")
        self.assertEqual(assignments["summary_and_pr_copy"]["api_model"], "qwen3.5-flash")
        self.assertTrue(routing["policy"]["external_llm_calls_enabled"])

    def test_model_routing_uses_config_defaults_when_env_missing(self) -> None:
        config_override = {
            "provider": {
                "provider_id": "bailian",
                "display_name": "Test Provider",
                "api_key_env": "DASHSCOPE_API_KEY",
                "base_url_env": "DASHSCOPE_BASE_URL",
                "base_url_env_aliases": ["BAILIAN_BASE_URL"],
                "default_base_url": "https://config.example/v1",
            },
            "models": {
                "planner": "planner-from-config",
                "critic": "critic-from-config",
                "coder": "coder-from-config",
                "summary": "summary-from-config",
                "embedding": "embedding-from-config",
                "rerank": "rerank-from-config",
            },
        }
        def fake_env_value_with_aliases(primary_name: str, aliases: list[str], default: str | None = None):
            if primary_name == "DASHSCOPE_BASE_URL":
                return config_override["provider"]["default_base_url"], None
            if primary_name == "DASHSCOPE_MODEL":
                return default, None
            return default, None

        with patch("llm.catalog.load_agent_model_config", return_value=config_override):
            with patch("llm.catalog.env_value_with_aliases", side_effect=fake_env_value_with_aliases):
                with patch.dict(environ, {"ENABLE_LIVE_AGENTS": "0"}, clear=False):
                    clear_env_cache()
                    routing = build_model_routing()
                    clear_env_cache()

        provider = routing["providers"][0]
        assignments = {item["role"]: item for item in routing["assignments"]}
        self.assertEqual(provider["base_url"], "https://config.example/v1")
        self.assertEqual(assignments["planner_triage_review"]["api_model"], "planner-from-config")
        self.assertEqual(assignments["critic_review"]["api_model"], "critic-from-config")
        self.assertEqual(assignments["refactor_and_test_fix"]["api_model"], "coder-from-config")
        self.assertEqual(assignments["summary_and_pr_copy"]["api_model"], "summary-from-config")

    def test_environment_variables_override_config_defaults(self) -> None:
        config_override = {
            "provider": {
                "provider_id": "bailian",
                "display_name": "Test Provider",
                "api_key_env": "DASHSCOPE_API_KEY",
                "base_url_env": "DASHSCOPE_BASE_URL",
                "base_url_env_aliases": ["BAILIAN_BASE_URL"],
                "default_base_url": "https://config.example/v1",
            },
            "models": {
                "planner": "planner-from-config",
                "critic": "critic-from-config",
                "coder": "coder-from-config",
                "summary": "summary-from-config",
                "embedding": "embedding-from-config",
                "rerank": "rerank-from-config",
            },
        }
        overrides = {
            "DASHSCOPE_API_KEY": "test-key",
            "DASHSCOPE_BASE_URL": "https://env.example/v1",
            "DASHSCOPE_MODEL": "summary-from-env",
            "CODER_MODEL": "coder-from-env",
            "PLANNER_MODEL": "planner-from-env",
            "ENABLE_LIVE_AGENTS": "1",
        }
        with patch("llm.catalog.load_agent_model_config", return_value=config_override):
            with patch.dict(environ, overrides, clear=False):
                clear_env_cache()
                routing = build_model_routing()
                clear_env_cache()

        provider = routing["providers"][0]
        assignments = {item["role"]: item for item in routing["assignments"]}
        self.assertEqual(provider["base_url"], "https://env.example/v1")
        self.assertEqual(assignments["planner_triage_review"]["api_model"], "planner-from-env")
        self.assertEqual(assignments["critic_review"]["api_model"], "planner-from-env")
        self.assertEqual(assignments["refactor_and_test_fix"]["api_model"], "coder-from-env")
        self.assertEqual(assignments["summary_and_pr_copy"]["api_model"], "summary-from-env")

    def test_model_routing_accepts_legacy_bailian_model_alias(self) -> None:
        overrides = {
            "DASHSCOPE_API_KEY": "test-key",
            "BAILIAN_MODEL": "legacy-summary-model",
            "ENABLE_LIVE_AGENTS": "1",
        }
        with patch.dict(environ, overrides, clear=False):
            clear_env_cache()
            routing = build_model_routing()
            clear_env_cache()

        assignments = {item["role"]: item for item in routing["assignments"]}
        self.assertEqual(assignments["summary_and_pr_copy"]["api_model"], "legacy-summary-model")

    def test_model_routing_accepts_legacy_bailian_base_url_alias(self) -> None:
        overrides = {
            "DASHSCOPE_API_KEY": "test-key",
            "BAILIAN_BASE_URL": "https://legacy.invalid/compatible/v1",
            "ENABLE_LIVE_AGENTS": "1",
        }
        with patch.dict(environ, overrides, clear=False):
            clear_env_cache()
            with patch(
                "llm.catalog.env_value_with_aliases",
                return_value=(overrides["BAILIAN_BASE_URL"], "BAILIAN_BASE_URL"),
            ):
                routing = build_model_routing()
            clear_env_cache()

        provider = routing["providers"][0]
        self.assertEqual(provider["base_url"], overrides["BAILIAN_BASE_URL"])
        self.assertEqual(provider["base_url_env_resolved_from"], "BAILIAN_BASE_URL")

    def test_governor_uses_live_planner_and_critic_when_client_available(self) -> None:
        class FakePlannerClient:
            def chat_json(self, **_: object) -> dict[str, object]:
                return {
                    "json": {
                        "strategy": "LLM-selected bounded cleanup plan",
                        "steps": [
                            {
                                "title": "Move DB logic out of handler",
                                "category": "architecture_boundary",
                                "priority": "P0",
                                "owner": "Refactor Agent",
                                "files": ["routes/user_handler.py"],
                                "finding_rule": "RULE_A",
                                "rationale": "Handler DB access should move behind a service boundary.",
                                "success_criteria": ["No direct DB access remains in the handler."],
                                "rollback_conditions": ["Endpoint behavior changes unexpectedly."],
                                "deterministic_tools": ["pytest"],
                                "guarded_by": ["Policy Engine"],
                            }
                        ],
                        "backlog": [],
                    },
                    "id": "planner-1",
                }

        class FakeCriticClient:
            def chat_json(self, **_: object) -> dict[str, object]:
                return {
                    "json": {
                        "status": "needs_review",
                        "blocked": False,
                        "risk_level": "medium",
                        "concerns": ["Validate the extracted service boundary with regression tests."],
                        "required_checks": ["pytest"],
                        "summary": "Plan looks reasonable but still needs review before execution.",
                    },
                    "id": "critic-1",
                }

        class FakeValidatorClient:
            def chat_json(self, **_: object) -> dict[str, object]:
                return {
                    "json": {
                        "confirmation_status": "confirmed",
                        "confidence": "medium",
                        "reason": "证据与代码片段一致，可以保留该 finding。",
                    },
                    "id": "validator-1",
                }

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "routes").mkdir()
            (repo / "routes" / "user_handler.py").write_text(
                textwrap.dedent(
                    """
                    from sqlalchemy import select

                    def list_users(session):
                        return session.execute(select("users"))
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            overrides = {
                "ENABLE_LIVE_AGENTS": "1",
                "DASHSCOPE_API_KEY": "fake-key",
                "PLANNER_MODEL": "deepseek-v3.2",
            }
            with patch.dict(environ, overrides, clear=False):
                clear_env_cache()
                with patch("agents.planner_agent.build_bailian_client", return_value=FakePlannerClient()):
                    with patch("agents.critic_agent.build_bailian_client", return_value=FakeCriticClient()):
                        with patch("agents.validator_agent.build_bailian_client", return_value=FakeValidatorClient()):
                            result = run_governed_analysis(repo)
                clear_env_cache()

            self.assertEqual(result["validated_findings"]["generation"]["mode"], "llm")
            self.assertEqual(result["validated_findings"]["findings"][0]["validation_source"], "llm")
            self.assertEqual(result["planner_agent"]["mode"], "llm")
            self.assertEqual(result["critic_agent"]["mode"], "llm")
            self.assertEqual(result["action_plan"]["generation"]["mode"], "llm")
            self.assertEqual(result["critic_review"]["generation"]["mode"], "llm")

    def test_llm_health_check_deduplicates_model_probes(self) -> None:
        routing = {
            "config_path": "config/agent_models.json",
            "providers": [
                {
                    "provider_id": "bailian",
                    "display_name": "Test Provider",
                    "api_key_env": "DASHSCOPE_API_KEY",
                    "configured": True,
                    "base_url_env": "DASHSCOPE_BASE_URL",
                    "base_url_env_aliases": ["BAILIAN_BASE_URL"],
                    "base_url_env_resolved_from": "DASHSCOPE_BASE_URL",
                    "base_url": "https://example.invalid/v1",
                }
            ],
            "assignments": [
                {
                    "role": "planner_triage_review",
                    "provider": "bailian",
                    "api_model": "deepseek-v3.2",
                    "model_env": "PLANNER_MODEL",
                },
                {
                    "role": "critic_review",
                    "provider": "bailian",
                    "api_model": "deepseek-v3.2",
                    "model_env": "PLANNER_MODEL",
                },
                {
                    "role": "finding_validation",
                    "provider": "bailian",
                    "api_model": "deepseek-v3.2",
                    "model_env": "PLANNER_MODEL",
                },
                {
                    "role": "refactor_and_test_fix",
                    "provider": "bailian",
                    "api_model": "qwen3-coder-flash",
                    "model_env": "CODER_MODEL",
                },
                {
                    "role": "summary_and_pr_copy",
                    "provider": "bailian",
                    "api_model": "qwen3.5-flash",
                    "model_env": "DASHSCOPE_MODEL",
                },
            ],
            "policy": {
                "external_llm_calls_enabled": True,
                "status": "live_enabled",
            },
        }

        class FakeClient:
            def __init__(self) -> None:
                self.models: list[str] = []

            def probe_model(self, *, model: str) -> dict[str, object]:
                self.models.append(model)
                return {
                    "id": f"probe-{model}",
                    "response_model": model,
                    "content_preview": "OK",
                }

        client = FakeClient()
        with patch("llm.health.build_model_routing", return_value=routing):
            with patch("llm.health.live_agent_runtime_enabled", return_value=True):
                with patch("llm.health.build_bailian_client", return_value=client):
                    result = run_llm_health_check()

        self.assertEqual(result["summary"]["status"], "healthy")
        self.assertTrue(result["summary"]["ok"])
        self.assertEqual(result["summary"]["checked_roles"], 5)
        self.assertEqual(result["summary"]["unique_models_probed"], 3)
        self.assertEqual(client.models, ["deepseek-v3.2", "qwen3-coder-flash", "qwen3.5-flash"])
        role_map = {item["role"]: item for item in result["roles"]}
        self.assertEqual(role_map["planner_triage_review"]["status"], "passed")
        self.assertEqual(role_map["finding_validation"]["status"], "passed")
        self.assertEqual(role_map["finding_validation"]["probe"]["cached"], True)
        self.assertEqual(role_map["critic_review"]["probe"]["cached"], True)

    def test_main_check_llm_config_writes_artifact(self) -> None:
        health_result = {
            "provider": {"provider_id": "bailian"},
            "runtime": {"external_llm_calls_enabled": True},
            "roles": [],
            "summary": {
                "status": "healthy",
                "ok": True,
                "checked_roles": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "unique_models_probed": 0,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            stream = io.StringIO()
            with patch("main.run_llm_health_check", return_value=health_result):
                with redirect_stdout(stream):
                    exit_code = main_module.main(["--check-llm-config", "--output", str(out)])

            self.assertEqual(exit_code, 0)
            self.assertIn('"status": "healthy"', stream.getvalue())
            self.assertTrue((out / "artifacts" / "llm_health_check.json").exists())

    def test_cli_generates_expected_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            out = Path(tmp) / "out"
            repo.mkdir()
            (repo / "main.py").write_text(
                textwrap.dedent(
                    """
                    import os

                    SETTINGS = {}

                    def run():
                        return os.getenv("APP_MODE")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            env = dict(environ)
            env["ENABLE_LIVE_AGENTS"] = "0"
            result = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "main.py"), "--repo", str(repo), "--output", str(out)],
                cwd=PROJECT_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertTrue((out / "summary.md").exists())
            summary_text = (out / "summary.md").read_text(encoding="utf-8")
            self.assertIn("## 扫描概览", summary_text)
            self.assertIn("## 行动计划", summary_text)
            self.assertIn("Validator 生成方式", summary_text)
            self.assertIn("已确认：0", summary_text)
            self.assertTrue((out / "artifacts" / "import_graph.json").exists())
            self.assertTrue((out / "artifacts" / "findings.json").exists())
            self.assertTrue((out / "artifacts" / "validated_findings.json").exists())
            self.assertTrue((out / "artifacts" / "module_inventory.json").exists())
            self.assertTrue((out / "artifacts" / "module_priorities.json").exists())
            self.assertTrue((out / "artifacts" / "module_deep_reviews.json").exists())
            self.assertTrue((out / "artifacts" / "action_plan.json").exists())
            self.assertTrue((out / "artifacts" / "critic_review.json").exists())
            self.assertTrue((out / "artifacts" / "planner_agent.json").exists())
            self.assertTrue((out / "artifacts" / "critic_agent.json").exists())
            self.assertTrue((out / "artifacts" / "model_routing.json").exists())
            self.assertTrue((out / "module_reports").exists())
            self.assertTrue((out / "module_reports" / "lightweight").exists())
            self.assertTrue((out / "module_reports" / "heavyweight").exists())


if __name__ == "__main__":
    unittest.main()
