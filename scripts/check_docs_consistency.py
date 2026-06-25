#!/usr/bin/env python3
"""문서-코드 정합성 가드 (Docs ↔ Source consistency guard).

기계적으로 추출 가능한 '사실'만 골라 소스코드를 단일 진실원천(SSOT)으로 두고,
문서가 소스와 어긋났는지 검사한다. 문서 표류(drift)를 전수 수작업 감사 없이 조기에
잡기 위한 경량 장치이며, 사람이 읽고 판단하는 서술(설명 문장)은 검사하지 않는다.

검사 항목:
  1. 시스템 manifest ↔ 시나리오 문서 1:1 대응 (docs/scenarios/{code}.md)
  2. manifest 의 모든 module_id 가 짝이 되는 시나리오 문서에 등장하는지
  3. FastAPI 라우트(메서드+경로)가 E2E_ARCHITECTURE.md 에 문서화되어 있는지
  4. 코드가 읽는 환경변수가 README.md 또는 .env.example 에 문서화되어 있는지
  5. 기본 Gemini 모델 체인(코드 상수)이 README.md / .env.example 와 일치하는지

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


def _configure_stdio_utf8() -> None:
    """Windows PowerShell/콘솔에서 한글 stdout이 깨지지 않도록 UTF-8로 맞춘다."""
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


_configure_stdio_utf8()


try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - 의존성 안내
    print("[error] PyYAML 이 필요합니다. `python3 -m pip install -r requirements.txt` 실행 후 다시 시도하세요.")
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent

MANIFEST_GLOB = "app/systems/*/manifest.yaml"
SCENARIO_DIR = REPO_ROOT / "docs" / "scenarios"
ARCHITECTURE_DOC = REPO_ROOT / "E2E_ARCHITECTURE.md"
README_DOC = REPO_ROOT / "README.md"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
API_DIR = REPO_ROOT / "app" / "api"
GEMINI_MODELS_SRC = REPO_ROOT / "app" / "ai" / "gemini_models.py"

# 코드가 동적으로 조합하는(접미사가 붙는) 환경변수 prefix 는 prefix 문자열만 문서에서 확인한다.
DYNAMIC_ENV_PREFIX_RE = re.compile(r"""f["'](E2E_[A-Z0-9_]+_)\{""")
LITERAL_ENV_RE = re.compile(
    r"""(?:resolve_env_value|resolve_env_with_source|env_flag)\(\s*["']([A-Z][A-Z0-9_]+)["']"""
)
SETTINGS_ALIAS_RE = re.compile(
    r"""validation_alias\s*=\s*["']([A-Z][A-Z0-9_]+)["']"""
)
OS_ENV_RE = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*["']([A-Z][A-Z0-9_]+)["']|os\.environ\[\s*["']([A-Z][A-Z0-9_]+)["']"""
)
ROUTER_PREFIX_RE = re.compile(r"""APIRouter\([^)]*prefix\s*=\s*["']([^"']*)["']""")
ROUTE_DECORATOR_RE = re.compile(
    r"""@router\.(get|post|put|patch|delete|websocket)\(\s*["']([^"']*)["']"""
)
MODEL_CHAIN_RE = re.compile(
    r"""DEFAULT_GEMINI_MODEL_CHAIN[^=]*=\s*\((.*?)\)""", re.DOTALL
)


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


def _iter_py_sources(root: Path):
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


# --------------------------------------------------------------------------- #
# 3. API 라우트 문서화
# --------------------------------------------------------------------------- #
def _extract_routes() -> list[tuple[str, str]]:
    routes: list[tuple[str, str]] = []
    for path in sorted(API_DIR.glob("*.py")):
        text = _read(path)
        prefix_match = ROUTER_PREFIX_RE.search(text)
        prefix = prefix_match.group(1) if prefix_match else ""
        for method, route_path in ROUTE_DECORATOR_RE.findall(text):
            full = (prefix + route_path) or "/"
            token = "WS" if method == "websocket" else method.upper()
            routes.append((token, full))
    return routes


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


# --------------------------------------------------------------------------- #
# 4. 환경변수 문서화
# --------------------------------------------------------------------------- #
def _collect_env_names() -> tuple[set[str], set[str]]:
    literals: set[str] = set()
    prefixes: set[str] = set()
    for _path, text in _iter_py_sources(REPO_ROOT / "app"):
        literals.update(LITERAL_ENV_RE.findall(text))
        literals.update(SETTINGS_ALIAS_RE.findall(text))
        for grp in OS_ENV_RE.findall(text):
            literals.update(name for name in grp if name)
        prefixes.update(DYNAMIC_ENV_PREFIX_RE.findall(text))
    return literals, prefixes


def check_env_vars_documented() -> CheckResult:
    result = CheckResult("코드가 읽는 환경변수가 README.md/.env.example 에 문서화")
    doc_text = _read(README_DOC) + "\n" + _read(ENV_EXAMPLE)
    literals, prefixes = _collect_env_names()
    for name in sorted(literals):
        if name not in doc_text:
            result.problems.append(
                f"환경변수 `{name}` 가 README.md/.env.example 에 문서화되지 않음."
            )
    for prefix in sorted(prefixes):
        if prefix not in doc_text:
            result.problems.append(
                f"동적 환경변수 prefix `{prefix}{{...}}` 가 README.md/.env.example 에 문서화되지 않음."
            )
    result.details.append(
        f"환경변수 {len(literals)}개 + 동적 prefix {len(prefixes)}개를 문서와 대조했습니다."
    )
    return result


# --------------------------------------------------------------------------- #
# 5. 기본 Gemini 모델 체인
# --------------------------------------------------------------------------- #
def check_model_chain_matches() -> CheckResult:
    result = CheckResult("기본 Gemini 모델 체인이 README.md/.env.example 와 일치")
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
    for doc_path in (README_DOC, ENV_EXAMPLE):
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
        check_api_routes_documented(),
        check_env_vars_documented(),
        check_model_chain_matches(),
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
