# Sample Output: `psf/requests`

This is a shortened sample of the kind of report Code Decoupling Agent emits after scanning a real Python repository.

Run:

```bash
git clone --depth 1 https://github.com/psf/requests.git /tmp/requests-dogfood
ENABLE_LIVE_AGENTS=0 python3 main.py \
  --repo /tmp/requests-dogfood \
  --output /tmp/requests-dogfood-output
```

Observed summary:

```text
Scanned 36 Python files
Generated 5 findings
Validated 5 actionable findings
Profiled 28 modules
```

## Scan Overview

| Metric | Value |
|--------|-------|
| Python files scanned | `36` |
| Parse failures | `0` |
| Raw findings | `5` |
| Actionable findings | `5` |
| Mode | deterministic fallback |

## Hotspot Modules

| Module | Why it surfaced |
|--------|-----------------|
| `src/requests/utils.py` | Broad shared helper surface and high fan-in |
| `src/requests/models.py` | Large product module with central request/response objects |
| `src/requests/sessions.py` | Orchestration-heavy product module |

## Example Finding Shape

```text
### Shared Utils Module Overuse

- Severity: medium
- Confirmation status: confirmed
- Confidence: medium
- File group: src/requests/utils.py and consumers
- Evidence: shared helper module is imported from multiple product modules
- Explanation: A broad helper surface can become an implicit cross-domain API.
- Suggestion: Keep genuinely generic helpers shared; move domain-specific helpers closer to their owning modules.
```

## Example Action Plan Shape

```text
STEP-01 [P1] Characterize current behavior before touching central helpers
- Scope: tests and call-site inventory
- Success criteria: behavior-preserving tests or snapshots exist for high-traffic helpers
- Rollback condition: any public helper behavior becomes ambiguous

STEP-02 [P1] Split domain-specific helper logic from generic utilities
- Scope: one helper cluster at a time
- Success criteria: import fan-in drops without changing public behavior
- Rollback condition: call sites require cross-module coordination beyond planned scope
```

## Notes

This sample is intentionally conservative. The tool is not claiming that `requests` needs a particular refactor; it is showing the scanner's evidence format and review-first workflow on a mature real-world repository.
