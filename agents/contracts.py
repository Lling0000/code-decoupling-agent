from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RepoInventory:
    scanned_files: int
    parse_errors: int
    finding_count: int
    has_tests: bool
    hotspots: list[dict[str, object]]


@dataclass(slots=True)
class TriageItem:
    finding_rule: str
    rule_name: str
    category: str
    priority: str
    severity: str
    score: int
    files: list[str]
    rationale: str
    recommended_owner: str


@dataclass(slots=True)
class PlanStep:
    step_id: str
    title: str
    category: str
    priority: str
    owner: str
    files: list[str]
    finding_rule: str
    rationale: str
    success_criteria: list[str]
    rollback_conditions: list[str]
    deterministic_tools: list[str]
    guarded_by: list[str]


@dataclass(slots=True)
class CriticReview:
    status: str
    blocked: bool
    risk_level: str
    concerns: list[str]
    required_checks: list[str]
    protected_files: list[str]
    summary: str
