# AGENTS.md

## 불변 원칙

1. **SSOT 및 문서 무표류(Zero Drift)**: 모든 지식은 단일 진실원천(SSOT)에만 서술하고 타 문서는 링크로만 참조한다. 코드·설정 변경 시 짝 문서를 반드시 동시 갱신한다.
2. **스펙 및 검증 주도(Spec & Gate First)**: 모든 변경은 행동 명세(Spec)에 기반하며, 완료 전 정의된 검증 게이트를 통과해야 한다.
3. **한국어 우선(Korean First)**: UI·로그·문서·커밋 등 사용자와 기여자가 읽는 모든 텍스트는 한국어로 작성한다.

## 문서 진입점 (라우팅)

- **전체 문서 지도·SSOT 매트릭스·PR 규칙**: [`docs/DOCS_GOVERNANCE.md`](docs/DOCS_GOVERNANCE.md)
- **요구사항·수용 기준·Agent 작업 프로토콜**: [`docs/specs/00-GOVERNANCE.md`](docs/specs/00-GOVERNANCE.md), [`docs/specs/README.md`](docs/specs/README.md)
- **시스템 아키텍처·폴더 구조·API**: [`docs/E2E_ARCHITECTURE.md`](docs/E2E_ARCHITECTURE.md)
- **설치·실행·CI 검증 게이트**: [`docs/INSTALL.md`](docs/INSTALL.md), [`docs/CI.md`](docs/CI.md)
- **에이전트 전용 스킬**: [`.agents/skills/`](.agents/skills/)
