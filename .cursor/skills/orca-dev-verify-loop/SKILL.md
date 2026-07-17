---
name: orca-dev-verify-loop
description: >-
  Orca orchestration dev-verify loop for e2eTester. Cursor Agent develops;
  adjacent Claude Code terminal verifies via orca orchestration task-create +
  dispatch --inject + worker_done. Use when the user asks for /orchestration,
  orca dev-verify loop, or Cursor+Claude Code supervised loop in the same worktree.
---

# Orca Dev-Verify Loop

**Cursor (coordinator/developer)** implements → **Claude Code (verifier)** independently checks → loop until PASS or max iterations.

Requires Orca runtime (`orca status --json` → `reachable: true`) and a **Claude Code** terminal in the same worktree.

## Preconditions

```bash
orca status --json
python3 .cursor/skills/orca-dev-verify-loop/scripts/resolve_terminals.py --workspace "<abs workspace>"
```

Resolve must return `ok: true` with `verifier` (Claude Code) and `coordinator` handles.

Config: `.cursor/orchestration/orca-loop.config.json`

## Coordinator loop (Cursor Agent)

```
1. init_loop
2. DEVELOP — implement user goal; keep scope minimal
3. dispatch_verify
4. wait_worker (rolling --timeout-ms from config; default 15m)
5. IF PASS → summarize and STOP
6. IF FAIL → read loop_dir/verify-report.json (+ gates-output.txt); fix; goto 3 if iterations remain
7. IF timeout/escalation → report blocker; ask user
```

### Commands

```bash
# 1. Init
python3 .cursor/skills/orca-dev-verify-loop/scripts/init_loop.py "<workspace>" "<user request>"

# 2. After implementing, dispatch verify (repeat after fixes)
python3 .cursor/skills/orca-dev-verify-loop/scripts/dispatch_verify.py --loop-dir "<loop_dir>"

# 3. Wait for Claude Code worker_done
python3 .cursor/skills/orca-dev-verify-loop/scripts/wait_worker.py --loop-dir "<loop_dir>"
```

Optional overrides:

```bash
python3 .cursor/skills/orca-dev-verify-loop/scripts/dispatch_verify.py \
  --loop-dir "<loop_dir>" --coordinator "<handle>" --verifier "<handle>"
python3 .cursor/skills/orca-dev-verify-loop/scripts/wait_worker.py \
  --loop-dir "<loop_dir>" --timeout-ms 1200000
```

Dry-run preamble (no inject):

```bash
python3 .cursor/skills/orca-dev-verify-loop/scripts/dispatch_verify.py --loop-dir "<loop_dir>" --dry-run
```

## Coordinator rules

- **Never** skip verify for product code changes.
- **Never** edit `verify-report.json` — verifier owns it.
- On FAIL, fix only what the report cites; re-dispatch verify (do not re-init unless goal changed).
- Use `orca orchestration check --peek --json` only for debugging; primary wait is `wait_worker.py`.
- Max iterations: `loop.json.max_iterations` (default 3). Do not exceed.
- Korean summaries for the user.

## Verifier role (Claude Code)

Dispatched automatically via `--inject`. Brief template: [verifier-brief.md](verifier-brief.md).

Verifier must:

1. Run `{gates_command}` from config (default full CI gates).
2. Write `<loop_dir>/verify-report.json` with `gate_decision: PASS|FAIL`.
3. Send exactly one `worker_done` with `reportPath` pointing to that file.

Verifier is **readonly** for product code.

## Artifacts

| Path | Owner |
|------|-------|
| `.cursor/orchestration/loops/{loop_id}/loop.json` | Coordinator scripts |
| `verify-report.json` / `verify-report.md` | Verifier |
| `gates-output.txt` | Verifier |
| `trace.log` | Both |

## vs e2e-orchestrator

| | orca-dev-verify-loop | e2e-orchestrator |
|--|---------------------|------------------|
| Developer | Cursor (this agent) | Task subagents |
| Verifier | Claude Code (Orca terminal) | Task subagents |
| Transport | `orca orchestration` | Cursor Task tool |
| Scope | Same-worktree fast loop | Full pipeline + ship |

Use **orca-dev-verify-loop** for interactive Cursor+Claude side-by-side work. Use **e2e-orchestrator** for unattended multi-agent pipelines.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `no terminal matching verifier pattern` | Open Claude Code tab; or set `verifier_terminal_title_pattern` in config |
| `timed_out` | Claude busy — `orca terminal read --terminal <verifier> --json`; re-dispatch or increase `wait_timeout_ms` |
| `verify_unknown` | Verifier sent worker_done without report — re-dispatch with clearer FAIL/PASS subject |
| Orca not reachable | Start Orca app; `orca status --json` |

## Entry phrases

- `/orchestration <goal>`
- `orca dev-verify loop: <goal>`
- `Cursor 개발 + Claude Code 검증 루프: <goal>`
