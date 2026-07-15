# Handoff Matrix

When any gate report, `mechanical-verdict.json`, `release-verdict.json`, or guardian `REJECTED` occurs, rerun from the mapped agent through the rest of the graph (including verification tiers, QC fan-out, and ship if applicable).

Limits: `MAX_RETRIES_PER_AGENT=2`, `MAX_TOTAL_ITERATIONS=10` (in `run.json`).

## E2E agents

| failed_agent / signal | restart_at | notes |
|-----------------------|------------|-------|
| e2e-intake | e2e-intake | misclassified profile |
| e2e-researcher | e2e-researcher | T0 research validation |
| research-gate fail | e2e-researcher | T0 mechanical |
| e2e-domain-scout | e2e-domain-scout | wrong layer/files |
| e2e-scenario-analyst | e2e-scenario-analyst | module scope wrong |
| e2e-manifest-planner | e2e-manifest-planner | manifest deps wrong |
| e2e-platform-architect | e2e-platform-architect | boundary flaw |
| e2e-selector-healer | e2e-selector-healer | selector strategy |
| e2e-docs-guardian | e2e-docs-guardian | SSOT checklist |
| planning-gate fail | run.json `last_planner` | from resolve_graph |
| e2e-implementer | e2e-implementer | code errors |
| e2e-docs-writer | e2e-docs-guardian | docs scope wrong |
| e2e-code-reviewer | e2e-implementer | review findings |
| e2e-security-auditor | e2e-platform-architect or e2e-implementer | design vs code |
| e2e-test-runner | e2e-implementer | default |
| e2e-release-judge | e2e-implementer | generic QC failure |

## Dev agents

| failed_agent | restart_at | notes |
|--------------|------------|-------|
| dev-spec-writer | dev-spec-writer | scope wrong |
| dev-context-scout | dev-context-scout | wrong files |
| dev-researcher | dev-researcher | tech misunderstanding |
| dev-architect | dev-architect | structure flaw |
| dev-task-planner | dev-task-planner | task breakdown wrong |
| dev-ux-designer | dev-ux-designer | UI contract |
| dev-build-integrator | e2e-implementer | lint/build after fix |
| dev-security-auditor | dev-architect or e2e-implementer | design vs code |
| dev-pr-publisher | dev-pr-publisher | PR format only |
| dev-ci-watcher | e2e-implementer | CI failures usually code |

## Global agents

| failed_agent | restart_at | notes |
|--------------|------------|-------|
| guardian REJECTED | dev-architect or run.json `last_planner` | per review.md blockers |
| triage | e2e-intake | reclassify path |

## Gates

| signal | restart_at |
|--------|------------|
| preflight fail | e2e-implementer |
| mechanical-verdict fail | see `failed_agent` in report |
| gates: docs_consistency | e2e-docs-guardian |
| gates: pytest domain | e2e-platform-architect |
| gates: pytest steps | e2e-implementer |

After backtrack from implementer+, always re-run: T2 preflight → QC parallel → T3 CI → mechanical verdict → release judge → ship (if enabled).

Re-run `resolve_graph.py` only when `intake.json` profile or ship_requested changes.

## Spike upgrade

1. Update `e2e_pipeline_profile` in `intake.json`.
2. Run `resolve_graph.py`.
3. Restart from first agent in new graph (skip intake if scope unchanged).
