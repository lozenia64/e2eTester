# e2e Orchestrator Smoke Test

Dry-run validation for the `step_fix` profile artifact chain (includes T0–T3 gate reports).

## Run

```bash
python3 .cursor/skills/e2e-orchestrator/scripts/smoke_fixtures.py "$(pwd)"
```

Expected: all agent validations return `"valid": true`.

## Gate scripts (manual)

```bash
RUN_DIR=".cursor/orchestration/runs/<run_id>"

python3 .cursor/skills/e2e-orchestrator/scripts/run_research_gate.py --run-dir "$RUN_DIR"
python3 .cursor/skills/e2e-orchestrator/scripts/run_planning_gate.py --run-dir "$RUN_DIR"
python3 .cursor/skills/e2e-orchestrator/scripts/run_preflight_gates.py --run-dir "$RUN_DIR"
python3 .cursor/skills/e2e-orchestrator/scripts/run_gates.py --run-dir "$RUN_DIR" --fail-fast
python3 .cursor/skills/e2e-orchestrator/scripts/run_mechanical_verdict.py --run-dir "$RUN_DIR"
```

## Unit tests

```bash
python3 -m pytest tests/test_orchestration_gates.py -q
```
