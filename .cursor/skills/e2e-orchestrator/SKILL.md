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
Task(e2e-intake) → validate → merge intake.json into run.json
FOR each agent in agent_graph (sequential except QC):
  IF agent in QualityCouncil: skip (handle after e2e-implementer)
  Task(agent skill) → validate_artifacts.py --run-dir --agent
  append_handoff.py on each transition
ON e2e-implementer done (or docs-writer for docs_only):
  python3 run_gates.py --run-dir
  PARALLEL Task for each active QC agent
  validate each QC report
Task(e2e-release-judge) → validate release-verdict.json
IF passed: status=complete, summarize to user
ELSE: backtrack per handoff-matrix.md
```

**Spike profile:** after `e2e-scenario-analyst`, stop and report to user. Offer upgrade to `step_fix` or `new_module`.

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
Feedback (if retry): <from release-verdict.json>
Readonly: <yes/no per subagent-map.md>
Subagent type: <per subagent-map.md>
Do NOT modify built-in subagent definitions — follow this skill contract only.
```

Launch **multiple Task calls in one message** for Quality Council parallel fan-out.

## Quality Council

After `e2e-implementer` (or `e2e-docs-writer` for docs_only):

| Agent | When active |
|-------|-------------|
| e2e-test-runner | always (runs `run_gates.py` first, then validates) |
| e2e-code-reviewer | always except docs_only |
| e2e-security-auditor | `conditional_agents` contains `security-auditor` OR risk_flags has `pii`/`otp`/`auth` |

QC agents map to built-in subagents per [subagent-map.md](subagent-map.md).

## Validation

After each agent:

```bash
python3 .cursor/skills/e2e-orchestrator/scripts/validate_artifacts.py --run-dir "<run_dir>" --agent "<skill-name>"
```

Record handoffs:

```bash
python3 .cursor/skills/e2e-orchestrator/scripts/append_handoff.py --run-dir "<run_dir>" --from-agent "<prev>" --to-agent "<next>" --reason "<why>"
```

Retry same agent once on invalid artifact; then abort with errors.

## Backtrack

On `release-verdict.json` `passed: false` or `gates-report.json` `passed: false`:

1. Load `failed_agent` from verdict (or infer from gate name).
2. Map restart via [handoff-matrix.md](handoff-matrix.md).
3. Increment `attempts[failed_agent]` in `run.json`; abort if over limits.
4. Rerun from restart agent through graph (include QC after implementer).

## Limits

- `max_retries_per_agent`: 2
- `max_total_iterations`: 10

## Human-in-the-loop

Use `AskQuestion` when:

- spike profile completes (upgrade to step_fix/new_module?)
- `live_site_claim` in risk_flags (confirm test claim submission)
- healing_patch profile with pending patch approval

## Final report

Include: `run_id`, `pipeline_profile`, `system_code`, gate results, retry count, path to `run_dir`.
