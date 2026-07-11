---
name: e2e-manifest-planner
description: >-
  Plans manifest.yaml module changes for e2eTester. Used by e2e-orchestrator
  for new_module and new_system profiles.
disable-model-invocation: true
---

# e2e Manifest Planner (E04)

Readonly planning. **Do not edit manifest.yaml yet.**

## Inputs

- `<run_dir>/intake.json`
- `<run_dir>/scenario-impact.md`
- `app/systems/{system_code}/manifest.yaml`
- `app/systems/{code}/executor.py` (step registry)

## Task

1. Plan module add/modify/reorder actions.
2. Ensure `depends_on` order is acyclic and matches execution intent.
3. Map each module to `workflow_step` registered in executor's `build_step_registry()`.
4. Set `requires_user_input: true` only for legitimate OTP/human-input pauses.
5. Propose reasonable `timeout_seconds` per module.

## Output

Write `<run_dir>/manifest-plan.yaml` per [artifacts-contract.md](../e2e-orchestrator/artifacts-contract.md).
