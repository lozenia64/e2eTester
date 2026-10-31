from __future__ import annotations

import re

from playwright.sync_api import Page

from app.runner.step_logging import log

from . import login_common as common

MARKETING_CONSENT_URL_FRAGMENT = "/my/member/change-addition01.do"
DISAGREE_LABEL_PATTERN = re.compile(r"동의하지\s*않습니다")
AGREE_LABEL_PATTERN = re.compile(r"동의합니다")
DETAIL_CONSENT_POPUP_SELECTOR = "#uiPOPGmea000"
DETAIL_CONSENT_POPUP_CLOSE_SELECTOR = "#uiPOPGmea000 #btnClose, #uiPOPGmea000 button.ui-close"
PERSONAL_CREDIT_QUESTION_PATTERN = re.compile(r"개인신용정보\s*수집")
AD_MARKETING_QUESTION_PATTERN = re.compile(r"광고성\s*정보.*?수신")
SMS_CONTACT_PATTERN = re.compile(r"^문자$")
CHANGE_BUTTON_SELECTOR = "#btnSubmit1"
FORM_PERSONAL_CREDIT_CHECKBOX = "#formCheck1"
FORM_AD_MARKETING_CHECKBOX = "#formAgree1"
CONTACT_CHECKBOX_IDS: tuple[str, ...] = ("return1", "return2", "return3", "return4")
SMS_CONTACT_CHECKBOX_ID = "return2"
STEP_TRANSITION_DELAY_MS = 1000


def pause_between_steps(page: Page, completed_step: str) -> None:
    common.wait_timeout_with_log(
        page, STEP_TRANSITION_DELAY_MS, f"{completed_step} 후 다음 단계 전 대기"
    )


def _wait_url_contains(page: Page, fragment: str, timeout_ms: int) -> None:
    log(f"[wait] Start URL contains wait: {fragment} ({timeout_ms} ms)")
    page.wait_for_function(
        "fragment => window.location.href.includes(fragment)",
        arg=fragment,
        timeout=timeout_ms,
    )
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    log(f"[wait] End URL contains wait: {fragment} -> {page.url}")


def _open_myhanwha_menu(page: Page, timeout_ms: int) -> None:
    menu_candidates = [
        page.get_by_role("link", name=re.compile(r"^MY한화$")),
        page.locator("header").get_by_text("MY한화", exact=True),
        page.get_by_text("MY한화", exact=True),
    ]

    for candidate in menu_candidates:
        try:
            menu = candidate.first
            if not menu.is_visible(timeout=2000):
                continue
            log("[step] Open MY한화 GNB menu")
            try:
                menu.hover(timeout=timeout_ms)
            except Exception:
                common.click_with_log(menu, "Open MY한화 GNB menu")
            common.wait_timeout_with_log(page, 600, "MY한화 menu expand delay")
            return
        except Exception:
            continue

    raise RuntimeError("MY한화 GNB 메뉴를 찾지 못했습니다.")


def _find_marketing_consent_link(page: Page):
    candidates = [
        page.locator(f'a[href*="{MARKETING_CONSENT_URL_FRAGMENT}"]:visible').first,
        page.get_by_role("link", name=re.compile(r"마케팅활용\s*동의\s*신청\s*/\s*철회")).first,
        page.locator('a:has-text("마케팅활용동의신청/철회")').first,
    ]

    for candidate in candidates:
        try:
            if candidate.is_visible(timeout=1500):
                return candidate
        except Exception:
            continue
    return None


def _navigate_via_direct_url(page: Page, config: common.LoginConfig) -> None:
    base_url = config.base_url.rstrip("/")
    common.open_url(page, f"{base_url}{MARKETING_CONSENT_URL_FRAGMENT}")
    _wait_url_contains(page, MARKETING_CONSENT_URL_FRAGMENT, config.timeout_ms)


def _wait_marketing_consent_form_ready(page: Page, timeout_ms: int) -> None:
    log(f"[wait] Start marketing consent form ready wait ({timeout_ms} ms)")
    page.wait_for_function(
        """
        () => {
            const disagree = document.querySelector('#formAllAgreeN');
            const agree = document.querySelector('#formAllAgreeY');
            const formCheck = document.querySelector('#formCheck1');
            if (!disagree || !agree || !formCheck) {
                return false;
            }
            if (disagree.checked || agree.checked) {
                return true;
            }
            const table = document.querySelector('#uiTabForm1 .data_table');
            const boxes = table
                ? Array.from(table.querySelectorAll('input[type="checkbox"]'))
                : [];
            if (boxes.length === 0) {
                return false;
            }
            const allDisabledUnchecked = boxes.every((cb) => cb.disabled && !cb.checked);
            const agreeFormReady = !formCheck.disabled && formCheck.checked;
            return allDisabledUnchecked || agreeFormReady;
        }
        """,
        timeout=timeout_ms,
    )
    log("[wait] End marketing consent form ready wait")


def _marketing_consent_all_agree_state(page: Page) -> str | None:
    return page.evaluate(
        """
        () => {
            const disagree = document.querySelector('#formAllAgreeN');
            const agree = document.querySelector('#formAllAgreeY');
            const formCheck = document.querySelector('#formCheck1');
            if (!disagree || !agree || !formCheck) {
                return null;
            }
            if (disagree.checked) {
                return 'disagree';
            }
            if (agree.checked) {
                return 'agree';
            }
            const table = document.querySelector('#uiTabForm1 .data_table');
            const boxes = table
                ? Array.from(table.querySelectorAll('input[type="checkbox"]'))
                : [];
            if (boxes.length > 0) {
                if (boxes.every((cb) => cb.disabled && !cb.checked)) {
                    return 'disagree';
                }
                if (!formCheck.disabled && formCheck.checked) {
                    return 'agree';
                }
            }
            return null;
        }
        """
    )


def navigate_to_marketing_consent_page(page: Page, config: common.LoginConfig) -> None:
    common.maybe_close_post_login_popup(page, config.timeout_ms)
    common.maybe_dismiss_cust_info_change_popup(page, config.timeout_ms)

    consent_link = _find_marketing_consent_link(page)
    if consent_link is None:
        _open_myhanwha_menu(page, config.timeout_ms)
        common.maybe_dismiss_cust_info_change_popup(page, config.timeout_ms)
        consent_link = _find_marketing_consent_link(page)

    if consent_link is None:
        _navigate_via_direct_url(page, config)
    else:
        try:
            common.click_with_log(consent_link, "Navigate to MY한화 > 마케팅활용동의신청/철회")
            _wait_url_contains(page, MARKETING_CONSENT_URL_FRAGMENT, config.timeout_ms)
        except Exception as exc:
            log(f"[warn] GNB 마케팅동의 메뉴 클릭 실패, 직접 URL 이동으로 대체: {exc}")
            common.maybe_dismiss_cust_info_change_popup(page, config.timeout_ms)
            _navigate_via_direct_url(page, config)

    _wait_marketing_consent_form_ready(page, config.timeout_ms)


def _detail_consent_popup(page: Page, timeout_ms: int):
    popup = page.locator(
        f"{DETAIL_CONSENT_POPUP_SELECTOR}.open, {DETAIL_CONSENT_POPUP_SELECTOR}:visible"
    ).first
    common.wait_locator_visible_with_log(popup, timeout_ms, "상세동의서 팝업")
    return popup


def _click_popup_list_agree(popup, question_pattern: re.Pattern[str], description: str) -> None:
    pattern_source = question_pattern.pattern
    clicked = popup.evaluate(
        """
        (root, patternSource) => {
            const pattern = new RegExp(patternSource);
            const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();

            for (const row of root.querySelectorAll('tr')) {
                const rowText = normalize(row.innerText || row.textContent);
                if (!pattern.test(rowText)) {
                    continue;
                }
                for (const item of row.querySelectorAll('ul.list_word2 li')) {
                    const itemText = normalize(item.textContent);
                    if (itemText.includes('동의함') && !itemText.includes('동의하지')) {
                        item.click();
                        return true;
                    }
                }
            }
            return false;
        }
        """,
        pattern_source,
    )
    if not clicked:
        raise RuntimeError(f"{description} 영역에서 '동의함' 항목을 찾지 못했습니다.")
    log(f"[step] {description} 영역 '동의함' 선택")


def fill_detail_consent_popup(page: Page, timeout_ms: int) -> None:
    popup = _detail_consent_popup(page, timeout_ms)
    _click_popup_list_agree(popup, PERSONAL_CREDIT_QUESTION_PATTERN, "개인신용정보 수집·이용")
    pause_between_steps(page, "개인신용정보 수집·이용 동의함 선택")
    _click_popup_list_agree(popup, AD_MARKETING_QUESTION_PATTERN, "광고성 정보 수신")
    log("[step] 상세동의서 팝업 내 동의함 선택 완료")


def close_detail_consent_popup(page: Page, timeout_ms: int) -> None:
    try:
        popup = _detail_consent_popup(page, min(timeout_ms, 5000))
    except Exception:
        log("[step] 상세동의서 팝업이 표시되지 않아 닫기 단계를 건너뜁니다.")
        return

    close_candidates = [
        popup.locator("#btnClose"),
        popup.locator("button.ui-close"),
        page.locator(DETAIL_CONSENT_POPUP_CLOSE_SELECTOR),
    ]
    for candidate in close_candidates:
        try:
            if candidate.count() == 0 or not candidate.first.is_visible(timeout=1200):
                continue
            common.click_with_log(candidate.first, "상세동의서 팝업 닫기")
            common.wait_timeout_with_log(page, 600, "상세동의서 팝업 닫힘 대기")
            if not popup.is_visible(timeout=800):
                log("[step] 상세동의서 팝업 닫기 완료")
                return
        except Exception:
            continue

    raise RuntimeError("상세동의서 팝업의 닫기 버튼을 찾지 못했습니다.")


def _radio_candidates(page: Page, label_pattern: re.Pattern[str]):
    return [
        page.locator('input[type="radio"][name="formAllAgree"]')
        .locator("xpath=ancestor::label[1]")
        .filter(has_text=label_pattern),
        page.get_by_role("radio", name=label_pattern).first,
        page.locator("label").filter(has_text=label_pattern).locator('input[type="radio"]').first,
    ]


def _find_radio(page: Page, label_pattern: re.Pattern[str], description: str):
    for candidate in _radio_candidates(page, label_pattern):
        try:
            if candidate.count() == 0:
                continue
            target = candidate.first
            if target.evaluate("el => el.tagName.toLowerCase()") == "label":
                radio = target.locator('input[type="radio"]').first
            else:
                radio = target
            if radio.is_visible(timeout=1200):
                return radio
        except Exception:
            continue
    raise RuntimeError(f"{description} 라디오 버튼을 찾지 못했습니다.")


def _click_radio(
    page: Page, label_pattern: re.Pattern[str], description: str, timeout_ms: int
) -> None:
    radio = _find_radio(page, label_pattern, description)
    radio_id = radio.get_attribute("id") or ""
    try:
        log(f"[click] {description}: input 직접 클릭")
        radio.click(force=True, timeout=timeout_ms)
    except Exception as exc:
        if not radio_id:
            raise RuntimeError(f"{description} 클릭에 실패했습니다: {exc}") from exc
        label = page.locator(f'label[for="{radio_id}"]').first
        if label.count() == 0:
            raise RuntimeError(
                f"{description} 클릭에 실패했고 연결된 라벨도 찾지 못했습니다: {exc}"
            ) from exc
        log(f"[warn] {description}: input 클릭 실패, 라벨 클릭으로 재시도: {exc}")
        common.click_with_log(label, f"{description} 라벨 클릭")


def is_disagree_selected(page: Page) -> bool:
    state = _marketing_consent_all_agree_state(page)
    if state == "disagree":
        return True
    if state == "agree":
        return False

    disagree = page.locator("#formAllAgreeN")
    if disagree.count() > 0:
        return disagree.is_checked()
    radio = _find_radio(page, DISAGREE_LABEL_PATTERN, "동의하지 않습니다")
    return radio.is_checked()


def select_disagree(page: Page, timeout_ms: int) -> None:
    _click_radio(page, DISAGREE_LABEL_PATTERN, "동의하지 않습니다", timeout_ms)


def select_agree(page: Page, timeout_ms: int) -> None:
    _click_radio(page, AGREE_LABEL_PATTERN, "동의합니다", timeout_ms)


def _set_checkbox_state(
    page: Page, selector: str, checked: bool, description: str, timeout_ms: int
) -> None:
    field_id = selector.removeprefix("#")
    checkbox = page.locator(f"#{field_id}").first
    common.wait_locator_visible_with_log(checkbox, timeout_ms, description)
    if checkbox.is_checked() == checked:
        log(f"[step] {description} 체크박스가 이미 {'선택' if checked else '해제'} 상태입니다.")
        return

    label = page.locator(f'label[for="{field_id}"]').first
    if label.count() > 0:
        common.click_with_log(label, f"{description} 라벨 {'선택' if checked else '해제'}")
    else:
        log(f"[click] {description} 체크박스 {'선택' if checked else '해제'} (input force)")
        checkbox.click(force=True, timeout=timeout_ms)

    state_arg = {"fieldId": field_id, "checked": checked}
    state_predicate = (
        "({fieldId, checked}) => { const el = document.getElementById(fieldId); "
        "return !!el && el.checked === checked; }"
    )
    try:
        page.wait_for_function(state_predicate, arg=state_arg, timeout=3000)
    except Exception:
        log(
            f"[warn] {description} 클릭 후 상태 미반영 — JS로 {'선택' if checked else '해제'} 재시도"
        )
        page.evaluate(
            """
            ({fieldId, checked}) => {
                const el = document.getElementById(fieldId);
                if (!el) {
                    throw new Error(`checkbox not found: ${fieldId}`);
                }
                if (el.checked !== checked) {
                    el.checked = checked;
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('click', { bubbles: true }));
                }
            }
            """,
            state_arg,
        )
        page.wait_for_function(state_predicate, arg=state_arg, timeout=timeout_ms)

    log(f"[step] {description} 체크박스 {'선택' if checked else '해제'} 완료")


def configure_apply_form_options(page: Page, timeout_ms: int) -> None:
    _set_checkbox_state(
        page, FORM_PERSONAL_CREDIT_CHECKBOX, True, "개인신용정보 수집·이용", timeout_ms
    )
    pause_between_steps(page, "개인신용정보 수집·이용 체크")
    _set_checkbox_state(page, FORM_AD_MARKETING_CHECKBOX, True, "광고성 정보 수신", timeout_ms)
    pause_between_steps(page, "광고성 정보 수신 체크")

    for checkbox_id in CONTACT_CHECKBOX_IDS:
        should_check = checkbox_id == SMS_CONTACT_CHECKBOX_ID
        _set_checkbox_state(
            page,
            f"#{checkbox_id}",
            should_check,
            f"연락 수단 {checkbox_id}",
            timeout_ms,
        )
        pause_between_steps(page, f"연락 수단 {checkbox_id} 설정")


def _click_change_button(page: Page, timeout_ms: int) -> None:
    change_button = page.locator(CHANGE_BUTTON_SELECTOR).first
    common.wait_locator_visible_with_log(change_button, timeout_ms, "변경 버튼")
    common.click_with_log(change_button, "마케팅동의 변경 버튼 클릭")


def submit_marketing_consent_change(
    page: Page, timeout_ms: int, dialog_messages: list[str]
) -> None:
    dialog_index = len(dialog_messages)
    try:
        with page.expect_response(
            lambda response: "update-addition-submit.json" in response.url,
            timeout=timeout_ms,
        ):
            _click_change_button(page, timeout_ms)
    except Exception as exc:
        log(f"[warn] 마케팅동의 변경 API 응답 대기 실패, 변경 버튼만 클릭 처리: {exc}")
        _click_change_button(page, timeout_ms)

    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    _wait_marketing_consent_form_ready(page, timeout_ms)
    common.ensure_no_failure_dialogs(dialog_messages, dialog_index, "마케팅동의 변경")
