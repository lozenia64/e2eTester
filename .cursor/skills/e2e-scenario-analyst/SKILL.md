---
name: e2e-scenario-analyst
description: >-
  Analyzes manifest and scenario doc impact for e2eTester changes. Used by
  e2e-orchestrator.
disable-model-invocation: true
---

# e2e Scenario Analyst (E03)

Readonly exploration. Use `explore` thoroughness: **medium**.

## Inputs

- `<run_dir>/intake.json`
- `app/systems/{system_code}/manifest.yaml`
- `docs/scenarios/{system_code}.md`
- `<run_dir>/context-map.md` (if present)

## Task

1. List affected `module_id`s and their `workflow_step`, `depends_on`, `requires_user_input`.
2. For HOM/MHM, note channel-specific step adapters vs shared scenario.
3. Identify scenario doc sections that must change.
4. Warn if compensation modules involved (`live_site_claim`).

## Output

Write `<run_dir>/scenario-impact.md` with sections:

- `## 시스템`
- `## 모듈 영향`
- `## 시나리오 문서`

Do not modify files.
