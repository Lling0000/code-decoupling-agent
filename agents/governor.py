from __future__ import annotations

from pathlib import Path

from common.log import get_logger

log = get_logger("decoupling.governor")

from agents.critic_agent import run_critic_agent
from agents.module_report_agent import (
    build_module_deep_reviews,
    build_module_heavyweight_cards,
    build_module_inventory,
    build_module_lightweight_cards,
    build_module_priority_groups,
)
from agents.planner_agent import build_action_plan, build_triage, run_planner_agent
from agents.scanner_agent import build_repo_inventory
from agents.tool_runner import run_deterministic_toolchain
from agents.validator_agent import actionable_findings_artifact, run_validator_agent
from llm.catalog import build_model_routing
from scanner import build_repo_context


def run_governed_analysis(repo_root: Path) -> dict[str, object]:
    log.info("Starting governed analysis for %s", repo_root)
    context = build_repo_context(repo_root)
    tool_results = run_deterministic_toolchain(context)
    model_routing = build_model_routing()
    repo_inventory = build_repo_inventory(context, tool_results)
    validator_result = run_validator_agent(
        findings_artifact=tool_results["findings"],
        context=context,
        model_routing=model_routing,
    )
    module_inventory = build_module_inventory(
        context=context,
        tool_results=tool_results,
        validated_findings=validator_result["validated_findings"],
    )
    module_priorities = build_module_priority_groups(module_inventory)
    module_deep_reviews = build_module_deep_reviews(
        module_inventory=module_inventory,
        model_routing=model_routing,
    )
    module_lightweight_cards = build_module_lightweight_cards(module_inventory)
    module_heavyweight_cards = build_module_heavyweight_cards(
        module_inventory,
        module_deep_reviews,
    )
    actionable_findings = actionable_findings_artifact(validator_result["validated_findings"])
    deterministic_triage = build_triage(actionable_findings)
    deterministic_action_plan = build_action_plan(deterministic_triage)
    planner_result = run_planner_agent(
        repo_inventory=repo_inventory,
        findings_artifact=actionable_findings,
        triage_artifact=deterministic_triage,
        deterministic_action_plan=deterministic_action_plan,
        model_routing=model_routing,
        repo_files=[parsed.relative_path for parsed in context.files],
    )
    critic_result = run_critic_agent(
        action_plan=planner_result["action_plan"],
        repo_inventory=repo_inventory,
        model_routing=model_routing,
    )
    log.info("Governed analysis complete: %d files, %d findings",
             len(context.files), tool_results["findings"]["counts"]["total"])
    return {
        "context": context,
        "artifacts": tool_results,
        "validated_findings": validator_result["validated_findings"],
        "module_inventory": module_inventory,
        "module_priorities": module_priorities,
        "module_deep_reviews": module_deep_reviews,
        "module_lightweight_cards": module_lightweight_cards,
        "module_heavyweight_cards": module_heavyweight_cards,
        "model_routing": model_routing,
        "repo_inventory": repo_inventory,
        "triage": planner_result["triage"],
        "action_plan": planner_result["action_plan"],
        "critic_review": critic_result["critic_review"],
        "planner_agent": planner_result["planner_agent"],
        "critic_agent": critic_result["critic_agent"],
    }
