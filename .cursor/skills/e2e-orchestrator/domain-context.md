# e2eTester Domain Context

Inject relevant sections into Task prompts. Full details live in repo SSOT docs.

## Systems

| Code | Name | Domain |
|------|------|--------|
| hom | 대표홈페이지(PC) | `www.hwgeneralins.com`, PC channel |
| mhm | 대표홈페이지(모바일) | `m.hwgeneralins.com`, mobile channel |
| fp | 영업가족 위촉서류 등록(PC) | 3 modules: access → identity → document |
| hrp | 현장출동 홈페이지(PC) | 4 modules: access → login → salvage bid |
| hwtc | 연수원(PC) | 3 modules: access → login → video |
| chbot | 챗봇(모바일) | 3 modules: access → simple auth → contract |

HOM and MHM share `app/scenarios/rep_homepage/` — single scenario, two `ChannelProfile`s.

## Architecture layers (touch → file)

| Layer | Path pattern | Rules |
|-------|--------------|-------|
| steps | `app/systems/{code}/steps/*.py` | Stateful Playwright automation; selectors tuned to live site |
| manifest | `app/systems/{code}/manifest.yaml` | module_id, depends_on, workflow_step, requires_user_input |
| executor | `app/systems/{code}/executor.py` | Extends RepHomepageExecutor or AccessWorkflowExecutor |
| gateway | `app/execution/*.py` | ExecutionGateway port; no Playwright in RunService |
| domain | `app/domain/*.py` | Pure state machines (RunAggregate, SuiteAggregate) — no await, no I/O |
| orchestrator | `app/orchestrator/*.py` | Thin I/O interpreters; rules in domain/builders |
| api | `app/api/*.py` | FastAPI routes; use `dependencies.py` Depends, not app.state |
| web | `app/web/` | Page-scoped JS (not piled on app.js for new pages) |
| healing | `app/healing/` | Self-healing engine; patches need human approval |
| scheduling | `app/scheduling/` | Cron schedules, schedule center |

## Invariants (implementer must respect)

1. **OTP pause**: only modules with `requires_user_input: true` in manifest may pause as WAITING_INPUT.
2. **Step registry**: add handlers via `build_step_registry()` — no per-executor if/elif chains.
3. **Screenshots**: engine captures at module end (`app/runner/screenshot.py`); steps do not take screenshots.
4. **HOM/MHM constants**: claim text SSOT is `app/scenarios/rep_homepage/constants.py`.
5. **Compensation modules**: submit real test claim with `CLAIM_CONTENT_TEXT`; cancel in follow-up module.
6. **Run wire format**: REST/WS via RunView/SuiteView — never `run.model_dump()` to clients.
7. **PII**: input_data in RunInputStorePort — never on Run blob or WebSocket.
8. **Docs**: manifest module_ids must appear in `docs/scenarios/{code}.md`; CI enforces via `check_docs_consistency.py`.

## CI gates (same as PR — SSOT: `scripts/ci/gates.py`)

```bash
python3 scripts/ci/run_all_gates.py --profile full
# Or individually:
python3 scripts/check_docs_consistency.py
python3 scripts/check_architecture_gates.py
python3 -m ruff check . && python3 -m ruff format --check .
python3 -m pytest tests/ -q
```

## Auth methods

HOM/MHM: `phone` or `kakao` only (validated at start_run). Phone → WAITING_INPUT for OTP. Kakao → 30s wait, no OTP pause.

## Terminal statuses

- PASSED (정상), ANOMALY (이상징후), ERROR (점검실패)
- Run final priority: ERROR > ANOMALY > PASSED

## Self-healing

On step failure, `SelfHealingEngine` may suggest/apply selector overrides via `HealedPage`. Patches are PROPOSED until human approves via `/api/healing/patches/{id}/approve`.

## Research folder

`research/` contains throwaway probes — not part of the app. Spike profile may write here.

## Key SSOT docs

- Platform architecture: `E2E_ARCHITECTURE.md`
- Per-system scenarios: `docs/scenarios/{code}.md`
- Docs governance: `docs/DOCS_GOVERNANCE.md`
- Agent/contributor summary: `CLAUDE.md`
