"""프론트엔드 게이트 FG-001~007 — check_architecture_gates.py 의 프론트 대응물.

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
MAIL_RENDERER = "app/notifications/report_renderer.py"

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

# 상태→표현 매핑을 아직 중복으로 들고 있는 템플릿(구조 탐지 기준 실측 4개).
# Step 7 이 화면을 이관할 때마다 한 줄씩 지운다. 비면 FG-006 이 완성된다 —
# 오탐이 섞이지 않으므로 이 전제는 실제로 성립한다.
# run.html·suite.html 은 P3-1 이 고쳤으므로 처음부터 여기에 없다.
FG006_ALLOWLIST = {
    # 상태→글리프 맵
    "app/web/templates/dashboard/partials/_macros.html",
    # 인라인 JS 의 상태→라벨+클래스 맵
    "app/web/templates/mobile_trigger.html",
    # <option value="PASSED">정상</option> 류 라벨 중복 + 필터 체크박스
    "app/web/templates/admin/runs.html",
    # 범례의 상태 라벨 중복
    "app/web/templates/schedules.html",
}

# FG-006 은 **어휘가 아니라 구조**를 본다.
#
# 초안은 상태 색 쌍(`bg-red-100 text-red-700`)과 한국어 라벨 리터럴을 탐지했는데,
# 실측에서 위반 70건 중 약 50건이 오탐이었다 — <body> 레이아웃 클래스, 네비 활성
# 표시 색, "취소" 버튼 문구, 히어로 산문("점검실패 N건 — 우선 확인이 필요합니다"),
# 페이지 이름("이상징후 인박스"), 부분 문자열 충돌("무인 실행 중 …"). 그 결과
# allowlist 가 16개로 불어 게이트가 run.html·suite.html 2개만 지키는 규칙이 됐고,
# 영구히 못 지울 항목이 섞여 "allowlist 가 비면 완성" 이라는 전제가 깨졌다.
#
# 실제 병은 어휘가 아니라 **상태→표현 매핑의 중복**이다. 그 구조만 탐지한다.
# (검증: 아래 두 규칙은 P3-1 이 고친 run.html:6 · suite.html:6 의 status_pill 을
#  둘 다 잡고, 위 오탐 6종은 모두 통과시킨다. 실측 16건/4파일, 오탐 0.)

# 규칙 A(MAP) — 상태 키로 인덱싱되는 리터럴 맵.
# `{'pending': ..., 'running': ...}` / `running: { label: ... }` 를 모두 잡는다.
_STATUS_MAP_KEYS = (
    "passed",
    "anomaly",
    "error",
    "running",
    "waiting_input",
    "blocked",
    "skipped",
    "cancelled",
    "pending",
    "queued",
    "failed",
)
_STATUS_MAP_KEY_RE = [
    re.compile(rf"(?<![\w-])['\"]?{key}['\"]?\s*:", re.IGNORECASE) for key in _STATUS_MAP_KEYS
]
# 한 줄에 상태 키가 둘 이상 콜론과 함께 나오면 맵 리터럴로 판정한다. 하나만으로는
# 평범한 CSS 선언(`color: …`)이나 산문과 구분되지 않는다.
_STATUS_MAP_MIN_KEYS = 2
# 맵 판정 창. allowlist 를 비우고 2~14줄을 실측했을 때 2~7은 같은 4파일을 잡되
# 같은 맵을 더 잘게 중복 보고했고, 8~14는 `_macros.html`·`admin/runs.html`·
# `mobile_trigger.html`·`schedules.html` 4파일/15건으로 안정화됐다.
# 그중 가장 좁게 같은 결과를 낸 최소값 8을 채택한다.
_STATUS_MAP_WINDOW = 8

# 규칙 B(PAIR) — enum 값과 한국어 라벨이 같은 줄에 함께 있음.
# `<option value="PASSED">정상</option>` 처럼 생성물(status.generated.ts)을 써야 하는 자리다.
# 라벨은 이 도메인 전용 어휘만 쓴다 — "취소"·"제외"·"차단"·"실행 중" 은 일반 한국어로
# 흔해서 단독 판정하면 버튼·산문을 오탐한다. enum 과 같은 줄이라는 조건이 문맥을 준다.
_ENUM_VALUES = (
    "PASSED",
    "ANOMALY",
    "ERROR",
    "RUNNING",
    "WAITING_INPUT",
    "BLOCKED",
    "SKIPPED",
    "CANCELLED",
    "FAILED",
)
_DOMAIN_LABELS = ("이상징후", "점검실패", "입력 대기", "정상", "취소")

_EXTERNAL_URL = re.compile(r"""(?:src|href)\s*=\s*["'](https?://[^"']+)["']""")
_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_STATIC_REF = re.compile(r"""(?:src|href)\s*=\s*["'](/static/[^"'?]+)""")
# 메일 상태 색 상수의 이름 규약. 레이아웃 색(PAGE_BG·INK·BORDER 등)은 상태와
# 무관하므로 대상이 아니다 — 이름으로 갈리므로 값 allowlist 가 필요 없다.
_MAIL_STATUS_CONST_RE = re.compile(r"^(PASS|FAIL|WARN|NEUTRAL|INFO)_(COLOR|SOFT_BG)\s*=\s*['\"]#")


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
    """FG-001: 템플릿에 외부 CDN script/link 금지. 예외 없음.

    차트 라이브러리 3종(Chart.js·ECharts·Plotly)에 예외를 두었던 이유는
    "vite.config.ts 가 단일 엔트리만 지원한다" 였다. P3-2 가 wall 엔트리를
    추가하며 그 전제가 소멸했고, P3-4 가 self-host 로 바꾸며 예외를 없앴다.
    """
    problems: list[str] = []
    for path in chain(_iter(root, TEMPLATE_DIR, ".html"), _iter_component_markup(root)):
        rel = _rel(path, root)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for url in _EXTERNAL_URL.findall(line):
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
    """FG-006: 템플릿이 상태→표현 매핑을 중복으로 들고 있는 것을 막는다.

    run.html 이 자체 status_pill 맵을 들고 있어 ANOMALY/ERROR 배지가 회색·영문으로
    렌더되던 사고(P3-1)를 막는다.

    맵 판정은 **블록 단위**다. 줄 단위이던 동안 한 줄에 한 항목씩 쓴 맵
    (mobile_trigger.html 의 STATUS_VIEW 8개)이 통째로 보이지 않았다(P3-4 §3.3).
    """
    problems: list[str] = []
    for path in _iter(root, TEMPLATE_DIR, ".html"):
        rel = _rel(path, root)
        if rel in FG006_ALLOWLIST:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        flagged_windows: list[int] = []
        for lineno, line in enumerate(lines, 1):
            window = "\n".join(lines[lineno - 1 : lineno - 1 + _STATUS_MAP_WINDOW])
            matched = [
                key
                for key, pattern in zip(_STATUS_MAP_KEYS, _STATUS_MAP_KEY_RE, strict=True)
                if pattern.search(window)
            ]
            if len(matched) >= _STATUS_MAP_MIN_KEYS:
                # 같은 맵이 창을 옮겨가며 여러 번 잡히는 것을 막는다 — 블록당 1건.
                if flagged_windows and lineno - flagged_windows[-1] < _STATUS_MAP_WINDOW:
                    continue
                flagged_windows.append(lineno)
                keys = ", ".join(matched[:4])
                problems.append(
                    f"[FG-006] {rel}:{lineno} 상태 키 맵 리터럴 (`{keys}`) — "
                    "components/status-badge/macro.jinja 의 status_badge 와 "
                    "status_badge_view(status) 를 쓰세요."
                )
                continue
            enum_hit = next((e for e in _ENUM_VALUES if e in line), None)
            label_hit = next((label for label in _DOMAIN_LABELS if label in line), None)
            if enum_hit and label_hit:
                problems.append(
                    f"[FG-006] {rel}:{lineno} enum 값 `{enum_hit}` 과 라벨 `{label_hit}` 이 "
                    "같은 줄에 하드코딩 — lib/status.generated.ts 또는 "
                    "status_badge_view(status).label 을 쓰세요."
                )
    return problems


def check_fg007_mail_status_colors_from_ssot(root: Path = REPO_ROOT) -> list[str]:
    """FG-007: 메일 상태 색은 status_colors.PALETTE 파생만.

    화면과 메일이 같은 상태를 다른 색으로 말하던 것을 P3-4 가 통일했다.
    되돌아가는 유일한 경로가 "여기에 hex 를 다시 적는 것" 이므로 그것만 막는다.
    """
    path = root / MAIL_RENDERER
    if not path.exists():
        return []
    problems: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if _MAIL_STATUS_CONST_RE.match(line):
            name = line.split("=", 1)[0].strip()
            problems.append(
                f"[FG-007] {MAIL_RENDERER}:{lineno} 상태 색 `{name}` 이 hex 리터럴 — "
                "app/core/status_colors.py 의 PALETTE 에서 파생시키세요."
            )
    return problems


CHECKS = (
    check_fg001_no_cdn,
    check_fg002_no_hex,
    check_fg003_status_source,
    check_fg004_file_size,
    check_fg005_no_static_ref,
    check_fg006_no_template_status_literals,
    check_fg007_mail_status_colors_from_ssot,
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
    print("프론트엔드 게이트 통과 (FG-001~007)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
