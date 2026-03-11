from __future__ import annotations

import textwrap
import tempfile
import unittest
from pathlib import Path

from common.helpers import is_test_file, find_assignment, string_list, non_empty_text
from rules_engine.engine import _is_business_path, run_rules, detect_import_cycles
from scanner import build_repo_context
from scanner.db_usage import scan_db_usage
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
    def test_oversized_file_rule_triggers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            # Create a file with 600 lines (over threshold of 500)
            lines = [f"x_{i} = {i}\n" for i in range(600)]
            (repo / "big_file.py").write_text("".join(lines), encoding="utf-8")

            context = build_repo_context(repo)
            from scanner.definitions import scan_definitions
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


if __name__ == "__main__":
    unittest.main()
