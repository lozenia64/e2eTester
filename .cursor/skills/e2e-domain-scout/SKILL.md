---
name: e2e-domain-scout
description: >-
  Maps e2eTester requests to architecture layers and relevant files. Used by
  e2e-orchestrator after intake.
disable-model-invocation: true
---

# e2e Domain Scout (E02)

Readonly exploration. Use `explore` thoroughness: **medium**.

## Inputs

- `<run_dir>/intake.json`
- `E2E_ARCHITECTURE.md`, `CLAUDE.md`
- `.cursor/skills/e2e-orchestrator/domain-context.md`

## Task

1. Identify files directly related to the request (steps, manifest, executor, orchestrator, api, etc.).
2. Map each file to an architecture layer.
3. Note existing patterns (registry dispatch, Depends injection, channel profiles).
4. Flag cross-cutting concerns (HOM/MHM shared scenario, gateway thread boundary).

## Output

Write `<run_dir>/context-map.md` with sections:

- `## 관련 파일`
- `## 계층`
- `## 패턴`

Do not propose code changes.
