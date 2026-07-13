"""런타임 셀렉터 오버라이드를 적용하는 Page/FrameLocator 프록시.

치유 엔진이 ``overrides``(깨진 셀렉터 → 대체 셀렉터)를 등록하면, 스텝 재시도 시 같은
셀렉터 문자열이 이 프록시를 지나며 대체 셀렉터로 번역된다. 스텝 코드는 손대지 않는다.

Playwright 를 import 하지 않는 순수 위임 래퍼다(엔진이 브라우저 없이도 import 가능해야
한다는 러너 규칙 유지). 오버라이드가 비어 있으면 사실상 무비용 pass-through 다.
"""

from __future__ import annotations

from typing import Any

# 첫 번째 위치 인자가 셀렉터 문자열인 Page/Frame 메서드들(오버라이드 번역 대상).
_SELECTOR_FIRST_ARG_METHODS = frozenset(
    {
        "click",
        "dblclick",
        "fill",
        "type",
        "press",
        "check",
        "uncheck",
        "set_checked",
        "hover",
        "tap",
        "focus",
        "select_option",
        "wait_for_selector",
        "query_selector",
        "query_selector_all",
        "is_visible",
        "is_hidden",
        "is_enabled",
        "is_disabled",
        "inner_text",
        "inner_html",
        "text_content",
        "get_attribute",
        "dispatch_event",
        "eval_on_selector",
        "eval_on_selector_all",
        "set_input_files",
    }
)


class _HealingBase:
    def __init__(self, target: Any, overrides: dict[str, str]) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_overrides", overrides)

    def _map(self, selector: Any) -> Any:
        if isinstance(selector, str):
            return self._overrides.get(selector, selector)
        return selector

    def locator(self, selector: str, *args: Any, **kwargs: Any) -> Any:
        return self._target.locator(self._map(selector), *args, **kwargs)

    def frame_locator(self, selector: str) -> HealedFrame:
        return HealedFrame(self._target.frame_locator(self._map(selector)), self._overrides)

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._target, name)
        if name in _SELECTOR_FIRST_ARG_METHODS and callable(attr):

            def _wrapped(selector: Any, *args: Any, **kwargs: Any) -> Any:
                return attr(self._map(selector), *args, **kwargs)

            return _wrapped
        return attr

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._target, name, value)


class HealedFrame(_HealingBase):
    """FrameLocator 래퍼 — frame.locator(셀렉터) 도 오버라이드 번역을 거친다."""


class HealedPage(_HealingBase):
    """Page 래퍼 — 스텝이 쓰는 최상위 셀렉터 호출에 오버라이드를 적용한다.

    셀렉터를 받지 않는 속성/메서드(goto, url, screenshot, evaluate 등)는 그대로
    위임하므로 엔진의 스크린샷 캡처·URL 조회도 이 래퍼를 통과해도 동작이 같다.
    """
