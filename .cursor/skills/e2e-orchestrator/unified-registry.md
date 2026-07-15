# Unified Agent Registry

Single source of truth for all agents orchestrated by `e2e-orchestrator` in e2eTester.
Includes project e2e skills, global dev skills, and `~/.cursor/agents/` definitions.

**Supersedes** [subagent-map.md](subagent-map.md) (kept as a thin pointer).

## e2eTester role resolution (fixed)

| Role | Active agent | Supersedes (never in graph) |
|------|--------------|----------------------------|
| Implementation | `e2e-implementer` | `dev-implementer`, global `implementer` |
| Code review QC | `e2e-code-reviewer` | `dev-code-reviewer` |
| Final verdict | `e2e-release-judge` | `dev-release-judge` |
| Design approval | `guardian` | — |
| Triage (minimal only) | `triage` | — |

## Dev skills (`~/.cursor/skills/`)

| agent_id | kind | path | subagent_type | readonly | artifact(s) |
|----------|------|------|---------------|----------|-------------|
| dev-spec-writer | skill | `~/.cursor/skills/dev-spec-writer/` | generalPurpose | yes | spec.md |
| dev-context-scout | skill | `~/.cursor/skills/dev-context-scout/` | explore | yes | context-map.md |
| dev-researcher | skill | `~/.cursor/skills/dev-researcher/` | docs-researcher | yes | research.md |
| dev-architect | skill | `~/.cursor/skills/dev-architect/` | architect | yes | architecture.md |
| dev-task-planner | skill | `~/.cursor/skills/dev-task-planner/` | generalPurpose | yes | tasks.yaml |
| dev-ux-designer | skill | `~/.cursor/skills/dev-ux-designer/` | generalPurpose | yes | ux-spec.md |
| dev-test-engineer | skill | `~/.cursor/skills/dev-test-engineer/` | shell | no | test-report.json |
| dev-code-reviewer | skill | `~/.cursor/skills/dev-code-reviewer/` | bugbot | yes | review-report.json |
| dev-security-auditor | skill | `~/.cursor/skills/dev-security-auditor/` | security-review | yes | security-report.json |
| dev-build-integrator | skill | `~/.cursor/skills/dev-build-integrator/` | shell | no | build-report.json |
| dev-release-judge | skill | `~/.cursor/skills/dev-release-judge/` | generalPurpose | yes | release-verdict.json |
| dev-pr-publisher | skill | `~/.cursor/skills/dev-pr-publisher/` | shell | no | pr.json |
| dev-ci-watcher | skill | `~/.cursor/skills/dev-ci-watcher/` | ci-investigator | yes | ci-report.json |
| dev-docs-curator | skill | `~/.cursor/skills/dev-docs-curator/` | documenter | no | implementation-notes.md |

`dev-intake` is replaced by `e2e-intake` (unified). `dev-implementer` is superseded by `e2e-implementer`.

## E2E skills (`.cursor/skills/`)

| agent_id | kind | path | subagent_type | readonly | artifact(s) |
|----------|------|------|---------------|----------|-------------|
| e2e-intake | skill | `.cursor/skills/e2e-intake/` | generalPurpose | yes | intake.json |
| e2e-researcher | skill | `.cursor/skills/e2e-researcher/` | generalPurpose | yes | research-brief.md |
| e2e-domain-scout | skill | `.cursor/skills/e2e-domain-scout/` | explore | yes | context-map.md |
| e2e-scenario-analyst | skill | `.cursor/skills/e2e-scenario-analyst/` | explore | yes | scenario-impact.md |
| e2e-manifest-planner | skill | `.cursor/skills/e2e-manifest-planner/` | architect | yes | manifest-plan.yaml |
| e2e-platform-architect | skill | `.cursor/skills/e2e-platform-architect/` | architect | yes | architecture-delta.md |
| e2e-selector-healer | skill | `.cursor/skills/e2e-selector-healer/` | generalPurpose | yes | healing-plan.md |
| e2e-docs-guardian | skill | `.cursor/skills/e2e-docs-guardian/` | generalPurpose | yes | docs-checklist.md |
| e2e-implementer | skill | `.cursor/skills/e2e-implementer/` | implementer | no | implementation-notes.md, preflight-report.json |
| e2e-docs-writer | skill | `.cursor/skills/e2e-docs-writer/` | documenter | no | implementation-notes.md |
| e2e-test-runner | skill | `.cursor/skills/e2e-test-runner/` | test-runner | no | gates-report.json |
| e2e-code-reviewer | skill | `.cursor/skills/e2e-code-reviewer/` | bugbot | yes | review-report.json |
| e2e-security-auditor | skill | `.cursor/skills/e2e-security-auditor/` | security-review | yes | security-report.json |
| e2e-release-judge | skill | `.cursor/skills/e2e-release-judge/` | verifier | yes | release-verdict.json |

## Global agents (`~/.cursor/agents/`)

| agent_id | kind | path | subagent_type | readonly | artifact(s) |
|----------|------|------|---------------|----------|-------------|
| triage | agent | `~/.cursor/agents/triage.md` | triage | yes | (HANDOFF_JSON only) |
| guardian | agent | `~/.cursor/agents/guardian.md` | guardian | yes | review.md, context.md |
| architect | agent | `~/.cursor/agents/architect.md` | architect | yes | spec.md, tasks.md |
| implementer | agent | `~/.cursor/agents/implementer.md` | implementer | no | (superseded in e2eTester) |
| test-runner | agent | `~/.cursor/agents/test-runner.md` | test-runner | no | test-report.json |
| verifier | agent | `~/.cursor/agents/verifier.md` | verifier | yes | verify-report.md |
| security-reviewer | agent | `~/.cursor/agents/security-reviewer.md` | security-reviewer | yes | security-report.md |
| documenter | agent | `~/.cursor/agents/documenter.md` | documenter | no | implementation-notes.md |
| debugger | agent | `~/.cursor/agents/debugger.md` | debugger | no | (on-demand only) |

## QC agents (parallel fan-out after implementer)

Resolved by `resolve_graph.py` — not in sequential `agent_graph`.

| agent_id | When |
|----------|------|
| e2e-test-runner | always (except spike) |
| e2e-code-reviewer | always except docs_only |
| e2e-security-auditor | pii/otp/auth in risk_flags or new_system |
| dev-build-integrator | platform, new_system, new_module, step_fix, healing_patch |
| dev-security-auditor | auth/pii/input/deps/network in risk_flags (if e2e-security-auditor not already) |

## Ship agents (conditional)

| agent_id | When |
|----------|------|
| dev-pr-publisher | ship_requested AND ship_eligible AND release passed |
| dev-ci-watcher | after dev-pr-publisher |

## Task prompt injection

Each Task must include:

1. Agent id and skill/agent path from this registry
2. `Run directory: <run_dir absolute>` (artifacts_dir = run_dir)
3. `Workspace: <workspace absolute>`
4. Read/write artifact paths from [artifacts-contract.md](artifacts-contract.md)
5. For e2e agents: relevant [domain-context.md](domain-context.md) sections
6. `Readonly` and `Subagent type` from this registry
7. On retry: `feedback` from release-verdict or gate reports
