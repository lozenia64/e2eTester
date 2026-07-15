# Unified Pipeline Profiles

Composes e2e domain profiles with dev-orchestrator phases.
Graph order is built mechanically by `resolve_graph.py` — do not hand-edit `agent_graph`.

## Profile matrix

### step_fix

```yaml
dev_profile: hotfix
dev_graph: [dev-context-scout]
e2e_graph: [e2e-domain-scout, e2e-scenario-analyst, e2e-selector-healer]
guardian: true
qc: [e2e-test-runner, e2e-code-reviewer, dev-build-integrator]
qc_conditional:
  e2e-security-auditor: pii|otp|auth in risk_flags
  dev-security-auditor: auth|pii|input_validation in risk_flags
ship_eligible: true
skip_research: false
last_planner: e2e-selector-healer
```

### new_module

```yaml
dev_profile: feature
dev_graph: [dev-spec-writer, dev-context-scout, dev-architect, dev-task-planner]
e2e_graph: [e2e-scenario-analyst, e2e-manifest-planner, e2e-docs-guardian]
guardian: true
qc: [e2e-test-runner, e2e-code-reviewer, dev-build-integrator]
qc_conditional:
  dev-ux-designer: user_facing in risk_flags
  e2e-security-auditor: pii|otp|auth in risk_flags
  dev-security-auditor: auth|pii|input_validation in risk_flags
ship_eligible: true
skip_research: false
last_planner: e2e-docs-guardian
```

### new_system

```yaml
dev_profile: feature
dev_graph: [dev-spec-writer, dev-context-scout, dev-architect, dev-task-planner]
e2e_graph: [e2e-domain-scout, e2e-platform-architect, e2e-manifest-planner, e2e-docs-guardian]
guardian: true
qc: [e2e-test-runner, e2e-code-reviewer, e2e-security-auditor, dev-build-integrator]
qc_conditional:
  dev-ux-designer: user_facing in risk_flags
  dev-security-auditor: auth|pii|input_validation in risk_flags
ship_eligible: true
skip_research: false
last_planner: e2e-docs-guardian
```

### platform

```yaml
dev_profile: feature
dev_graph: [dev-spec-writer, dev-context-scout, dev-architect, dev-task-planner]
e2e_graph: [e2e-domain-scout, e2e-platform-architect]
guardian: true
qc: [e2e-test-runner, e2e-code-reviewer, dev-build-integrator]
qc_conditional:
  dev-ux-designer: user_facing in risk_flags
  e2e-security-auditor: pii|otp|auth in risk_flags
  dev-security-auditor: auth|pii|input_validation in risk_flags
ship_eligible: true
skip_research: false
last_planner: e2e-platform-architect
```

### healing_patch

```yaml
dev_profile: hotfix
dev_graph: [dev-context-scout]
e2e_graph: [e2e-selector-healer]
guardian: true
qc: [e2e-test-runner, e2e-code-reviewer, dev-build-integrator]
qc_conditional:
  e2e-security-auditor: pii|otp|auth in risk_flags
ship_eligible: true
skip_research: false
last_planner: e2e-selector-healer
```

### docs_only

```yaml
dev_profile: docs
dev_graph: []
e2e_graph: [e2e-docs-guardian, e2e-docs-writer]
guardian: false
qc: [e2e-test-runner]
qc_conditional: {}
ship_eligible: false
skip_research: true
last_planner: e2e-docs-guardian
implementer: e2e-docs-writer
```

### spike

```yaml
dev_profile: spike
dev_graph: []
e2e_graph: []
guardian: false
qc: []
qc_conditional: {}
ship_eligible: false
skip_research: false
stop_after_research: true
```

## Conditional insertion rules

| Condition | Insert into graph |
|-----------|-------------------|
| `dev_path` == `minimal` | `triage` at start |
| `unknown_tech` in risk_flags | `dev-researcher` after dev-context-scout |
| `user_facing` in risk_flags | `dev-ux-designer` after dev-task-planner |
| `conditional_agents` contains agent id | that agent in appropriate phase |
| `ship_requested` + `ship_eligible` | ship phase after release judge |

## Verification tiers

| Tier | Script | When |
|------|--------|------|
| T0 Research | `run_research_gate.py` | After e2e-researcher (skip docs_only, spike ends early) |
| T1 Planning | `run_planning_gate.py` | After last_planner, before guardian/implementer |
| T2 Preflight | `run_preflight_gates.py` | After e2e-implementer (or e2e-docs-writer) |
| T3 Full CI | `run_gates.py --fail-fast` | QC phase |
| T3 Mechanical | `run_mechanical_verdict.py` | After QC, before e2e-release-judge |

## Profile selection (intake guidance)

| Signal | e2e_pipeline_profile |
|--------|----------------------|
| broken selector, step exception | step_fix |
| add module to existing system | new_module |
| new system under app/systems/ | new_system |
| API, dashboard, RunService, scheduling | platform |
| healing patch workflow | healing_patch |
| scenario doc, README sync only | docs_only |
| probe, feasibility | spike |
