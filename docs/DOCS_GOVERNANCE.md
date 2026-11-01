# 문서 거버넌스

문서 표류(drift) 방지를 위한 SSOT·가드·PR 체크리스트.

## 문서 위치

- **루트:** `README.md`(사용자), `AGENTS.md`(에이전트·기여자 진입점)
- **`docs/`:** 정식 프로젝트 문서(아키텍처·설치·CI·시나리오·SDD 스펙 등)
- **`.agents/skills/`:** 에이전트 전용 스킬(`e2e-browser` 등)
- **`research/`:** 1회성 탐색·스냅샷 기록(앱 구성 요소 아님)
- **`graphify-out/`:** 코드·문서 지식 그래프 산출물

## SSOT 매트릭스

| 사실 영역 | SSOT | 다른 문서 |
| --- | --- | --- |
| 아키텍처·API·폴더 트리 | `docs/E2E_ARCHITECTURE.md` | 링크만 |
| 시나리오·모듈·입력 | `docs/scenarios/{code}.md` | 링크만 |
| 행동·AC·SDD 규칙 | `docs/specs/00-GOVERNANCE.md`, `docs/specs/README.md`, `docs/specs/**` | 링크만 |
| 사용 안내 | `README.md` | 링크만 |
| 설치·env | `docs/INSTALL.md`, `.env.example` | 링크만 |
| OTP 중계기(안드로이드) | `docs/otp_relay.md` | INSTALL 은 env만 |
| 텔레그램 봇 설정 | `docs/telegram_bot.md` | INSTALL 은 env만 |
| 에이전트 지침·스킬 | `AGENTS.md`, `.agents/skills/` | 링크만 |
| CI 게이트 | `scripts/ci/gates.py`(코드), `docs/CI.md`(문서) | 링크만 |
| 상태 라벨·색상·런타임 기본값 | 소스코드(`status_labels.py`, `status_colors.py`, `gemini_models.py` 등) | 가드로 동기화 |

원칙: 코드로 추출 가능한 사실의 SSOT 는 **소스**. 문서는 사본이며 `check_docs_consistency.py` 등 가드가 검증한다.

## 정합성 가드

```bash
python3 scripts/check_docs_consistency.py
```

검사:
- manifest ↔ `docs/scenarios/{code}.md` · `docs/specs/systems/{code}.md` 1:1 대응 및 `module_id` 포함, `execution_profile` 허용값(`heavy|light|interactive`)
- `docs/specs/README.md` 인덱스 ↔ `docs/specs/**/*.md` 파일 양방향 1:1 및 `SPEC-*` ID 일치(`tests/test_spec_traceability.py` 로 `@pytest.mark.spec` ↔ Spec·AC 검증 병행)
- API 라우트(`app/` 전체) ↔ `docs/E2E_ARCHITECTURE.md` §5.2 양방향(`include_in_schema=False` 인프라 라우트 제외)
- 환경변수(`app/` + `worker/`) ↔ `docs/INSTALL.md` · `.env.example` 양방향 및 기본 Gemini 모델 체인(`app/ai/gemini_models.py`) 일치
- `docs/E2E_ARCHITECTURE.md` §4 폴더 트리 경로 실재 및 주요 디렉터리(`app/api·core·runner·notifications·contexts·templates`, `worker`, `docs`) 역방향 등재

CI: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml), 전체 게이트(`architecture_gates`, `frontend_gates`, `frontend_tokens`, `ci_config_valid` 포함): [docs/CI.md](CI.md).

## PR 체크리스트

- [ ] `python3 scripts/ci/run_all_gates.py --profile full` 통과
- [ ] 커버리지 하락 없음 (`python3 scripts/ci/run_all_gates.py --gate coverage`)
- [ ] `python3 scripts/check_docs_consistency.py` 통과
- [ ] manifest 변경 → `docs/scenarios/{code}.md` + `docs/specs/systems/{code}.md` 동시 갱신
- [ ] 동작·기능 변경 → 관련 `docs/specs/**` (및 신규 SPEC ID 시 `docs/specs/README.md`) 갱신
- [ ] API 변경 → `docs/E2E_ARCHITECTURE.md` §5.2 갱신
- [ ] env 변경 → `docs/INSTALL.md` + `.env.example`
- [ ] SSOT 중복 서술 추가 금지(링크 참조)

상세: [`.github/pull_request_template.md`](../.github/pull_request_template.md), [`docs/specs/00-GOVERNANCE.md`](specs/00-GOVERNANCE.md).

## 새 시스템 추가

1. `app/systems/{code}/manifest.yaml` 및 `executor.py` (자동화 Flow·PageObject 는 `app/automation/` 배치 및 `wiring.py` 연결, 실험 스크립트는 `research/` 앱 외부 격리)
2. `docs/scenarios/{code}.md`
3. `docs/specs/systems/{code}.md` 작성 및 `docs/specs/README.md` 인덱스 등록
4. `docs/E2E_ARCHITECTURE.md` §4 폴더 트리 및 §6 시스템 시나리오 링크 갱신
5. env 필요 시 `docs/INSTALL.md` + `.env.example` 갱신
6. `python3 scripts/check_docs_consistency.py`

## 에이전트 탐색 도구 (graphify)

`graphify-out/graph.json` 은 **방향 그래프**다. 무방향으로 되돌리지 말 것 — 허브(`RunStatus` 등)가 in-degree 싱크라서 무방향에서는 BFS 가 폭발한다(쿼리당 17.8k → 1.6k 토큰). 그래프 갱신(`graphify update`) 후에는 `python3 scripts/graphify_doc_bridge.py` 를 실행해 문서↔코드 `mentions` 브리지 엣지를 재연결한다.

- 정방향 질문("X 는 무엇을 쓰는가", "동작 흐름"): `graphify query "<질문>" --budget 4000`
- 역방향 질문("무엇이 X 를 쓰는가", 변경 영향 범위): `graphify affected "<심볼>" --depth 1`
- 단일 심볼 설명: `graphify explain "<심볼>"`

