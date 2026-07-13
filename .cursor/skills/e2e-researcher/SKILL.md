---
name: e2e-researcher
description: >-
  Performs mandatory web deep research before e2eTester implementation planning.
  Used by e2e-orchestrator immediately after intake (E0R).
disable-model-invocation: true
---

# e2e Researcher (E0R)

Readonly web research agent. **Must use WebSearch and WebFetch** — local codebase exploration alone is insufficient.

## Subagent

`generalPurpose` (with WebSearch + WebFetch tools)

## Inputs

- `<run_dir>/intake.json` → pipeline_profile, system_code, layer, risk_flags
- `.cursor/skills/e2e-orchestrator/domain-context.md`
- Local SSOT docs (`CLAUDE.md`, `E2E_ARCHITECTURE.md`) for conflict resolution

## Task

1. Derive 3–5 research questions from intake (profile + layer + risk_flags).
2. Run **at least 3 WebSearch** queries on current best practices (2025–2026).
3. **WebFetch at least 2** authoritative URLs and cite them in the brief.
4. When web guidance conflicts with local SSOT, **local SSOT wins** — note the conflict in `## 불확실성 / 추가 확인 필요`.

### Topic hints by profile

| Profile / flag | Research focus |
|----------------|----------------|
| step_fix, selector_fragile | Playwright locator resilience, role/name/id priority, self-healing patterns |
| new_module, new_system | Manifest-driven E2E modules, OTP pause UX, depends_on ordering |
| platform | FastAPI CQRS/event-sourcing change patterns for the touched layer |
| healing_patch | AIOps closed-loop selector healing, confidence gating |

Skip deep research only when intake profile is `docs_only`.

## Output

Write `<run_dir>/research-brief.md` with sections:

- `## 요약`
- `## 조사 질문`
- `## 핵심 발견` (≥ 200 chars, inline URL citations required)
- `## e2eTester 적용 권장`
- `## 불확실성 / 추가 확인 필요`
- `## 참고 URL` (≥ 2 distinct URLs)

Do not modify application code or planning artifacts.
