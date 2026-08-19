// 자동 생성 파일 — 직접 수정하지 마세요.
// 출처: app/core/status_labels.py
// 생성: python3 scripts/gen_frontend_tokens.py

export type StatusTone = "passed" | "anomaly" | "error" | "running" | "waiting_input" | "blocked" | "skipped" | "cancelled" | "pending";

export const STATUS_TONES: readonly StatusTone[] = ["passed", "anomaly", "error", "running", "waiting_input", "blocked", "skipped", "cancelled", "pending"] as const;

export const STATUS_TONE_MAP: Record<string, StatusTone> = {
  "pending": "pending",
  "running": "running",
  "waiting_input": "waiting_input",
  "passed": "passed",
  "anomaly": "anomaly",
  "error": "error",
  "failed": "anomaly",
  "cancelled": "cancelled",
  "queued": "pending",
  "blocked": "blocked",
  "skipped": "skipped",
};

export const RUN_STATUS_LABELS: Record<string, string> = {
  "pending": "대기",
  "running": "실행 중",
  "waiting_input": "입력 대기",
  "passed": "정상",
  "anomaly": "이상징후",
  "error": "점검실패",
  "failed": "이상징후",
  "cancelled": "취소",
};

export const MODULE_STATUS_LABELS: Record<string, string> = {
  "pending": "대기",
  "queued": "대기",
  "running": "실행 중",
  "waiting_input": "입력 대기",
  "passed": "정상",
  "anomaly": "이상징후",
  "error": "점검실패",
  "failed": "이상징후",
  "blocked": "차단",
  "skipped": "제외",
  "cancelled": "취소",
};

export const SUITE_STATUS_LABELS: Record<string, string> = {
  "pending": "대기",
  "running": "실행 중",
  "waiting_input": "입력 대기",
  "passed": "정상",
  "anomaly": "이상징후",
  "error": "점검실패",
  "failed": "이상징후",
  "skipped": "제외",
  "cancelled": "취소",
};
