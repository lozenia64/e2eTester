---
name: e2e-intake
description: >-
  Classifies e2eTester requests into pipeline profiles and emits intake.json
  with system_code, layer, touch_surfaces, and agent_graph. Used by e2e-orchestrator.
disable-model-invocation: true
---

# e2e Intake (E01)

Readonly classification agent. **Do not modify code.**

## Inputs

- `run_dir/run.json` → `user_request`
- `.cursor/skills/e2e-orchestrator/pipeline-profiles.md`
- `.cursor/skills/e2e-orchestrator/domain-context.md`

## Task

1. Parse the user request for system code, layer, and intent.
2. Select `pipeline_profile` from: `step_fix`, `new_module`, `new_system`, `platform`, `healing_patch`, `docs_only`, `spike`.
3. Set `system_code` (hom/mhm/fp/hrp/hwtc/chbot or null for platform-wide).
4. Set `layer` and `touch_surfaces` arrays.
5. Set `affected_modules` when module names are mentioned or inferable.
6. Set `risk_flags`: `pii`, `live_site_claim`, `selector_fragile`, `cross_channel_hom_mhm`, `auth`, `otp` as applicable.
7. Set `conditional_agents`: include `security-auditor` when pii/otp/auth or new_system.
8. Build `agent_graph` from pipeline-profiles.md (exclude E01, E0R, and QC agents).

## Output

Write `<run_dir>/intake.json` per [artifacts-contract.md](../e2e-orchestrator/artifacts-contract.md).

## Profile hints

| Keywords | Profile |
|----------|---------|
| selector, locator, timeout, step failed | step_fix |
| 모듈 추가, new module | new_module |
| 새 시스템, new system | new_system |
| API, dashboard, RunService, scheduling | platform |
| healing, patch, 자가치유 | healing_patch |
| 문서, scenario doc, README | docs_only |
| probe, research, 탐색 | spike |
