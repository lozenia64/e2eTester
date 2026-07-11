# e2e Orchestrator Smoke Test

Dry-run validation for the `step_fix` profile artifact chain.

## Run

```bash
# 1. Init
python3 .cursor/skills/e2e-orchestrator/scripts/init_run.py \
  "$(pwd)" "HOM login 스텝 셀렉터 수정"

# 2. Use run_dir from JSON output, then validate sample artifacts:
RUN_DIR=".cursor/orchestration/runs/<run_id>"

# 3. After placing sample artifacts (see scripts/smoke_fixtures.py), validate each agent:
python3 .cursor/skills/e2e-orchestrator/scripts/validate_artifacts.py --run-dir "$RUN_DIR" --agent e2e-intake
# ... repeat for each agent in step_fix graph
```

Or run the automated fixture script:

```bash
python3 .cursor/skills/e2e-orchestrator/scripts/smoke_fixtures.py "$(pwd)"
```

Expected: all validations return `"valid": true`.
