# Orchestration runtime

Unified e2e-orchestrator v2 run state (wraps dev-orchestrator phases + e2e domain skills + global agents).

- **Runs:** `.cursor/orchestration/runs/{run_id}/` (gitignored)
- **Skills:** `.cursor/skills/e2e-orchestrator/` + `~/.cursor/skills/dev-*` + `~/.cursor/agents/`

## Invoke (sole entry point)

```
e2e-orchestrator 실행: <your request>
```

## Run directory layout

After intake:

```bash
python3 .cursor/skills/e2e-orchestrator/scripts/resolve_graph.py --run-dir "<run_dir>"
```

See [artifacts-contract.md](../skills/e2e-orchestrator/artifacts-contract.md) and [unified-registry.md](../skills/e2e-orchestrator/unified-registry.md).

## Ship phase

PR/CI (`dev-pr-publisher`, `dev-ci-watcher`) runs only when `ship_requested: true` in intake and profile is ship-eligible.
