# Code Decoupling Agent

**A controlled diagnosis system for taming tightly-coupled Python codebases.**

Every team has one -- the sprawling legacy codebase where imports form cycles, handlers talk directly to the database, environment variables are scattered across dozens of files, and shared utility modules have become implicit dependencies for everything. Refactoring it is terrifying because you cannot see the blast radius.

Code Decoupling Agent scans your Python repository, maps its structural coupling, and produces a verified diagnosis with actionable refactoring plans -- all under a strict gate system that ensures nothing advances without passing tests, policy checks, and runtime verification.

---

## Key Features

- **AST-based static analysis** -- import graphs, call graphs, DB access signals, env variable mapping, global state detection, utils over-dependency tracking
- **7 diagnostic rules** covering the most common coupling patterns in real-world Python projects
- **Multi-agent pipeline** -- Governor, Scanner, Validator, Planner, Critic working in sequence with deterministic guardrails
- **Finding validation** -- raw rule output is never treated as ground truth; every finding is reviewed and assigned a confidence score before entering planning
- **Hard gate system** -- test gate + policy gate + runtime gate; no iteration proceeds without all three passing
- **Dual output** -- structured JSON for agent consumption, readable Markdown for humans
- **Zero mandatory dependencies** -- runs on Python standard library alone
- **LLM-optional** -- works fully in deterministic fallback mode; optionally connects to DashScope/Bailian-compatible APIs for intelligent review and planning
- **Fully configurable** -- priority weights, policy rules, model routing, protected paths, and thresholds are all externalized to config files

---

## Architecture

```
                         Target Python Repository
                                  |
                                  v
                     +------------------------+
                     |       Governor         |   Orchestrates the full pipeline
                     +------------------------+
                                  |
                  +---------------+----------------+
                  |                                 |
                  v                                 v
     +------------------------+       +------------------------+
     |     Tool Runner        |       |    Model Routing       |
     | (deterministic scan)   |       |  (config/env/fallback) |
     +------------------------+       +------------------------+
                  |
    +------+------+------+------+------+------+------+
    |      |      |      |      |      |      |      |
    v      v      v      v      v      v      v      v
 imports  defs  calls  envs   db    utils  globals  rules
                                                   engine
                  |
                  v
     +------------------------+
     |   Validator Agent      |   Confirms/rejects each finding
     +------------------------+
                  |
                  v
     +------------------------+
     |   Module Report Agent  |   Profiles and ranks modules
     +------------------------+
                  |
                  v
     +------------------------+
     |    Planner Agent       |   Generates triage + action plan
     +------------------------+
                  |
                  v
     +------------------------+
     |    Critic Agent        |   Reviews plan for risk/scope
     +------------------------+
                  |
                  v
     +------------------------+
     |    Policy Engine       |   Hard guardrails enforcement
     +------------------------+
                  |
          +-------+-------+
          |               |
          v               v
   summary.md      artifacts/*.json
  (for humans)     (for agents)
```

---

## Quick Start

### Install

```bash
git clone https://github.com/study8677/code-decoupling-agent.git
cd code-decoupling-agent
python -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

Runtime dependencies are **Python standard library only**. The `requirements.txt` exists for development tooling.

### Run

```bash
python main.py --repo /path/to/your/python/repo --output ./output
```

### Run with iteration gates

```bash
python main.py \
  --repo /path/to/your/python/repo \
  --output ./output \
  --run-gates \
  --target-test-command "pytest" \
  --runtime-command "python app.py"
```

### Check LLM configuration

```bash
python main.py --check-llm-config
python main.py --check-llm-config --output ./output   # also writes health check artifact
```

---

## Output

A single run produces the following artifacts:

### Core scan artifacts

| File | Content |
|------|---------|
| `artifacts/import_graph.json` | Local import edges and module dependency map |
| `artifacts/definitions.json` | Classes, functions, methods with line counts |
| `artifacts/call_graph.json` | Approximate call edges across files |
| `artifacts/env_usage.json` | Environment variable reads by file |
| `artifacts/db_usage.json` | Database/ORM access signals with confidence |
| `artifacts/utils_usage.json` | Shared utility module dependency counts |
| `artifacts/global_state.json` | Mutable global state candidates with mutation evidence |
| `artifacts/findings.json` | Raw rule engine findings |

### Agent pipeline artifacts

| File | Content |
|------|---------|
| `artifacts/validated_findings.json` | Findings after Validator review (with confidence and status) |
| `artifacts/repo_inventory.json` | Hotspot-oriented repository profile |
| `artifacts/module_inventory.json` | Per-module structural profile |
| `artifacts/module_priorities.json` | Priority-ranked module groups |
| `artifacts/triage.json` | Prioritized finding groups for action |
| `artifacts/action_plan.json` | Bounded, file-scoped refactoring steps |
| `artifacts/critic_review.json` | Risk assessment of the action plan |
| `artifacts/planner_agent.json` | Planner agent execution metadata |
| `artifacts/critic_agent.json` | Critic agent execution metadata |
| `artifacts/model_routing.json` | Resolved model assignments for each agent role |

### Reports

| File | Content |
|------|---------|
| `summary.md` | Human-readable diagnosis report |
| `module_reports/lightweight/*.md` | Quick-glance module cards |
| `module_reports/heavyweight/*.md` | Deep-dive module analysis |
| `iteration_human_report.md` | Gate results in human-readable form (with `--run-gates`) |
| `artifacts/iteration_agent_report.json` | Gate results in structured form (with `--run-gates`) |

---

## Multi-Agent Pipeline

The system runs 6 agents in a strict sequence. Each agent has a defined input contract, output contract, and failure mode.

### 1. Governor

Orchestrates the entire pipeline. Calls the Tool Runner first, then chains the agent sequence. Never makes decisions itself -- it only routes data between stages.

### 2. Tool Runner

Executes all 7 deterministic scanners and the rule engine. This is the factual backbone -- no LLM is involved, no heuristics are applied. Pure AST parsing.

### 3. Scanner Agent

Converts raw scan artifacts into a hotspot-oriented repository inventory. Identifies the highest-risk modules based on configurable priority weights (DB signal count, global state risk, upstream fan-in, missing test coverage, etc.).

### 4. Validator Agent

Reviews every raw finding from the rule engine. Assigns a `confirmation_status` (confirmed / needs_review / rejected) and a `confidence` level. Runs in deterministic fallback mode when no LLM is available; uses LLM-backed validation when configured.

### 5. Planner Agent

Takes actionable (confirmed + needs_review) findings and generates:
- A **triage** that groups findings by priority
- A **bounded action plan** with file-scoped steps, success criteria, and rollback conditions

The plan is never auto-executed. It is a proposal for human review.

### 6. Critic Agent

Reviews the action plan for:
- Scope creep (too many files per step)
- Protected path violations (auth, migration, security files)
- Risk level assessment
- Whether additional tests should be written before proceeding

---

## Gate System

The gate system enforces a hard rule:

> Only changes that pass tests, pass policy, and keep the repository runnable are allowed to advance to the next iteration.

### Test Gate

- System test suite (`python -m unittest`)
- Golden regression suite (known-good fixture expectations)
- Target repository regression tests (user-provided commands)

### Policy Gate

- Protected path check (auth, migration, security, credentials)
- Step scope check (max files per step)
- No auto-execution check

### Runtime Gate

- Target repository entrypoint smoke run
- Core command check
- Artifact completeness verification

Each gate produces one of three decisions:

| Decision | Meaning |
|----------|---------|
| `allow_next_iteration` | All gates passed; safe to proceed |
| `hold_for_review` | Tests passed but medium/high risk concerns remain; needs human review |
| `blocked` | At least one gate failed; iteration must stop |

---

## Configuration

### Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `DASHSCOPE_API_KEY` | API key for DashScope/Bailian provider | (none) |
| `DASHSCOPE_BASE_URL` | Provider API base URL | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `DASHSCOPE_MODEL` | Default model for summaries and cheap tasks | `qwen3.5-flash` |
| `PLANNER_MODEL` | Model for planner, critic, validator, governor | `deepseek-v3.2` |
| `CODER_MODEL` | Model for refactor and code-related tasks | `qwen3-coder-flash` |
| `ENABLE_LIVE_AGENTS` | Set to `1` to enable LLM-backed agents; `0` for deterministic-only | `0` |

Legacy aliases `BAILIAN_BASE_URL` and `BAILIAN_MODEL` are still accepted.

### Config files

| File | Purpose |
|------|---------|
| `config/agent_models.json` | Model routing: which model serves each agent role |
| `config/policy_config.json` | Protected paths, max files per step, plan window size |
| `config/priority_weights.json` | Scoring weights for module priority ranking |
| `config/gate_spec.json` | Gate definitions, required checks, pass conditions |
| `config/module_registry.json` | Module metadata registry |

Priority order for model resolution: built-in fallback < config file < environment variable.

---

## Diagnostic Rules

The rule engine runs 7 rules against the scan artifacts:

| Rule ID | Name | Detects | Severity |
|---------|------|---------|----------|
| **RULE_A** | Handler DB Access | Handler/controller/router files directly executing database operations | high/medium |
| **RULE_B** | Shared Env Vars | Same environment variable read directly in multiple business files | high/medium |
| **RULE_C** | Utils Overuse | Shared utils/common/helper modules depended on by 5+ files across 3+ packages | high/medium |
| **RULE_D** | Mutable Globals | Module-level mutable objects modified inside function scope | high/medium |
| **RULE_E** | Import Cycles | Strongly connected components in the import graph (Tarjan's algorithm) | high/medium |
| **RULE_F** | Oversized Files | Files exceeding 500 lines or classes with 15+ methods | medium |
| **RULE_G** | Cross-Layer DB Access | Non-handler, non-data-access files directly performing multiple high-confidence DB operations | medium |

Each finding includes: affected files, evidence lines, a Chinese-language explanation, and a concrete refactoring suggestion.

---

## Design Philosophy

**Agents think; deterministic tools execute.**

This is the core boundary of the system:

| Responsibility | Owner |
|---------------|-------|
| Scanning, rule evaluation, policy enforcement, test execution, final go/no-go | Deterministic modules |
| Understanding, reviewing, triaging, planning, explaining | Agent modules |

What agents are explicitly **not** allowed to decide:

- Whether to skip tests
- Whether to skip policy checks
- Whether to modify protected files
- Whether to continue when the repository is broken
- Whether to carry failed changes into the next iteration

This separation exists because diagnosis and planning benefit from intelligence, but verification and enforcement must be mechanical and unchallengeable.

---

## Limitations

- Analysis is AST-based and approximate; it does not resolve dynamic imports, runtime indirection, or metaprogramming
- Database access detection is signal-based (pattern matching on known ORM/driver names); it will miss unconventional data access patterns
- Call graph construction is approximate -- indirect calls through variables or decorators may not be captured
- Only Python `.py` files are analyzed; templates, config files, SQL files, and other languages are not scanned
- The Refactor Agent is planning-only; it does not auto-edit code or generate patches
- Import cycle detection uses Tarjan's SCC algorithm on the static import graph; runtime conditional imports may not be reflected
- LLM-backed agents require a DashScope/Bailian-compatible API; other providers are not yet supported

---

## Roadmap

- Stronger repository understanding heuristics (cross-file data flow, decorator resolution)
- Controlled patch plan generation with diff preview
- Target repository test execution integration
- Rollback strategy for failed iterations
- Per-iteration state persistence (stop/resume across sessions)
- Richer module-level contract and testing infrastructure
- Support for additional LLM providers beyond DashScope
- Multi-language repository support (starting with TypeScript/JavaScript)

---

## Project Structure

```
code-decoupling-agent/
  main.py                  # CLI entry point
  agents/
    governor.py            # Pipeline orchestrator
    tool_runner.py         # Deterministic scan executor
    scanner_agent.py       # Repository inventory builder
    validator_agent.py     # Finding reviewer
    planner_agent.py       # Triage and action plan generator
    critic_agent.py        # Plan risk reviewer
    module_report_agent.py # Module profiling and card generation
    contracts.py           # Agent contract definitions
  scanner/
    imports.py             # Import graph scanner
    definitions.py         # Class/function/method scanner
    calls.py               # Call graph scanner
    envs.py                # Environment variable usage scanner
    db_usage.py            # Database/ORM signal scanner
    utils_usage.py         # Shared utils dependency scanner
    globals.py             # Global state risk scanner
  rules_engine/
    engine.py              # Rule evaluation (RULE_A through RULE_G)
  rules/
    config.py              # Rule thresholds and keyword lists
  policy/
    engine.py              # Protected path and scope enforcement
  iteration/
    gate_runner.py         # Test/policy/runtime gate execution
  llm/
    client.py              # DashScope/Bailian API client
    catalog.py             # Model routing resolver
    env.py                 # Provider environment variable handling
    health.py              # LLM health check probes
  config/
    agent_models.json      # Model assignments per agent role
    policy_config.json     # Policy rules and thresholds
    priority_weights.json  # Module priority scoring weights
    gate_spec.json         # Gate definitions
    module_registry.json   # Module metadata
  report/
    renderer.py            # Markdown summary generator
  models/
    schema.py              # Data models (Finding, RepoContext, etc.)
  common/
    helpers.py             # Shared internal utilities
    log.py                 # Logging setup
  tests/
    test_smoke.py          # Basic smoke tests
    test_design_specs.py   # Design constraint tests
    test_goldens.py        # Golden fixture regression tests
    test_reporting.py      # Report output tests
    test_module_reports.py # Module report tests
    test_gate_runner.py    # Gate runner tests
    test_validator_agent.py # Validator agent tests
    test_improvements.py   # Improvement verification tests
    fixtures/              # Test fixture repositories
```

---

## Design Documents

| Document | Content |
|----------|---------|
| `ARCHITECTURE.md` | System architecture, layer definitions, and hard constraints (Chinese) |
| `MODULE_SPEC.md` | Module contract, testing, and report expectations (Chinese) |
| `ITERATION_LOOP.md` | Iteration gate, stop/go criteria, and controlled loop design (Chinese) |
| `MULTI_AGENT.md` | Multi-agent roles, model routing, and phase boundaries |
| `AGENTS.md` | Project identity, scope, and explicit non-goals |

---

## License

See repository for license information.
