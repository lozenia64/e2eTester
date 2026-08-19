"""status_labels.py → 프론트 토큰(CSS) · 타입/라벨(TS) 생성기.

생성물은 커밋한다(빌드 없이 코드를 읽을 수 있어야 하므로). CI 는 `--check` 로
재생성 diff 를 검사해 어긋남을 차단한다 — docs_consistency 와 동일한 패턴.

사용:
    python3 scripts/gen_frontend_tokens.py            # 생성/갱신
    python3 scripts/gen_frontend_tokens.py --check    # 불일치 시 exit 1
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.core.status_labels import (
    MODULE_STATUS_LABELS,
    RUN_STATUS_LABELS,
    STATUS_TONES,
    SUITE_STATUS_LABELS,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CSS_OUT = REPO_ROOT / "app/web/frontend/styles/tokens.generated.css"
TS_OUT = REPO_ROOT / "app/web/frontend/lib/status.generated.ts"

BANNER_CSS = (
    "/* 자동 생성 파일 — 직접 수정하지 마세요.\n"
    "   출처: app/core/status_labels.py\n"
    "   생성: python3 scripts/gen_frontend_tokens.py */\n"
)
BANNER_TS = (
    "// 자동 생성 파일 — 직접 수정하지 마세요.\n"
    "// 출처: app/core/status_labels.py\n"
    "// 생성: python3 scripts/gen_frontend_tokens.py\n"
)

# 톤별 팔레트(라이트 전용). Tailwind 표준 색값을 쓰되 기존 --st-* 선택을 계승한다.
# solid=칩/점, surface=배경, text=전경, border=테두리.
PALETTE: dict[str, dict[str, str]] = {
    "passed": {"solid": "#10b981", "surface": "#d1fae5", "text": "#047857", "border": "#6ee7b7"},
    "anomaly": {"solid": "#f59e0b", "surface": "#fef3c7", "text": "#b45309", "border": "#fcd34d"},
    "error": {"solid": "#ef4444", "surface": "#fee2e2", "text": "#b91c1c", "border": "#fca5a5"},
    "running": {"solid": "#3b82f6", "surface": "#dbeafe", "text": "#1d4ed8", "border": "#93c5fd"},
    # waiting_input 은 사람의 OTP 입력을 기다리는 상태 — running 과 반드시 구분한다.
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

VARIANTS = ("solid", "surface", "text", "border")


def _assert_palette_covers_tones() -> None:
    missing = [tone for tone in STATUS_TONES if tone not in PALETTE]
    if missing:
        msg = f"PALETTE 에 톤이 없습니다: {missing} — status_labels.STATUS_TONES 와 맞추세요."
        raise SystemExit(msg)


def render_css() -> str:
    _assert_palette_covers_tones()
    lines = [BANNER_CSS, ":root {"]
    for tone in STATUS_TONES:
        for variant in VARIANTS:
            lines.append(f"  --st-{tone}-{variant}: {PALETTE[tone][variant]};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _ts_label_map(name: str, labels: dict) -> str:
    # enum 값은 대문자("PASSED")지만 프론트 규약은 소문자다(app.js 가 lower() 로 정규화).
    # 생성 시점에 소문자로 맞춰 런타임 변환을 없앤다.
    body = "\n".join(f'  "{key.value.lower()}": "{value}",' for key, value in labels.items())
    return f"export const {name}: Record<string, string> = {{\n{body}\n}};\n"


def render_ts() -> str:
    _assert_palette_covers_tones()
    union = " | ".join(f'"{tone}"' for tone in STATUS_TONES)
    tone_list = ", ".join(f'"{tone}"' for tone in STATUS_TONES)
    parts = [
        BANNER_TS,
        f"export type StatusTone = {union};\n",
        f"export const STATUS_TONES: readonly StatusTone[] = [{tone_list}] as const;\n",
        _ts_label_map("RUN_STATUS_LABELS", RUN_STATUS_LABELS),
        _ts_label_map("MODULE_STATUS_LABELS", MODULE_STATUS_LABELS),
        _ts_label_map("SUITE_STATUS_LABELS", SUITE_STATUS_LABELS),
    ]
    return "\n".join(parts)


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    targets = ((CSS_OUT, render_css()), (TS_OUT, render_ts()))
    stale: list[str] = []
    for path, content in targets:
        if check_only:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != content:
                stale.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    if stale:
        print("생성물이 status_labels.py 와 어긋났습니다:")
        for name in stale:
            print(f"  - {name}")
        print("해결: python3 scripts/gen_frontend_tokens.py")
        return 1
    if not check_only:
        print(f"생성 완료: {CSS_OUT.name}, {TS_OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
