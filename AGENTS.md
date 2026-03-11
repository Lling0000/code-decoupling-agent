# AGENTS.md

## Project identity

This repository is for a minimal MVP of a code decoupling diagnosis agent.

The product is not a general autonomous coding agent.
The product is a focused static analysis and diagnosis tool for Python repositories.

Its job is to:
- scan a local Python repository
- collect structural artifacts
- run rule-based diagnosis
- generate a markdown summary and json artifacts

## Scope of this MVP

This version only supports:

- local CLI usage
- Python repository analysis
- `.py` file scanning
- import relationship scanning
- class / function / method definition scanning
- approximate call graph scanning
- environment variable usage scanning
- database / ORM usage signal scanning
- shared utils/common/helper dependency scanning
- global state signal scanning
- rule-based findings generation
- markdown/json report generation

## Explicit non-goals

Do NOT implement any of the following in this version:

- automatic code rewriting
- patch generation for source code changes
- code execution agent loops
- external LLM API integration
- web frontend
- database persistence
- background jobs
- distributed architecture
- multi-language repository support
- highly advanced whole-program static analysis
- enterprise-scale plugin system

## Design principles

When making implementation choices, prefer:

- simplicity over cleverness
- runnable code over abstract architecture
- small modules over giant files
- explicit data flow over hidden coupling
- lightweight dependencies over heavy frameworks
- stable output formats over fancy presentation

Avoid over-engineering.

## Technical constraints

- Python 3.11+
- analyze only `.py` files
- prefer Python standard library:
  - `ast`
  - `pathlib`
  - `argparse`
  - `json`
  - `collections`
  - `dataclasses`
  - `typing`
- if a dependency is needed, keep it lightweight
- do not introduce unnecessary frameworks

## Expected CLI

Target CLI shape:

```bash
python main.py --repo /path/to/repo --output ./output
```

## Expected outputs

The implementation should generate:

- `summary.md`
- `artifacts/import_graph.json`
- `artifacts/definitions.json`
- `artifacts/call_graph.json`
- `artifacts/env_usage.json`
- `artifacts/db_usage.json`
- `artifacts/utils_usage.json`
- `artifacts/global_state.json`
- `artifacts/findings.json`

## Required scanner capabilities

At minimum, implement these scanners:

1. import scanner
2. definitions scanner
3. call scanner
4. env usage scanner
5. db usage scanner
6. utils usage scanner
7. global state scanner

## Rule engine requirements

At minimum, support findings for:

- handler/controller/router files directly using database access signals
- the same environment variable being directly read in multiple files
- utils/common/helper modules being overused
- suspected mutable global state
- simple cyclic import detection

## Reporting requirements

Generate a readable `summary.md` that includes:

- scan overview
- top import-heavy files
- environment variable usage overview
- database access signal overview
- shared utils dependency overview
- global state risk overview
- findings list
- explanation and suggestion for each finding
- limitations section

## Testing requirements

Add basic tests.
At minimum include tests for:

- import scanning
- env scanning
- at least one rule engine case

## Important phase boundary

This repository is only Phase 1:

Phase 1 = diagnosis
Phase 2 = planning
Phase 3 = controlled execution

Do not jump into Phase 2 or Phase 3 yet.
