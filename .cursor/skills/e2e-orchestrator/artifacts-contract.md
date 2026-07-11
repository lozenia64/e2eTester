# Artifacts Contract

All artifacts live in `<run_dir>`. Paths are relative to run directory.

## Shared

| File | Writer | Readers |
|------|--------|---------|
| `run.json` | init_run.py, manager | all agents |
| `trace.log` | append_handoff.py, manager | human |
| `handoffs.jsonl` | append_handoff.py | human |

## Per-agent artifacts

### e2e-intake → `intake.json`

```json
{
  "pipeline_profile": "step_fix|new_module|new_system|platform|healing_patch|docs_only|spike",
  "system_code": "hom|mhm|fp|hrp|hwtc|chbot|null",
  "layer": "steps|manifest|executor|gateway|domain|orchestrator|api|web|healing|scheduling",
  "touch_surfaces": ["selector", "otp", "manifest", "api", "ws", "sqlite", "docs"],
  "affected_modules": ["module_id", "..."],
  "risk_flags": ["pii", "live_site_claim", "selector_fragile", "cross_channel_hom_mhm", "auth", "otp"],
  "conditional_agents": ["security-auditor"],
  "agent_graph": ["e2e-domain-scout", "e2e-scenario-analyst", "..."],
  "summary": "한 줄 요약"
}
```

Note: `agent_graph` excludes E01 and QC agents; manager expands QC after E08.

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

### e2e-implementer → `implementation-notes.md`

Required sections:

- `## 변경 요약` — files changed and why

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
