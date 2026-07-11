# Orchestration runtime

This directory holds **ephemeral** e2e-orchestrator run state.

- **Runs:** `.cursor/orchestration/runs/{run_id}/` (gitignored)
- **Skills:** `.cursor/skills/e2e-orchestrator/` and specialist skills (committed)

## Run directory layout

See [artifacts-contract.md](../skills/e2e-orchestrator/artifacts-contract.md).

## Invoke

In Cursor chat:

```
e2e-orchestrator 실행: <your request>
```
