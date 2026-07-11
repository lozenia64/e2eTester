---
name: e2e-test-runner
description: >-
  Runs e2eTester CI gates for orchestration QC. Used by e2e-orchestrator
  Quality Council.
disable-model-invocation: true
---

# e2e Test Runner (QC-T)

Runs project CI gates. May fix test failures only when explicitly in backtrack retry for implementer.

## Inputs

- `<run_dir>/run.json` → workspace, pipeline_profile
- `.cursor/skills/e2e-orchestrator/scripts/run_gates.py`

## Task

1. Execute:
   ```bash
   python3 .cursor/skills/e2e-orchestrator/scripts/run_gates.py --run-dir "<run_dir>"
   ```
2. If gates fail, capture which gate failed and stderr tail in notes.
3. Do not change production code unless this is a retry delegated from implementer backtrack.

## Output

- `gates-report.json` (written by script)
- Optionally `<run_dir>/test-report.json`:
  ```json
  {"passed": true, "commands": ["run_gates.py"], "notes": ""}
  ```
