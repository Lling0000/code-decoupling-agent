# Code Decoupling Agent MVP

Minimal MVP for diagnosing coupling issues in a local Python repository.

## What It Does

The tool scans a local Python repository and produces:

- import dependency artifacts
- definition and approximate call graph artifacts
- environment variable usage artifacts
- database / ORM usage signal artifacts
- shared utils dependency artifacts
- mutable global state artifacts
- rule-based findings
- a human-readable markdown summary

## What It Does Not Do

This repository still does not include:

- automatic code rewriting
- patch execution
- autonomous LLM-driven code execution
- web UI
- database persistence
- multi-language analysis

## CLI

```bash
python main.py --repo /path/to/repo --output ./output
```

```bash
python main.py --check-llm-config
```

```bash
python main.py --repo /path/to/repo --output ./output --run-gates
```

## Output

The tool writes:

- `summary.md`
- `artifacts/import_graph.json`
- `artifacts/definitions.json`
- `artifacts/call_graph.json`
- `artifacts/env_usage.json`
- `artifacts/db_usage.json`
- `artifacts/utils_usage.json`
- `artifacts/global_state.json`
- `artifacts/findings.json`

It now also writes multi-agent-ready planning artifacts:

- `artifacts/repo_inventory.json`
- `artifacts/module_inventory.json`
- `artifacts/module_priorities.json`
- `artifacts/module_deep_reviews.json`
- `artifacts/triage.json`
- `artifacts/action_plan.json`
- `artifacts/critic_review.json`
- `artifacts/planner_agent.json`
- `artifacts/critic_agent.json`
- `artifacts/model_routing.json`
- `artifacts/iteration_agent_report.json`
- `iteration_human_report.md`
- `module_reports/lightweight/*.md`
- `module_reports/heavyweight/*.md`

## Multi-Agent Ready, Still Deterministic

This version supports live Planner and Critic agents through a Bailian-compatible API,
while deterministic guardrails remain in control:

- Governor
- Tool Runner
- Scanner Agent
- Planner Agent
- Critic Agent
- Policy Engine

The rule is:

`agents think and propose; deterministic tools execute and judge`

See `MULTI_AGENT.md` for details.

## Provider Environment Variables

The repository now stores a provider blueprint for future integration.
When you are ready to connect real APIs, set:

- `DASHSCOPE_API_KEY`
- `DASHSCOPE_BASE_URL`
- `DASHSCOPE_MODEL`
- `CODER_MODEL`
- `PLANNER_MODEL`
- `ENABLE_LIVE_AGENTS`

Set `ENABLE_LIVE_AGENTS=0` if you want to force deterministic fallback without making
live provider calls.

Default agent model routing now lives in:

- `config/agent_models.json`
- `config/module_registry.json`
- `config/gate_spec.json`

Priority order:

- built-in fallback
- `config/agent_models.json`
- environment variables

Compatibility note:

- `BAILIAN_BASE_URL` is still accepted as a legacy alias
- preferred name is `DASHSCOPE_BASE_URL`
- `BAILIAN_MODEL` is still accepted as a legacy alias
- preferred name is `DASHSCOPE_MODEL`

Recommended defaults for your current routing idea:

```powershell
$env:DASHSCOPE_API_KEY="your-key"
$env:DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:DASHSCOPE_MODEL="qwen3.5-flash"
$env:CODER_MODEL="qwen3-coder-flash"
$env:PLANNER_MODEL="deepseek-v3.2"
$env:ENABLE_LIVE_AGENTS="1"
```

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Runtime dependencies are standard-library only.

## Run

```bash
python main.py --repo ./example_repo --output ./output
```

Run analysis plus iteration gates:

```bash
python main.py --repo ./example_repo --output ./output --run-gates --target-test-command "pytest" --runtime-command "python app.py"
```

## Check LLM Config

```bash
python main.py --check-llm-config
```

Optional artifact output:

```bash
python main.py --check-llm-config --output ./output
```

This command:

- validates the resolved provider configuration
- shows whether live agent calls are enabled
- probes the planner, critic, coder, and summary models
- writes `artifacts/llm_health_check.json` when `--output` is provided

## Run Gates

`--run-gates` will execute the current iteration gate runner and emit:

- `artifacts/iteration_agent_report.json`
- `iteration_human_report.md`

Current gate model:

- `test_gate`: system tests, goldens, and optional target repo regression commands
- `policy_gate`: protected path, step scope, and no-auto-execution checks
- `runtime_gate`: output completeness plus optional target repo runtime smoke commands

Decision rules:

- `allow_next_iteration`
- `hold_for_review`
- `blocked`

If you do not provide target repo test or runtime commands, the runner will mark those gates as
manual review instead of pretending they passed.

## Current Limitations

- analysis is AST-based and approximate
- database access detection is signal-based
- dynamic imports and runtime indirection are not resolved precisely
- only Planner and Critic are live LLM agents
- Refactor Agent is still planning-only and does not auto-edit code

## Roadmap

- stronger repo understanding heuristics
- richer prioritization and planning contracts
- controlled refactor planning
- future LLM-backed planner / critic integration behind policy guardrails

## Design Docs

New top-level design documents:

- `ARCHITECTURE.md`: overall system architecture and hard boundaries
- `MODULE_SPEC.md`: module contract, testing, and report expectations
- `ITERATION_LOOP.md`: iteration gate, stop/go criteria, and controlled loop design

Reusable templates:

- `templates/module_README.md`
- `templates/module_agent_report.json`
- `templates/module_human_report.md`
