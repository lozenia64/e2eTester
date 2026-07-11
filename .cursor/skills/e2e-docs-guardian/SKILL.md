---
name: e2e-docs-guardian
description: >-
  Ensures e2eTester documentation SSOT compliance before and after changes.
  Used by e2e-orchestrator.
disable-model-invocation: true
---

# e2e Docs Guardian (E07)

Readonly checklist. **Do not edit docs** (e2e-docs-writer or implementer applies edits).

## Inputs

- `<run_dir>/intake.json`
- `<run_dir>/scenario-impact.md` or `<run_dir>/manifest-plan.yaml` (if present)
- `docs/DOCS_GOVERNANCE.md`
- `scripts/check_docs_consistency.py` (read to know guard rules)

## Task

1. Map each changed fact to its SSOT document.
2. List files that must be updated (scenario doc, E2E_ARCHITECTURE, README, .env.example).
3. List check_docs_consistency rules at risk (manifest↔scenario, routes, env vars, folder tree).
4. Note what must NOT be duplicated across docs (link only).

## Output

Write `<run_dir>/docs-checklist.md` with sections:

- `## SSOT`
- `## 수정 대상`
- `## 가드 항목`
