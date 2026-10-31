#!/usr/bin/env python3
"""문서-코드 정합성 가드 (Docs ↔ Source consistency guard).

기계적으로 추출 가능한 '사실'만 골라 소스코드를 단일 진실원천(SSOT)으로 두고,
문서가 소스와 어긋났는지 검사한다. 문서 표류(drift)를 전수 수작업 감사 없이 조기에
잡기 위한 경량 장치이며, 사람이 읽고 판단하는 서술(설명 문장)은 검사하지 않는다.

검사 항목:
  1. 시스템 manifest ↔ 시나리오 문서 1:1 대응 (docs/scenarios/{code}.md)
  2. manifest 의 모든 module_id 가 짝이 되는 시나리오 문서에 등장하는지
  3. 시스템 manifest ↔ SDD Spec 1:1 대응 (docs/specs/systems/{code}.md)
  4. manifest 의 모든 module_id 가 짝이 되는 SDD Spec에 등장하는지
  5. docs/specs/README.md 인덱스의 .md 링크 대상 파일이 실재하는지
  6. FastAPI 라우트(메서드+경로)가 E2E_ARCHITECTURE.md 에 문서화되어 있는지
     — 스캔 범위는 app/ 전체(app/api 외 app/auth/router.py·app/main.py 포함)이며,
       `include_in_schema=False` 라우트는 문서화 대상에서 제외한다(§5.2 인프라 라우트 규칙)
  6. 코드가 읽는 환경변수가 docs/INSTALL.md 와 .env.example 양쪽에 모두 문서화되어 있는지
  7. 기본 Gemini 모델 체인(코드 상수)이 docs/INSTALL.md / .env.example 와 일치하는지
  8. (역방향) E2E_ARCHITECTURE.md 가 문서화한 라우트가 실제 코드에 존재하는지 — 유령 라우트 차단
  9. (역방향) docs/INSTALL.md/.env.example 의 환경변수가 실제로 코드에서 읽히는지 — 죽은 변수 차단
  10. E2E_ARCHITECTURE.md §4 폴더 트리에 나열된 경로가 실제로 존재하는지 — 유령 파일 차단
  11. (역방향) 주요 디렉터리(app/api, app/contexts, docs)의 항목이 §4 폴더 트리에 누락 없이 등재되어 있는지

사용법:
  python3 scripts/check_docs_consistency.py            # 전체 검사
  python3 scripts/check_docs_consistency.py --verbose  # 통과 항목까지 상세 출력

종료 코드: 모두 통과 0, 하나라도 실패 1 (CI 게이트로 사용 가능).

거버넌스 규칙(SSOT 매트릭스/PR 체크리스트)은 docs/DOCS_GOVERNANCE.md 참고.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.platform.stdio_utf8 import configure_stdio_utf8

configure_stdio_utf8()


try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - 의존성 안내
    print(
        "[error] PyYAML 이 필요합니다. `python3 -m pip install -r requirements.txt` 실행 후 다시 시도하세요."
    )
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent

MANIFEST_GLOB = "app/systems/*/manifest.yaml"
SCENARIO_DIR = REPO_ROOT / "docs" / "scenarios"
SPECS_SYSTEMS_DIR = REPO_ROOT / "docs" / "specs" / "systems"
SPECS_INDEX_DOC = REPO_ROOT / "docs" / "specs" / "README.md"
SPEC_INDEX_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+\.md)\)")
ARCHITECTURE_DOC = REPO_ROOT / "docs" / "E2E_ARCHITECTURE.md"
README_DOC = REPO_ROOT / "README.md"
INSTALL_DOC = REPO_ROOT / "docs" / "INSTALL.md"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
API_DIR = REPO_ROOT / "app" / "api"
GEMINI_MODELS_SRC = REPO_ROOT / "app" / "ai" / "gemini_models.py"

# 코드가 동적으로 조합하는(접미사가 붙는) 환경변수 prefix 는 prefix 문자열만 문서에서 확인한다.
DYNAMIC_ENV_PREFIX_RE = re.compile(r"""f["'](E2E_[A-Z0-9_]+_)\{""")
LITERAL_ENV_RE = re.compile(
    r"""(?:resolve_env_value|resolve_env_with_source|env_flag)\(\s*["']([A-Z][A-Z0-9_]+)["']"""
)
SETTINGS_ALIAS_RE = re.compile(r"""validation_alias\s*=\s*["']([A-Z][A-Z0-9_]+)["']""")
OS_ENV_RE = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*["']([A-Z][A-Z0-9_]+)["']|os\.environ\[\s*["']([A-Z][A-Z0-9_]+)["']"""
)
ROUTER_PREFIX_RE = re.compile(r"""APIRouter\([^)]*prefix\s*=\s*["']([^"']*)["']""")
# @router.* 와 @app.* 데코레이터 공용. 셋째 그룹(데코레이터 나머지)으로 include_in_schema=False
# (§5.2 인프라 라우트 제외 규칙 — 문서화·검사 대상 아님)를 식별한다.
ROUTE_DECORATOR_RE = re.compile(
    r"""@(?:router|app)\.(get|post|put|patch|delete|websocket)\(\s*["']([^"']*)["']([^\n]*)"""
)
# 문서(E2E_ARCHITECTURE.md)에 백틱으로 표기된 라우트: `METHOD /path`
DOC_ROUTE_RE = re.compile(r"""`(GET|POST|PUT|PATCH|DELETE|WS)\s+(/[^\s`]*)`""")
# 경로 파라미터({run_id}, {module_id:path} 등)는 이름이 달라도 같은 라우트로 취급한다.
ROUTE_PARAM_RE = re.compile(r"\{[^}]*\}")
# 문서에 등장하는 환경변수 후보. 프로젝트 관례상 E2E_*/GEMINI_* 만 환경변수다.
DOC_ENV_RE = re.compile(r"\b((?:E2E|GEMINI)_[A-Z0-9_]+)\b")
# 환경변수처럼 보이지만 아닌 토큰(파일명 등) — 역방향 검사(7)에서 제외.
DOC_ENV_EXEMPT = {"E2E_ARCHITECTURE"}
# §4 트리 실재 검사(8)에서 존재하지 않아도 되는 런타임 생성 디렉터리.
TREE_RUNTIME_DIRS = {"artifacts"}
MODEL_CHAIN_RE = re.compile(r"""DEFAULT_GEMINI_MODEL_CHAIN[^=]*=\s*\((.*?)\)""", re.DOTALL)


@dataclass
class CheckResult:
    name: str
    problems: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _iter_py_sources(*roots: Path):
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            yield path, _read(path)


# --------------------------------------------------------------------------- #
# 1 & 2. manifest ↔ scenario 문서
# --------------------------------------------------------------------------- #
def _load_manifests() -> dict[str, dict]:
    manifests: dict[str, dict] = {}
    for manifest_path in sorted(REPO_ROOT.glob(MANIFEST_GLOB)):
        data = yaml.safe_load(_read(manifest_path)) or {}
        system_code = data.get("system_code") or manifest_path.parent.name
        manifests[system_code] = data
    return manifests


def check_systems_have_scenarios(manifests: dict[str, dict]) -> CheckResult:
    result = CheckResult("시스템 manifest ↔ 시나리오 문서 1:1 대응")
    manifest_codes = set(manifests)
    scenario_codes = {p.stem for p in SCENARIO_DIR.glob("*.md")}

    for code in sorted(manifest_codes - scenario_codes):
        result.problems.append(
            f"manifest 는 있으나 시나리오 문서가 없음: docs/scenarios/{code}.md 를 추가하세요."
        )
    for code in sorted(scenario_codes - manifest_codes):
        result.problems.append(
            f"시나리오 문서는 있으나 등록된 manifest 가 없음: docs/scenarios/{code}.md "
            f"(app/systems/{code}/manifest.yaml 누락 또는 문서 삭제 필요)."
        )
    result.details.append(
        f"manifest {len(manifest_codes)}개, 시나리오 문서 {len(scenario_codes)}개 확인: "
        f"{', '.join(sorted(manifest_codes))}"
    )
    return result


def check_scenario_lists_modules(manifests: dict[str, dict]) -> CheckResult:
    result = CheckResult("manifest module_id 가 시나리오 문서에 등장")
    checked = 0
    for code, data in sorted(manifests.items()):
        scenario_path = SCENARIO_DIR / f"{code}.md"
        if not scenario_path.exists():
            continue  # 1번 검사에서 이미 보고됨
        doc_text = _read(scenario_path)
        for module in data.get("modules", []):
            module_id = module.get("module_id")
            if not module_id:
                continue
            checked += 1
            if module_id not in doc_text:
                result.problems.append(
                    f"[{code}] module_id `{module_id}` 가 docs/scenarios/{code}.md 에 없음 "
                    f"(모듈 추가/이름변경 시 시나리오 문서 동시 갱신 필요)."
                )
    result.details.append(f"module_id {checked}개를 시나리오 문서와 대조했습니다.")
    return result


def check_systems_have_specs(manifests: dict[str, dict]) -> CheckResult:
    result = CheckResult("시스템 manifest ↔ SDD Spec 1:1 대응")
    manifest_codes = set(manifests)
    spec_codes = {p.stem for p in SPECS_SYSTEMS_DIR.glob("*.md") if not p.name.startswith("_")}

    for code in sorted(manifest_codes - spec_codes):
        result.problems.append(
            f"manifest 는 있으나 SDD Spec 이 없음: docs/specs/systems/{code}.md 를 추가하세요."
        )
    for code in sorted(spec_codes - manifest_codes):
        result.problems.append(
            f"SDD Spec 은 있으나 등록된 manifest 가 없음: docs/specs/systems/{code}.md "
            f"(app/systems/{code}/manifest.yaml 누락 또는 문서 삭제 필요)."
        )
    result.details.append(
        f"manifest {len(manifest_codes)}개, SDD Spec {len(spec_codes)}개 확인: "
        f"{', '.join(sorted(manifest_codes))}"
    )
    return result


def check_spec_lists_modules(manifests: dict[str, dict]) -> CheckResult:
    result = CheckResult("manifest module_id 가 SDD Spec 에 등장")
    checked = 0
    for code, data in sorted(manifests.items()):
        spec_path = SPECS_SYSTEMS_DIR / f"{code}.md"
        if not spec_path.exists():
            continue  # check_systems_have_specs 에서 이미 보고됨
        doc_text = _read(spec_path)
        for module in data.get("modules", []):
            module_id = module.get("module_id")
            if not module_id:
                continue
            checked += 1
            if module_id not in doc_text:
                result.problems.append(
                    f"[{code}] module_id `{module_id}` 가 docs/specs/systems/{code}.md 에 없음 "
                    f"(모듈 추가/이름변경 시 SDD Spec 동시 갱신 필요)."
                )
    result.details.append(f"module_id {checked}개를 SDD Spec 과 대조했습니다.")
    return result


def check_spec_index_links_exist() -> CheckResult:
    """docs/specs/README.md 인덱스에 나열된 Spec 파일이 실제로 존재하는지 검사."""
    result = CheckResult("docs/specs/README.md 인덱스 링크 파일 실재")
    if not SPECS_INDEX_DOC.exists():
        result.problems.append("docs/specs/README.md 가 없습니다.")
        return result
    text = _read(SPECS_INDEX_DOC)
    specs_root = SPECS_INDEX_DOC.parent
    checked = 0
    seen: set[str] = set()
    for raw in SPEC_INDEX_LINK_RE.findall(text):
        rel = raw.split("#", 1)[0].strip()
        if not rel or rel.startswith("http"):
            continue
        if rel in seen:
            continue
        seen.add(rel)
        checked += 1
        target = specs_root / rel
        if not target.is_file():
            result.problems.append(
                f"인덱스 링크 `{rel}` 대상 파일이 없음 "
                f"(docs/specs/README.md 또는 Spec 파일 경로 갱신 필요)."
            )
    result.details.append(f"인덱스 .md 링크 {checked}개의 실재를 확인했습니다.")
    return result


VALID_EXECUTION_PROFILES = frozenset({"heavy", "light", "interactive"})


def check_manifest_execution_profile(manifests: dict[str, dict]) -> CheckResult:
    """manifest execution_profile 이 허용 값인지 검사."""
    result = CheckResult("manifest execution_profile 값 (heavy|light|interactive)")
    for code, data in sorted(manifests.items()):
        profile = data.get("execution_profile", "light")
        if profile not in VALID_EXECUTION_PROFILES:
            result.problems.append(
                f"[{code}] execution_profile={profile!r} — "
                f"heavy|light|interactive 중 하나여야 합니다."
            )
    result.details.append(f"manifest {len(manifests)}개의 execution_profile 확인")
    return result


# --------------------------------------------------------------------------- #
# 3. API 라우트 문서화
# --------------------------------------------------------------------------- #
def _extract_routes() -> list[tuple[str, str]]:
    """app/ 전체에서 실제 등록 라우트(메서드, 경로)를 추출한다.

    app/api 뿐 아니라 app/auth/router.py 와 app/main.py(@app.*)도 스캔한다 — 문서화된
    /login·/auth/* 라우트가 검사 사각에 있던 문제를 막는다. `include_in_schema=False` 가
    붙은 라우트(파비콘 등 인프라 자산)는 §5.2 규칙에 따라 문서화 대상이 아니므로 제외한다.
    """
    routes: list[tuple[str, str]] = []
    for _path, text in _iter_py_sources(REPO_ROOT / "app"):
        prefix_match = ROUTER_PREFIX_RE.search(text)
        prefix = prefix_match.group(1) if prefix_match else ""
        for method, route_path, rest in ROUTE_DECORATOR_RE.findall(text):
            if "include_in_schema=False" in rest.replace(" ", ""):
                continue
            full = (prefix + route_path) or "/"
            token = "WS" if method == "websocket" else method.upper()
            routes.append((token, full))
    return routes


def _normalize_route(path: str) -> str:
    # 쿼리스트링은 라우트 정체성이 아니다(`GET /api/runs?scope=today` == `GET /api/runs`).
    # 경로 파라미터는 이름 차이를 무시한다(`{run_id}` == `{id}`).
    return ROUTE_PARAM_RE.sub("{}", path.split("?", 1)[0])


def check_api_routes_documented() -> CheckResult:
    result = CheckResult("API 라우트가 E2E_ARCHITECTURE.md 에 문서화")
    doc_text = _read(ARCHITECTURE_DOC)
    routes = _extract_routes()
    for method, full in routes:
        needle = f"{method} {full}"
        if needle not in doc_text:
            result.problems.append(
                f"라우트 `{needle}` 가 E2E_ARCHITECTURE.md (API 목록)에 없음 "
                f"(엔드포인트 추가/변경 시 §5.2 동시 갱신 필요)."
            )
    result.details.append(f"라우트 {len(routes)}개를 E2E_ARCHITECTURE.md 와 대조했습니다.")
    return result


def check_documented_routes_exist() -> CheckResult:
    """역방향: 문서가 주장하는 라우트가 코드에 실제로 존재하는지(유령 라우트 차단).

    코드→문서 단방향 검사만으로는 삭제된 엔드포인트가 문서에 남아도 통과한다. 경로
    파라미터 이름 차이는 무시하고(`{run_id}` == `{id}`) 메서드+경로 골격으로 대조한다.
    """
    result = CheckResult("E2E_ARCHITECTURE.md 의 라우트가 코드에 존재 (유령 라우트 없음)")
    doc_text = _read(ARCHITECTURE_DOC)
    code_routes = {(method, _normalize_route(path)) for method, path in _extract_routes()}
    documented = sorted({(m, p) for m, p in DOC_ROUTE_RE.findall(doc_text)})
    for method, path in documented:
        if (method, _normalize_route(path)) not in code_routes:
            result.problems.append(
                f"문서화된 라우트 `{method} {path}` 가 코드에 없음 "
                f"(엔드포인트 삭제/변경 시 E2E_ARCHITECTURE.md 에서도 제거/갱신 필요)."
            )
    result.details.append(f"문서 라우트 {len(documented)}개를 코드 라우트와 대조했습니다.")
    return result


# --------------------------------------------------------------------------- #
# 4. 환경변수 문서화
# --------------------------------------------------------------------------- #
def _collect_env_names() -> tuple[set[str], set[str]]:
    """설정을 읽는 런타임 프로세스(`app/` + `worker/`)의 프로젝트 환경변수 이름을 모은다.

    `worker/` 를 포함해야 하는 이유: 씬 워커는 API 와 별개 프로세스로 기동하면서
    자기 바인드 주소를 직접 `os.environ` 에서 읽는다. `app/` 만 훑던 동안
    `E2E_WORKER_HTTP_HOST`/`_PORT` 가 어느 문서에도 없이 새어나갔다.
    `scripts/` 는 개발 도구라 제외한다 — CI 전용 변수(GITHUB_* 등)까지 설치 문서에
    올리라고 요구하게 된다. OS 기본 환경변수(LOCALAPPDATA 등)는 제외하고 프로젝트
    환경변수(E2E_*/GEMINI_*)만 대상으로 삼는다.
    """
    literals: set[str] = set()
    prefixes: set[str] = set()
    for _path, text in _iter_py_sources(REPO_ROOT / "app", REPO_ROOT / "worker"):
        literals.update(LITERAL_ENV_RE.findall(text))
        literals.update(SETTINGS_ALIAS_RE.findall(text))
        for grp in OS_ENV_RE.findall(text):
            literals.update(name for name in grp if name)
        prefixes.update(DYNAMIC_ENV_PREFIX_RE.findall(text))
    project_literals = {name for name in literals if name.startswith(("E2E_", "GEMINI_"))}
    return project_literals, prefixes


def check_env_vars_documented() -> CheckResult:
    result = CheckResult("코드가 읽는 환경변수가 docs/INSTALL.md 와 .env.example 양쪽에 문서화")
    literals, prefixes = _collect_env_names()
    for doc_path in (INSTALL_DOC, ENV_EXAMPLE):
        doc_label = doc_path.relative_to(REPO_ROOT).as_posix()
        doc_text = _read(doc_path)
        for name in sorted(literals):
            if name not in doc_text:
                result.problems.append(
                    f"환경변수 `{name}` 가 `{doc_label}` 에 문서화되지 않음 "
                    f"(docs/INSTALL.md 와 .env.example 양쪽 모두 갱신 필요)."
                )
        for prefix in sorted(prefixes):
            if prefix not in doc_text:
                result.problems.append(
                    f"동적 환경변수 prefix `{prefix}{{...}}` 가 `{doc_label}` 에 문서화되지 않음."
                )
    result.details.append(
        f"환경변수 {len(literals)}개 + 동적 prefix {len(prefixes)}개를 "
        f"docs/INSTALL.md 및 .env.example 각각과 대조했습니다."
    )
    return result


def check_documented_env_vars_used() -> CheckResult:
    """역방향: 문서가 안내하는 환경변수를 코드가 실제로 읽는지(죽은 변수 차단).

    문서에만 남은 변수는 사용자를 헛돌게 한다. 코드의 리터럴 이름과 동적 prefix
    (`E2E_EMAIL_RECIPIENTS_{...}` 류) 양쪽과 대조하고, 환경변수처럼 보이지만 아닌
    토큰(DOC_ENV_EXEMPT — 예: 파일명 E2E_ARCHITECTURE)은 제외한다.
    """
    result = CheckResult("docs/INSTALL.md/.env.example 의 환경변수를 코드가 읽음 (죽은 변수 없음)")
    doc_text = _read(INSTALL_DOC) + "\n" + _read(ENV_EXAMPLE)
    literals, prefixes = _collect_env_names()
    documented = sorted(set(DOC_ENV_RE.findall(doc_text)) - DOC_ENV_EXEMPT)
    for name in documented:
        if name in literals:
            continue
        if any(name.startswith(prefix) for prefix in prefixes):
            continue
        result.problems.append(
            f"문서화된 환경변수 `{name}` 를 읽는 코드가 없음 "
            f"(변수 제거/개명 시 docs/INSTALL.md/.env.example 에서도 제거/갱신 필요)."
        )
    result.details.append(f"문서 환경변수 {len(documented)}개를 코드와 대조했습니다.")
    return result


# --------------------------------------------------------------------------- #
# 8. 폴더 트리 실재 검증
# --------------------------------------------------------------------------- #
def _extract_folder_tree_entries() -> list[tuple[str, bool]]:
    """E2E_ARCHITECTURE.md §4 트리 블록을 (상대경로, is_dir) 목록으로 파싱한다.

    들여쓰기 2칸 = 1단계. `# 주석` 은 무시하고, `a / b / c*.png` 처럼 한 줄에 여러
    항목이 오면 각각을 파일 항목으로 본다(글롭 패턴 허용).
    """
    doc_text = _read(ARCHITECTURE_DOC)
    section = doc_text.split("## 4. 현재 폴더 구조", 1)[1]
    block = section.split("```text", 1)[1].split("```", 1)[0]

    entries: list[tuple[str, bool]] = []
    stack: list[str] = []
    for line in block.splitlines():
        if not line.strip():
            continue
        depth = (len(line) - len(line.lstrip(" "))) // 2
        name_part = line.split("#", 1)[0].strip()
        if not name_part:
            continue
        if depth == 0:  # 루트(e2eTester/) 자체
            stack = []
            continue
        stack = stack[: depth - 1]
        parent = "/".join(stack)
        tokens = [token.strip() for token in name_part.split(" / ") if token.strip()]
        for token in tokens:
            is_dir = token.endswith("/")
            rel = f"{parent}/{token.rstrip('/')}" if parent else token.rstrip("/")
            entries.append((rel, is_dir))
        if len(tokens) == 1 and tokens[0].endswith("/"):
            stack.append(tokens[0].rstrip("/"))
    return entries


def check_folder_tree_paths_exist() -> CheckResult:
    """E2E_ARCHITECTURE.md §4 트리의 경로가 실제로 존재하는지(유령 파일 차단)."""
    result = CheckResult("E2E_ARCHITECTURE.md §4 폴더 트리 경로가 실재 (유령 파일 없음)")
    entries = _extract_folder_tree_entries()
    for rel, is_dir in entries:
        if is_dir and rel.split("/")[-1] in TREE_RUNTIME_DIRS:
            continue  # 런타임에 생성되는 디렉터리(신선한 클론엔 없음)
        target = REPO_ROOT / rel
        if "*" in rel:
            parent = target.parent
            if not (parent.exists() and any(parent.glob(target.name))):
                result.problems.append(f"§4 트리의 글롭 `{rel}` 에 매칭되는 파일이 없음.")
            continue
        if not target.exists():
            result.problems.append(
                f"§4 트리에 있으나 실제로 없는 경로: `{rel}` "
                f"(파일 이동/삭제 시 폴더 트리 동시 갱신 필요)."
            )
    result.details.append(f"트리 경로 {len(entries)}개의 실재를 확인했습니다.")
    return result


def check_key_dirs_documented_in_tree() -> CheckResult:
    """역방향: 주요 디렉터리의 1단계 항목이 E2E_ARCHITECTURE.md §4 폴더 트리에 등재되어 있는지."""
    result = CheckResult("주요 디렉터리(app/api, app/contexts, docs) 항목이 §4 폴더 트리에 등재")
    documented_paths = {rel for rel, _ in _extract_folder_tree_entries()}
    checked = 0

    for api_file in sorted((REPO_ROOT / "app" / "api").glob("*.py")):
        if api_file.name == "__init__.py":
            continue
        checked += 1
        rel = api_file.relative_to(REPO_ROOT).as_posix()
        if rel not in documented_paths:
            result.problems.append(
                f"`{rel}` 가 E2E_ARCHITECTURE.md §4 폴더 트리에 없음 "
                f"(라우터/모듈 추가 시 §4 동시 갱신 필요)."
            )

    for ctx_dir in sorted((REPO_ROOT / "app" / "contexts").iterdir()):
        if not ctx_dir.is_dir() or ctx_dir.name.startswith("__"):
            continue
        checked += 1
        rel = ctx_dir.relative_to(REPO_ROOT).as_posix()
        if rel not in documented_paths:
            result.problems.append(
                f"바운디드 컨텍스트 `{rel}/` 가 E2E_ARCHITECTURE.md §4 폴더 트리에 없음."
            )

    for doc_entry in sorted((REPO_ROOT / "docs").iterdir()):
        if doc_entry.name.startswith("."):
            continue
        checked += 1
        rel = doc_entry.relative_to(REPO_ROOT).as_posix()
        if rel not in documented_paths:
            result.problems.append(f"`{rel}` 가 E2E_ARCHITECTURE.md §4 폴더 트리에 없음.")

    result.details.append(f"주요 디렉터리 항목 {checked}개를 §4 폴더 트리와 대조했습니다.")
    return result


# --------------------------------------------------------------------------- #
# 5. 기본 Gemini 모델 체인
# --------------------------------------------------------------------------- #
def check_model_chain_matches() -> CheckResult:
    result = CheckResult("기본 Gemini 모델 체인이 docs/INSTALL.md/.env.example 와 일치")
    src = _read(GEMINI_MODELS_SRC)
    match = MODEL_CHAIN_RE.search(src)
    if not match:
        result.problems.append(
            "app/ai/gemini_models.py 에서 DEFAULT_GEMINI_MODEL_CHAIN 을 파싱하지 못했습니다."
        )
        return result
    models = re.findall(r"""["']([^"']+)["']""", match.group(1))
    chain = "|".join(models)
    result.details.append(f"코드 기본 모델 체인: {chain}")
    for doc_path in (INSTALL_DOC, ENV_EXAMPLE):
        if chain not in _read(doc_path):
            result.problems.append(
                f"기본 모델 체인 `{chain}` 가 {doc_path.name} 와 일치하지 않음 "
                f"(app/ai/gemini_models.py 가 SSOT)."
            )
    return result


# --------------------------------------------------------------------------- #
# 실행
# --------------------------------------------------------------------------- #
def run_all() -> list[CheckResult]:
    manifests = _load_manifests()
    return [
        check_systems_have_scenarios(manifests),
        check_scenario_lists_modules(manifests),
        check_systems_have_specs(manifests),
        check_spec_lists_modules(manifests),
        check_spec_index_links_exist(),
        check_manifest_execution_profile(manifests),
        check_api_routes_documented(),
        check_env_vars_documented(),
        check_model_chain_matches(),
        check_documented_routes_exist(),
        check_documented_env_vars_used(),
        check_folder_tree_paths_exist(),
        check_key_dirs_documented_in_tree(),
    ]


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv or "-v" in argv
    results = run_all()

    print("문서-코드 정합성 가드 (docs ↔ source)\n" + "=" * 44)
    failed = 0
    for result in results:
        marker = "[OK]  " if result.ok else "[FAIL]"
        print(f"{marker} {result.name}")
        if verbose:
            for detail in result.details:
                print(f"       - {detail}")
        for problem in result.problems:
            failed += 1
            print(f"       ✗ {problem}")

    print("-" * 44)
    if failed:
        print(f"실패 {failed}건. 소스를 기준으로 문서를 갱신하거나, 문서에 맞게 소스를 수정하세요.")
        print("규칙은 docs/DOCS_GOVERNANCE.md 를 참고하세요.")
        return 1
    print("모든 정합성 검사를 통과했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
