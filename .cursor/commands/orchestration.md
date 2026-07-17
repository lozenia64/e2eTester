# /orchestration

Activate the **Orca plan-build-verify loop**: Claude Code plans and holds the
final verification gate, this Cursor Agent implements, and the adjacent Grok
terminal is the strict verifier that also coordinates the Cursor↔Grok fix
loop — all via `orca orchestration`.

## Instructions

1. Read and follow `.cursor/skills/orca-plan-build-verify-loop/SKILL.md`
   completely.
2. Confirm Orca is reachable: `orca status --json`
3. Resolve terminals: `python3 .cursor/skills/orca-plan-build-verify-loop/scripts/resolve_terminals.py --workspace "<workspace>"`
4. **The loop is normally started from Claude Code**, not from here: the user
   states the goal to Claude Code, which writes the plan and dispatches the
   first implementation task to this Cursor terminal via `init_loop.py` +
   `dispatch_next.py --to cursor`.
5. If this command is invoked directly in Cursor (no live dispatch preamble
   present), treat the user's message after this command as the development
   goal, but first check with the user whether Claude Code should author the
   plan (recommended) before any implementation starts — Grok and Claude
   Code's final gate both verify against that plan, so skipping it breaks the
   loop's acceptance criteria.
6. When acting as the implementer under a live dispatch, follow
   `cursor-implement-brief.md` exactly: implement → `dispatch_next.py --to
   grok` → `wait_result.py` → fix on FAIL and repeat, until PASS or max
   iterations.
7. Persist state under `.cursor/orchestration/loops/{loop_id}/`.

If no goal follows this command and no plan exists yet, ask the user what to
build and who should write the plan.

Do **not** use `e2e-orchestrator` for this command unless the user explicitly
asks for the full multi-agent pipeline instead.
