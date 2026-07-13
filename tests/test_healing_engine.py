"""자가 치유 엔진 테스트 — 진짜 브라우저 대신 페이크 Page 로 폐루프 결정을 검증한다."""

from __future__ import annotations

from app.contexts.healing.engine import SelfHealingEngine
from app.contexts.healing.models import HealingAction, ResolvedHealingPolicy
from app.contexts.healing.page_proxy import HealedPage
from app.core.system_models import ModuleDefinition


class FakeLocator:
    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        return self._count


class FakePage:
    """DOM 스캔·후보 검증에 필요한 최소 표면만 흉내 내는 페이크."""

    url = "https://example.com/login"

    def __init__(self, candidates: list[dict], counts: dict[str, int] | None = None) -> None:
        self._candidates = candidates
        self._counts = counts or {}
        self.locator_calls: list[str] = []

    def evaluate(self, script: str):
        return self._candidates

    def locator(self, selector: str):
        self.locator_calls.append(selector)
        return FakeLocator(self._counts.get(selector, 1))


class FixedPolicy:
    def __init__(self, enabled: bool = True, threshold: float = 0.75) -> None:
        self._policy = ResolvedHealingPolicy(enabled=enabled, threshold=threshold)

    def resolve(self, system_code: str) -> ResolvedHealingPolicy:
        return self._policy


def _module() -> ModuleDefinition:
    return ModuleDefinition(
        module_id="login",
        system_code="hrp",
        name="로그인",
        description="",
        group="인증",
        order=2,
        workflow_step="login",
    )


def _error(selector: str = "#btnRA") -> Exception:
    return TimeoutError(f'Timeout 30000ms exceeded.\nwaiting for locator("{selector}")')


def test_auto_heal_registers_override_above_threshold():
    page = FakePage([{"tag": "button", "id": "btnRA2", "text": "로그인", "visible": True}])
    engine = SelfHealingEngine(FixedPolicy(threshold=0.75))
    overrides: dict[str, str] = {}

    attempt = engine.try_heal(page, _module(), _error(), overrides, log=lambda _line: None)

    assert attempt is not None
    assert attempt.action is HealingAction.AUTO_HEALED
    assert overrides["#btnRA"] == "#btnRA2"
    assert attempt.confidence >= 0.75


def test_low_confidence_is_suggested_not_applied():
    # class 만 겹치는 약한 후보 → 임계 미만 → 자동 적용 없이 제안만.
    page = FakePage(
        [{"tag": "button", "cls": "btn primary submit", "text": "다른버튼", "visible": True}]
    )
    engine = SelfHealingEngine(FixedPolicy(threshold=0.9))
    overrides: dict[str, str] = {}

    attempt = engine.try_heal(
        page, _module(), _error("button.btn.primary"), overrides, log=lambda _line: None
    )

    assert attempt is not None
    assert attempt.action is HealingAction.SUGGESTED
    assert overrides == {}


def test_no_candidate_is_recorded():
    page = FakePage([])
    engine = SelfHealingEngine(FixedPolicy())
    attempt = engine.try_heal(page, _module(), _error(), {}, log=lambda _line: None)
    assert attempt is not None
    assert attempt.action is HealingAction.NO_CANDIDATE
    assert attempt.healed_selector is None


def test_disabled_policy_skips_healing():
    page = FakePage([{"tag": "button", "id": "btnRA2", "visible": True}])
    engine = SelfHealingEngine(FixedPolicy(enabled=False))
    assert engine.try_heal(page, _module(), _error(), {}, log=lambda _line: None) is None


def test_non_selector_error_is_out_of_scope():
    engine = SelfHealingEngine(FixedPolicy())
    error = RuntimeError("로그인 실패: 인증번호가 올바르지 않습니다.")
    assert engine.try_heal(FakePage([]), _module(), error, {}, log=lambda _line: None) is None


def test_already_overridden_selector_is_not_rehealed():
    engine = SelfHealingEngine(FixedPolicy())
    page = FakePage([{"tag": "button", "id": "btnRA2", "visible": True}])
    overrides = {"#btnRA": "#btnRA2"}
    assert engine.try_heal(page, _module(), _error(), overrides, log=lambda _line: None) is None


def test_multi_match_candidate_gets_nth_pin():
    page = FakePage(
        [{"tag": "button", "id": "btnRA2", "visible": True}],
        counts={"#btnRA2": 2},
    )
    engine = SelfHealingEngine(FixedPolicy(threshold=0.5))
    attempt = engine.try_heal(page, _module(), _error(), {}, log=lambda _line: None)
    assert attempt is not None
    assert attempt.healed_selector == "#btnRA2 >> nth=0"


# --- 페이지 프록시(오버라이드 번역) ------------------------------------------


class RecordingPage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def locator(self, selector: str):
        self.calls.append(("locator", selector))
        return FakeLocator(1)

    def click(self, selector: str, **kwargs):
        self.calls.append(("click", selector))

    def goto(self, url: str):
        self.calls.append(("goto", url))


def test_healed_page_translates_overridden_selectors():
    real = RecordingPage()
    page = HealedPage(real, {"#old": "#new"})
    page.locator("#old")
    page.click("#old")
    page.locator("#untouched")
    page.goto("https://example.com")
    assert ("locator", "#new") in real.calls
    assert ("click", "#new") in real.calls
    assert ("locator", "#untouched") in real.calls
    assert ("goto", "https://example.com") in real.calls
