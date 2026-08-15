# CI 검증

PR 게이트: 순수 단위 테스트 + 문서/아키텍처 정책 + ruff. **라이브 Playwright E2E 는 CI 밖.**

## 실행

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/ci/run_all_gates.py --profile full
```

SSOT: `scripts/ci/gates.py`, 워크플로: `.github/workflows/ci.yml`.

## 게이트 계층

| Tier | 게이트 |
| --- | --- |
| 0 | `ruff`, `ruff_format`, `docs_consistency` |
| 1 | `architecture_gates` (AG-001~009), `import_contracts`, `projection_validate`, `snapshot_validate` |
| 2 | `pytest` |
| 3 | `pip_audit`, `bandit_security` (auth/PII 경로·주간) |

## 아키텍처 게이트 요약

| 규칙 | 내용 |
| --- | --- |
| AG-001 | `list_runs()` 직접 호출 금지 |
| AG-002 | orchestrator 에서 playwright import 금지 |
| AG-003 | domain 에 I/O import 금지 |
| AG-004~005 | list_all_runs·aggregate 직접 접근 금지 |
| AG-006 | 스텝 계층 `print`/`redirect_stdout` 금지 |
| AG-007 | QueryPort 반환에 Run/Suite 엔티티 금지 |
| AG-008 | 서비스에서 run/suite 필드 직접 대입 금지 |
| AG-009 | contexts/api 에서 실행 평면 import 금지 |

## GitHub Actions

| Required check | 내용 |
| --- | --- |
| `ci / docs` | docs + architecture (항상) |
| `ci / lint` | ruff (코드 변경 시) |
| `ci / test` | pytest (코드 변경 시) |
| `ci / security` | 조건부 |

docs-only PR: `ci / docs` 만. `ci / security` 는 required 비권장(조건부 skip 시 merge queue 멈춤).

## PR DoD

[docs/DOCS_GOVERNANCE.md](DOCS_GOVERNANCE.md) · [`.github/pull_request_template.md`](../.github/pull_request_template.md)

## CI 밖 (수동)

라이브 사이트 Run/Suite, AI/메일(env 미설정). 서버 기동 후 대시보드에서 확인.
