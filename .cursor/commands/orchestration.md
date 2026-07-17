# /orchestration

Activate the **Orca dev-verify loop**: this Cursor Agent develops; the adjacent **Claude Code** terminal verifies via `orca orchestration`.

## Instructions

1. Read and follow `.cursor/skills/orca-dev-verify-loop/SKILL.md` completely.
2. Confirm Orca is reachable: `orca status --json`
3. Resolve terminals: `python3 .cursor/skills/orca-dev-verify-loop/scripts/resolve_terminals.py --workspace "<workspace>"`
4. Treat the user's message (after this command) as the **development goal**.
5. Run the coordinator loop: `init_loop` → develop → `dispatch_verify` → `wait_worker` → fix on FAIL until PASS or max iterations.
6. Persist state under `.cursor/orchestration/loops/{loop_id}/`.

If no goal follows this command, ask the user what to build.

Do **not** use `e2e-orchestrator` for this command unless the user explicitly asks for the full multi-agent pipeline instead.
