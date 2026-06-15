# HRP 시나리오 (현장출동 홈페이지 / PC)

이 문서는 `hrp` 시스템의 E2E 테스트 시나리오를 설명한다.

플랫폼 공통 아키텍처(계층 구조, 상태 전이, 이벤트 모델, 아티팩트 전략)는 [E2E_ARCHITECTURE.md](../../E2E_ARCHITECTURE.md)를 참고한다.

## 1. 시스템 개요

- 시스템 코드: `hrp`
- manifest: `app/systems/hrp/manifest.yaml`
- 대상 사이트: `https://www.eagleprm.co.kr`
- 플랫폼: PC 웹
- 인증 수단: 없음. 이 시스템은 대표홈페이지와 별개의 업무를 수행하며, 현재는 로그인 없이 메인화면 접속만 점검한다(`supported_auth_methods: []`).
- 실행기: 공용 접속 점검 프레임워크 `app/systems/access_common/`(`AccessWorkflowExecutor`, `execution_mode = hrp_workflow_step`)를 사용한다. 시스템별 진입점은 `app/systems/hrp/executor.py`.

## 2. 모듈 목록

`manifest.yaml` `order` 기준:

1. `hrp.main.access` — 메인화면 접속 (`workflow_step: main_access`, `timeout_seconds: 120`)

의존성 그래프:

- `hrp.main.access` → 없음

## 3. 시나리오 상세

### 3.1 메인화면 접속 (`hrp.main.access`)

1. Playwright로 Chrome(영속 프로파일 `~/.e2etester/hrp-chrome-profile`)을 기동한다.
2. `https://www.eagleprm.co.kr` 으로 직접 이동(`domcontentloaded`)한다.
3. 초기 안내 팝업이 있으면 `닫기` 형태 버튼으로 정리한다(`app/systems/access_common/browser.py` 의 `maybe_close_popup`).
4. 메인화면 스크린샷(`final.png`)을 남기고 "메인화면 접속 성공"으로 종료한다.

## 4. 향후 시나리오

현장출동 본 업무 시나리오는 추후 모듈로 하나씩 추가한다. 모듈을 추가할 때는 이 문서와 `app/systems/hrp/manifest.yaml`을 함께 갱신한다.
