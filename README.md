# Code Decoupling Agent

[English](README.md) | [简体中文](README.zh-CN.md)

**Find the coupling hotspots in a Python codebase before a refactor turns into a regression hunt.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Static analysis](https://img.shields.io/badge/analysis-AST%20based-2F855A)](#what-it-detects)
[![Runtime deps](https://img.shields.io/badge/runtime%20deps-stdlib%20only-0F766E)](#quick-start)
[![LLM optional](https://img.shields.io/badge/LLM-optional-7C3AED)](#llm-optional)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Code Decoupling Agent is a local CLI for diagnosing structural coupling in Python repositories. It scans ASTs, ranks risky modules, validates findings, and emits both human-readable Markdown and machine-readable JSON.

It does **not** rewrite your code. It tells you where the dangerous risk boundaries are, why they matter, and what a bounded refactor plan would look like.

```bash
ENABLE_LIVE_AGENTS=0 python3 main.py --repo /path/to/python/repo --output ./output
```

Typical result:

```text
Scanned 36 Python files
Generated 5 findings
Validated 5 actionable findings
Profiled 28 modules
Output written to ./output
```

See a sample report: [docs/sample-output/requests-summary.md](docs/sample-output/requests-summary.md)

## Why Teams Use It

Refactors usually fail because the codebase has invisible coupling:

- request handlers that reach straight into the database
- one environment variable read from many business modules
- shared `utils` modules that become unofficial APIs
- mutable global state that leaks across functions
- import cycles that make initialization fragile
- oversized modules that mix unrelated responsibilities

This tool turns those suspicions into evidence:

- exact files and signals, not generic advice
- product-code-first hotspot ranking
- confirmed / needs-review / rejected finding states
- JSON artifacts for automation and Markdown for humans
- policy and gate reports for controlled iteration

## Quick Start

### 1. Install

```bash
git clone https://github.com/Lling0000/code-decoupling-agent.git
cd code-decoupling-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The deterministic runtime path uses the Python standard library. `requirements.txt` is for development and test tooling.

### 2. Scan a Repository

```bash
ENABLE_LIVE_AGENTS=0 python3 main.py \
  --repo /path/to/your/python/repo \
  --output ./output
```

### 3. Open the Human Report

```bash
open ./output/summary.md
```

### 4. Inspect Machine Artifacts

```bash
ls ./output/artifacts
```

```text
findings.json
validated_findings.json
action_plan.json
critic_review.json
import_graph.json
call_graph.json
definitions.json
env_usage.json
db_usage.json
utils_usage.json
global_state.json
```

## What It Detects

| Rule | Coupling smell | Why it matters |
|------|----------------|----------------|
| `RULE_A` | Handler/controller/router files directly accessing DB/ORM APIs | Request code and data access become hard to test separately |
| `RULE_B` | Same environment variable read directly in multiple business files | Configuration ownership is scattered |
| `RULE_C` | Shared `utils/common/helper` modules depended on by many packages | A convenience module becomes an implicit cross-domain API |
| `RULE_D` | Mutable module-level globals modified inside functions | Hidden state makes behavior order-dependent |
| `RULE_E` | Import cycles in the static import graph | Module initialization becomes fragile |
| `RULE_F` | Large files/classes with corroborating structural signals | Too many responsibilities accumulate in one place |
| `RULE_G` | Cross-layer DB access outside handlers and data-access modules | Persistence details leak through business layers |

Each finding includes affected files, evidence, severity, validation status, confidence, explanation, and a concrete refactoring suggestion.

## Proof: Real Repository Dogfood

The project has been dogfooded against [`psf/requests`](https://github.com/psf/requests) in deterministic mode.

```bash
git clone --depth 1 https://github.com/psf/requests.git /tmp/requests-dogfood
ENABLE_LIVE_AGENTS=0 python3 main.py \
  --repo /tmp/requests-dogfood \
  --output /tmp/requests-dogfood-output
```

Observed run:

| Metric | Value |
|--------|-------|
| Python files scanned | `36` |
| Generated findings | `5` |
| Actionable findings after validation | `5` |
| Notable hotspot modules | `src/requests/utils.py`, `src/requests/models.py`, `src/requests/sessions.py` |

The point is not that `requests` is bad code. It is a mature, real repository with enough structure to prove the scanner produces conservative, reviewable output outside toy fixtures.

## Sample Finding

```text
### Shared Utils Module Overuse

- Severity: medium
- Confirmation status: confirmed
- Confidence: medium
- Files: app/feature_a/consumer.py, app/feature_b/consumer.py, ...
- Evidence: app.common.helpers is imported by 5 files across 5 packages
- Explanation: A shared helper module is becoming a horizontal dependency across domains.
- Suggestion: Split helpers by domain boundary and keep only truly generic helpers shared.
```

## Safety Model

Code Decoupling Agent is built around one boundary:

> Agents may explain and plan. Deterministic tools decide facts, gates, and stop conditions.

What the tool will do:

- scan local Python files with AST-based analyzers
- generate JSON artifacts and Markdown reports
- validate raw findings before treating them as actionable
- propose file-scoped refactoring steps
- optionally run tests/runtime commands as gates

What the tool will **not** do:

- auto-edit source code
- apply patches
- skip configured tests
- override protected-path policy
- continue a gated iteration after a hard failure
- claim dynamic whole-program precision

## Run With Gates

Use gates when you want the output to include explicit test, policy, and runtime decisions:

```bash
python3 main.py \
  --repo /path/to/your/python/repo \
  --output ./output \
  --run-gates \
  --target-test-command "pytest" \
  --runtime-command "python app.py"
```

Gate decisions:

| Decision | Meaning |
|----------|---------|
| `allow_next_iteration` | Tests, policy, and runtime checks passed |
| `hold_for_review` | Checks passed but risk requires human review |
| `blocked` | At least one hard gate failed |

Gate outputs:

- `output/iteration_human_report.md`
- `output/artifacts/iteration_agent_report.json`

## LLM Optional

The default path is deterministic:

```bash
ENABLE_LIVE_AGENTS=0 python3 main.py --repo ./my-repo --output ./output
```

You can enable LLM-backed validation and planning with DashScope/Bailian-compatible APIs:

```bash
export DASHSCOPE_API_KEY="..."
export ENABLE_LIVE_AGENTS=1
python3 main.py --repo ./my-repo --output ./output
```

Check configuration:

```bash
python3 main.py --check-llm-config
python3 main.py --check-llm-config --output ./output
```

Relevant environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `ENABLE_LIVE_AGENTS` | Set `1` for LLM-backed agents, `0` for deterministic fallback | `0` |
| `DASHSCOPE_API_KEY` | DashScope/Bailian-compatible API key | none |
| `DASHSCOPE_BASE_URL` | Compatible API base URL | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `DASHSCOPE_MODEL` | Default model for lightweight tasks | `qwen3.5-flash` |
| `PLANNER_MODEL` | Planner, critic, validator, governor model | `deepseek-v3.2` |
| `CODER_MODEL` | Code-oriented model assignment | `qwen3-coder-flash` |

Legacy aliases `BAILIAN_BASE_URL` and `BAILIAN_MODEL` are also accepted.

## Output Map

| Path | Purpose |
|------|---------|
| `summary.md` | Human-readable diagnosis report |
| `artifacts/findings.json` | Raw rule-engine findings |
| `artifacts/validated_findings.json` | Findings after validation |
| `artifacts/action_plan.json` | Bounded refactoring plan |
| `artifacts/critic_review.json` | Risk review of the plan |
| `artifacts/import_graph.json` | Local import graph |
| `artifacts/call_graph.json` | Approximate call graph |
| `artifacts/definitions.json` | Classes, functions, methods |
| `artifacts/env_usage.json` | Environment variable reads |
| `artifacts/db_usage.json` | DB/ORM access signals |
| `artifacts/utils_usage.json` | Shared utility dependency counts |
| `artifacts/global_state.json` | Mutable global-state candidates |
| `module_reports/lightweight/*.md` | Quick module cards |
| `module_reports/heavyweight/*.md` | Deeper module reviews |

Raw artifacts intentionally retain more detail than the final diagnosis. Tests and docs may appear in scan artifacts while being filtered or downweighted in diagnosis-focused views.

## Architecture

```text
Target Python repository
        |
        v
Governor
        |
        +--> Tool Runner
        |       |
        |       +--> imports / definitions / calls / envs
        |       +--> db signals / utils usage / globals
        |       +--> rules engine
        |
        +--> Validator Agent
        +--> Module Report Agent
        +--> Planner Agent
        +--> Critic Agent
        +--> Policy + Gate Runner
        |
        v
summary.md + artifacts/*.json
```

Core split:

| Responsibility | Owner |
|----------------|-------|
| AST scanning, rule evaluation, policy enforcement, gate decisions | deterministic modules |
| validation, triage, planning, explanation, risk review | agent modules with deterministic fallback |

## Configuration Files

| File | Purpose |
|------|---------|
| `config/agent_models.json` | Model routing by agent role |
| `config/policy_config.json` | Protected paths, max files per step, plan scope |
| `config/priority_weights.json` | Module priority scoring |
| `config/gate_spec.json` | Gate definitions and required checks |
| `config/module_registry.json` | Module metadata registry |

Model resolution priority: built-in fallback < config file < environment variable.

## Limitations

- AST analysis is approximate; dynamic imports, monkey patching, runtime reflection, and metaprogramming are not fully resolved.
- DB detection is signal-based and can miss unconventional persistence layers.
- The call graph is approximate and does not capture every indirect call.
- Only Python `.py` files are scanned.
- Findings favor product-code signals; tests and docs are visible in raw artifacts but filtered or downweighted in diagnosis stages.
- LLM-backed agents currently target DashScope/Bailian-compatible APIs.

## Roadmap

- richer repository heuristics for decorators and cross-file data flow
- stronger characterization-test recommendations before risky refactors
- controlled patch-plan previews without automatic application
- resumable iteration state
- additional LLM providers
- TypeScript/JavaScript support

## Project Layout

```text
code-decoupling-agent/
  main.py                  # CLI entry point
  agents/                  # governor, validator, planner, critic, module reports
  scanner/                 # AST scanners
  rules_engine/            # RULE_A through RULE_G
  policy/                  # protected-path and scope enforcement
  iteration/               # test/policy/runtime gate execution
  llm/                     # optional provider health and model routing
  report/                  # Markdown renderer
  config/                  # routing, policy, priority, gate specs
  tests/                   # smoke, golden, reporting, gate, validator tests
```

## Design Documents

| Document | Content |
|----------|---------|
| `ARCHITECTURE.md` | Architecture, layers, hard constraints |
| `MODULE_SPEC.md` | Module contracts, testing, report expectations |
| `ITERATION_LOOP.md` | Gate and controlled iteration design |
| `MULTI_AGENT.md` | Agent roles, model routing, phase boundaries |
| `AGENTS.md` | Product scope and explicit non-goals |

## License

MIT. See [LICENSE](LICENSE).
