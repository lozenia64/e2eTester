---
name: e2e-release-judge
description: >-
  Final quality gate for e2e-orchestrator runs. Synthesizes QC reports and
  e2e invariants into release-verdict.json.
disable-model-invocation: true
---

# e2e Release Judge (E09)

Readonly verdict. **Do not modify code.**

## Inputs

- `<run_dir>/gates-report.json`
- `<run_dir>/review-report.json` (if present)
- `<run_dir>/security-report.json` (if present)
- `<run_dir>/implementation-notes.md`
- `<run_dir>/intake.json`
- `.cursor/skills/e2e-orchestrator/domain-context.md`

## Invariants to verify

- [ ] manifest `module_id` ↔ `docs/scenarios/{code}.md` sync (if manifest touched)
- [ ] Step changes use registry, not if/elif chains
- [ ] OTP pause matches manifest `requires_user_input`
- [ ] HOM/MHM constants from `app/scenarios/rep_homepage/constants.py`
- [ ] New API routes use `dependencies.py` Depends pattern
- [ ] No PII on Run/Suite wire payloads

## Task

1. Aggregate gate and QC results.
2. Check e2e-specific invariants against implementation-notes and diff scope.
3. Emit pass/fail with actionable feedback.

## Output

Write `<run_dir>/release-verdict.json`:

```json
{
  "passed": true,
  "failed_agent": null,
  "feedback": "",
  "invariants_checked": ["manifest_docs_sync", "otp_policy", "view_projection"]
}
```

When `passed` is false, set `failed_agent` (restart target per handoff-matrix) and specific `feedback`.
