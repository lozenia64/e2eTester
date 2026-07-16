from __future__ import annotations

from playwright.sync_api import Page

from app.runner.step_logging import log

from . import login_common as common
from . import marketing_consent_common as consent


def run(page: Page, config: common.LoginConfig, dialog_messages: list[str]) -> str:
    consent.navigate_to_marketing_consent_page(page, config)
    consent.pause_between_steps(page, "마케팅활용동의신청/철회 화면 진입")

    if consent.is_disagree_selected(page):
        log("[step] 이미 '동의하지 않습니다'가 선택되어 있어 철회 완료 상태로 판단합니다.")
        return f"마케팅동의 철회 성공 (이미 미동의 상태, {page.url})"
    consent.pause_between_steps(page, "동의 상태 확인")

    consent.select_disagree(page, config.timeout_ms)
    consent.pause_between_steps(page, "동의하지 않습니다 선택")

    consent.submit_marketing_consent_change(page, config.timeout_ms, dialog_messages)
    consent.pause_between_steps(page, "변경 버튼 클릭")

    if not consent.is_disagree_selected(page):
        raise RuntimeError(
            "마케팅동의 철회 실패: 변경 후에도 '동의하지 않습니다'가 선택되지 않았습니다."
        )

    return f"마케팅동의 철회 성공 ({page.url})"
