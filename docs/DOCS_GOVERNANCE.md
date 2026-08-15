# 문서 거버넌스 (SSOT + 정합성 가드)

이 문서는 프로젝트 문서의 **단일 진실원천(SSOT)** 과 **문서-코드 정합성 유지 규칙**을 정의한다.
목적은 같은 사실이 여러 문서에 중복 기술되어 한 곳만 고쳤을 때 나머지가 어긋나는 **문서 표류(drift)** 를,
전수 수작업 감사 없이 조기에 차단하는 것이다.

## 1. 왜 필요한가 (배경)

과거 다음과 같은 표류가 실제로 발생했다.

- 종료 메일 본문 생성 방식이 `README.md`("Gemini가 HTML 생성")와 `E2E_ARCHITECTURE.md` §5.8("HTML은 고정 템플릿, Gemini는 콘텐츠 JSON만")에서 **상반되게** 기술됨.
- `E2E_ARCHITECTURE.md` 의 폴더 트리가 실제 코드 구조와 어긋남(`access_common` 구성, `app/ai` 누락 파일).

근본 원인은 **같은 사실이 `README.md`·`AGENTS.md`·`E2E_ARCHITECTURE.md` 등 여러 문서에 중복 기술**되고, 이를 잡아낼 자동 장치가 없었다는 점이다.

## 2. SSOT 매트릭스 (사실 영역별 소유 문서)

각 "사실 영역"은 **소유 문서 1개**만 상세 서술하고, 나머지 문서는 **링크 참조**만 둔다.
같은 사실을 두 문서에서 상세 서술하지 않는다.

| 사실 영역 | 단일 진실원천(SSOT) | 다른 문서에서의 처리 |
| --- | --- | --- |
| 플랫폼 아키텍처·계층 역할·상태머신·이벤트 모델·아티팩트 전략·폴더 구조·**목표(로드맵) 아키텍처** | `E2E_ARCHITECTURE.md` | 링크 참조 |
| API 엔드포인트 목록(메서드+경로) | `E2E_ARCHITECTURE.md` §5.2 | 링크 참조 |
| 시스템별 시나리오·모듈 동작·selector·화면 검증·입력 모델 | `docs/scenarios/{system_code}.md` | 링크 참조 |
| 점검 도구 사용 안내(화면·결과 해석·FAQ) | `README.md` | 링크 참조 |
| 설치·실행 방법, 선택 기능(AI/메일/예약) 사용법, 환경변수 카탈로그 | `docs/INSTALL.md` | 링크 참조 |
| 환경변수 예시값 | `.env.example` | `docs/INSTALL.md` 가 의미·기본값 서술 |
| OTP SMS 중계기 구성(안드로이드 측)·인입 엔드포인트 계약 상세 | `docs/otp_relay.md` | `docs/INSTALL.md` 는 서버 설정(환경변수)만 서술 + 링크 참조 |
| 코드베이스 작업 지침(에이전트/기여자용 요약) | `AGENTS.md` | 상세 사실은 위 소유 문서로 링크 |
| 런타임 기본값(모델 체인, 스케줄러 주기/TZ, 타임아웃 등) | **소스코드**(`app/...`) | 문서는 값이 아니라 출처(파일/상수)를 가리키거나 가드로 동기화 |
| (역사 기록) 아키텍처 냉정 평가 스냅샷 | `docs/ARCHITECTURE_REVIEW_IDEAL.md` | **현재 상태의 근거로 인용 금지** — 시점 고정 평가 + 적용 현황 부록. 현재/목표 구조는 `E2E_ARCHITECTURE.md` 가 소유 |

원칙:

- **코드로 추출 가능한 사실(모듈 목록, 엔드포인트, 환경변수명, 기본 모델 체인)의 진짜 SSOT는 항상 소스코드다.** 문서는 그 사본일 뿐이며, 아래 정합성 가드가 사본의 일치를 강제한다.
- 사람이 읽고 판단해야 하는 서술(설계 의도, 시나리오 흐름 설명)은 소유 문서에서만 상세히 쓴다.

## 3. 정합성 가드 (자동 검사)

`scripts/check_docs_consistency.py` 가 **기계적으로 검증 가능한 사실**만 소스와 문서 사이에서 대조한다.

검사 항목:

1. 시스템 `manifest.yaml` ↔ `docs/scenarios/{code}.md` 1:1 대응
2. `manifest` 의 모든 `module_id` 가 짝이 되는 시나리오 문서에 등장
3. FastAPI 라우트(메서드+경로)가 `E2E_ARCHITECTURE.md` 에 문서화 — 스캔 범위는 `app/` 전체
   (`app/api` 외 `app/auth/router.py`·`app/main.py` 포함), `include_in_schema=False` 라우트
   (파비콘 등 인프라 자산)는 §5.2 인프라 라우트 규칙에 따라 문서화·검사 대상에서 제외
4. 코드가 읽는 환경변수가 `docs/INSTALL.md` 또는 `.env.example` 에 문서화
5. 기본 Gemini 모델 체인(`app/ai/gemini_models.py` 상수)이 `docs/INSTALL.md`/`.env.example` 와 일치
6. **(역방향)** `E2E_ARCHITECTURE.md` 가 문서화한 라우트가 실제 코드에 존재 — 삭제된 엔드포인트가
   문서에 남는 "유령 라우트" 차단
7. **(역방향)** `docs/INSTALL.md`/`.env.example` 의 환경변수를 코드가 실제로 읽음 — 개명·제거된 변수가
   문서에 남는 "죽은 변수" 차단
8. `E2E_ARCHITECTURE.md` §4 폴더 트리에 나열된 경로가 실제로 존재 — 이동·삭제된 파일이 트리에
   남는 "유령 파일" 차단 (런타임 생성 디렉터리 `artifacts/` 는 예외)

3~8번이 **양방향**을 이루므로, 코드→문서 누락뿐 아니라 문서→코드 유령 서술도 CI 가 잡는다.

실행:

```bash
python3 scripts/check_docs_consistency.py            # 전체 검사 (CI 게이트와 동일)
python3 scripts/check_docs_consistency.py --verbose  # 통과 항목 상세까지 출력
```

종료 코드는 모두 통과 시 `0`, 하나라도 실패 시 `1` 이다. GitHub Actions([`.github/workflows/ci.yml`](../.github/workflows/ci.yml))가 PR마다 이 스크립트를 실행해 표류를 차단하며, 같은 워크플로에서 **아키텍처 게이트·ruff(린트·포맷)·pytest(단위 테스트)** 도 함께 실행한다. 전체 CI 계층·로컬 실행 방법은 [`docs/CI.md`](CI.md) 를 참고한다.

가드는 의도적으로 **검증 가능한 것만** 본다. 설계 의도·시나리오 서술처럼 자연어 판단이 필요한 영역은 아래 PR 체크리스트(사람 검토)로 보완한다.

## 4. PR Definition of Done (문서 체크리스트)

코드를 바꾼 PR은 머지 전에 아래를 만족해야 한다. (`.github/pull_request_template.md` 에 동일 체크리스트가 들어 있다.)

- [ ] `python3 scripts/ci/run_all_gates.py` 또는 개별 게이트가 통과한다(로컬/CI). 규칙: [`docs/CI.md`](CI.md).
- [ ] `python3 scripts/check_docs_consistency.py` 가 통과한다(로컬/CI).
- [ ] `python3 scripts/check_architecture_gates.py` 가 통과한다(AG-001~003).
- [ ] 시스템 `manifest.yaml` 을 추가·변경했다면, 짝이 되는 `docs/scenarios/{code}.md` 를 같은 PR에서 갱신했다(모듈 추가/순서/의존성/`workflow_step`/타임아웃).
- [ ] 사이트 흐름·selector 를 바꿨다면, 해당 시나리오 문서의 단계 설명을 갱신했다.
- [ ] API 라우트를 추가·변경·삭제했다면, `E2E_ARCHITECTURE.md` §5.2 를 갱신했다.
- [ ] 환경변수를 추가·변경했다면, `docs/INSTALL.md` 와 `.env.example` 을 갱신했다.
- [ ] 런타임 기본값(모델 체인 등)을 바꿨다면, 관련 문서/예시를 갱신했다.
- [ ] 위 SSOT 매트릭스를 위반하는 **중복 서술을 새로 추가하지 않았다**(필요하면 링크 참조).

## 5. 새 시스템을 추가할 때

1. `app/systems/{code}/manifest.yaml` 추가.
2. `docs/scenarios/{code}.md` 추가(개요·모듈 목록·단계 상세·입력 모델). 가드 1·2번이 누락을 잡는다.
3. 환경변수를 새로 읽으면 `docs/INSTALL.md`/`.env.example` 갱신(가드 4번).
4. `python3 scripts/check_docs_consistency.py` 로 확인 후 PR.
