---
name: e2e-intake
description: >-
  Unified intake for e2e-orchestrator: classifies e2e + dev pipeline profiles,
  risk flags, and ship intent. Emits intake.json; agent_graph is resolved by
  resolve_graph.py (do not hand-build graph).
disable-model-invocation: true
---

# e2e Intake (E01) — Unified

Readonly classification agent. **Do not modify code.**

## Inputs

- `<run_dir>/run.json` → `user_request`
- `.cursor/skills/e2e-orchestrator/unified-profiles.md`
- `.cursor/skills/e2e-orchestrator/domain-context.md`
- `~/.cursor/skills/dev-orchestrator/pipeline-profiles.md` (dev profile hints)

## Task

1. Parse the user request for system code, layer, and intent.
2. Select `e2e_pipeline_profile`: `step_fix`, `new_module`, `new_system`, `platform`, `healing_patch`, `docs_only`, `spike`.
3. Select `dev_pipeline_profile` hint (or leave for resolve_graph): `trivial`, `hotfix`, `feature`, `refactor`, `docs`, `spike` — resolve_graph maps from e2e profile; only set if override needed.
4. Set `system_code` (hom/mhm/fp/hrp/hwtc/chbot or null for platform-wide).
5. Set `layer` and `touch_surfaces` arrays.
6. Set `affected_modules` when mentioned or inferable.
7. Set `risk_flags`: e2e flags (`pii`, `live_site_claim`, `selector_fragile`, `cross_channel_hom_mhm`, `auth`, `otp`) plus dev flags (`user_facing`, `unknown_tech`, `input_validation`, `dependencies`, `network`, `high_impact`) as applicable.
8. Set `conditional_agents`: e.g. `dev-ux-designer`, `dev-security-auditor`, `e2e-security-auditor` when flags warrant.
9. Set `dev_path`: `full`, `standard`, or `minimal` (minimal only for single-file LOW_RISK fixes).
10. Set `ship_requested`: true if user asks for PR, commit, deploy, or "머지".
11. Set `agent_graph` to **null** — never hand-build the graph.

Also set `pipeline_profile` to the same value as `e2e_pipeline_profile` for backward compatibility.

## Output

Write `<run_dir>/intake.json` per [artifacts-contract.md](../e2e-orchestrator/artifacts-contract.md).

## Profile hints

| Keywords | e2e_pipeline_profile |
|----------|------------------------|
| selector, locator, timeout, step failed | step_fix |
| 모듈 추가, new module | new_module |
| 새 시스템, new system | new_system |
| API, dashboard, RunService, scheduling | platform |
| healing, patch, 자가치유 | healing_patch |
| 문서, scenario doc, README | docs_only |
| probe, research, 탐색 | spike |
