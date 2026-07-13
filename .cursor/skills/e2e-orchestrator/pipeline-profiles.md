# Pipeline Profiles

Each profile defines an ordered agent graph. Agent IDs map to project skills under `.cursor/skills/`.

| ID | Skill |
|----|-------|
| E01 | e2e-intake |
| E0R | e2e-researcher |
| E02 | e2e-domain-scout |
| E03 | e2e-scenario-analyst |
| E04 | e2e-manifest-planner |
| E05 | e2e-platform-architect |
| E06 | e2e-selector-healer |
| E07 | e2e-docs-guardian |
| E08 | e2e-implementer |
| E09 | e2e-release-judge |
| QC-T | e2e-test-runner |
| QC-R | e2e-code-reviewer |
| QC-S | e2e-security-auditor |
| DOC-W | e2e-docs-writer |

Quality Council = QC-T, QC-R, QC-S (conditional) — run in **parallel** after E08 preflight.

## Verification tiers (orchestrator)

| Tier | Script | When |
|------|--------|------|
| T0 Research | `run_research_gate.py` | After E0R (skip `docs_only`) |
| T1 Planning | `run_planning_gate.py` | After last planner, before E08 |
| T2 Preflight | `run_preflight_gates.py` | After E08 (implementer runs; manager re-verifies) |
| T3 Full CI | `run_gates.py --fail-fast` | QC phase |
| T3 Mechanical | `run_mechanical_verdict.py` | After QC, before E09 |

## step_fix

Selector/step failure, failed run artifact, `app/systems/*/steps/` changes.

```
E01 → E0R → E02 → E03 → E06 → [T1 planning gate] → E08 → [T2 preflight] → [QC-T, QC-R parallel] → [T3 mechanical] → E09
```

Add QC-S when `pii`/`otp`/`auth` in risk_flags.

## new_module

Add module to existing system (manifest + steps + scenario doc).

```
E01 → E0R → E03 → E04 → [T1] → E08 → E07 → [T2] → [QC parallel] → [T3 mechanical] → E09
```

## new_system

New `app/systems/{code}/` with manifest, executor, steps, scenario doc.

```
E01 → E0R → E02 → E05 → E04 → [T1] → E08 → E07 → [T2] → [QC-T, QC-R, QC-S] → [T3 mechanical] → E09
```

QC-S always on for new_system.

## platform

Orchestrator, API, dashboard, scheduling, healing UI — no live site step changes.

```
E01 → E0R → E02 → E05 → [T1] → E08 → [T2] → [QC parallel] → [T3 mechanical] → E09
```

## healing_patch

Self-healing pending patch approve/apply workflow.

```
E01 → E0R → E06 → [T1] → E08 → [T2] → [QC parallel] → [T3 mechanical] → E09
```

## docs_only

Scenario or architecture documentation sync only.

```
E01 → E07 → DOC-W → [T2 docs paths optional] → QC-T (docs gate only) → [T3 mechanical] → E09
```

No E0R (research skipped).

## spike

Live site probe via `research/`, feasibility exploration.

```
E01 → E0R → (end — report to user; offer upgrade)
```

No implementer/QC unless user confirms upgrade to `step_fix` or `new_module`.

## Profile selection (Intake guidance)

| Signal | Profile |
|--------|---------|
| broken selector, step exception, failed module screenshot | step_fix |
| add/reorder module in existing system | new_module |
| new system code under `app/systems/` | new_system |
| RunService, gateway, API routes, web UI, scheduling | platform |
| healing patch approve/reject/apply | healing_patch |
| scenario doc, E2E_ARCHITECTURE, README sync only | docs_only |
| probe site, evaluate selectors in research/ | spike |

## Conditional QC rules

| Condition | Insert |
|-----------|--------|
| `risk_flags` contains `pii`, `otp`, or `auth` | QC-S |
| `new_system` profile | QC-S |
| `touch_surfaces` contains `api` and user-facing change | QC-R required |
| `docs_only` | QC-T docs_consistency only |

## Agent graph in intake.json

Intake must emit `agent_graph` as ordered list of skill names (exclude E01, E0R, and QC agents). Manager runs E0R after intake, then loops `agent_graph`, expands QC after E08 preflight, and runs mechanical verdict before E09.
