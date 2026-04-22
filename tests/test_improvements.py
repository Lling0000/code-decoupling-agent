from __future__ import annotations

import textwrap
import tempfile
import unittest
from pathlib import Path

from agents.scanner_agent import build_repo_inventory
from common.helpers import (
    find_assignment,
    is_docs_file,
    is_non_product_file,
    is_test_file,
    non_empty_text,
    string_list,
)
from rules_engine.engine import _is_business_path, run_rules, detect_import_cycles
from scanner import build_repo_context
from scanner.db_usage import scan_db_usage
from scanner.definitions import scan_definitions
from scanner.globals import scan_global_state
from scanner.imports import scan_imports
from scanner.utils_usage import scan_utils_usage


class CommonHelpersTests(unittest.TestCase):
    def test_is_test_file_detects_common_patterns(self) -> None:
        self.assertTrue(is_test_file("tests/test_foo.py"))
        self.assertTrue(is_test_file("test_bar.py"))
        self.assertTrue(is_test_file("app/bar_test.py"))
        self.assertFalse(is_test_file("app/service.py"))
        self.assertFalse(is_test_file("app/testing_utils.py"))

    def test_docs_and_non_product_helpers_detect_common_patterns(self) -> None:
        self.assertTrue(is_docs_file("docs/conf.py"))
        self.assertTrue(is_non_product_file("docs/conf.py"))
        self.assertTrue(is_non_product_file("tests/test_api.py"))
        self.assertFalse(is_docs_file("app/docs_helper.py"))
        self.assertFalse(is_non_product_file("src/service.py"))

    def test_find_assignment_returns_matching_role(self) -> None:
        routing = {
            "assignments": [
                {"role": "planner", "model": "a"},
                {"role": "critic", "model": "b"},
            ]
        }
        self.assertEqual(find_assignment(routing, "critic")["model"], "b")
        self.assertIsNone(find_assignment(routing, "missing"))

    def test_string_list_extracts_valid_strings(self) -> None:
        self.assertEqual(string_list(["a", "b"], []), ["a", "b"])
        self.assertEqual(string_list(["a", 123, ""], ["fallback"]), ["a"])
        self.assertEqual(string_list(None, ["fallback"]), ["fallback"])
        self.assertEqual(string_list([], ["fallback"]), ["fallback"])

    def test_non_empty_text_returns_value_or_fallback(self) -> None:
        self.assertEqual(non_empty_text("hello", "default"), "hello")
        self.assertEqual(non_empty_text("", "default"), "default")
        self.assertEqual(non_empty_text(None, "default"), "default")
        self.assertEqual(non_empty_text("  ", "default"), "default")


class BusinessPathTests(unittest.TestCase):
    def test_config_file_excluded(self) -> None:
        self.assertFalse(_is_business_path("app/config.py"))
        self.assertFalse(_is_business_path("app/settings.py"))

    def test_test_files_excluded(self) -> None:
        self.assertFalse(_is_business_path("tests/test_something.py"))
        self.assertFalse(_is_business_path("test_handler.py"))

    def test_docs_files_excluded(self) -> None:
        self.assertFalse(_is_business_path("docs/conf.py"))

    def test_business_handler_not_excluded(self) -> None:
        # A handler file should NOT be excluded even though it contains "handler".
        self.assertTrue(_is_business_path("app/routes/user_handler.py"))

    def test_conftest_excluded(self) -> None:
        self.assertFalse(_is_business_path("tests/conftest.py"))

    def test_normal_business_file_included(self) -> None:
        self.assertTrue(_is_business_path("app/services/payment.py"))
        self.assertTrue(_is_business_path("app/feature/module.py"))


class DbScannerPrecisionTests(unittest.TestCase):
    def test_generic_client_get_not_flagged_as_db(self) -> None:
        """A file that imports a DB module but has client.get() should not flag it as DB."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "app.py").write_text(
                textwrap.dedent("""
                    import sqlite3

                    class HttpClient:
                        def get(self, url):
                            return url

                    client = HttpClient()
                    result = client.get("/api/users")
                """).strip() + "\n",
                encoding="utf-8",
            )
            context = build_repo_context(repo)
            artifact = scan_db_usage(context)

            # The import should be flagged, but client.get() should NOT be a DB signal
            # because "client" is now in DB_GENERIC_ROOT_HINTS (not DB_ROOT_NAME_HINTS)
            # and "get" is a low-confidence method.
            call_signals = [
                s for s in artifact["files"][0]["signals"]
                if s["kind"] == "call" and "client" in s["signal"]
            ]
            self.assertEqual(len(call_signals), 0)

    def test_real_db_session_still_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "app.py").write_text(
                textwrap.dedent("""
                    from sqlalchemy import select

                    def fetch(session):
                        return session.execute(select("users"))
                """).strip() + "\n",
                encoding="utf-8",
            )
            context = build_repo_context(repo)
            artifact = scan_db_usage(context)

            call_signals = [
                s for s in artifact["files"][0]["signals"]
                if s["kind"] == "call" and s["confidence"] in ("high", "medium")
            ]
            self.assertGreater(len(call_signals), 0)


class GlobalsScannerSafeMethodTests(unittest.TestCase):
    def test_safe_method_calls_not_treated_as_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "app.py").write_text(
                textwrap.dedent("""
                    REGISTRY = {}

                    def read_registry():
                        keys = REGISTRY.keys()
                        values = REGISTRY.values()
                        copy = REGISTRY.copy()
                        return keys, values, copy
                """).strip() + "\n",
                encoding="utf-8",
            )
            context = build_repo_context(repo)
            artifact = scan_global_state(context)

            # REGISTRY should be detected as a candidate but should NOT have mutations
            # from .keys(), .values(), .copy() since those are safe methods.
            for file_entry in artifact["files"]:
                for glob in file_entry["globals"]:
                    if glob["name"] == "REGISTRY":
                        self.assertEqual(glob["mutation_count"], 0)


class UtilsUnderscoreNamingTests(unittest.TestCase):
    def test_underscore_separated_utils_name_matched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "my_utils.py").write_text("def foo(): pass\n", encoding="utf-8")
            # Create enough consumers to trigger detection
            for i in range(6):
                pkg = repo / f"pkg{i}"
                pkg.mkdir()
                (pkg / "__init__.py").write_text("", encoding="utf-8")
                (pkg / "consumer.py").write_text(
                    f"from my_utils import foo\n",
                    encoding="utf-8",
                )

            context = build_repo_context(repo)
            import_graph = scan_imports(context)
            artifact = scan_utils_usage(import_graph)

            matched_modules = [m["module"] for m in artifact["modules"]]
            self.assertIn("my_utils", matched_modules)


class RuleFOversizedFileTests(unittest.TestCase):
    def test_oversized_file_rule_ignores_simple_large_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            lines = [f"x_{i} = {i}\n" for i in range(600)]
            (repo / "big_file.py").write_text("".join(lines), encoding="utf-8")

            context = build_repo_context(repo)
            definitions = scan_definitions(context)

            findings = run_rules(
                import_graph={"files": [], "local_edges": []},
                env_usage={"reads": [], "variables": []},
                db_usage={"files": []},
                utils_usage={"modules": []},
                global_state={"files": []},
                definitions=definitions,
            )

            rule_ids = {f["rule_id"] for f in findings["findings"]}
            self.assertNotIn("RULE_F", rule_ids)

    def test_oversized_file_rule_triggers_for_combined_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            methods = [
                f"    def method_{index}(self):\n        return {index}\n"
                for index in range(15)
            ]
            filler = "\n".join(f"PADDING_{index} = {index}" for index in range(520))
            (repo / "big_file.py").write_text(
                "class LargeService:\n\n"
                + "\n".join(methods)
                + "\n"
                + filler
                + "\n",
                encoding="utf-8",
            )

            context = build_repo_context(repo)
            definitions = scan_definitions(context)
            findings = run_rules(
                import_graph={"files": [], "local_edges": []},
                env_usage={"reads": [], "variables": []},
                db_usage={"files": []},
                utils_usage={"modules": []},
                global_state={"files": []},
                definitions=definitions,
            )

            rule_ids = {f["rule_id"] for f in findings["findings"]}
            self.assertIn("RULE_F", rule_ids)

    def test_oversized_file_rule_skips_test_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            tests_dir = repo / "tests"
            tests_dir.mkdir()
            methods = [
                f"    def test_case_{index}(self):\n        return {index}\n"
                for index in range(30)
            ]
            filler = "\n".join(f"PADDING_{index} = {index}" for index in range(900))
            (tests_dir / "test_big_file.py").write_text(
                "class TestMassiveFile:\n\n"
                + "\n".join(methods)
                + "\n"
                + filler
                + "\n",
                encoding="utf-8",
            )

            context = build_repo_context(repo)
            definitions = scan_definitions(context)
            findings = run_rules(
                import_graph={"files": [], "local_edges": []},
                env_usage={"reads": [], "variables": []},
                db_usage={"files": []},
                utils_usage={"modules": []},
                global_state={"files": []},
                definitions=definitions,
            )

            rule_ids = {f["rule_id"] for f in findings["findings"]}
            self.assertNotIn("RULE_F", rule_ids)


class RuleDNonProductPathTests(unittest.TestCase):
    def test_global_state_rule_skips_test_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            tests_dir = repo / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_state.py").write_text(
                textwrap.dedent("""
                    ITEMS = []

                    def mutate():
                        ITEMS.append("x")
                """).strip() + "\n",
                encoding="utf-8",
            )

            context = build_repo_context(repo)
            global_state = scan_global_state(context)
            findings = run_rules(
                import_graph={"files": [], "local_edges": []},
                env_usage={"reads": [], "variables": []},
                db_usage={"files": []},
                utils_usage={"modules": []},
                global_state=global_state,
                definitions={"files": []},
            )

            rule_ids = {f["rule_id"] for f in findings["findings"]}
            self.assertNotIn("RULE_D", rule_ids)


class RepoInventoryHotspotTests(unittest.TestCase):
    def test_non_product_files_are_downweighted_in_hotspots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            app_dir = repo / "app"
            app_dir.mkdir()
            tests_dir = repo / "tests"
            tests_dir.mkdir()
            (app_dir / "service.py").write_text("def run():\n    return 1\n", encoding="utf-8")
            (tests_dir / "test_service.py").write_text("def test_run():\n    return 1\n", encoding="utf-8")

            context = build_repo_context(repo)
            inventory = build_repo_inventory(
                context,
                {
                    "import_graph": {
                        "files": [
                            {"file": "app/service.py", "imports": list(range(6))},
                            {"file": "tests/test_service.py", "imports": list(range(20))},
                        ],
                    },
                    "env_usage": {"reads": []},
                    "db_usage": {"files": []},
                    "global_state": {"files": []},
                    "findings": {"counts": {"total": 0}},
                },
            )

            self.assertEqual(inventory["hotspots"][0]["file"], "app/service.py")
            self.assertEqual(inventory["hotspots"][1]["file"], "tests/test_service.py")
            self.assertFalse(inventory["hotspots"][0]["is_non_product"])
            self.assertTrue(inventory["hotspots"][1]["is_non_product"])
            self.assertEqual(inventory["hotspots"][1]["raw_score"], 20)
            self.assertEqual(inventory["hotspots"][1]["score"], 5)


if __name__ == "__main__":
    unittest.main()
