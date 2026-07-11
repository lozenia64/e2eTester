# Pipeline Profiles

Each profile defines an ordered agent graph. Agent IDs map to project skills under `.cursor/skills/`.

| ID | Skill |
|----|-------|
| E01 | e2e-intake |
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

Quality Council = QC-T, QC-R, QC-S (conditional) — run in **parallel** after E08.

## step_fix

Selector/step failure, failed run artifact, `app/systems/*/steps/` changes.

```
E01 → E02 → E03 → E06 → E08 → [QC-T, QC-R parallel] → E09
```

Add QC-S when `pii`/`otp`/`auth` in risk_flags.

## new_module

Add module to existing system (manifest + steps + scenario doc).

```
E01 → E03 → E04 → E08 → E07 → [QC parallel] → E09
```

## new_system

New `app/systems/{code}/` with manifest, executor, steps, scenario doc.

```
E01 → E02 → E05 → E04 → E08 → E07 → [QC-T, QC-R, QC-S] → E09
```

QC-S always on for new_system.

## platform

Orchestrator, API, dashboard, scheduling, healing UI — no live site step changes.

```
E01 → E02 → E05 → E08 → [QC parallel] → E09
```

## healing_patch

Self-healing pending patch approve/apply workflow.

```
E01 → E06 → E08 → [QC parallel] → E09
```

## docs_only

Scenario or architecture documentation sync only.

```
E01 → E07 → DOC-W → QC-T (docs gate only) → E09
```

## spike

Live site probe via `research/`, feasibility exploration.

```
E01 → E03 → (end — report to user; offer upgrade)
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

Intake must emit `agent_graph` as ordered list of skill names (e.g. `["e2e-intake", "e2e-domain-scout", ...]`). Manager skips E01 in the loop (already run) and expands QC as parallel Tasks after E08.
