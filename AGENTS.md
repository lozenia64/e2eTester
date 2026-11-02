# AGENTS.md

## 불변 원칙

1. **SSOT 및 문서 무표류(Zero Drift)**: 모든 지식은 단일 진실원천(SSOT)에만 서술하고 타 문서는 링크로만 참조한다. 코드·설정 변경 시 짝 문서를 반드시 동시 갱신한다.
2. **스펙 및 검증 주도(Spec & Gate First)**: 모든 변경은 행동 명세(Spec)에 기반하며, 완료 전 정의된 검증 게이트를 통과해야 한다.
3. **한국어 우선(Korean First)**: UI·로그·문서·커밋 등 사용자와 기여자가 읽는 모든 텍스트는 한국어로 작성한다.

## 작업 절차

1. **시작**: [`docs/specs/00-GOVERNANCE.md`](docs/specs/00-GOVERNANCE.md) §4에 따라 SPEC ID를 먼저 매핑한다.
2. **완료**: 같은 문서 §4.3을 통과해야 완료이며, UI 변경은 [`e2e-browser`](.agents/skills/e2e-browser/SKILL.md)로 검증한다.
3. **Spec 면제**: 동작이 바뀌지 않는 변경(문서·의존성·빌드 설정)은 Spec 없이 게이트만 통과하며, 문서만 바꾸면 `--profile docs_only`를 쓴다.
4. **커밋**: `type(scope): 한국어 요약` 형식으로 작성한다.

## 안전 규칙

- **라이브 Run**: 라이브 사이트 Run/Suite는 사용자가 요청한 경우에만 시작한다.
- **OTP**: OTP를 지어내 제출하지 않고 `WAITING_INPUT`에서 멈춰 사람에게 넘긴다.
- **브라우저**: 사용자가 로그인해 둔 브라우저를 재시작하지 않는다.

## 문서 진입점 (라우팅)

- **전체 문서 지도·SSOT 매트릭스·PR 규칙**: [`docs/DOCS_GOVERNANCE.md`](docs/DOCS_GOVERNANCE.md)
- **요구사항·수용 기준·Agent 작업 프로토콜**: [`docs/specs/00-GOVERNANCE.md`](docs/specs/00-GOVERNANCE.md), [`docs/specs/README.md`](docs/specs/README.md)
- **시스템 아키텍처·폴더 구조·API**: [`docs/E2E_ARCHITECTURE.md`](docs/E2E_ARCHITECTURE.md)
- **설치·실행·CI 검증 게이트**: [`docs/INSTALL.md`](docs/INSTALL.md), [`docs/CI.md`](docs/CI.md)
- **에이전트 전용 스킬**: [`.agents/skills/`](.agents/skills/)
