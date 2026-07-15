# Artifacts Contract

All artifacts live in `<run_dir>`. Paths are relative to run directory.

## Shared

| File | Writer | Readers |
|------|--------|---------|
| `run.json` | init_run.py, manager | all agents |
| `trace.log` | append_handoff.py, manager | human |
| `handoffs.jsonl` | append_handoff.py | human |

## Gate reports (mechanical — manager scripts)

| File | Writer | Tier |
|------|--------|------|
| `research-gate-report.json` | run_research_gate.py | T0 |
| `planning-gate-report.json` | run_planning_gate.py | T1 |
| `preflight-report.json` | run_preflight_gates.py | T2 |
| `gates-report.json` | run_gates.py | T3 |
| `mechanical-verdict.json` | run_mechanical_verdict.py | T3 |

## Per-agent artifacts

### e2e-researcher → `research-brief.md`

Required sections:

- `## 요약`
- `## 조사 질문`
- `## 핵심 발견` — ≥ 200 chars, inline URL citations
- `## e2eTester 적용 권장`
- `## 불확실성 / 추가 확인 필요`
- `## 참고 URL` — ≥ 2 distinct URLs

Skipped when `pipeline_profile` is `docs_only`.

### e2e-intake → `intake.json`

```json
{
  "e2e_pipeline_profile": "step_fix|new_module|new_system|platform|healing_patch|docs_only|spike",
  "dev_pipeline_profile": "feature",
  "pipeline_profile": "platform",
  "system_code": "hom|mhm|fp|hrp|hwtc|chbot|null",
  "layer": "steps|manifest|executor|gateway|domain|orchestrator|api|web|healing|scheduling",
  "touch_surfaces": ["selector", "otp", "manifest", "api", "ws", "sqlite", "docs"],
  "affected_modules": ["module_id", "..."],
  "risk_flags": ["pii", "user_facing", "unknown_tech", "auth", "otp"],
  "conditional_agents": ["dev-ux-designer", "e2e-security-auditor"],
  "dev_path": "full|standard|minimal",
  "ship_requested": false,
  "agent_graph": null,
  "summary": "한 줄 요약"
}
```

Note: `agent_graph` must be **null** at intake time. Manager runs `resolve_graph.py` to populate `run.json.agent_graph`, `qc_agents`, and `ship_agents`.
For `system_code`, prefer JSON `null` for platform-wide scope.

### guardian → `review.md` + `context.md`

`review.md` must contain `APPROVED` or `REJECTED`. `context.md` is the implementer ground-truth bundle.

### dev-spec-writer → `spec.md`

Sections: `## 목표`, `## 범위`, `## 수용 기준`, `## 비범위`

### dev-context-scout → `context-map.md`

Sections: `## 관련 파일`, `## 패턴` (e2e-domain-scout may append `## E2E 확장`)

### dev-architect → `architecture.md`

Sections: `## 개요`, `## 컴포넌트`, `## 데이터 흐름`

### dev-task-planner → `tasks.yaml`

YAML task breakdown, min 5 lines.

### dev-ux-designer → `ux-spec.md`

Sections: `## 레이아웃`, `## 상태`

### dev-researcher → `research.md`

Sections: `## 요약`, `## 권장 사항`

### dev-build-integrator → `build-report.json`

```json
{"passed": true, "commands": []}
```

### dev-security-auditor → `security-report.json`

Same shape as e2e-security-auditor.

### dev-pr-publisher → `pr.json`

```json
{"url": "https://github.com/...", "branch": "feature/name"}
```

### dev-ci-watcher → `ci-report.json`

```json
{"passed": true}
```

### e2e-domain-scout → `context-map.md`

Required sections:

- `## 관련 파일` — bullet list with paths and one-line role
- `## 계층` — which architecture layer(s) are touched
- `## 패턴` — existing conventions to follow

### e2e-scenario-analyst → `scenario-impact.md`

Required sections:

- `## 시스템` — system_code, channel if applicable
- `## 모듈 영향` — affected module_ids, depends_on implications
- `## 시나리오 문서` — `docs/scenarios/{code}.md` sections to update

### e2e-manifest-planner → `manifest-plan.yaml`

YAML with at least:

```yaml
system_code: hom
modules:
  - action: add|modify|reorder
    module_id: example
    workflow_step: step_name
    depends_on: []
    requires_user_input: false
    timeout_seconds: 120
```

### e2e-platform-architect → `architecture-delta.md`

Required sections:

- `## 개요`
- `## 경계` — ports, aggregates, event bus boundaries
- `## 변경 범위` — files and layers

### e2e-selector-healer → `healing-plan.md`

Required sections:

- `## 깨진 셀렉터` — broken selector literal from error
- `## 치유 전략` — id/name/role preference, HealedPage notes
- `## 검증` — how to verify fix (unit vs manual run)

### e2e-docs-guardian → `docs-checklist.md`

Required sections:

- `## SSOT` — which doc owns each fact
- `## 수정 대상` — file paths to edit
- `## 가드 항목` — check_docs_consistency items at risk

### e2e-implementer → `implementation-notes.md` + `preflight-report.json`

Required:

- `preflight-report.json` with `"passed": true` (from run_preflight_gates.py)
- `implementation-notes.md` with `## 변경 요약`

Optional:

- `## 문서 변경` — if docs edited in same pass

### e2e-docs-writer → `implementation-notes.md`

Required section: `## 문서 변경`

### e2e-test-runner → `gates-report.json`

Written by `run_gates.py`. QC agent may append `test-report.json` with manual notes.

### e2e-code-reviewer → `review-report.json`

```json
{
  "passed": true,
  "issues": [{"severity": "high|medium|low", "file": "path", "message": "..."}]
}
```

### e2e-security-auditor → `security-report.json`

```json
{
  "passed": true,
  "issues": [{"severity": "high|medium|low", "area": "pii|auth|api", "message": "..."}]
}
```

### e2e-release-judge → `release-verdict.json`

```json
{
  "passed": true,
  "failed_agent": "e2e-implementer",
  "feedback": "구체적 수정 지시",
  "invariants_checked": ["manifest_docs_sync", "otp_policy", "view_projection"]
}
```

When `passed` is false, `failed_agent` and `feedback` are required.
