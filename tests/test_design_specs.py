from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DesignSpecTests(unittest.TestCase):
    def test_module_registry_has_unique_modules_and_existing_paths(self) -> None:
        registry_path = PROJECT_ROOT / "config" / "module_registry.json"
        data = json.loads(registry_path.read_text(encoding="utf-8"))

        modules = data["modules"]
        module_ids = [item["module_id"] for item in modules]
        self.assertEqual(len(module_ids), len(set(module_ids)))

        required_keys = {
            "module_id",
            "module_type",
            "status",
            "implementation_paths",
            "responsibility",
            "inputs",
            "outputs",
            "dependencies",
            "test_entrypoints",
            "readme_required",
            "readme_template_path",
        }

        for module in modules:
            self.assertTrue(required_keys.issubset(module))
            for rel_path in module["implementation_paths"]:
                self.assertTrue((PROJECT_ROOT / rel_path).exists(), rel_path)
            for rel_path in module["test_entrypoints"]:
                self.assertTrue((PROJECT_ROOT / rel_path).exists(), rel_path)
            self.assertTrue((PROJECT_ROOT / module["readme_template_path"]).exists())

        expected_modules = {
            "repo_context",
            "import_scanner",
            "rule_engine",
            "validator_agent",
            "planner_agent",
            "critic_agent",
            "policy_engine",
            "module_report_agent",
            "gate_runner",
            "report_renderer",
            "cli_entrypoint",
        }
        self.assertTrue(expected_modules.issubset(set(module_ids)))

    def test_gate_spec_defines_required_gate_order_and_decisions(self) -> None:
        gate_spec_path = PROJECT_ROOT / "config" / "gate_spec.json"
        data = json.loads(gate_spec_path.read_text(encoding="utf-8"))

        self.assertEqual(data["gate_order"], ["test_gate", "policy_gate", "runtime_gate"])
        gates = {item["gate_id"]: item for item in data["gates"]}
        self.assertEqual(set(gates), {"test_gate", "policy_gate", "runtime_gate"})

        for gate in gates.values():
            self.assertIn("display_name", gate)
            self.assertIn("purpose", gate)
            self.assertIn("required_checks", gate)
            self.assertGreaterEqual(len(gate["required_checks"]), 1)
            for check in gate["required_checks"]:
                self.assertIn("check_id", check)
                self.assertIn("owner", check)
                self.assertIn("status", check)
                self.assertIn("evidence", check)

        decisions = data["iteration_decisions"]
        self.assertIn("allow_next_iteration", decisions)
        self.assertIn("hold_for_review", decisions)
        self.assertIn("blocked", decisions)
        self.assertEqual(
            decisions["allow_next_iteration"]["requires_gates"],
            ["test_gate", "policy_gate", "runtime_gate"],
        )

    def test_templates_exist_and_expose_placeholders(self) -> None:
        template_paths = {
            "templates/module_README.md": "{{ module_id }}",
            "templates/module_agent_report.json": "{{ module_id }}",
            "templates/module_human_report.md": "{{ module_id }}",
        }

        for rel_path, placeholder in template_paths.items():
            path = PROJECT_ROOT / rel_path
            self.assertTrue(path.exists(), rel_path)
            content = path.read_text(encoding="utf-8")
            self.assertIn(placeholder, content)


if __name__ == "__main__":
    unittest.main()
