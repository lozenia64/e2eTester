"""프론트엔드 게이트 FG-001~005 — check_architecture_gates.py 의 프론트 대응물.

디자인 시스템은 강제력이 없으면 6개월 안에 하드코딩으로 되돌아간다.
각 규칙은 실제로 발생했던 사고를 막는다(설계 문서 §3.6 참조).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

TEMPLATE_DIR = "app/web/templates"
FRONTEND_DIR = "app/web/frontend"

MAX_FILE_LINES = 400

# hex 를 담을 수 있는 유일한 예외 — 팔레트 원본.
# 스크립트로 생성되는 파일(tokens.generated.css, status.generated.ts)뿐 아니라
# 손으로 작성하는 primitive 팔레트(primitives.css)도 포함한다 — 3계층 토큰
# 모델(primitive → semantic/생성 토큰 → 컴포넌트)에서 둘 다 정당한 hex 출처다.
GENERATED_FILES = {
    "app/web/frontend/styles/tokens.generated.css",
    "app/web/frontend/lib/status.generated.ts",
    "app/web/frontend/styles/primitives.css",
}

# 프론트엔드 툴체인 도입 이전부터 있던 레거시 모놀리식 스타일시트.
# 아직 이들을 분리·모듈화하는 작업이 계획에 없어 당분간 grandfather 한다.
# 향후 단계에서 컴포넌트 단위로 쪼갤 때마다 여기서 한 줄씩 지운다. 비면 FG-004 가 완성된다.
FG004_ALLOWLIST = {
    "app/web/frontend/styles/app.css",
    "app/web/frontend/styles/dashboard.css",
}

# P3 이관 완료 전까지 템플릿이 직접 로드하는 레거시 페이지 스크립트.
# 화면을 이관할 때마다 여기서 한 줄씩 지운다. 비면 FG-005 가 완성된다.
FG005_ALLOWLIST = {
    "/static/admin-dashboard.js",
    "/static/admin-ops.js",
    "/static/admin-runs.js",
    "/static/admin-stats.js",
    "/static/anomalies.js",
    "/static/app.js",
    "/static/dashboard.js",
    "/static/healing.js",
    "/static/insights.js",
    "/static/mobile-nav.js",
    "/static/nav-badges.js",
    "/static/presets.js",
    "/static/schedules.js",
    "/static/favicon.svg",
}

# 차트 라이브러리(Chart.js/ECharts/Plotly) CDN 예외 — 이 계획(P1)의 범위 밖이다.
# self-host 하려면 npm 의존성 추가 + 페이지별 Vite 엔트리가 필요한데, 현재
# vite.config.ts 는 단일 엔트리만 지원해 그 구조 변경은 이후 작업으로 미룬다.
# FG005_ALLOWLIST 와 달리 파일 전체가 아니라 "파일 + 정확한 URL" 쌍만 예외로
# 둔다 — 내일 admin/runs.html 에 엉뚱한 CDN 이 추가되면 여전히 걸려야 한다.
FG001_EXCEPTIONS: dict[str, set[str]] = {
    "app/web/templates/insights.html": {
        "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js",
    },
    "app/web/templates/admin/runs.html": {
        "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js",
        "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js",
    },
    "app/web/templates/admin/stats.html": {
        "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js",
    },
}

_EXTERNAL_URL = re.compile(r"""(?:src|href)\s*=\s*["'](https?://[^"']+)["']""")
_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_STATIC_REF = re.compile(r"""(?:src|href)\s*=\s*["'](/static/[^"'?]+)""")


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _iter(root: Path, subdir: str, *suffixes: str):
    base = root / subdir
    if not base.exists():
        return
    for path in sorted(base.rglob("*")):
        if path.is_file() and path.suffix in suffixes:
            yield path


def check_fg001_no_cdn(root: Path = REPO_ROOT) -> list[str]:
    """FG-001: 템플릿에 외부 CDN script/link 금지(차트 라이브러리 예외 제외)."""
    problems: list[str] = []
    for path in _iter(root, TEMPLATE_DIR, ".html"):
        rel = _rel(path, root)
        exceptions = FG001_EXCEPTIONS.get(rel, set())
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for url in _EXTERNAL_URL.findall(line):
                if url in exceptions:
                    continue
                problems.append(
                    f"[FG-001] {rel}:{lineno} 외부 자산 참조 `{url}` — "
                    "npm 으로 self-host 하고 asset 매크로를 쓰세요."
                )
    return problems


def check_fg002_no_hex(root: Path = REPO_ROOT) -> list[str]:
    """FG-002: frontend/ 내 하드코딩 hex 금지(생성물 제외)."""
    problems: list[str] = []
    for path in _iter(root, FRONTEND_DIR, ".css", ".ts"):
        rel = _rel(path, root)
        if rel in GENERATED_FILES:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for hex_value in _HEX.findall(line):
                problems.append(
                    f"[FG-002] {rel}:{lineno} 하드코딩 색 `{hex_value}` — "
                    "var(--st-*) 또는 var(--c-*) 토큰을 쓰세요."
                )
    return problems


def check_fg003_status_source(root: Path = REPO_ROOT) -> list[str]:
    """FG-003: 상태 라벨은 status.generated.ts 경유만.

    `*.test.ts` 는 예외다 — 컴포넌트가 실제로 올바른 한국어 라벨을 렌더하는지
    검증하려면 단언문에 기대값 리터럴이 필요하다(예: `expect(statusLabel("error")).toBe("점검실패")`).
    이 규칙이 막으려는 건 컴포넌트/엔트리 소스가 라벨을 하드코딩하는 것이지,
    테스트가 생성된 라벨을 검증하는 것이 아니다.
    """
    labels = ("정상", "이상징후", "점검실패", "입력 대기", "실행 중", "차단", "제외", "취소")
    problems: list[str] = []
    for path in _iter(root, FRONTEND_DIR, ".ts"):
        rel = _rel(path, root)
        if rel in GENERATED_FILES or rel.endswith(".test.ts"):
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for label in labels:
                if f'"{label}"' in line or f"'{label}'" in line:
                    problems.append(
                        f"[FG-003] {rel}:{lineno} 상태 라벨 `{label}` 하드코딩 — "
                        "lib/status.generated.ts 의 라벨 맵을 임포트하세요."
                    )
    return problems


def check_fg004_file_size(root: Path = REPO_ROOT) -> list[str]:
    """FG-004: 엔트리·컴포넌트 400줄 상한(레거시 모놀리식 스타일시트는 allowlist 제외)."""
    problems: list[str] = []
    for path in _iter(root, FRONTEND_DIR, ".ts", ".css"):
        rel = _rel(path, root)
        if rel in GENERATED_FILES or rel in FG004_ALLOWLIST:
            continue
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > MAX_FILE_LINES:
            problems.append(
                f"[FG-004] {rel} 가 {lines}줄 (상한 {MAX_FILE_LINES}) — 책임 단위로 분리하세요."
            )
    return problems


def check_fg005_no_static_ref(root: Path = REPO_ROOT) -> list[str]:
    """FG-005: static/ 직접 참조 금지(allowlist 제외). manifest 경유만."""
    problems: list[str] = []
    for path in _iter(root, TEMPLATE_DIR, ".html"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for ref in _STATIC_REF.findall(line):
                if ref in FG005_ALLOWLIST:
                    continue
                problems.append(
                    f"[FG-005] {_rel(path, root)}:{lineno} static 직접 참조 `{ref}` — "
                    "_assets.html 의 asset 매크로를 쓰거나 FG005_ALLOWLIST 에 등록하세요."
                )
    return problems


CHECKS = (
    check_fg001_no_cdn,
    check_fg002_no_hex,
    check_fg003_status_source,
    check_fg004_file_size,
    check_fg005_no_static_ref,
)


def main() -> int:
    problems: list[str] = []
    for check in CHECKS:
        problems.extend(check(REPO_ROOT))
    if problems:
        print(f"프론트엔드 게이트 위반 {len(problems)}건:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("프론트엔드 게이트 통과 (FG-001~005)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
