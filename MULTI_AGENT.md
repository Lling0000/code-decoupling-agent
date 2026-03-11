# Multi-Agent Ready Architecture

This project keeps deterministic diagnosis as the execution backbone.
Planner Agent and Critic Agent can now run as live Bailian-backed LLM agents without
adding autonomous code execution loops.

## Principle

Multi-agent components are responsible for:

- repository understanding
- triage
- planning
- critique

Deterministic tools remain responsible for:

- scanning
- rule evaluation
- hard verification
- policy enforcement

## Current Components

- `Governor`: orchestrates the whole diagnosis pass and bounded planning pass
- `Tool Runner`: runs the deterministic scanning and rule engine stack
- `Scanner Agent`: converts raw artifacts into hotspot-oriented repo inventory
- `Planner Agent`: turns findings into bounded action steps
- `Critic Agent`: checks plan scope and policy risks
- `Policy Engine`: enforces protected path and file-scope guardrails

## Current Outputs

In addition to the original diagnosis artifacts, the tool now writes:

- `artifacts/repo_inventory.json`
- `artifacts/triage.json`
- `artifacts/action_plan.json`
- `artifacts/critic_review.json`
- `artifacts/planner_agent.json`
- `artifacts/critic_agent.json`
- `artifacts/model_routing.json`

## Current Model Routing Blueprint

- governor / planner / triage / critic: `PLANNER_MODEL`, fallback `DASHSCOPE_MODEL`, default `deepseek-v3.2`
- refactor / test fix / small bug fix: `CODER_MODEL`, fallback `DASHSCOPE_MODEL`, default `qwen3-coder-flash`
- cheap summaries / PR copy / scan explanation: `DASHSCOPE_MODEL`, default `qwen3.5-flash`
- vector recall: `text-embedding-v4`
- rerank: `qwen3-rerank`

Provider environment variables are:

- `DASHSCOPE_API_KEY`
- `DASHSCOPE_BASE_URL`
- `DASHSCOPE_MODEL`
- `CODER_MODEL`
- `PLANNER_MODEL`
- `ENABLE_LIVE_AGENTS`

Legacy compatibility:

- `BAILIAN_BASE_URL` is still accepted as an alias for `DASHSCOPE_BASE_URL`
- `BAILIAN_MODEL` is still accepted as an alias for `DASHSCOPE_MODEL`

Default routing source:

- `config/agent_models.json`

Priority:

- internal fallback
- config file
- environment variables

## Config Self-Check

Use:

```bash
python main.py --check-llm-config
```

The check reports:

- resolved provider config
- live agent runtime status
- planner / critic / coder / summary model health

If `--output` is also provided, the tool writes:

- `artifacts/llm_health_check.json`

## Phase Boundary

Planner and Critic may call a live LLM provider.
Tool Runner and Policy Engine remain deterministic.
No agent is allowed to execute code changes automatically.
