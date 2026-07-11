---
name: e2e-code-reviewer
description: >-
  Code review for e2e-orchestrator implementation. Uses bugbot subagent.
  Used by e2e-orchestrator Quality Council.
disable-model-invocation: true
---

# e2e Code Reviewer (QC-R)

Readonly review of changes since orchestration run started.

## Inputs

- `<run_dir>/implementation-notes.md`
- `<run_dir>/intake.json`
- Git diff of changed files
- `.cursor/skills/e2e-orchestrator/domain-context.md`

## Task

Review for:

1. e2e domain invariants (registry, OTP, constants SSOT, view projection)
2. Selector durability (id/name/role preferred)
3. Scope creep beyond intake scope
4. Missing scenario doc updates when manifest changed

## Output

Write `<run_dir>/review-report.json`:

```json
{
  "passed": true,
  "issues": []
}
```

Set `passed: false` for high-severity invariant violations.
