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
- **Dev phase artifacts** (when present):
  - `<run_dir>/spec.md` (dev-spec-writer)
  - `<run_dir>/tasks.yaml` (dev-task-planner)
  - `<run_dir>/ux-spec.md` (dev-ux-designer, if exists)
  - `<run_dir>/architecture.md` (dev-architect, if exists)
  - `<run_dir>/context.md` (guardian — primary ground truth for implementer)
- **E2E phase artifacts**:
  - context-map, scenario-impact, manifest-plan, architecture-delta, healing-plan, docs-checklist
- `.cursor/skills/e2e-orchestrator/domain-context.md`

Read `context.md` and `spec.md` first when both exist; e2e artifacts refine domain-specific scope.

## Task

1. Implement the minimal correct diff per planning artifacts.
2. Respect invariants: step registry, OTP policy, constants SSOT, RunView projection, PII off blob.
3. Update `docs/scenarios/{code}.md` when manifest modules change (or defer to docs-checklist).
4. Do not add dependencies without justification.
5. Match existing code style.

## Preflight gate (required before handoff)

Before writing `implementation-notes.md`, run:

```bash
python3 .cursor/skills/e2e-orchestrator/scripts/run_preflight_gates.py --run-dir "<run_dir>"
```

- If `preflight-report.json` has `"passed": false`, fix lint/format issues and re-run until it passes.
- Do **not** write `implementation-notes.md` until preflight passes.

## Output

1. Code changes in workspace.
2. `<run_dir>/preflight-report.json` with `"passed": true`.
3. Write `<run_dir>/implementation-notes.md` with `## 변경 요약` listing every file touched and why.

## Warnings

- `live_site_claim` risk: use `CLAIM_CONTENT_TEXT` from `app/scenarios/rep_homepage/constants.py`.
- HOM/MHM step changes may need both channel adapters if shared workflow_step.
