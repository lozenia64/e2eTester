# 문서 거버넌스

문서 표류(drift) 방지를 위한 SSOT·가드·PR 체크리스트.

## 문서 위치

- **루트:** `README.md`(사용자), `AGENTS.md`(에이전트·기여자 진입점)
- **`docs/`:** 그 외 모든 문서(아키텍처·설치·CI·시나리오 등)

## SSOT 매트릭스

| 사실 영역 | SSOT | 다른 문서 |
| --- | --- | --- |
| 아키텍처·API·폴더 트리 | `docs/E2E_ARCHITECTURE.md` | 링크만 |
| 시나리오·모듈·입력 | `docs/scenarios/{code}.md` | 링크만 |
| 행동·AC·Agent 개발 | `docs/specs/` | `docs/specs/README.md` |
| 사용 안내 | `README.md` | 링크만 |
| 설치·env | `docs/INSTALL.md`, `.env.example` | 링크만 |
| OTP 중계기(안드로이드) | `docs/otp_relay.md` | INSTALL 은 env만 |
| 텔레그램 봇 설정 | `docs/telegram_bot.md` | INSTALL 은 env만 |
| 에이전트 지침 | `AGENTS.md` | 링크만 |
| CI 게이트 | `docs/CI.md` | 링크만 |
| 런타임 기본값 | 소스코드 | 가드로 동기화 |

원칙: 코드로 추출 가능한 사실의 SSOT 는 **소스**. 문서는 사본이며 `check_docs_consistency.py` 가 검증한다.

## 정합성 가드

```bash
python3 scripts/check_docs_consistency.py
```

검사: manifest↔시나리오·manifest↔`docs/specs/systems/{code}.md` 1:1·module_id, API↔`docs/E2E_ARCHITECTURE.md` §5.2 양방향, env↔INSTALL/.env.example 양방향, §4 폴더 트리 실재.

CI: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml), 전체 게이트: [docs/CI.md](CI.md).

## PR 체크리스트

- [ ] `python3 scripts/ci/run_all_gates.py --profile full` 통과
- [ ] manifest 변경 → `docs/scenarios/{code}.md` + `docs/specs/systems/{code}.md` 동시 갱신
- [ ] API 변경 → `docs/E2E_ARCHITECTURE.md` §5.2 갱신
- [ ] env 변경 → `docs/INSTALL.md` + `.env.example`
- [ ] SSOT 중복 서술 추가 금지(링크 참조)

상세: [`.github/pull_request_template.md`](../.github/pull_request_template.md).

## 새 시스템 추가

1. `app/systems/{code}/manifest.yaml` (자동화 스크립트는 `app/automation/` 배치, 실험 스크립트는 `research/` 앱 외부 격리)
2. `docs/scenarios/{code}.md`
3. `docs/specs/systems/{code}.md`
4. env 필요 시 INSTALL/.env.example
5. `python3 scripts/check_docs_consistency.py`

## 에이전트 탐색 도구 (graphify)

`graphify-out/graph.json` 은 **방향 그래프**다. 무방향으로 되돌리지 말 것 — 허브(`RunStatus` 등)가 in-degree 싱크라서 무방향에서는 BFS 가 폭발한다(쿼리당 17.8k → 1.6k 토큰).

- 정방향 질문("X 는 무엇을 쓰는가", "동작 흐름"): `graphify query "<질문>" --budget 4000`
- 역방향 질문("무엇이 X 를 쓰는가", 변경 영향 범위): `graphify affected "<심볼>" --depth 1`
- 단일 심볼 설명: `graphify explain "<심볼>"`

