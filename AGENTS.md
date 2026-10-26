# AGENTS.md

## SSOT

- 아키텍처·API: `docs/E2E_ARCHITECTURE.md`
- 설치·env: `docs/INSTALL.md`, `.env.example`
- CI: `docs/CI.md`
- 시나리오: `docs/scenarios/{code}.md` (manifest 1:1)
- 행동·AC Spec: `docs/specs/` (`docs/specs/README.md`)
- 문서·PR DoD: `docs/DOCS_GOVERNANCE.md`

## 실행·검증

`docs/INSTALL.md`. PR 전 `python3 scripts/ci/run_all_gates.py --profile full` (장시간 → 백그라운드). 새 워크트리는 `npm ci` 먼저.

## 에이전트 스킬

- 프로젝트 스킬: `.agents/skills/` (Codex·Copilot CLI 등 크로스 런타임 공유)
- **수동 E2E / UI 검증** 요청 시 `.agents/skills/e2e-browser/SKILL.md`를 먼저 읽고 따른다.
  브라우저 우선순위: Orca 내장 브라우저(열림 확인 → 없으면 탭 생성) → 실패 시 Playwright MCP.
- 대표홈페이지(hom/mhm) 실사이트 재현은 위 브라우저 대신 `RepHomepageExecutor.build_runtime` 기동 순서로. 사용자 로그인된 브라우저는 재시작 금지.

## 제약

- automation: `app/automation/`
- manifest·flow 변경 시 짝 시나리오 문서 동시 갱신
- UI·로그·README 문자열 한국어
- `research/` 앱 외부
- Windows `.sh`: `bash <path>.sh`
