from __future__ import annotations

import json
import unittest
from pathlib import Path

from agents.tool_runner import run_deterministic_toolchain
from scanner import build_repo_context


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures"
GOLD_REPO = FIXTURE_ROOT / "repos" / "gold_repo"
EXPECTATIONS = json.loads((FIXTURE_ROOT / "gold_expectations.json").read_text(encoding="utf-8"))


class GoldenRepoTests(unittest.TestCase):
    def test_gold_repo_matches_expected_findings(self) -> None:
        context = build_repo_context(GOLD_REPO)
        artifacts = run_deterministic_toolchain(context)
        findings_by_rule = {item["rule_id"]: item for item in artifacts["findings"]["findings"]}

        self.assertEqual(set(findings_by_rule), set(EXPECTATIONS["expected_rule_ids"]))
        self.assertEqual(findings_by_rule["RULE_A"]["files"], EXPECTATIONS["expected_rule_files"]["RULE_A"])
        self.assertEqual(findings_by_rule["RULE_B"]["files"], EXPECTATIONS["expected_rule_files"]["RULE_B"])
        self.assertEqual(findings_by_rule["RULE_D"]["files"], EXPECTATIONS["expected_rule_files"]["RULE_D"])
        self.assertEqual(sorted(findings_by_rule["RULE_E"]["files"]), EXPECTATIONS["expected_cycle_files"])

    def test_gold_repo_filters_known_false_positives(self) -> None:
        context = build_repo_context(GOLD_REPO)
        artifacts = run_deterministic_toolchain(context)

        db_usage = {item["file"]: item for item in artifacts["db_usage"]["files"]}
        global_state = {item["file"]: item for item in artifacts["global_state"]["files"]}
        findings_by_rule = {item["rule_id"]: item for item in artifacts["findings"]["findings"]}
        utils_modules = {item["module"]: item for item in artifacts["utils_usage"]["modules"]}

        for file_path in EXPECTATIONS["db_noise_absent_files"]:
            self.assertEqual(db_usage[file_path]["signal_count"], 0)

        for file_path in EXPECTATIONS["global_state_absent_files"]:
            self.assertEqual(global_state[file_path]["globals"], [])

        self.assertEqual(findings_by_rule["RULE_B"]["files"], EXPECTATIONS["expected_rule_files"]["RULE_B"])
        self.assertEqual(
            utils_modules[EXPECTATIONS["utils_module"]]["consumer_package_count"],
            EXPECTATIONS["utils_consumer_package_count"],
        )


if __name__ == "__main__":
    unittest.main()
