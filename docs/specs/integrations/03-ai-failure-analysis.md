# SPEC-INT-003: AI 실패 분석 (Gemini)

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-INT-003` |
| **상태** | `approved` |
| **구현** | `failure_analysis_subscriber.py`, `app/ai/` |

## 1. 개요

Run 종료 **후** 실패 모듈 diagnostic context로 Gemini 분석. **기본 비활성**.

## 2. FR-001: 트리거

`FailureAnalysisSubscriber` on `RunFinished`

## 3. FR-002: 입력

per-module: `current_url`, `dialog_messages`, screenshot artifact, logs (hydrated run)

## 3. FR-003: 출력

`FailureAnalysis` on module → `module_finished` WS re-emit (dashboard 갱신)

## 4. Env

Gemini API key, model chain — `check_docs_consistency` 검증

## 5. 수용 기준

### AC-001: 비활성

```gherkin
Given GEMINI unset
When Run finishes with ANOMALY
Then no API call, run completes normally
```

### AC-002: RunService 무의존

```gherkin
Given codebase
When grep RunService for gemini
Then no direct import
```
