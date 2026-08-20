"""프론트엔드 게이트 FG-001~006 — check_architecture_gates.py 의 프론트 대응물.

디자인 시스템은 강제력이 없으면 6개월 안에 하드코딩으로 되돌아간다.
각 규칙은 실제로 발생했던 사고를 막는다(설계 문서 §3.6 참조).
"""

from __future__ import annotations

import re
from itertools import chain
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

TEMPLATE_DIR = "app/web/templates"
FRONTEND_DIR = "app/web/frontend"

# 스캔에서 통째로 제외할 디렉터리 이름. node_modules 는 서드파티 소스라 우리
# 규칙의 대상이 아니고(.css/.ts 가 하나만 들어와도 FG-002/004 가 오발화한다),
# 점으로 시작하는 디렉터리는 도구 캐시(.vite 등)다.
SKIP_DIRS = {"node_modules"}

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

# P3-1 이후에도 상태 색·라벨을 하드코딩한 채 남아 있는 템플릿.
# Step 7 이 화면을 이관할 때마다 한 줄씩 지운다. 비면 FG-006 이 완성된다.
# run.html·suite.html 은 P3-1 이 고쳤으므로 처음부터 여기에 없다.
FG006_ALLOWLIST = {
    "app/web/templates/base.html",
    "app/web/templates/execute.html",
    "app/web/templates/self_healing.html",
    "app/web/templates/admin/base.html",
    "app/web/templates/admin/users.html",
    # 이하 Step 7 이관 대기 — P3-1 실측에서 계획 초안 5개 외에 라벨/색 쌍이 남아 있었다.
    "app/web/templates/account/password.html",
    "app/web/templates/admin/index.html",
    "app/web/templates/admin/modules.html",
    "app/web/templates/admin/ops.html",
    "app/web/templates/admin/runs.html",
    "app/web/templates/admin/stats.html",
    "app/web/templates/anomalies.html",
    "app/web/templates/dashboard/partials/zone_a_kpi.html",
    "app/web/templates/insights.html",
    "app/web/templates/mobile_trigger.html",
    "app/web/templates/schedules.html",
}

# 상태 배지의 형태 — 배경+전경이 쌍으로 붙은 유틸리티. 장식용 단독 배경색과 구분된다.
_STATUS_COLOR_PAIR = re.compile(
    r"bg-(?:emerald|amber|red|orange|slate|zinc|blue|gray|green|yellow)-\d{2,3}"
    r"\s+text-\w+-\d{2,3}"
)

_STATUS_LABEL_LITERALS = (
    "정상",
    "이상징후",
    "점검실패",
    "입력 대기",
    "실행 중",
    "차단",
    "제외",
    "취소",
)

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


def _is_skipped(path: Path, base: Path) -> bool:
    """node_modules · 점 디렉터리 아래의 파일인가."""
    parts = path.relative_to(base).parts[:-1]  # 파일명 제외 = 디렉터리 성분만
    return any(part in SKIP_DIRS or part.startswith(".") for part in parts)


def _iter(root: Path, subdir: str, *suffixes: str):
    base = root / subdir
    if not base.exists():
        return
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if _is_skipped(path, base):
            continue
        yield path


def _iter_component_markup(root: Path):
    """컴포넌트가 자기 폴더에 두는 Jinja 매크로.

    `app/web/templates/**.html` 만 훑던 시절엔 이 파일들이 어떤 게이트에도
    걸리지 않았다 — macro.jinja 가 CDN·hex·/static 참조를 담아도 무사통과였다.
    """
    return _iter(root, FRONTEND_DIR, ".jinja")


def check_fg001_no_cdn(root: Path = REPO_ROOT) -> list[str]:
    """FG-001: 템플릿에 외부 CDN script/link 금지(차트 라이브러리 예외 제외)."""
    problems: list[str] = []
    for path in chain(_iter(root, TEMPLATE_DIR, ".html"), _iter_component_markup(root)):
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
    for path in _iter(root, FRONTEND_DIR, ".css", ".ts", ".jinja"):
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
    for path in chain(_iter(root, TEMPLATE_DIR, ".html"), _iter_component_markup(root)):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for ref in _STATIC_REF.findall(line):
                if ref in FG005_ALLOWLIST:
                    continue
                problems.append(
                    f"[FG-005] {_rel(path, root)}:{lineno} static 직접 참조 `{ref}` — "
                    "_assets.html 의 asset 매크로를 쓰거나 FG005_ALLOWLIST 에 등록하세요."
                )
    return problems


def check_fg006_no_template_status_literals(root: Path = REPO_ROOT) -> list[str]:
    """FG-006: 템플릿에 상태 색 쌍·상태 라벨 하드코딩 금지.

    run.html 이 자체 status_pill 맵을 들고 있어 ANOMALY/ERROR 배지가 회색으로
    렌더되던 사고(P3-1)를 막는다. FG-003 은 frontend/**/*.ts 만 보므로
    템플릿은 무검증이었다.
    """
    problems: list[str] = []
    for path in _iter(root, TEMPLATE_DIR, ".html"):
        rel = _rel(path, root)
        if rel in FG006_ALLOWLIST:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            pair = _STATUS_COLOR_PAIR.search(line)
            if pair:
                problems.append(
                    f"[FG-006] {rel}:{lineno} 상태 색 하드코딩 `{pair.group(0)}` — "
                    "components/status-badge/macro.jinja 의 status_badge 를 쓰세요."
                )
            for label in _STATUS_LABEL_LITERALS:
                if label in line:
                    # 실행 취소·전체 점검 취소 는 액션 버튼 문구이지 상태 배지 라벨이 아니다.
                    if label == "취소" and (
                        'id="run-cancel"' in line or 'id="suite-cancel"' in line
                    ):
                        continue
                    problems.append(
                        f"[FG-006] {rel}:{lineno} 상태 라벨 하드코딩 `{label}` — "
                        "status_badge_view(status).label 을 쓰세요."
                    )
    return problems


CHECKS = (
    check_fg001_no_cdn,
    check_fg002_no_hex,
    check_fg003_status_source,
    check_fg004_file_size,
    check_fg005_no_static_ref,
    check_fg006_no_template_status_literals,
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
    print("프론트엔드 게이트 통과 (FG-001~006)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
