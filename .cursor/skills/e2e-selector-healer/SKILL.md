---
name: e2e-selector-healer
description: >-
  Plans selector fixes and self-healing workflow for e2eTester step failures.
  Used by e2e-orchestrator step_fix and healing_patch profiles.
disable-model-invocation: true
---

# e2e Selector Healer (E06)

Readonly analysis unless healing_patch profile explicitly applies approved patch.

## Inputs

- `<run_dir>/intake.json`
- `<run_dir>/scenario-impact.md` (if present)
- `app/healing/` (engine, selector_healer, page_proxy)
- Failing step source under `app/systems/{code}/steps/`
- `app/systems/hom/steps/login_common.py` as selector pattern reference

## Task

1. Extract broken selector from error context or user description.
2. Rank fix strategy: prefer `#id`, `name`, `role` over class/text/nth/xpath.
3. Note if SelfHealingEngine would auto-recover vs needs source patch.
4. For healing_patch: reference pending patch from healing center API shape.
5. Plan verification: pytest unit tests vs manual headed run.

## Output

Write `<run_dir>/healing-plan.md` with sections:

- `## 깨진 셀렉터`
- `## 치유 전략`
- `## 검증`

## Selector rules

Follow patterns in existing step modules. Do not introduce xpath unless unavoidable.
