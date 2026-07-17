---
name: orca-plan-build-verify-loop
description: >-
  Orca orchestration plan→build→verify loop across three terminals in the same
  worktree: Claude Code plans and holds the final verification gate, Cursor
  implements, Grok is the strict verifier that also coordinates the inner
  Cursor↔Grok fix loop. Use when the user asks for a 3-terminal orchestration
  loop across Claude Code / Cursor / Grok, or "plan-build-verify loop".
---

# Orca Plan-Build-Verify Loop (Claude Code / Cursor / Grok)

Three-way supervised loop in one worktree:

```
User → Claude Code: writes a detailed plan → dispatches to Cursor
Cursor: implements per plan → dispatches verify task to Grok
Grok: strictly verifies against the plan
  FAIL → dispatches fix task back to Cursor (repeat, same task-pair loop)
  PASS → dispatches a final-gate task to Claude Code
Claude Code: strictly re-verifies against its own plan (does not trust Grok's PASS)
  PASS → worker_done to Grok → loop ends, report to user
  FAIL → escalation to Grok (this IS "지시 to escalate verification")
Grok: on escalation from Claude Code → re-dispatches fix to Cursor, loop again,
  then re-requests Claude Code once Cursor↔Grok round passes again
```

Requires Orca runtime (`orca status --json` → `reachable: true`) and three
terminals in the **same worktree**: this Claude Code session, a Cursor Agent
tab, and a Grok CLI tab.

## Preconditions

```bash
orca status --json
python3 .cursor/skills/orca-plan-build-verify-loop/scripts/resolve_terminals.py --workspace "<abs workspace>"
```

Resolve must return `ok: true` with `claude`, `cursor`, `grok` handles. Handles
are session-specific and change after an app/terminal restart — always
re-resolve (or pass explicit `--claude-handle/--cursor-handle/--grok-handle`)
at the start of a new loop rather than reusing an old `loop.json`'s handles.

Config: `.cursor/orchestration/plan-build-verify-loop.config.json`
(title/preview match patterns per role, iteration caps, wait timeout, gates
command). Tune the `*_preview_patterns` if auto-resolution picks the wrong
terminal — verify with `orca terminal list --json` before trusting it, since a
misrouted dispatch lands in someone else's live terminal.

## Claude Code role (this agent) — plan + final gate

1. Analyze the user's requirement and write a detailed, unambiguous plan as a
   checklist (acceptance criteria Grok and you yourself can verify against
   code, not vibes). Save it to a scratch file, e.g.
   `<scratchpad>/plan.md`.
2. Init the loop and dispatch to Cursor:
   ```bash
   python3 .cursor/skills/orca-plan-build-verify-loop/scripts/init_loop.py \
     "<workspace>" "<user request summary>" --plan-file "<path to plan.md>"
   python3 .cursor/skills/orca-plan-build-verify-loop/scripts/dispatch_next.py \
     --loop-dir "<loop_dir>" --to cursor
   ```
   This is a real dispatch into Cursor's live terminal — confirm the resolved
   handles with the user before running it for the first time in a session.
3. End your turn. You are re-invoked automatically **later, in this same
   terminal**, when Grok dispatches the final-gate task to you (per
   `claude-final-verify-brief.md`, embedded in the injected task spec). Follow
   that brief exactly: verify independently, then `worker_done` (PASS) or
   `escalation` (FAIL) to Grok — never trust Grok's PASS claim without
   checking the diff yourself.
4. If `claude_gate_iteration` reaches `max_claude_gate_iterations` without a
   clean PASS, stop escalating and report the blocker to the user directly
   instead of looping forever.

## Cursor role — implementer

Dispatched automatically via `--inject` with `cursor-implement-brief.md`.
Implements the plan (or the latest fix feedback), then coordinates its own
verify request to Grok and loops on FAIL, per the brief. Never edits Grok's or
Claude Code's verification output.

## Grok role — strict verifier + inner-loop coordinator

Dispatched automatically via `--inject` with `grok-verify-brief.md` (from
Cursor) — verifies strictly against the plan, `worker_done` PASS/FAIL to
Cursor, and on PASS additionally dispatches the final-gate task to Claude
Code. On receiving an `escalation` back from Claude Code, re-dispatches a fix
task to Cursor with that feedback and restarts the inner loop.

## Coordinator/worker rules (apply to whichever agent is acting)

- `worker_done` is sent **exactly once** per received dispatch, even on FAIL —
  use the subject (`PASS: ...` / `FAIL: ...`) to carry the verdict for
  ordinary loop iterations.
- `escalation` is reserved for the Claude Code → Grok hop only (final-gate
  FAIL): that is the one point in this design where a worker asks its
  coordinator to actively redirect other agents, matching Orca's "coordinator
  must intervene" semantics.
- Never skip Grok's verification for product code changes, and never skip
  Claude Code's final gate — Grok's PASS alone does not end the loop.
- Respect the iteration caps in the config; on exhaustion, stop and report to
  the user instead of looping indefinitely.
- Read `{loop_dir}/loop.json` (`history`, `phase`, iteration counters) before
  acting if you are picking this loop up cold — it is the shared source of
  truth across all three terminals.

## Artifacts

| Path | Owner |
|------|-------|
| `.cursor/orchestration/loops/{loop_id}/loop.json` | All three, via the scripts |
| `.cursor/orchestration/loops/{loop_id}/plan.md` | Claude Code (immutable copy of the plan) |
| `.cursor/orchestration/loops/{loop_id}/trace.log` | All three (append-only) |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `resolve_terminals.py` picks the wrong terminal | Pass explicit `--claude-handle/--cursor-handle/--grok-handle`, or tune `*_preview_patterns` in the config |
| `max iterations ... exceeded` from `dispatch_next.py` | Loop is stuck — read `trace.log`/`loop.json` history and report to the user instead of raising the cap blindly |
| `timed_out` from `wait_result.py` | Target terminal busy — `orca terminal read --terminal <handle> --json`; re-run wait or increase `--timeout-ms` |
| Orca not reachable | Start the Orca app; `orca status --json` |

## Entry phrases

- `/orchestration <goal>` (3자 plan-build-verify)
- `Claude Code 계획 + Cursor 구현 + Grok 검증 루프: <goal>`
- `orca plan-build-verify loop: <goal>`
