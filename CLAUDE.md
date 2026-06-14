# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An internal web-triggered E2E test platform (Korean-language UI/docs). A FastAPI server serves a dashboard where employees launch Playwright-based browser tests against the Hanwha General Insurance website ("HOM" system), watch live module status/logs over WebSocket, and submit OTP codes mid-run. See `E2E_ARCHITECTURE.md` for the full architecture doc (current state vs. target state). Per-system test scenarios live in `docs/scenarios/{system_code}.md` (one file per system, paired 1:1 with its manifest); the HOM scenario is `docs/scenarios/hom.md`.

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
    → ModuleRegistry (app/registry/loader.py + app/systems/*/manifest.yaml) — system/form/module definitions
    → InMemoryRunRepository (app/storage/run_repository.py) — runs, logs, WebSocket listener queues
    → HomWorkflowExecutor (app/systems/hom/executor.py) — Playwright sync API
      → app/systems/{system_code}/steps/*.py — the actual site automation
```

Key points that span multiple files:

- **Threading model**: Playwright's sync API objects must be used from the thread that created them. `RunService` creates a dedicated single-thread `ThreadPoolExecutor` per run (`max_workers=1`) and runs every step of that run's shared browser session on it. Async code (FastAPI/WebSocket) talks back via `asyncio.run_coroutine_threadsafe`. Don't call runtime/page objects from the event loop or another thread.
- **Shared browser session per run**: one browser/context/page (`HomWorkflowRuntime`) is created at the first module and reused by all subsequent modules, because login state must carry through contract inquiry and claim modules. The runtime is also held alive across the OTP pause (`PendingOtpState`) so the run can resume in the same session.
- **Manifest-driven modules**: `app/systems/hom/manifest.yaml` defines the run form (with `show_when` conditional fields keyed on `auth_method`), module order, `depends_on`, timeouts, and `workflow_step` names. `HomWorkflowExecutor` maps each `workflow_step` to a function in `app/systems/hom/steps/*.py`. Adding/reordering a step means touching both the manifest and the executor's step dispatch.
- **Auth methods**: `auth_method` may only be `phone` or `kakao` — `RunService.start_run` rejects anything else even though the form shows certificate options as placeholders. Phone auth pauses the run as `WAITING_INPUT` until OTP is submitted via `POST /api/runs/{run_id}/otp`; Kakao auth never pauses (it clicks 인증요청, waits ~60s for the user to approve in KakaoTalk, then clicks 인증완료).
- **State machine**: Run statuses are PENDING/RUNNING/WAITING_INPUT/PASSED/FAILED; modules add QUEUED and BLOCKED (a module is BLOCKED when a `depends_on` prerequisite didn't PASS). Status changes are published as WebSocket events (`run_*`, `module_*` in `app/api/ws_runs.py` consumers); the front-end (`app/web/static/app.js`) renders nodes/logs/OTP panel from these events.
- **Everything is in memory**: runs, logs, and OTP-wait state vanish on server restart; only `artifacts/` files persist. There is no cancel, retry, or parallel-run support yet.
- **Log capture**: step modules just `print()`; the executor intercepts stdout/stderr per step (`_LineWriter`) and fans lines out to both `execution.log` and live WebSocket log events.

## Conventions and cautions

- `app/systems/{system_code}/steps/*.py` files are stateful, ordered automation steps against a live external website, full of carefully tuned selectors and Korean UI text matching — selector changes should follow the patterns already in `app/systems/hom/steps/login_common.py`. `app/systems/hom/scripts/login_phone.py` is a manual CLI entry point, not part of the manifest workflow.
- The claim-filing step (`app/systems/hom/steps/compensation_charge.py`) submits a real test claim (uploads PNGs found on the local Desktop, claim text `IT직원 테스트입니다. 바로 취소할 예정입니다.`); `app/systems/hom/steps/compensation_result.py` then verifies that claim's detail/submitted documents and `app/systems/hom/steps/compensation_cancel.py` finds and cancels exactly that claim (both share `app/systems/hom/steps/compensation_result_common.py` for list entry / row lookup / detail navigation) — all three are coupled by that literal claim text and "today" date matching.
- When adding a new system or changing an existing system's flow/selectors, update (or create) its scenario doc in `docs/scenarios/{system_code}.md` alongside the manifest — scenario details do not belong in `E2E_ARCHITECTURE.md`.
- `research/` contains throwaway probe scripts, not part of the app.
- User-facing strings (UI labels, log messages, README) are in Korean; keep that consistent.
