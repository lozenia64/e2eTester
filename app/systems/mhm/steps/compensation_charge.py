from __future__ import annotations

import random
import re
from calendar import monthrange
from datetime import date
from pathlib import Path

from . import login_common as common

CLAIM_INTRO_URL_FRAGMENT = "/cmp/dii/IbnfDmRcp1020"
TARGET_SELECT_URL_FRAGMENT = "/cmp/dii/IbnfDmRcp1040"
CLAIM_REASON_URL_FRAGMENT = "/cmp/dii/IbnfDmRcp1050"
CLAIM_DETAIL_URL_FRAGMENT = "/cmp/dii/IbnfDmRcp1052"
DOCUMENT_UPLOAD_URL_FRAGMENT = "/cmp/dii/IbnfDmRcp1070"
CLAIM_COMPLETE_URL_FRAGMENT = "/cmp/dii/IbnfDmRcp1090"
CLAIM_COMPLETE_HEADING_PATTERN = re.compile(r"보험금청구를\s*완료")
SERVICE_SATISFACTION_DIALOG_TEXT = re.compile(r"서비스\s*만족도\s*조사|서비스이용은\s*어떠셨")
SERVICE_SATISFACTION_DIALOG_SELECTOR = ".dialog.full.show"
SERVICE_SATISFACTION_CLOSE_SELECTOR = "button.dialog_close.ui_dialog_close, a.dialog_close.ui_dialog_close"
VISIBLE_MODAL_SELECTOR = (
    ".ui_dialog:visible, [role='dialog']:visible, .dialog.modal.show:visible, "
    ".dialog.show:visible, .modal.show:visible, .pop_wrap:visible"
)
SILSOM24_DIALOG_SELECTOR = "#dialog_silson24Url"
SILSOM24_DISMISS_LINK_SELECTOR = f'{SILSOM24_DIALOG_SELECTOR} a.link_txt[title="오늘 더이상 안볼래요"]'
SILSOM24_CLOSE_LINK_SELECTOR = f"{SILSOM24_DIALOG_SELECTOR} a.dialog_close.ui_dialog_close"
SELF_CLAIM_LABEL_SELECTOR = "label.ic_self.man"
SELF_CLAIM_INPUT_SELECTOR = "#selectionRadio1_0_selectionRadio1_0"
NEW_CLAIM_LABEL_SELECTOR = "label.ic_new"
NEW_CLAIM_INPUT_SELECTOR = "#selectionRadio1_1_selectionRadio2_2"
LOADING_OVERLAY_SELECTOR = "#loading"
TARGET_SELECT_NEXT_SELECTOR = '.fixed_bottom_button button.btn.s1.c1:has-text("다음")'
CLAIM_FLOW_DIALOG_SELECTOR = ".dialog.modal.show, .dialog.show"
DUPLICATE_CLAIM_NOTICE_TEXT = re.compile(r"동일한\s*사고|청구하신\s*이력|동일한\s*질병")
DUPLICATE_ACCIDENT_DATE_TYPE_TEXT = re.compile(
    r"동일한\s*발병|사고유형으로\s*완료|기존\s*청구내역"
)
EXISTING_CLAIM_HISTORY_ALERT_SELECTOR = ".dialog.modal.alert.show"
CLAIM_CONFIRM_MODAL_TEXT = re.compile(
    r"신규\s*접수|중복\s*청구|접수\s*확인|동일한\s*사고|청구하신\s*이력|동일한\s*질병"
)
ACCIDENT_TYPE_ETC_LABEL_SELECTOR = 'label:has(em.sel_lb_tit:text-is("기타"))'
ACCIDENT_TYPE_ETC_INPUT_SELECTOR = 'main input[type="radio"][value="05"]'
CLAIM_REASON_COMPLETE_SELECTOR = '.fixed_bottom_button button.btn.s1.c1:has-text("청구사유 입력완료")'
ACCIDENT_TYPE_CONFIRM_TEXT = re.compile(r"사고\s*유형")
CLAIM_CONTENT_TEXT = "IT직원 테스트입니다. 바로 취소할 예정입니다."
DESKTOP_SCREENSHOT_GLOB_PATTERNS = (
    "스크린샷*.PNG",
    "스크린샷*.png",
    "Screenshot*.PNG",
    "Screenshot*.png",
)
DESKTOP_PNG_FALLBACK_GLOB_PATTERNS = (
    "*.PNG",
    "*.png",
)
DATE_INPUT_SELECTOR = "#dateInput"
CLAIM_CONTENT_TEXTAREA_SELECTOR = "#cont"
ACCOUNT_COMBO_SELECTOR = "#acccombo"
ACCOUNT_SELECT_TRIGGER_SELECTOR = "main .sel_panel.active a.select_btn, main a.select_btn"
ACCOUNT_SELECT_DIALOG_TEXT = re.compile(r"계좌\s*선택")
SAVED_ACCOUNT_ITEM_PATTERN = re.compile(r"은행\s*/\s*\d+|/\s*\d{6,}")
DETAIL_COMPLETE_SELECTOR = '.fixed_bottom_button button.btn.s1.c1:has-text("상세정보 입력완료")'
CLAIM_TYPE_DIAGNOSIS_LABEL_SELECTOR = 'label:has(span.sel_lb_cont:text-is("진단비"))'
CLAIM_DETAIL_OTHER_DIAGNOSIS_LABEL_SELECTOR = 'label:has(span.sel_lb_cont:text-is("기타 진단"))'
CLAIM_TYPE_DIAGNOSIS_INPUT_SELECTOR = "#selectionCh_1"
CLAIM_DETAIL_OTHER_DIAGNOSIS_INPUT_SELECTOR = "#selectionCh2_A010204"
MEDICAL_BENEFIT_NONE_LABEL_SELECTOR = '.btn_radio label[for="radio10"]'
MEDICAL_BENEFIT_NONE_INPUT_SELECTOR = "#radio10"
CONSENT_FULL_AGREE_FOR = "[필수] 전체동의"
CONSENT_GUIDE_PATTERN = re.compile(r"동의\s*안내|보험금청구를\s*위한\s*동의")
CONSENT_SUMMARY_PATTERN = re.compile(r"요약\s*동의서|보험금청구를\s*위한")
CONSENT_MODAL_SELECTOR = (
    ".ui_dialog, [role='dialog'], .dialog.full.show, .dialog.modal.show, .dialog.bottom.show, .dialog.show"
)
GALLERY_FILE_INPUT_SELECTOR = "#galleyFile"
PRIMARY_UPLOAD_BUTTON_PATTERN = re.compile(r"보험금청구서류")
SECONDARY_UPLOAD_BUTTON_PATTERN = re.compile(r"진료비\s*세부")


def _wait_url_contains(page, fragment: str, timeout_ms: int) -> None:
    print(f"[wait] Start URL contains wait: {fragment} ({timeout_ms} ms)")
    page.wait_for_function(
        "f => window.location.href.includes(f)",
        arg=fragment,
        timeout=timeout_ms,
    )
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    print(f"[wait] End URL contains wait: {fragment} -> {page.url}")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _action_locators(root, name_pattern: str | re.Pattern[str]):
    locators = [
        root.get_by_role("button", name=name_pattern),
        root.get_by_role("link", name=name_pattern),
        root.get_by_role("radio", name=name_pattern),
        root.get_by_role("tab", name=name_pattern),
    ]
    if isinstance(name_pattern, str):
        locators.extend(
            [
                root.locator(f'button:has-text("{name_pattern}")'),
                root.locator(f'a:has-text("{name_pattern}")'),
                root.locator(f'label:has-text("{name_pattern}")'),
                root.locator(f'input[type="button"][value*="{name_pattern}"]'),
                root.locator(f'input[type="submit"][value*="{name_pattern}"]'),
            ]
        )
    return locators


def _find_visible_action(root, names: list[str | re.Pattern[str]], description: str):
    for name in names:
        for locator in _action_locators(root, name):
            try:
                return common.first_visible_locator(locator, f"{description}: {name}")
            except RuntimeError:
                continue
            except Exception:
                continue
    return None


def _click_named_action(page, names: list[str | re.Pattern[str]], description: str, *, scope=None) -> None:
    root = scope or page
    action = _find_visible_action(root, names, description)
    if action is None:
        joined = ", ".join(pattern.pattern if hasattr(pattern, "pattern") else str(pattern) for pattern in names)
        raise RuntimeError(f"{description} 요소를 찾지 못했습니다: {joined}")
    common.click_with_log(action, description)


def _maybe_click_named_action(
    page,
    names: list[str | re.Pattern[str]],
    description: str,
    *,
    scope=None,
    settle_ms: int = 400,
) -> bool:
    root = scope or page
    action = _find_visible_action(root, names, description)
    if action is None:
        return False
    common.click_with_log(action, description)
    common.wait_timeout_with_log(page, settle_ms, f"{description} 후 안정화")
    return True


def _find_visible_modal_with_text(page, pattern: re.Pattern[str]):
    roots = page.locator(VISIBLE_MODAL_SELECTOR)
    for index in range(roots.count()):
        root = roots.nth(index)
        try:
            if not root.is_visible(timeout=600):
                continue
            text = _normalize_text(root.inner_text(timeout=800))
        except Exception:
            continue
        if pattern.search(text):
            return root
    return None


def _maybe_click_modal_action(
    page,
    modal_text_pattern: re.Pattern[str],
    action_names: list[str | re.Pattern[str]],
    description: str,
    *,
    settle_ms: int = 400,
) -> bool:
    modal = _find_visible_modal_with_text(page, modal_text_pattern)
    if modal is None:
        return False
    return _maybe_click_named_action(
        page,
        action_names,
        description,
        scope=modal,
        settle_ms=settle_ms,
    )


def _claim_flow_dialog_open(page, text_pattern: re.Pattern[str]) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                (patternSource) => {
                    const pattern = new RegExp(patternSource);
                    for (const dialog of document.querySelectorAll('.dialog.modal, [role="dialog"]')) {
                        if (!dialog.classList.contains('show')) {
                            continue;
                        }
                        const text = (dialog.innerText || '').replace(/\\s+/g, ' ');
                        if (pattern.test(text)) {
                            return true;
                        }
                    }
                    return false;
                }
                """,
                text_pattern.pattern,
            )
        )
    except Exception:
        return False


def _existing_claim_history_popup_open(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                () => {
                    const pattern = /동일한\\s*발병|사고유형으로\\s*완료|기존\\s*청구내역/;
                    for (const dialog of document.querySelectorAll(
                        '.dialog.modal.alert.show, .dialog.modal.show, [role="dialog"]'
                    )) {
                        if (!dialog.classList.contains('show')) {
                            continue;
                        }
                        const text = (dialog.innerText || '').replace(/\\s+/g, ' ');
                        if (pattern.test(text)) {
                            return true;
                        }
                    }
                    return false;
                }
                """
            )
        )
    except Exception:
        return False


def _click_existing_claim_history_no(page) -> bool:
    alert = page.locator(EXISTING_CLAIM_HISTORY_ALERT_SELECTOR).filter(
        has_text=DUPLICATE_ACCIDENT_DATE_TYPE_TEXT
    )
    try:
        if alert.count() > 0:
            no_button = alert.first.locator('button.btn:has-text("아니오")').first
            if no_button.count() > 0:
                print("[click] 동일 발병일/사고유형 청구 이력 안내: 아니오")
                no_button.click(force=True, timeout=3000)
                common.wait_timeout_with_log(page, 500, "기존 청구내역 확인 팝업 닫힘 대기")
                return True
    except Exception as exc:
        print(f"[warn] 기존 청구내역 확인 팝업 Playwright 클릭 실패: {exc}")

    clicked = page.evaluate(
        """
        () => {
            const pattern = /동일한\\s*발병|사고유형으로\\s*완료|기존\\s*청구내역/;
            const dialogs = Array.from(document.querySelectorAll(
                '.dialog.modal.alert.show, .dialog.modal.show, [role="dialog"]'
            )).reverse();
            for (const dialog of dialogs) {
                if (!dialog.classList.contains('show')) {
                    continue;
                }
                const text = (dialog.innerText || '').replace(/\\s+/g, ' ');
                if (!pattern.test(text)) {
                    continue;
                }
                for (const button of dialog.querySelectorAll('.dialog_btn button, button.btn')) {
                    const label = (button.innerText || button.getAttribute('title') || '')
                        .replace(/\\s+/g, ' ')
                        .trim();
                    if (label === '아니오' || label.startsWith('아니오')) {
                        button.click();
                        return label;
                    }
                }
            }
            return '';
        }
        """
    )
    if clicked:
        print(f"[click] 동일 발병일/사고유형 청구 이력 안내(DOM): {clicked}")
        common.wait_timeout_with_log(page, 500, "기존 청구내역 확인 팝업 닫힘 대기")
        return True
    return False


def _click_claim_flow_dialog_button(
    page,
    text_pattern: re.Pattern[str],
    button_labels: list[str | re.Pattern[str]],
    description: str,
) -> bool:
    label_sources = [
        label.pattern if isinstance(label, re.Pattern) else label for label in button_labels
    ]
    clicked = page.evaluate(
        """
        ([patternSource, buttonLabelSources]) => {
            const pattern = new RegExp(patternSource);
            const matchesLabel = (label) => {
                const normalized = (label || '').replace(/\\s+/g, ' ').trim();
                return buttonLabelSources.some((source) => {
                    try {
                        return new RegExp(source).test(normalized);
                    } catch (error) {
                        return normalized === source || normalized.startsWith(source);
                    }
                });
            };
            for (const dialog of document.querySelectorAll('.dialog.modal, [role="dialog"]')) {
                if (!dialog.classList.contains('show')) {
                    continue;
                }
                const text = (dialog.innerText || '').replace(/\\s+/g, ' ');
                if (!pattern.test(text)) {
                    continue;
                }
                const buttons = dialog.querySelectorAll('button, a[role="button"]');
                for (const button of buttons) {
                    const label = (button.innerText || button.getAttribute('title') || '')
                        .replace(/\\s+/g, ' ')
                        .trim();
                    if (matchesLabel(label)) {
                        button.click();
                        return label;
                    }
                }
            }
            return '';
        }
        """,
        [text_pattern.pattern, label_sources],
    )
    if clicked:
        print(f"[click] {description}: {clicked}")
        common.wait_timeout_with_log(page, 500, f"{description} 후 안정화")
        return True

    dialog = page.locator(CLAIM_FLOW_DIALOG_SELECTOR).filter(has_text=text_pattern).first
    try:
        if dialog.count() == 0:
            return False
        for label in button_labels:
            if isinstance(label, re.Pattern):
                button = dialog.get_by_role("button", name=label).first
            else:
                button = dialog.locator(f'button:has-text("{label}")').first
            if button.count() == 0:
                continue
            print(f"[click] {description}: {label if isinstance(label, str) else label.pattern}")
            button.click(force=True, timeout=3000)
            common.wait_timeout_with_log(page, 500, f"{description} 후 안정화")
            return True
    except Exception:
        return False
    return False


def _click_claim_flow_dialog_confirm(page, text_pattern: re.Pattern[str], description: str) -> bool:
    return _click_claim_flow_dialog_button(
        page,
        text_pattern,
        ["확인", re.compile(r"^확인")],
        description,
    )


def _dismiss_duplicate_accident_date_type_popup(page, timeout_ms: int) -> bool:
    if not _existing_claim_history_popup_open(page):
        return False
    for _ in range(max(3, timeout_ms // 500)):
        _wait_for_loading_overlay_gone(page, min(timeout_ms, 5000))
        if _click_existing_claim_history_no(page):
            if not _existing_claim_history_popup_open(page):
                return True
        elif _click_claim_flow_dialog_button(
            page,
            DUPLICATE_ACCIDENT_DATE_TYPE_TEXT,
            ["아니오", re.compile(r"^아니오$")],
            "동일 발병일/사고유형 청구 이력 안내",
        ):
            if not _existing_claim_history_popup_open(page):
                return True
        common.wait_timeout_with_log(page, 400, "동일 발병일/사고유형 청구 이력 안내 팝업 재시도")
    raise RuntimeError("동일 발병일/사고유형 청구 이력 안내 팝업을 닫지 못했습니다.")


def _dismiss_duplicate_claim_notice_popup(page, timeout_ms: int) -> bool:
    if not _claim_flow_dialog_open(page, DUPLICATE_CLAIM_NOTICE_TEXT):
        return False
    for _ in range(max(3, timeout_ms // 500)):
        if _click_claim_flow_dialog_confirm(page, DUPLICATE_CLAIM_NOTICE_TEXT, "동일 사고 청구 이력 안내"):
            _wait_for_loading_overlay_gone(page, min(timeout_ms, 5000))
            if not _claim_flow_dialog_open(page, DUPLICATE_CLAIM_NOTICE_TEXT):
                return True
        common.wait_timeout_with_log(page, 400, "동일 사고 청구 이력 안내 팝업 재시도")
    raise RuntimeError("동일 사고 청구 이력 안내 팝업을 닫지 못했습니다.")


def _dismiss_claim_confirm_modals(page, timeout_ms: int) -> bool:
    dismissed = False
    if _dismiss_duplicate_accident_date_type_popup(page, timeout_ms):
        dismissed = True
    elif _dismiss_duplicate_claim_notice_popup(page, timeout_ms):
        dismissed = True
    elif _claim_flow_dialog_open(page, CLAIM_CONFIRM_MODAL_TEXT):
        if _click_claim_flow_dialog_confirm(page, CLAIM_CONFIRM_MODAL_TEXT, "청구 접수 확인 팝업"):
            _wait_for_loading_overlay_gone(page, min(timeout_ms, 5000))
            dismissed = True
    elif _maybe_click_modal_action(
        page,
        CLAIM_CONFIRM_MODAL_TEXT,
        [re.compile(r"^확인$"), "확인", "확인했어요"],
        "청구 접수 확인 팝업",
    ):
        dismissed = True
    return dismissed


def _one_month_ago(today: date) -> date:
    target_year = today.year
    target_month = today.month - 1
    if target_month == 0:
        target_year -= 1
        target_month = 12
    target_day = min(today.day, monthrange(target_year, target_month)[1])
    return date(target_year, target_month, target_day)


def _set_accident_date_one_month_ago(page) -> None:
    target = _one_month_ago(date.today())
    dotted = target.strftime("%Y.%m.%d")
    date_input = page.locator(DATE_INPUT_SELECTOR).first
    try:
        if date_input.is_visible(timeout=1500):
            date_input.fill(dotted)
            date_input.evaluate(
                """
                (element) => {
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.blur();
                    return element.value;
                }
                """
            )
            print(f"[step] 발병(사고)일을 1개월 전 날짜로 입력: {dotted}")
            common.wait_timeout_with_log(page, 400, "발병(사고)일 입력 반영 대기")
            return
    except Exception:
        pass
    raise RuntimeError("발병(사고)일 입력 필드(#dateInput)를 찾지 못했습니다.")


def _pick_random_desktop_screenshot() -> Path:
    desktop = Path.home() / "Desktop"
    candidates: list[Path] = []
    for pattern in DESKTOP_SCREENSHOT_GLOB_PATTERNS:
        candidates.extend(path for path in desktop.glob(pattern) if path.is_file())
    if not candidates:
        for pattern in DESKTOP_PNG_FALLBACK_GLOB_PATTERNS:
            candidates.extend(path for path in desktop.glob(pattern) if path.is_file())
    unique_candidates = sorted({path.resolve() for path in candidates}, key=str)
    if not unique_candidates:
        raise RuntimeError("Desktop에서 업로드할 PNG 파일을 찾지 못했습니다.")
    return random.choice(unique_candidates)


def _silsom24_dialog_open(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                () => {
                    const dialog = document.querySelector('#dialog_silson24Url');
                    return !!(dialog && dialog.classList.contains('show'));
                }
                """
            )
        )
    except Exception:
        return False


def _close_gnb_menu_if_open(page) -> None:
    try:
        gnb_open = page.evaluate(
            """
            () => {
                const gnb = document.querySelector('#gnb.mhm_gnb');
                return !!(gnb && gnb.getAttribute('aria-hidden') === 'false');
            }
            """
        )
    except Exception:
        return
    if not gnb_open:
        return
    clicked = page.evaluate(
        """
        () => {
            const closeButton = document.querySelector('#gnb a.btn_gnb_close');
            if (!closeButton) {
                return false;
            }
            closeButton.click();
            return true;
        }
        """
    )
    if clicked:
        print("[click] 전체메뉴 닫기(청구 화면 상호작용 전)")
        common.wait_timeout_with_log(page, 400, "전체메뉴 닫힘 대기")


def _click_silsom24_dismiss_via_dom(page) -> str:
    return page.evaluate(
        """
        () => {
            const dialog = document.querySelector('#dialog_silson24Url');
            if (!dialog || !dialog.classList.contains('show')) {
                return '';
            }
            const selectors = [
                'a.dialog_close.ui_dialog_close',
                'a.link_txt[title*="안볼"]',
            ];
            for (const selector of selectors) {
                const element = dialog.querySelector(selector);
                if (!element) {
                    continue;
                }
                element.click();
                return element.getAttribute('title') || (element.innerText || '').trim();
            }
            return '';
        }
        """
    )


def _wait_for_silsom24_popup(page, wait_ms: int = 3000) -> bool:
    print(f"[wait] 실손24 알림 팝업 노출 대기 ({wait_ms} ms)")
    for _ in range(max(1, wait_ms // 200)):
        if _silsom24_dialog_open(page):
            print("[wait] 실손24 알림 팝업 표시됨")
            return True
        common.wait_timeout_with_log(page, 200, "실손24 팝업 표시 대기")
    return _silsom24_dialog_open(page)


def _dismiss_silsom24_popup(page, timeout_ms: int) -> None:
    _wait_for_silsom24_popup(page, 3000)
    for _ in range(max(5, timeout_ms // 400)):
        if not _silsom24_dialog_open(page):
            return

        dismissed_label = ""
        for selector, description in (
            (SILSOM24_CLOSE_LINK_SELECTOR, "팝업창 닫기"),
            (SILSOM24_DISMISS_LINK_SELECTOR, "오늘 더이상 안볼래요"),
        ):
            target = page.locator(selector).first
            try:
                if target.count() == 0:
                    continue
                print(f"[click] 실손24 알림 닫기: {description}")
                target.click(force=True, timeout=3000)
                dismissed_label = description
                common.wait_timeout_with_log(page, 500, "실손24 팝업 닫힘 대기")
                break
            except Exception:
                continue

        if not dismissed_label:
            dismissed_label = _click_silsom24_dismiss_via_dom(page)
            if dismissed_label:
                print(f"[click] 실손24 알림 닫기(DOM): {dismissed_label}")
                common.wait_timeout_with_log(page, 500, "실손24 팝업 닫힘 대기")

        if not _silsom24_dialog_open(page):
            print("[step] 실손24 알림 팝업 닫기 완료")
            return
        if not dismissed_label:
            common.wait_timeout_with_log(page, 400, "실손24 팝업 재시도 대기")

    if _silsom24_dialog_open(page):
        raise RuntimeError("실손24 알림 팝업을 닫지 못했습니다.")


def _dismiss_claim_entry_popups(page, timeout_ms: int) -> None:
    _close_gnb_menu_if_open(page)
    _dismiss_silsom24_popup(page, timeout_ms)


def _open_hamburger_menu(page, timeout_ms: int) -> None:
    close_button = page.get_by_role("button", name=re.compile(r"전체\s*메뉴\s*닫기"))
    try:
        if close_button.is_visible(timeout=800):
            return
    except Exception:
        pass

    open_candidates = [
        page.locator("banner").get_by_text("전체메뉴 열기").first,
        page.get_by_text("전체메뉴 열기").first,
        page.get_by_role("button", name=re.compile(r"전체\s*메뉴")).first,
    ]
    for candidate in open_candidates:
        try:
            if candidate.is_visible(timeout=1500):
                common.click_with_log(candidate, "전체메뉴 열기")
                common.wait_timeout_with_log(page, 600, "전체메뉴 펼침 대기")
                return
        except Exception:
            continue
    raise RuntimeError("전체메뉴 열기 버튼을 찾지 못했습니다.")


def _click_claim_entry_menu(page, timeout_ms: int) -> None:
    claim_entry = page.locator("#code03020100, nav #code03020100").first
    try:
        claim_entry.scroll_into_view_if_needed(timeout=timeout_ms)
        common.click_with_log(claim_entry, "질병/상해보험 > 보험금청구 접수")
    except Exception as exc:
        print(f"[warn] 보험금청구 접수 메뉴 일반 클릭 실패, JS 클릭 시도: {exc}")
        claim_entry.evaluate("element => element.click()")


def _wait_for_loading_overlay_gone(page, timeout_ms: int) -> None:
    wait_ms = min(timeout_ms, 15000)
    try:
        page.wait_for_function(
            """
            () => {
                const loading = document.querySelector('#loading');
                if (!loading) {
                    return true;
                }
                const style = window.getComputedStyle(loading);
                const rect = loading.getBoundingClientRect();
                return style.display === 'none'
                    || style.visibility === 'hidden'
                    || style.pointerEvents === 'none'
                    || rect.width === 0
                    || rect.height === 0
                    || loading.getAttribute('aria-hidden') === 'true';
            }
            """,
            timeout=wait_ms,
        )
    except Exception:
        print("[warn] 로딩 오버레이(#loading) 대기 시간 초과, 계속 진행")


def _scroll_target_to_center(target) -> None:
    target.evaluate("element => element.scrollIntoView({ block: 'center', inline: 'nearest' })")


def _is_native_css_selector(selector: str) -> bool:
    playwright_tokens = (":has(", ":text-is(", ":text(", ">>", "nth-match")
    return not any(token in selector for token in playwright_tokens)


def _click_selection_label(
    page,
    *,
    label_selector: str,
    input_selector: str,
    description: str,
    label_text: str | None = None,
) -> None:
    main = page.locator("main")
    input_id = input_selector.lstrip("#") if input_selector.startswith("#") else ""
    candidates = [
        main.locator(label_selector),
    ]
    if input_id:
        candidates.append(main.locator(f'label[for="{input_id}"]'))
    candidates.append(main.locator(input_selector))

    for candidate in candidates:
        try:
            target = candidate.first
            if target.count() == 0:
                continue
            target.scroll_into_view_if_needed(timeout=3000)
            _scroll_target_to_center(target)
            common.wait_timeout_with_log(page, 200, f"{description} 스크롤 안정화")
            print(f"[click] {description}")
            target.click(force=True, timeout=3000)
            common.wait_timeout_with_log(page, 400, f"{description} 후 안정화")
            return
        except Exception:
            continue

    clicked = page.evaluate(
        """
        ([labelSelector, inputSelector, labelText, useLabelSelector]) => {
            const scrollAndClick = (element) => {
                element.scrollIntoView({ block: 'center', inline: 'nearest' });
                element.click();
            };
            const normalize = (text) => (text || '').replace(/\\s+/g, ' ').trim();

            if (useLabelSelector) {
                const label = document.querySelector(`main ${labelSelector}`);
                if (label) {
                    scrollAndClick(label);
                    return 'label';
                }
            }

            if (inputSelector.startsWith('#')) {
                const inputId = inputSelector.slice(1);
                const byFor = document.querySelector(`label[for="${inputId}"]`);
                if (byFor) {
                    scrollAndClick(byFor);
                    return 'label';
                }
            }

            if (labelText) {
                for (const label of document.querySelectorAll('main label')) {
                    if (normalize(label.innerText).includes(labelText)) {
                        scrollAndClick(label);
                        return 'label';
                    }
                }
            }

            const input = document.querySelector(inputSelector);
            if (input) {
                scrollAndClick(input);
                input.dispatchEvent(new Event('change', { bubbles: true }));
                return 'input';
            }
            return '';
        }
        """,
        [label_selector, input_selector, label_text or "", _is_native_css_selector(label_selector)],
    )
    if clicked:
        print(f"[click] {description} (DOM fallback: {clicked})")
        common.wait_timeout_with_log(page, 400, f"{description} 후 안정화")
        return
    raise RuntimeError(f"{description} 요소를 찾지 못했습니다.")


def _click_self_claim_target(page, timeout_ms: int) -> None:
    _dismiss_claim_entry_popups(page, timeout_ms)
    _wait_for_loading_overlay_gone(page, timeout_ms)
    _click_selection_label(
        page,
        label_selector=SELF_CLAIM_LABEL_SELECTOR,
        input_selector=SELF_CLAIM_INPUT_SELECTOR,
        description="청구 대상: 본인",
    )


def _click_new_claim_type(page, timeout_ms: int) -> None:
    _close_gnb_menu_if_open(page)
    _wait_for_loading_overlay_gone(page, timeout_ms)
    page.locator(f"main {NEW_CLAIM_LABEL_SELECTOR}").first.wait_for(state="attached", timeout=timeout_ms)
    _click_selection_label(
        page,
        label_selector=NEW_CLAIM_LABEL_SELECTOR,
        input_selector=NEW_CLAIM_INPUT_SELECTOR,
        description="청구 유형: 신규접수",
    )


def _click_next_target_selection(page, timeout_ms: int) -> None:
    next_button = page.locator(TARGET_SELECT_NEXT_SELECTOR).first
    for _ in range(max(1, timeout_ms // 400)):
        _wait_for_loading_overlay_gone(page, min(timeout_ms, 5000))
        try:
            next_button.wait_for(state="visible", timeout=1500)
            if next_button.is_enabled(timeout=800):
                next_button.scroll_into_view_if_needed(timeout=3000)
                print("[click] 청구 대상 선택 다음")
                next_button.click(force=True, timeout=3000)
                common.wait_timeout_with_log(page, 400, "청구 대상 선택 다음 후 안정화")
                return
        except Exception:
            pass
        common.wait_timeout_with_log(page, 400, "다음 버튼 활성화 대기")
    raise RuntimeError("청구 대상 선택 다음 버튼을 활성화하지 못했습니다.")


def _click_compensation_tab(page, timeout_ms: int) -> None:
    compensation_tab = page.locator("nav").get_by_role("tab", name="보상").first
    compensation_tab.scroll_into_view_if_needed(timeout=timeout_ms)
    try:
        common.click_with_log(compensation_tab, "전체메뉴 보상 탭")
    except Exception as exc:
        print(f"[warn] 보상 탭 일반 클릭 실패, JS 클릭 시도: {exc}")
        compensation_tab.evaluate("element => element.click()")
    common.wait_timeout_with_log(page, 400, "보상 탭 전환 대기")


def _navigate_to_claim_entry(page, timeout_ms: int, base_url: str) -> None:
    common.maybe_close_post_login_popup(page, timeout_ms)
    if CLAIM_INTRO_URL_FRAGMENT in page.url:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        _dismiss_claim_entry_popups(page, timeout_ms)
        return

    try:
        _open_hamburger_menu(page, timeout_ms)
        _click_compensation_tab(page, timeout_ms)
        _click_claim_entry_menu(page, timeout_ms)
        _wait_url_contains(page, CLAIM_INTRO_URL_FRAGMENT, timeout_ms)
        _dismiss_claim_entry_popups(page, timeout_ms)
        return
    except Exception as exc:
        print(f"[warn] 메뉴로 보험금청구 접수 진입 실패, 직접 URL 시도: {exc}")

    common.open_url(page, f"{base_url.rstrip('/')}{CLAIM_INTRO_URL_FRAGMENT}")
    _wait_url_contains(page, CLAIM_INTRO_URL_FRAGMENT, timeout_ms)
    _dismiss_claim_entry_popups(page, timeout_ms)


def _start_claim_from_intro(page, timeout_ms: int) -> None:
    _dismiss_claim_entry_popups(page, timeout_ms)
    _click_named_action(page, ["보험금청구하기", re.compile(r"보험금\s*청구\s*하기")], "보험금청구하기")
    _wait_url_contains(page, TARGET_SELECT_URL_FRAGMENT, timeout_ms)
    _dismiss_claim_entry_popups(page, timeout_ms)


def _complete_target_selection(page, timeout_ms: int) -> None:
    _dismiss_claim_entry_popups(page, timeout_ms)
    _click_self_claim_target(page, timeout_ms)
    _dismiss_claim_entry_popups(page, timeout_ms)
    _wait_for_loading_overlay_gone(page, timeout_ms)
    common.wait_timeout_with_log(page, 600, "청구 유형 섹션 노출 대기")
    _click_new_claim_type(page, timeout_ms)
    _dismiss_claim_entry_popups(page, timeout_ms)
    _click_next_target_selection(page, timeout_ms)
    _dismiss_claim_entry_popups(page, timeout_ms)
    _wait_for_loading_overlay_gone(page, timeout_ms)
    for _ in range(max(1, timeout_ms // 400)):
        if _silsom24_dialog_open(page):
            _dismiss_silsom24_popup(page, timeout_ms)
            continue
        if _dismiss_claim_confirm_modals(page, timeout_ms):
            continue
        if CLAIM_REASON_URL_FRAGMENT in page.url:
            _wait_url_contains(page, CLAIM_REASON_URL_FRAGMENT, timeout_ms)
            return
        common.wait_timeout_with_log(page, 400, "청구사유 입력 화면 대기")
    _wait_url_contains(page, CLAIM_REASON_URL_FRAGMENT, timeout_ms)


def _click_accident_type_etc(page) -> None:
    _click_selection_label(
        page,
        label_selector=ACCIDENT_TYPE_ETC_LABEL_SELECTOR,
        input_selector=ACCIDENT_TYPE_ETC_INPUT_SELECTOR,
        description="사고 유형: 기타",
        label_text="기타",
    )


def _click_claim_reason_complete(page, timeout_ms: int) -> None:
    complete_button = page.locator(CLAIM_REASON_COMPLETE_SELECTOR).first
    for _ in range(max(1, timeout_ms // 400)):
        _wait_for_loading_overlay_gone(page, min(timeout_ms, 5000))
        try:
            complete_button.wait_for(state="visible", timeout=1500)
            _scroll_target_to_center(complete_button)
            if complete_button.is_enabled(timeout=800):
                print("[click] 청구사유 입력완료(1/3)")
                complete_button.click(force=True, timeout=3000)
                common.wait_timeout_with_log(page, 400, "청구사유 입력완료(1/3) 후 안정화")
                return
        except Exception:
            pass
        common.wait_timeout_with_log(page, 400, "청구사유 입력완료 버튼 활성화 대기")
    raise RuntimeError("청구사유 입력완료(1/3) 버튼을 활성화하지 못했습니다.")


def _dismiss_accident_type_confirm_popup(page, timeout_ms: int) -> bool:
    if _claim_flow_dialog_open(page, ACCIDENT_TYPE_CONFIRM_TEXT):
        return _click_claim_flow_dialog_confirm(page, ACCIDENT_TYPE_CONFIRM_TEXT, "사고유형 확인 팝업")
    return _maybe_click_modal_action(
        page,
        ACCIDENT_TYPE_CONFIRM_TEXT,
        ["확인했어요", re.compile(r"^확인$"), "확인"],
        "사고유형 확인 팝업",
    )


def _complete_claim_reason_step(page, timeout_ms: int) -> None:
    _close_gnb_menu_if_open(page)
    _wait_for_loading_overlay_gone(page, timeout_ms)
    _set_accident_date_one_month_ago(page)
    _click_accident_type_etc(page)
    for _ in range(max(1, timeout_ms // 400)):
        if _dismiss_duplicate_accident_date_type_popup(page, timeout_ms):
            continue
        break
    _click_claim_reason_complete(page, timeout_ms)
    for _ in range(max(1, timeout_ms // 400)):
        if _existing_claim_history_popup_open(page):
            _dismiss_duplicate_accident_date_type_popup(page, timeout_ms)
            _click_claim_reason_complete(page, timeout_ms)
            continue
        if _dismiss_accident_type_confirm_popup(page, timeout_ms):
            continue
        if _dismiss_claim_confirm_modals(page, timeout_ms):
            continue
        if _handle_consent_flow(page, timeout_ms):
            continue
        if CLAIM_DETAIL_URL_FRAGMENT in page.url:
            _wait_url_contains(page, CLAIM_DETAIL_URL_FRAGMENT, timeout_ms)
            return
        common.wait_timeout_with_log(page, 400, "상세정보 입력 화면 대기")
    _wait_url_contains(page, CLAIM_DETAIL_URL_FRAGMENT, timeout_ms)


def _find_consent_modal(page, pattern: re.Pattern[str]):
    roots = page.locator(CONSENT_MODAL_SELECTOR)
    for index in range(roots.count()):
        root = roots.nth(index)
        try:
            if not root.is_visible(timeout=600):
                continue
            text = _normalize_text(root.inner_text(timeout=800))
        except Exception:
            continue
        if pattern.search(text):
            return root
    return None


def _click_label_in_modal(
    modal,
    *,
    label_for: str | None,
    text_pattern: re.Pattern[str] | None,
    description: str,
) -> bool:
    label_text = modal.evaluate(
        """
        (modal, args) => {
            const [labelFor, patternSource] = args;
            const pattern = patternSource ? new RegExp(patternSource) : null;
            const clickTarget = (element) => {
                element.scrollIntoView({ block: 'center', inline: 'nearest' });
                element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                element.click();
                return (element.innerText || element.textContent || '').replace(/\\s+/g, ' ').trim();
            };
            if (labelFor) {
                const byFor = modal.querySelector(`label[for="${labelFor}"]`);
                if (byFor) {
                    return clickTarget(byFor);
                }
            }
            for (const label of modal.querySelectorAll('label')) {
                const text = (label.innerText || label.textContent || '').replace(/\\s+/g, ' ').trim();
                if (pattern && pattern.test(text)) {
                    return clickTarget(label);
                }
            }
            return '';
        }
        """,
        [label_for or "", text_pattern.pattern if text_pattern else ""],
    )
    if label_text:
        print(f"[click] {description}: {label_text}")
        common.wait_timeout_with_log(modal.page, 400, f"{description} 후 안정화")
        return True
    return False


def _click_button_in_modal(
    modal,
    *,
    names: list[str | re.Pattern[str]],
    description: str,
) -> bool:
    for name in names:
        pattern_source = name.pattern if isinstance(name, re.Pattern) else name
        clicked = modal.evaluate(
            """
            (modal, patternSource) => {
                const pattern = new RegExp(patternSource);
                const clickTarget = (element) => {
                    element.scrollIntoView({ block: 'center', inline: 'nearest' });
                    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                    element.click();
                    return (element.innerText || element.textContent || element.value || '')
                        .replace(/\\s+/g, ' ')
                        .trim();
                };
                for (const element of modal.querySelectorAll('button, a[role="button"], input[type="button"], input[type="submit"]')) {
                    const text = (element.innerText || element.textContent || element.value || '')
                        .replace(/\\s+/g, ' ')
                        .trim();
                    if (pattern.test(text)) {
                        return clickTarget(element);
                    }
                }
                return '';
            }
            """,
            pattern_source,
        )
        if clicked:
            print(f"[click] {description}: {clicked}")
            common.wait_timeout_with_log(modal.page, 400, f"{description} 후 안정화")
            return True
    return False


def _scroll_consent_sheet_to_bottom(page) -> None:
    scrolled = page.evaluate(
        """
        () => {
            const isVisible = (element) => {
                if (!element) {
                    return false;
                }
                const style = window.getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
            };
            const roots = Array.from(document.querySelectorAll('.ui_dialog, [role="dialog"], .bottom_sheet, .sheet'))
                .filter((element) => isVisible(element));
            for (const root of roots) {
                const text = (root.innerText || '').replace(/\\s+/g, ' ').trim();
                if (!text.includes('요약 동의서') && !text.includes('보험금청구를 위한')) {
                    continue;
                }
                const scrollables = Array.from(root.querySelectorAll('main, article, .scroll, .scroll_area, .dialog_content, .content'))
                    .filter((element) => element.scrollHeight > element.clientHeight + 20);
                const target = scrollables[0] || root;
                target.scrollTop = target.scrollHeight;
                target.dispatchEvent(new Event('scroll', { bubbles: true }));
                return true;
            }
            return false;
        }
        """
    )
    if scrolled:
        common.wait_timeout_with_log(page, 400, "요약 동의서 스크롤 반영 대기")


def _maybe_click_consent_action(
    page,
    names: list[str | re.Pattern[str]],
    description: str,
    *,
    scope=None,
    settle_ms: int = 400,
) -> bool:
    if _existing_claim_history_popup_open(page):
        return _click_existing_claim_history_no(page)
    _wait_for_loading_overlay_gone(page, 5000)
    root = scope or page
    if scope is not None:
        if _click_button_in_modal(root, names=names, description=description):
            return True
        label_for = CONSENT_FULL_AGREE_FOR if "필수" in description and "전체" in description else None
        text_pattern = next((name for name in names if isinstance(name, re.Pattern)), None)
        if label_for or text_pattern is not None:
            if _click_label_in_modal(
                root,
                label_for=label_for,
                text_pattern=text_pattern,
                description=description,
            ):
                return True
        for name in names:
            if isinstance(name, str) and _click_label_in_modal(
                root,
                label_for=name if name.startswith("[") else None,
                text_pattern=re.compile(re.escape(name)),
                description=description,
            ):
                return True
    action = _find_visible_action(root, names, description)
    if action is None:
        return False
    print(f"[click] {description}")
    try:
        _scroll_target_to_center(action)
        action.click(force=True, timeout=3000)
    except Exception as exc:
        print(f"[warn] {description} Playwright 클릭 실패, DOM 클릭 시도: {exc}")
        action.evaluate(
            """
            (element) => {
                element.scrollIntoView({ block: 'center', inline: 'nearest' });
                element.click();
            }
            """
        )
    common.wait_timeout_with_log(page, settle_ms, f"{description} 후 안정화")
    return True


def _handle_consent_flow(page, timeout_ms: int) -> bool:
    if _existing_claim_history_popup_open(page):
        return _dismiss_duplicate_accident_date_type_popup(page, timeout_ms)

    consent_modal = _find_consent_modal(page, CONSENT_GUIDE_PATTERN)
    if consent_modal is None:
        return False

    if _click_label_in_modal(
        consent_modal,
        label_for=CONSENT_FULL_AGREE_FOR,
        text_pattern=re.compile(r"\[?\s*필수\s*\]?\s*전체\s*동의"),
        description="동의 안내: [필수] 전체동의",
    ) or _maybe_click_consent_action(
        page,
        [re.compile(r"\[?\s*필수\s*\]?\s*전체\s*동의"), "[필수] 전체동의"],
        "동의 안내: [필수] 전체동의",
        scope=consent_modal,
    ):
        if _existing_claim_history_popup_open(page):
            return _click_existing_claim_history_no(page)
        common.wait_timeout_with_log(page, 600, "요약 동의서 시트 표시 대기")

    if _existing_claim_history_popup_open(page):
        return _dismiss_duplicate_accident_date_type_popup(page, timeout_ms)

    summary_modal = _find_consent_modal(page, CONSENT_SUMMARY_PATTERN)
    if summary_modal is not None:
        _scroll_consent_sheet_to_bottom(page)
        if not (
            _click_label_in_modal(
                summary_modal,
                label_for=None,
                text_pattern=re.compile(r"^전체동의$|아래로\s*내려서\s*동의"),
                description="요약 동의서: 전체동의",
            )
            or _maybe_click_consent_action(
                page,
                ["전체동의", re.compile(r"아래로\s*내려서\s*동의")],
                "요약 동의서: 전체동의",
                scope=summary_modal,
            )
        ):
            _scroll_consent_sheet_to_bottom(page)
            _click_label_in_modal(
                summary_modal,
                label_for=None,
                text_pattern=re.compile(r"^전체동의$"),
                description="요약 동의서: 전체동의(재시도)",
            )

    consent_modal = _find_consent_modal(page, re.compile(r"동의\s*안내"))
    if consent_modal is not None:
        return _click_button_in_modal(
            consent_modal,
            names=["다음", re.compile(r"^다음$")],
            description="동의 안내: 다음",
        ) or _maybe_click_consent_action(page, ["다음"], "동의 안내: 다음", scope=consent_modal)
    return False


def _ensure_checkbox_checked(
    page,
    *,
    label_selector: str,
    input_selector: str,
    description: str,
    label_text: str | None = None,
) -> None:
    try:
        checkbox = page.locator(input_selector).first
        if checkbox.count() > 0 and checkbox.is_checked(timeout=800):
            print(f"[step] {description} (이미 선택됨)")
            return
    except Exception:
        pass
    _click_selection_label(
        page,
        label_selector=label_selector,
        input_selector=input_selector,
        description=description,
        label_text=label_text,
    )


def _is_medical_beneficiary_none_selected(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                () => {
                    const input = document.querySelector('#radio10');
                    if (!input) {
                        return false;
                    }
                    const activeItem = input.closest('li');
                    return input.checked || !!(activeItem && activeItem.classList.contains('active'));
                }
                """
            )
        )
    except Exception:
        return False


def _select_medical_beneficiary_none(page) -> None:
    if _is_medical_beneficiary_none_selected(page):
        print("[step] 의료급여 수급권자: 해당없음 (이미 선택됨)")
        return
    _click_selection_label(
        page,
        label_selector=MEDICAL_BENEFIT_NONE_LABEL_SELECTOR,
        input_selector=MEDICAL_BENEFIT_NONE_INPUT_SELECTOR,
        description="의료급여 수급권자: 해당없음",
    )


def _is_saved_account_selected(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                () => {
                    const isSavedAccount = (text) => {
                        const normalized = (text || '').replace(/\\s+/g, ' ').trim();
                        return normalized
                            && !normalized.includes('선택해')
                            && (/\\d{6,}/.test(normalized) || normalized.includes('은행'));
                    };
                    const select = document.querySelector('#loanAccountSel2');
                    if (select && select.options.length > 0) {
                        const optionText = (select.options[select.selectedIndex]?.text || '').replace(/\\s+/g, ' ').trim();
                        if (isSavedAccount(optionText)) {
                            return true;
                        }
                    }
                    const trigger = document.querySelector('main .sel_panel.active a.select_btn');
                    const triggerText = (trigger?.innerText || trigger?.textContent || '').replace(/\\s+/g, ' ').trim();
                    return isSavedAccount(triggerText);
                }
                """
            )
        )
    except Exception:
        return False


def _click_detail_complete_button(page, timeout_ms: int) -> None:
    complete_button = page.locator(DETAIL_COMPLETE_SELECTOR).first
    for _ in range(max(1, timeout_ms // 400)):
        _close_gnb_menu_if_open(page)
        _wait_for_loading_overlay_gone(page, min(timeout_ms, 5000))
        if _existing_claim_history_popup_open(page):
            _dismiss_duplicate_accident_date_type_popup(page, timeout_ms)
            continue
        try:
            complete_button.wait_for(state="visible", timeout=1500)
            _scroll_target_to_center(complete_button)
            if complete_button.is_enabled(timeout=800):
                print("[click] 상세정보 입력완료(2/3)")
                complete_button.click(force=True, timeout=3000)
                common.wait_timeout_with_log(page, 400, "상세정보 입력완료(2/3) 후 안정화")
                return
        except Exception:
            pass
        common.wait_timeout_with_log(page, 400, "상세정보 입력완료 버튼 활성화 대기")
    raise RuntimeError("상세정보 입력완료(2/3) 버튼을 활성화하지 못했습니다.")


def _fill_claim_content(page) -> None:
    textarea = page.locator(CLAIM_CONTENT_TEXTAREA_SELECTOR).first
    common.wait_locator_visible_with_log(textarea, common.MAX_TIMEOUT_MS, "사고 내용 입력(#cont)")
    textarea.fill(CLAIM_CONTENT_TEXT)
    textarea.evaluate(
        """
        (element) => {
            element.dispatchEvent(new Event('input', { bubbles: true }));
            element.dispatchEvent(new Event('change', { bubbles: true }));
            element.blur();
        }
        """
    )
    print(f"[step] 사고 내용 입력: {CLAIM_CONTENT_TEXT}")


def _account_select_dialog_open(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                () => {
                    for (const dialog of document.querySelectorAll('.dialog.bottom.show, .dialog.show')) {
                        if (!dialog.classList.contains('show')) {
                            continue;
                        }
                        const text = (dialog.innerText || '').replace(/\\s+/g, ' ');
                        if (text.includes('계좌선택') || text.includes('계좌 선택')) {
                            return true;
                        }
                    }
                    return false;
                }
                """
            )
        )
    except Exception:
        return False


def _open_account_select_dialog(page, timeout_ms: int) -> None:
    if _account_select_dialog_open(page):
        return

    trigger = page.locator(ACCOUNT_SELECT_TRIGGER_SELECTOR).first
    common.wait_locator_visible_with_log(trigger, timeout_ms, "계좌선택 트리거(a.select_btn)")
    print("[click] 등록 계좌 선택 팝업 열기")
    try:
        trigger.click(force=True, timeout=3000)
    except Exception as exc:
        print(f"[warn] 계좌선택 트리거 일반 클릭 실패, JS 클릭 시도: {exc}")
        trigger.evaluate("element => element.click()")
    common.wait_timeout_with_log(page, 400, "계좌선택 팝업 표시 대기")

    for _ in range(max(3, timeout_ms // 1000)):
        if _account_select_dialog_open(page):
            return
        common.wait_timeout_with_log(page, 400, "계좌선택 팝업 표시 재시도")
    raise RuntimeError("계좌선택 팝업을 열지 못했습니다.")


def _click_saved_account_item(page, timeout_ms: int) -> None:
    dialog = page.locator(".dialog.bottom.show, .dialog.show").filter(has_text=ACCOUNT_SELECT_DIALOG_TEXT)
    saved_account = dialog.locator("a.ui-pop-select-btn").filter(has_text=SAVED_ACCOUNT_ITEM_PATTERN).first
    try:
        if saved_account.count() > 0:
            common.wait_locator_visible_with_log(saved_account, timeout_ms, "등록된 계좌 항목")
            print("[click] 등록된 계좌 선택")
            saved_account.click(force=True, timeout=3000)
            common.wait_timeout_with_log(page, 400, "계좌 선택 반영 대기")
            return
    except Exception as exc:
        print(f"[warn] 등록 계좌 Playwright 클릭 실패: {exc}")

    selected_label = page.evaluate(
        """
        () => {
            const dialogs = Array.from(document.querySelectorAll('.dialog.bottom.show, .dialog.show'))
                .filter((dialog) => dialog.classList.contains('show'));
            for (const dialog of dialogs) {
                const text = (dialog.innerText || '').replace(/\\s+/g, ' ');
                if (!text.includes('계좌선택') && !text.includes('계좌 선택')) {
                    continue;
                }
                for (const link of dialog.querySelectorAll('a.ui-pop-select-btn')) {
                    const label = (link.innerText || '').replace(/\\s+/g, ' ').trim();
                    if (!label || label.includes('선택해 주세요')) {
                        continue;
                    }
                    if (/\\d{6,}/.test(label) || label.includes('은행')) {
                        link.click();
                        return label;
                    }
                }
                for (const link of dialog.querySelectorAll('a.ui-pop-select-btn[data-value]')) {
                    const value = link.getAttribute('data-value');
                    if (!value || value === '0') {
                        continue;
                    }
                    link.click();
                    return (link.innerText || '').replace(/\\s+/g, ' ').trim() || value;
                }
            }
            return '';
        }
        """
    )
    if selected_label:
        print(f"[click] 등록된 계좌 선택(DOM): {selected_label}")
        common.wait_timeout_with_log(page, 400, "계좌 선택 반영 대기")
        return
    raise RuntimeError("등록된 계좌 항목을 찾지 못했습니다.")


def _select_saved_bank_account(page, timeout_ms: int) -> None:
    if _is_saved_account_selected(page):
        print("[step] 등록 계좌가 이미 선택되어 있습니다.")
        return

    account_combo = page.locator(ACCOUNT_COMBO_SELECTOR).first
    common.wait_locator_visible_with_log(account_combo, timeout_ms, "계좌선택(#acccombo)")
    account_combo.select_option(value="account")
    common.wait_timeout_with_log(page, 400, "계좌선택 모드 전환 대기")
    _wait_for_loading_overlay_gone(page, min(timeout_ms, 5000))
    _open_account_select_dialog(page, timeout_ms)
    _click_saved_account_item(page, timeout_ms)
    for _ in range(max(3, timeout_ms // 1000)):
        if not _account_select_dialog_open(page):
            return
        common.wait_timeout_with_log(page, 400, "계좌선택 팝업 닫힘 대기")
    print("[warn] 계좌선택 팝업이 닫히지 않았지만 계속 진행")


def _complete_detail_step(page, timeout_ms: int) -> None:
    _close_gnb_menu_if_open(page)
    _wait_for_loading_overlay_gone(page, timeout_ms)
    _ensure_checkbox_checked(
        page,
        label_selector=CLAIM_TYPE_DIAGNOSIS_LABEL_SELECTOR,
        input_selector=CLAIM_TYPE_DIAGNOSIS_INPUT_SELECTOR,
        description="청구 유형: 진단비",
        label_text="진단비",
    )
    _ensure_checkbox_checked(
        page,
        label_selector=CLAIM_DETAIL_OTHER_DIAGNOSIS_LABEL_SELECTOR,
        input_selector=CLAIM_DETAIL_OTHER_DIAGNOSIS_INPUT_SELECTOR,
        description="청구 상세 유형: 기타 진단",
        label_text="기타 진단",
    )
    _fill_claim_content(page)
    _select_saved_bank_account(page, timeout_ms)
    _select_medical_beneficiary_none(page)
    _click_detail_complete_button(page, timeout_ms)
    for _ in range(max(1, timeout_ms // 400)):
        if _existing_claim_history_popup_open(page):
            _dismiss_duplicate_accident_date_type_popup(page, timeout_ms)
            _click_detail_complete_button(page, timeout_ms)
            continue
        if _maybe_click_modal_action(
            page,
            re.compile(r"접수\s*정보|서류\s*제출"),
            ["확인 후 서류제출 하러 가기", re.compile(r"확인\s*후\s*서류\s*제출")],
            "접수정보 확인: 서류제출 이동",
        ):
            if DOCUMENT_UPLOAD_URL_FRAGMENT in page.url:
                _wait_url_contains(page, DOCUMENT_UPLOAD_URL_FRAGMENT, timeout_ms)
                return
            continue
        if _maybe_click_named_action(
            page,
            ["확인 후 서류제출 하러 가기", re.compile(r"확인\s*후\s*서류\s*제출")],
            "접수정보 확인: 서류제출 이동",
        ):
            if DOCUMENT_UPLOAD_URL_FRAGMENT in page.url:
                _wait_url_contains(page, DOCUMENT_UPLOAD_URL_FRAGMENT, timeout_ms)
                return
            continue
        if DOCUMENT_UPLOAD_URL_FRAGMENT in page.url:
            _wait_url_contains(page, DOCUMENT_UPLOAD_URL_FRAGMENT, timeout_ms)
            return
        common.wait_timeout_with_log(page, 400, "서류등록 화면 대기")
    _wait_url_contains(page, DOCUMENT_UPLOAD_URL_FRAGMENT, timeout_ms)


def _upload_via_album(page, category_pattern: re.Pattern[str], file_path: Path, description: str) -> None:
    category_button = page.get_by_role("button", name=category_pattern).first
    common.click_with_log(category_button, f"{description} 업로드 영역 열기")
    common.wait_timeout_with_log(page, 500, "서류 등록 시트 표시 대기")
    album_label = page.locator('label[for="galleyFile"]').first
    print(f"[upload] {description}: {file_path.name}")
    try:
        with page.expect_file_chooser(timeout=5000) as chooser_info:
            common.click_with_log(album_label, f"{description} 앨범 선택")
        chooser_info.value.set_files(str(file_path))
    except Exception:
        page.locator(GALLERY_FILE_INPUT_SELECTOR).set_input_files(str(file_path))
    page.wait_for_function(
        """
        () => {
            const previews = Array.from(document.querySelectorAll('img[alt="미리보기 이미지"], img[alt*="미리보기"]'))
                .filter((element) => {
                    const rect = element.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                });
            return previews.length > 0;
        }
        """,
        timeout=common.MAX_TIMEOUT_MS,
    )
    common.wait_timeout_with_log(page, 800, f"{description} 업로드 반영 대기")


def _upload_claim_documents(page) -> None:
    primary_file = _pick_random_desktop_screenshot()
    secondary_file = _pick_random_desktop_screenshot()
    _upload_via_album(page, PRIMARY_UPLOAD_BUTTON_PATTERN, primary_file, "보험금청구서류")
    _upload_via_album(page, SECONDARY_UPLOAD_BUTTON_PATTERN, secondary_file, "진료비 세부(산정)내역서")


def _submit_documents(page, timeout_ms: int) -> None:
    _click_named_action(
        page,
        ["서류 제출 후 완료(3/3)", re.compile(r"서류\s*제출\s*후\s*완료")],
        "서류 제출 후 완료(3/3)",
    )
    for _ in range(max(1, timeout_ms // 400)):
        if _maybe_click_modal_action(
            page,
            re.compile(r"첨부파일을\s*전송|서류를\s*추가"),
            ["서류제출", re.compile(r"^서류제출$")],
            "첨부파일 전송 확인: 서류제출",
        ):
            continue
        if CLAIM_COMPLETE_URL_FRAGMENT in page.url:
            return
        common.wait_timeout_with_log(page, 400, "보험금청구 완료 화면 대기")
    _wait_url_contains(page, CLAIM_COMPLETE_URL_FRAGMENT, timeout_ms)


def _service_satisfaction_popup_open(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                () => {
                    for (const dialog of document.querySelectorAll('.dialog.full.show, .dialog.show')) {
                        if (!dialog.classList.contains('show')) {
                            continue;
                        }
                        const text = (dialog.innerText || '').replace(/\\s+/g, ' ');
                        if (text.includes('서비스만족도 조사') || text.includes('서비스이용은')) {
                            return true;
                        }
                    }
                    return false;
                }
                """
            )
        )
    except Exception:
        return False


def _dismiss_service_satisfaction_popup(page, timeout_ms: int) -> None:
    saw_popup = False
    for _ in range(max(5, timeout_ms // 400)):
        if not _service_satisfaction_popup_open(page):
            if saw_popup:
                print("[step] 서비스만족도 조사 팝업 닫기 완료")
                return
            common.wait_timeout_with_log(page, 400, "서비스만족도 조사 팝업 표시 대기")
            continue

        saw_popup = True
        clicked = page.evaluate(
            """
            () => {
                for (const dialog of document.querySelectorAll('.dialog.full.show, .dialog.show')) {
                    if (!dialog.classList.contains('show')) {
                        continue;
                    }
                    const text = (dialog.innerText || '').replace(/\\s+/g, ' ');
                    if (!text.includes('서비스만족도 조사') && !text.includes('서비스이용은')) {
                        continue;
                    }
                    const closeButton = dialog.querySelector(
                        'button.dialog_close.ui_dialog_close, a.dialog_close.ui_dialog_close'
                    );
                    if (!closeButton) {
                        continue;
                    }
                    closeButton.click();
                    return (closeButton.getAttribute('title') || closeButton.innerText || '팝업창 닫기')
                        .replace(/\\s+/g, ' ')
                        .trim();
                }
                return '';
            }
            """
        )
        if clicked:
            print(f"[click] 서비스만족도 조사 팝업 닫기: {clicked}")
            common.wait_timeout_with_log(page, 500, "서비스만족도 조사 팝업 닫힘 대기")
            if not _service_satisfaction_popup_open(page):
                return
        else:
            dialog = page.locator(SERVICE_SATISFACTION_DIALOG_SELECTOR).filter(
                has_text=SERVICE_SATISFACTION_DIALOG_TEXT
            )
            try:
                close_button = dialog.locator(SERVICE_SATISFACTION_CLOSE_SELECTOR).first
                if close_button.count() > 0:
                    print("[click] 서비스만족도 조사 팝업 닫기: 팝업창 닫기")
                    close_button.click(force=True, timeout=3000)
                    common.wait_timeout_with_log(page, 500, "서비스만족도 조사 팝업 닫힘 대기")
                    if not _service_satisfaction_popup_open(page):
                        return
            except Exception as exc:
                print(f"[warn] 서비스만족도 조사 팝업 Playwright 닫기 실패: {exc}")
        common.wait_timeout_with_log(page, 400, "서비스만족도 조사 팝업 재시도")
    if _service_satisfaction_popup_open(page):
        raise RuntimeError("서비스만족도 조사 팝업을 닫지 못했습니다.")
    print("[step] 서비스만족도 조사 팝업 없음")


def _assert_claim_complete(page, timeout_ms: int) -> None:
    for _ in range(max(1, timeout_ms // 500)):
        url_ok = CLAIM_COMPLETE_URL_FRAGMENT in page.url
        try:
            body_text = page.locator("body").inner_text()
        except Exception:
            body_text = ""
        if url_ok and CLAIM_COMPLETE_HEADING_PATTERN.search(body_text):
            return
        if _maybe_click_named_action(
            page,
            [re.compile(r"팝업창\s*닫기"), "팝업창 닫기"],
            "완료 후 부가 팝업 닫기",
        ):
            continue
        common.wait_timeout_with_log(page, 400, "보험금청구 완료 화면 대기")
    raise RuntimeError("보험금청구 완료 화면(IbnfDmRcp1090)을 확인하지 못했습니다.")


def run(page, config: common.LoginConfig) -> str:
    _navigate_to_claim_entry(page, config.timeout_ms, config.base_url)
    _start_claim_from_intro(page, config.timeout_ms)
    _complete_target_selection(page, config.timeout_ms)
    _complete_claim_reason_step(page, config.timeout_ms)
    _complete_detail_step(page, config.timeout_ms)
    _upload_claim_documents(page)
    _submit_documents(page, config.timeout_ms)
    _assert_claim_complete(page, config.timeout_ms)
    _dismiss_service_satisfaction_popup(page, config.timeout_ms)
    return f"보험금청구 접수 프로세스 완료 성공 ({page.url})"
