# CI 검증

PR 게이트: 순수 단위 테스트 + 문서/아키텍처 정책 + ruff. **라이브 Playwright E2E 는 CI 밖.**

## 실행

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/ci/run_all_gates.py --profile full
```

`ci_config_valid` 는 CI 설정 자체를 검사한다 — `gates.py` 의 경로 글롭이 실재
파일에 매칭되는지, 프로필이 없는 게이트를 참조하지 않는지. 코드 이동으로 CI 가
조용히 죽는 것을 막는다.

SSOT: `scripts/ci/gates.py`, 워크플로: `.github/workflows/ci.yml`.

## 게이트 계층

| Tier | 게이트 |
| --- | --- |
| 0 | `ci_config_valid`, `ruff`, `ruff_format`, `docs_consistency`, `frontend_gates`, `frontend_tokens`, `typecheck_web`, `eslint_web`, `build_web`, `vitest_web` |
| 1 | `architecture_gates` (AG-001~009), `import_contracts`, `pyright_decider`, `projection_validate`, `snapshot_validate` |
| 2 | `coverage` (= `pytest --cov`, 바닥선 57%) |
| 3 | `pip_audit`, `bandit_security` (auth/PII 경로·주간) |

로컬 러너(`--profile full`)는 Tier 2 에서 `coverage` 대신 빠른 `pytest` 를 쓴다.
커버리지 확인이 필요하면 `--gate coverage`.

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

## 프론트엔드 게이트 요약

SSOT: `scripts/check_frontend_gates.py`. 상태 토큰 생성기: `scripts/gen_frontend_tokens.py`.

| 규칙 | 내용 |
| --- | --- |
| FG-001 | 템플릿에 외부 CDN `<script>`/`<link>` 금지 |
| FG-002 | `app/web/frontend/` 내 하드코딩 hex 금지 (생성물 제외) |
| FG-003 | 상태 라벨은 `lib/status.generated.ts` 경유만 |
| FG-004 | 엔트리·컴포넌트 파일 400줄 상한 |
| FG-005 | 템플릿의 `/static/` 직접 참조 금지 (allowlist 제외) |

`frontend_tokens` 는 `status_labels.py` 에서 토큰·타입을 재생성해 커밋본과
diff 를 검사한다 — 상태를 추가하고 프론트 갱신을 잊는 것을 막는다.

`build_web`(`npm run build`)와 `vitest_web`(`npm run test`)은 정적 검사만으로는
잡히지 않는 것을 막는다 — 타입·린트가 통과해도 Vite/PostCSS/Tailwind 파이프라인이
깨져 자산이 번들에서 빠질 수 있고, Vitest 를 돌리지 않으면 프론트 순수 로직 테스트가
아무것도 강제하지 않는다. 둘 다 Node 를 요구하므로 `docs_only` 프로파일에서는 제외한다.

## GitHub Actions

| Job | 내용 |
| --- | --- |
| `ci / plan` | `gates.py` + 변경 파일로 실행할 게이트 목록 결정 |
| `ci / <게이트명>` | matrix — 게이트당 job 하나 (`fail-fast: false`) |
| `ci / required` | 집계. **브랜치 보호가 거는 유일한 required check** |

게이트를 추가하려면 `scripts/ci/gates.py` 에만 등록하면 된다. `ci.yml` 은 목록을
들고 있지 않으므로 CI job 이 자동으로 생긴다. required check 이름은 게이트가
늘거나 줄어도 `ci / required` 로 고정이라 브랜치 보호를 다시 손댈 일이 없다.

조건부 게이트(`pip_audit` 등)는 해당되지 않으면 matrix 에 아예 들어가지 않는다.
skip 된 체크가 남지 않으므로 merge queue 가 멈추지 않는다.

## PR DoD

[docs/DOCS_GOVERNANCE.md](DOCS_GOVERNANCE.md) · [`.github/pull_request_template.md`](../.github/pull_request_template.md)

## CI 밖 (수동)

라이브 사이트 Run/Suite, AI/메일(env 미설정). 서버 기동 후 대시보드에서 확인.
