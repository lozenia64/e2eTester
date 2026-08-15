# AGENTS.md

## SSOT

- 아키텍처·API: `docs/E2E_ARCHITECTURE.md`
- 설치·env: `docs/INSTALL.md`, `.env.example`
- CI: `docs/CI.md`
- 시나리오: `docs/scenarios/{code}.md` (manifest 1:1)
- 행동·AC Spec: `docs/specs/` (`docs/specs/README.md`)
- 문서·PR DoD: `docs/DOCS_GOVERNANCE.md`

## 실행·검증

`docs/INSTALL.md`. PR 전 `python3 scripts/ci/run_all_gates.py --profile full`.

## 제약

- automation: `app/automation/`
- manifest·flow 변경 시 짝 시나리오 문서 동시 갱신
- UI·로그·README 문자열 한국어
- `research/` 앱 외부
- Windows `.sh`: `bash <path>.sh`
