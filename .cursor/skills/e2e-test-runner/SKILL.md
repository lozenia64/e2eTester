---
name: e2e-test-runner
description: >-
  Runs e2eTester CI gates for orchestration QC. Used by e2e-orchestrator
  Quality Council.
disable-model-invocation: true
---

# e2e Test Runner (QC-T)

Runs project CI gates after T2 preflight. May fix test failures only when explicitly in backtrack retry for implementer.

## Inputs

- `<run_dir>/run.json` → workspace, pipeline_profile
- `<run_dir>/preflight-report.json` (must have `"passed": true`)
- `.cursor/skills/e2e-orchestrator/scripts/run_gates.py`

## Task

1. Confirm `preflight-report.json` passed (or skipped for spike).
2. Execute:
   ```bash
   python3 .cursor/skills/e2e-orchestrator/scripts/run_gates.py --run-dir "<run_dir>" --fail-fast
   ```
3. If gates fail, copy structured `findings` from `gates-report.json` into notes.
4. Do not change production code unless this is a retry delegated from implementer backtrack.

## Output

- `gates-report.json` (written by script)
- Write `<run_dir>/test-report.json`:
  ```json
  {
    "passed": true,
    "commands": ["run_gates.py --fail-fast"],
    "notes": "",
    "failed_gates": [],
    "findings": []
  }
  ```
  Set `passed: false` and populate `failed_gates` / `findings` when any gate fails.
