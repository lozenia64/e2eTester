"""상태 톤의 색 SSOT — 화면 토큰과 메일이 같은 출처를 본다.

이 값이 scripts/gen_frontend_tokens.py 안에 있던 동안 메일 렌더러는 쓸 수 없었다.
"정상은 초록" 은 도메인 지식이지 빌드 도구의 소관이 아니다(P3-4 설계 D4).

톤 축은 app/core/status_labels.py 의 STATUS_TONES 가 정의한다 — 여기에 톤을
더하거나 빼지 말고 그쪽을 고친 뒤 맞춘다.
"""

from __future__ import annotations

PALETTE: dict[str, dict[str, str]] = {
    "passed": {"solid": "#10b981", "surface": "#d1fae5", "text": "#047857", "border": "#6ee7b7"},
    "anomaly": {"solid": "#f59e0b", "surface": "#fef3c7", "text": "#b45309", "border": "#fcd34d"},
    "error": {"solid": "#ef4444", "surface": "#fee2e2", "text": "#b91c1c", "border": "#fca5a5"},
    "running": {"solid": "#3b82f6", "surface": "#dbeafe", "text": "#1d4ed8", "border": "#93c5fd"},
    "waiting_input": {
        "solid": "#8b5cf6",
        "surface": "#ede9fe",
        "text": "#6d28d9",
        "border": "#c4b5fd",
    },
    "blocked": {"solid": "#f97316", "surface": "#ffedd5", "text": "#c2410c", "border": "#fdba74"},
    "skipped": {"solid": "#94a3b8", "surface": "#f1f5f9", "text": "#475569", "border": "#cbd5e1"},
    "cancelled": {"solid": "#71717a", "surface": "#f4f4f5", "text": "#52525b", "border": "#d4d4d8"},
    "pending": {"solid": "#a1a1aa", "surface": "#f4f4f5", "text": "#6b7280", "border": "#e4e4e7"},
}

# 톤 → 글리프. 색과 같은 파일에 두는 이유: 둘 다 "톤의 표현" 이라는 하나의 개념이고,
# 흩어 두면 톤이 늘 때 한쪽만 갱신되는 사고가 난다.
TONE_GLYPHS: dict[str, str] = {
    "passed": "✓",
    "anomaly": "!",
    "error": "×",
    "running": "●",
    "waiting_input": "●",
    "blocked": "—",
    "skipped": "—",
    "cancelled": "—",
    "pending": "○",
}
