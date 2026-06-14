# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An internal web-triggered E2E test platform (Korean-language UI/docs). A FastAPI server serves a dashboard where employees launch Playwright-based browser tests against the Hanwha General Insurance websites, watch live module status/logs over WebSocket, and submit OTP codes mid-run. Two systems ship by default: **HOM** (PC web, `대표홈페이지(PC)`, `www.hwgeneralins.com`) and **MHM** (mobile web, `대표홈페이지(모바일)`, `m.hwgeneralins.com`). See `E2E_ARCHITECTURE.md` for the full architecture doc (current state vs. target state). Per-system test scenarios live in `docs/scenarios/{system_code}.md` (one file per system, paired 1:1 with its manifest): `docs/scenarios/hom.md` and `docs/scenarios/mhm.md`.

## Commands

```bash
# Install
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium   # fallback browser; local Chrome channel is preferred at runtime

# Run the server (then open http://127.0.0.1:8000)
python3 -m uvicorn app.main:app --reload
```

There is no test suite, linter, or build step. Verification is manual: run the server and trigger a run from the web UI. Run artifacts (logs + screenshots) land in `artifacts/{run_id}/{module_id}/` (`execution.log`, `final.png`).

Optional features (AI failure analysis via Gemini, end-of-run Gmail notifications) are configured via env vars / `.env` (see `.env.example`); real env vars take precedence over `.env`. Both are disabled by default and the app must keep working when they are unset or misconfigured.

## Architecture

Single process: web layer and test execution live in the same FastAPI app. Flow:

```
Browser → FastAPI (app/main.py wires everything in lifespan)
  → RunService (app/orchestrator/run_service.py) — orchestration, state transitions, events
    → ModuleRegistry (app/registry/loader.py + app/systems/*/manifest.yaml) — system/form/module definitions, manifest validation
    → InMemoryRunRepository (app/storage/run_repository.py) — runs, logs, WebSocket listener queues
    → Workflow executors (app/systems/loader.py loads each app/systems/{code}/executor.py by execution_mode) — Playwright sync API
      → HomWorkflowExecutor ("hom_workflow_step") / MhmWorkflowExecutor ("mhm_workflow_step")
        → app/systems/{system_code}/steps/*.py — the actual site automation
```

Key points that span multiple files:

- **Threading model**: Playwright's sync API objects must be used from the thread that created them. `RunService` creates a dedicated single-thread `ThreadPoolExecutor` per run (`max_workers=1`) and runs every step of that run's shared browser session on it. Async code (FastAPI/WebSocket) talks back via `asyncio.run_coroutine_threadsafe`. Don't call runtime/page objects from the event loop or another thread.
- **Shared browser session per run**: one browser/context/page (`HomWorkflowRuntime` / `MhmWorkflowRuntime`) is created at the first module and reused by all subsequent modules, because login state must carry through contract inquiry and claim modules. The runtime is also held alive across the OTP pause (`PendingOtpState`) so the run can resume in the same session. MHM's `build_runtime()` additionally applies mobile device mode (`apply_mobile_device_mode()`) before navigating.
- **Manifest-driven modules**: each `app/systems/{code}/manifest.yaml` defines the run form (with `show_when` conditional fields keyed on `auth_method`), module order, `depends_on`, timeouts, and `workflow_step` names. The system's executor maps each `workflow_step` to a function in `app/systems/{code}/steps/*.py` (`_run_step` dispatch). Adding/reordering a step means touching both the manifest and the executor's step dispatch. HOM and MHM currently mirror each other's 9-module structure; the registry validates each manifest on load (duplicate ids, `system_code` match, dependency existence/order, cycles).
- **Auth methods**: validated against the manifest's `supported_auth_methods` — HOM and MHM allow only `phone` or `kakao`, so `RunService.start_run` rejects anything else even though the form shows certificate options as placeholders. Phone auth pauses the run as `WAITING_INPUT` until OTP is submitted via `POST /api/runs/{run_id}/otp`; Kakao auth never pauses (it clicks 인증요청, waits ~60s for the user to approve in KakaoTalk, then clicks 인증완료/인증확인).
- **Module selection**: `start_run` accepts `selected_module_ids`; unselected modules are kept on the Run but marked `SKIPPED` and excluded from the execution loop. Combinations missing a `depends_on` prerequisite are rejected with a 400.
- **State machine**: Run statuses are PENDING/RUNNING/WAITING_INPUT/PASSED/FAILED; modules add QUEUED, BLOCKED (a `depends_on` prerequisite didn't PASS), and SKIPPED (deselected). Status changes are published as WebSocket events (`run_*`, `module_*` in `app/api/ws_runs.py` consumers); the front-end (`app/web/static/app.js`) renders nodes/logs/OTP panel from these events.
- **Everything is in memory**: runs, logs, and OTP-wait state vanish on server restart; only `artifacts/` files persist. The home page's "진행 중 / 최근 Run" panel reads `GET /api/runs` (in-memory summaries). There is no cancel, retry, or parallel-run support yet.
- **Log capture**: step modules just `print()`; the executor intercepts stdout/stderr per step (`LineWriter` in `app/runner/workflow_common.py`) and fans lines out to both `execution.log` and live WebSocket log events.

## Conventions and cautions

- `app/systems/{system_code}/steps/*.py` files are stateful, ordered automation steps against a live external website, full of carefully tuned selectors and Korean UI text matching — selector changes should follow the patterns already in `app/systems/hom/steps/login_common.py`. `app/systems/hom/scripts/login_phone.py` is a manual CLI entry point, not part of the manifest workflow.
- The claim-filing step (`app/systems/hom/steps/compensation_charge.py`) submits a real test claim (uploads PNGs found on the local Desktop, claim text `IT직원 테스트입니다. 바로 취소할 예정입니다.`); `app/systems/hom/steps/compensation_result.py` then verifies that claim's detail/submitted documents and `app/systems/hom/steps/compensation_cancel.py` finds and cancels exactly that claim (both share `app/systems/hom/steps/compensation_result_common.py` for list entry / row lookup / detail navigation) — all three are coupled by that literal claim text and "today" date matching. MHM has the parallel set under `app/systems/mhm/steps/` with the same coupling against the mobile UI.
- When adding a new system or changing an existing system's flow/selectors, update (or create) its scenario doc in `docs/scenarios/{system_code}.md` alongside the manifest — scenario details do not belong in `E2E_ARCHITECTURE.md`.
- `research/` contains throwaway probe scripts, not part of the app.
- User-facing strings (UI labels, log messages, README) are in Korean; keep that consistent.
