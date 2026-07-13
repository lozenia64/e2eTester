# Handoff Matrix

When any gate report, `mechanical-verdict.json`, or `release-verdict.json` has `passed: false`, rerun from the mapped agent through the rest of the graph (including all verification tiers and QC fan-out).

Limits: `MAX_RETRIES_PER_AGENT=2`, `MAX_TOTAL_ITERATIONS=10` (in `run.json`).

| failed_agent / signal | restart_at | notes |
|-----------------------|------------|-------|
| e2e-intake | E01 | misclassified profile or missing system_code |
| e2e-researcher | E0R | research brief missing citations/sections |
| research-gate fail | E0R | T0 mechanical research validation |
| e2e-domain-scout | E02 | wrong layer/files identified |
| e2e-scenario-analyst | E03 | wrong module/channel scope |
| e2e-manifest-planner | E04 | manifest deps/order wrong |
| e2e-platform-architect | E05 | boundary/state-machine design flaw |
| e2e-selector-healer | E06 | selector strategy needs redesign |
| e2e-docs-guardian | E07 | SSOT checklist incomplete |
| planning-gate fail | profile last planner | step_fix→E06, new_module/new_system→E07, platform→E05, healing_patch→E06 |
| e2e-implementer | E08 | code/step logic errors |
| preflight: ruff_changed / ruff_format_changed | E08 | T2 shift-left lint/format on changed files |
| e2e-docs-writer | E07 | docs scope wrong; re-run guardian first |
| e2e-code-reviewer | E08 | review findings → fix code |
| e2e-security-auditor | E05 | design-level PII/auth; else E08 |
| e2e-test-runner | E08 | default; E05 if domain aggregate tests fail |
| mechanical-verdict fail | see failed_agent in report | do not run E09 until mechanical pass |
| gates: docs_consistency | E07 | manifest ↔ scenario drift |
| gates: ruff / ruff_format (tier 0) | E08 | re-run preflight + full CI |
| gates: pytest domain | E05 | RunAggregate/SuiteAggregate invariant |
| gates: pytest steps | E08 | step handler logic |
| e2e-release-judge | E08 | generic QC failure → implementer |

After backtrack from E08+, always re-run: T2 preflight → T3 full CI → QC parallel → mechanical verdict → Release Judge.

Increment `gate_attempts.preflight` or `gate_attempts.full_ci` in `run.json` when T2/T3 gates fail.

Inject `release-verdict.json` or gate report `failed_agent` → `feedback` into the restart agent's Task prompt.

## Spike upgrade

When user confirms spike → feature:

1. Update `pipeline_profile` in `run.json` to `step_fix` or `new_module`.
2. Rebuild `agent_graph` from pipeline-profiles.md.
3. Restart from E02 or E03 (skip E01/E0R unless scope changed).
