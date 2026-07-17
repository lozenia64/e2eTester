# Orchestration runtime

Two complementary orchestration modes:

| Mode | Entry | State dir |
|------|-------|-----------|
| **Orca plan-build-verify loop** (Claude Code plans + final gate, Cursor implements, Grok strictly verifies) | `/orchestration <goal>` | `.cursor/orchestration/loops/{loop_id}/` |
| **e2e-orchestrator** (full multi-agent pipeline) | `e2e-orchestrator 실행: <request>` | `.cursor/orchestration/runs/{run_id}/` |

- **Skills:** `.cursor/skills/orca-plan-build-verify-loop/` · `.cursor/skills/e2e-orchestrator/` + `~/.cursor/skills/dev-*` + `~/.cursor/agents/`
- **Orca loop config:** `.cursor/orchestration/plan-build-verify-loop.config.json`

## Orca plan-build-verify loop (interactive)

Requires Orca runtime + Claude Code, Cursor, and Grok terminals in the same worktree.

```
/orchestration <your development goal>
```

See [orca-plan-build-verify-loop/SKILL.md](../skills/orca-plan-build-verify-loop/SKILL.md).

## e2e-orchestrator (full pipeline)

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
