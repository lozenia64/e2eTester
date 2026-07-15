---
name: e2e-orchestrator
description: >-
  Sole entry point for e2eTester multi-agent orchestration. Wraps dev-orchestrator
  phases plus e2e domain skills and global ~/.cursor/agents. Use when the user
  asks to run e2e-orchestrator or automate E2E platform work in this repository.
---

# e2e Orchestrator (Unified Wrapper)

Manager agent for **e2eTester**. **Wraps dev-orchestrator phases** and owns the full loop.

**Do not write application code or intake.json** — delegate via `Task` per [unified-registry.md](unified-registry.md).

## Start

1. Resolve workspace root (absolute path to e2eTester).
2. Run init:
   ```bash
   python3 .cursor/skills/e2e-orchestrator/scripts/init_run.py "<workspace>" "<user_request>"
   ```
3. Parse JSON output → `run_id`, `run_dir`.
4. Read [unified-registry.md](unified-registry.md), [unified-profiles.md](unified-profiles.md), [handoff-matrix.md](handoff-matrix.md), [domain-context.md](domain-context.md).

## Manager rules (mandatory)

- **Never** write `intake.json` or implementation code yourself — always `Task(e2e-intake)` then `Task(e2e-implementer)`.
- **Never** hand-build or shorten `agent_graph` — only `resolve_graph.py` output.
- **Never** skip guardian when graph includes it.
- Parse subagent output; run `validate_artifacts.py` after every agent.

## Execution loop

```
init_run.py
Task(e2e-intake) → validate_artifacts --agent e2e-intake
resolve_graph.py --run-dir → updates run.json.agent_graph, qc_agents, ship_agents
IF stop_after_research (spike): report and offer upgrade → STOP
IF NOT skip_research: Task(e2e-researcher) → validate → run_research_gate.py
FOR each agent in run.json.agent_graph:
  IF agent == guardian:
    Task(guardian) → validate_artifacts --agent guardian
    IF review.md REJECTED: backtrack per handoff-matrix
  ELSE:
    Task(agent per unified-registry) → validate_artifacts --agent <id>
  IF agent == run.json.last_planner: run_planning_gate.py
IF implementer == e2e-implementer:
  Task(e2e-implementer) → validate → run_preflight_gates.py
ELIF implementer == e2e-docs-writer:
  Task(e2e-docs-writer) → validate
PARALLEL Task for each agent in run.json.qc_agents → validate each
run_gates.py --fail-fast → run_mechanical_verdict.py
Task(e2e-release-judge) → validate
IF release passed AND ship_agents non-empty:
  Task(dev-pr-publisher) → validate
  Task(dev-ci-watcher) → validate → backtrack on CI fail
IF passed: status=complete, summarize
ELSE: backtrack per handoff-matrix.md
```

**Spike profile:** after research gate, stop and report. Offer upgrade to `step_fix` or `new_module`.

Launch **multiple Task calls in one message** for QC parallel fan-out.

## Task invocation template

```
Run skill/agent: <agent_id from unified-registry>
Run directory: <run_dir absolute>   # artifacts_dir = run_dir
Workspace: <workspace absolute>
User request: <from run.json>
Context variables: <run.json context_variables>
Inputs: <artifact paths from artifacts-contract.md>
Output: write <artifact> per artifacts-contract.md
Domain context: read domain-context.md (e2e agents)
Feedback (if retry): <from release-verdict.json or gate reports>
Readonly: <per unified-registry>
Subagent type: <per unified-registry>
Load handoff-protocol skill for HANDOFF_JSON footer.
```

## Quality Council

QC agents come from `run.json.qc_agents` (resolved by `resolve_graph.py`). Always includes e2e-test-runner except spike. e2e-code-reviewer except docs_only. Security auditors when risk_flags warrant.

After QC: `run_mechanical_verdict.py` must pass before `e2e-release-judge`.

## Ship phase (conditional)

Only when `run.json.ship_agents` is non-empty (`ship_requested` + `ship_eligible` profile).

## Validation

After each agent:

```bash
python3 .cursor/skills/e2e-orchestrator/scripts/validate_artifacts.py --run-dir "<run_dir>" --agent "<agent-id>"
```

After intake:

```bash
python3 .cursor/skills/e2e-orchestrator/scripts/resolve_graph.py --run-dir "<run_dir>"
```

Gate scripts:

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

## Backtrack

On any gate, mechanical-verdict, release-verdict, or guardian REJECTED failure — see [handoff-matrix.md](handoff-matrix.md).

Re-run `resolve_graph.py` only if intake.json profile changes.

## Limits

- `max_retries_per_agent`: 2
- `max_total_iterations`: 10

## Human-in-the-loop

Use `AskQuestion` when:

- spike completes (upgrade profile?)
- `live_site_claim` in risk_flags
- healing_patch with pending patch approval
- guardian REJECTED twice

## Final report

Include: `run_id`, `e2e_pipeline_profile`, `dev_pipeline_profile`, T0–T3 gates, QC agents, ship status, retry count, `run_dir` path.
