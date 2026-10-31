# AGENTS.md

## SSOT

> 전체 매트릭스·동기화 규칙: `docs/DOCS_GOVERNANCE.md`

- 아키텍처·API: `docs/E2E_ARCHITECTURE.md`
- 설치·env: `docs/INSTALL.md`, `.env.example`
- 외부 연동(OTP 중계·텔레그램 봇): `docs/otp_relay.md`, `docs/telegram_bot.md`
- CI: `docs/CI.md` (`scripts/ci/gates.py`)
- 시나리오: `docs/scenarios/{code}.md` (manifest 1:1)
- 행동·AC Spec: `docs/specs/` (`docs/specs/README.md`, `docs/specs/00-GOVERNANCE.md`)
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

## 코드베이스 그래프 (graphify)

`graphify-out/graph.json` 은 **방향 그래프**다. 무방향으로 되돌리지 말 것 — 허브(`RunStatus` 등)가
in-degree 싱크라서 무방향에서는 BFS 가 폭발한다(쿼리당 17.8k → 1.6k 토큰).

- 정방향 질문("X 는 무엇을 쓰는가", "동작 흐름"): `graphify query "<질문>" --budget 4000`
- 역방향 질문("무엇이 X 를 쓰는가", 변경 영향 범위): `graphify affected "<심볼>" --depth 1`
- 단일 심볼 설명: `graphify explain "<심볼>"`
