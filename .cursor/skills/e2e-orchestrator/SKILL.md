---
name: e2e-orchestrator
description: >-
  Runs the e2eTester project-specific multi-agent pipeline (intake, domain scout,
  scenario analysis, manifest planning, implementation, CI gates, release judge).
  Use when the user asks to run e2e-orchestrator or automate E2E platform work
  in this repository.
---

# e2e Orchestrator

Manager agent for the **e2eTester** project multi-agent pipeline. **Do not write application code** — delegate via `Task` to built-in subagents using e2e skill contracts.

This orchestrator is **project-local** (`.cursor/skills/`). It does not replace the global `dev-orchestrator`.

## Start

1. Resolve workspace root (absolute path to e2eTester).
2. Run init:
   ```bash
   python3 .cursor/skills/e2e-orchestrator/scripts/init_run.py "<workspace>" "<user_request>"
   ```
3. Parse JSON output → `run_id`, `run_dir`.
4. Read [pipeline-profiles.md](pipeline-profiles.md), [handoff-matrix.md](handoff-matrix.md), [subagent-map.md](subagent-map.md), [domain-context.md](domain-context.md).

## Execution loop

```
Task(e2e-intake) → validate → merge intake.json into run.json (pipeline_profile)
IF profile != docs_only:
  Task(e2e-researcher) → validate
  python3 run_research_gate.py --run-dir → fail → backtrack e2e-researcher
FOR each agent in agent_graph (skip E01, E0R; skip QC agents):
  Task(agent skill) → validate_artifacts.py --run-dir --agent
  append_handoff.py on each transition
  IF agent is last planner before e2e-implementer:
    python3 run_planning_gate.py --run-dir → fail → backtrack per handoff-matrix
Task(e2e-implementer) OR e2e-docs-writer (docs_only) → validate (incl. preflight-report)
python3 run_preflight_gates.py --run-dir → fail → backtrack e2e-implementer
python3 run_gates.py --run-dir --fail-fast
PARALLEL Task for each active QC agent → validate each QC report
python3 run_mechanical_verdict.py --run-dir → fail → backtrack (no E09)
Task(e2e-release-judge) → validate release-verdict.json
IF passed: status=complete, summarize to user
ELSE: backtrack per handoff-matrix.md
```

**Spike profile:** after `e2e-researcher` + research gate, stop and report to user. Offer upgrade to `step_fix` or `new_module`.

**Last planner before E08** (for T1 gate): profile-specific — see [pipeline-profiles.md](pipeline-profiles.md) and [handoff-matrix.md](handoff-matrix.md).

## Task invocation template

For each specialist:

```
Run skill: <e2e-skill-name>
Run directory: <run_dir absolute>
Workspace: <workspace absolute>
User request: <from run.json>
Context variables: <run.json context_variables + pipeline_profile>
Inputs: <list artifact paths this agent reads>
Output: write <artifact> per artifacts-contract.md
Domain context: read relevant sections from .cursor/skills/e2e-orchestrator/domain-context.md
Feedback (if retry): <from release-verdict.json or mechanical-verdict.json>
Readonly: <yes/no per subagent-map.md>
Subagent type: <per subagent-map.md>
Do NOT modify built-in subagent definitions — follow this skill contract only.
```

Launch **multiple Task calls in one message** for Quality Council parallel fan-out.

## Quality Council

After E08 preflight passes (or `e2e-docs-writer` for docs_only):

| Agent | When active |
|-------|-------------|
| e2e-test-runner | always — confirm preflight passed, then `run_gates.py --fail-fast` |
| e2e-code-reviewer | always except docs_only |
| e2e-security-auditor | `conditional_agents` contains `security-auditor` OR risk_flags has `pii`/`otp`/`auth` |

After QC: `run_mechanical_verdict.py` must pass before `e2e-release-judge`.

QC agents map to built-in subagents per [subagent-map.md](subagent-map.md).

## Validation

After each agent:

```bash
python3 .cursor/skills/e2e-orchestrator/scripts/validate_artifacts.py --run-dir "<run_dir>" --agent "<skill-name>"
```

Gate scripts (mechanical — manager runs these, not LLM judgment):

```bash
python3 .cursor/skills/e2e-orchestrator/scripts/run_research_gate.py --run-dir "<run_dir>"
python3 .cursor/skills/e2e-orchestrator/scripts/run_planning_gate.py --run-dir "<run_dir>"
python3 .cursor/skills/e2e-orchestrator/scripts/run_preflight_gates.py --run-dir "<run_dir>"
python3 .cursor/skills/e2e-orchestrator/scripts/run_gates.py --run-dir "<run_dir>" --fail-fast
python3 .cursor/skills/e2e-orchestrator/scripts/run_mechanical_verdict.py --run-dir "<run_dir>"
```

Record handoffs:

```bash
python3 .cursor/skills/e2e-orchestrator/scripts/append_handoff.py --run-dir "<run_dir>" --from-agent "<prev>" --to-agent "<next>" --reason "<why>"
```

Retry same agent once on invalid artifact; then abort with errors.

## Backtrack

On `release-verdict.json` `passed: false`, `mechanical-verdict.json` `passed: false`, or any gate report `passed: false`:

1. Load `failed_agent` from verdict/gate report (or infer from gate name).
2. Map restart via [handoff-matrix.md](handoff-matrix.md).
3. Increment `attempts[failed_agent]` and `gate_attempts` in `run.json`; abort if over limits.
4. Rerun from restart agent through graph (include all verification tiers after implementer).

## Limits

- `max_retries_per_agent`: 2
- `max_total_iterations`: 10

## Human-in-the-loop

Use `AskQuestion` when:

- spike profile completes (upgrade to step_fix/new_module?)
- `live_site_claim` in risk_flags (confirm test claim submission)
- healing_patch profile with pending patch approval

## Final report

Include: `run_id`, `pipeline_profile`, `system_code`, T0–T3 gate results, retry count, path to `run_dir`.
