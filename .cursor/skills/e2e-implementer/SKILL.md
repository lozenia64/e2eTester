---
name: e2e-implementer
description: >-
  Implements code changes for e2eTester per orchestration artifacts. Used by
  e2e-orchestrator after planning agents complete.
disable-model-invocation: true
---

# e2e Implementer (E08)

Writes application code. Follow all e2e domain invariants.

## Inputs

- `<run_dir>/intake.json`
- All prior artifacts in `<run_dir>/` (context-map, scenario-impact, manifest-plan, architecture-delta, healing-plan, docs-checklist)
- `.cursor/skills/e2e-orchestrator/domain-context.md`

## Task

1. Implement the minimal correct diff per planning artifacts.
2. Respect invariants: step registry, OTP policy, constants SSOT, RunView projection, PII off blob.
3. Update `docs/scenarios/{code}.md` when manifest modules change (or defer to docs-checklist).
4. Do not add dependencies without justification.
5. Match existing code style; run ruff mentally before finishing.

## Output

1. Code changes in workspace.
2. Write `<run_dir>/implementation-notes.md` with `## 변경 요약` listing every file touched and why.

## Warnings

- `live_site_claim` risk: use `CLAIM_CONTENT_TEXT` from `app/scenarios/rep_homepage/constants.py`.
- HOM/MHM step changes may need both channel adapters if shared workflow_step.
