# Handoff Matrix

When `release-verdict.json` has `passed: false` or `gates-report.json` has `passed: false`, rerun from the mapped agent through the rest of the graph (including QC fan-out).

Limits: `MAX_RETRIES_PER_AGENT=2`, `MAX_TOTAL_ITERATIONS=10` (in `run.json`).

| failed_agent / signal | restart_at | notes |
|-----------------------|------------|-------|
| e2e-intake | E01 | misclassified profile or missing system_code |
| e2e-domain-scout | E02 | wrong layer/files identified |
| e2e-scenario-analyst | E03 | wrong module/channel scope |
| e2e-manifest-planner | E04 | manifest deps/order wrong |
| e2e-platform-architect | E05 | boundary/state-machine design flaw |
| e2e-selector-healer | E06 | selector strategy needs redesign |
| e2e-docs-guardian | E07 | SSOT checklist incomplete |
| e2e-implementer | E08 | code/step logic errors |
| e2e-docs-writer | E07 | docs scope wrong; re-run guardian first |
| e2e-code-reviewer | E08 | review findings → fix code |
| e2e-security-auditor | E05 | design-level PII/auth; else E08 |
| e2e-test-runner | E08 | default; E05 if domain aggregate tests fail |
| gates: docs_consistency | E07 | manifest ↔ scenario drift |
| gates: ruff / ruff_format | E08 | formatting/lint in changed files |
| gates: pytest domain | E05 | RunAggregate/SuiteAggregate invariant |
| gates: pytest steps | E08 | step handler logic |
| e2e-release-judge | E08 | generic QC failure → implementer |

After backtrack from E08+, always re-run Quality Council parallel + Release Judge.

Inject `release-verdict.json` → `feedback` into the restart agent's Task prompt.

## Spike upgrade

When user confirms spike → feature:

1. Update `pipeline_profile` in `run.json` to `step_fix` or `new_module`.
2. Rebuild `agent_graph` from pipeline-profiles.md.
3. Restart from E02 or E03 (skip E01 unless scope changed).
