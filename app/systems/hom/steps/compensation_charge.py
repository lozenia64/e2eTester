from __future__ import annotations

import random
import re
from calendar import monthrange
from datetime import date
from pathlib import Path

from . import login_common as common

CHARGE00_FRAGMENT = "/fplaza/compensation/charge00.do"
POPUP_CONFIRM_PATTERN = re.compile(r"보험금청구를 위한 필요서류는 확인하셨나요")
READY_LINK_PATTERN = re.compile(r"준비가 된 상태")
STEP02_HEADING_PATTERN = re.compile(r"청구대상자\s*선택|질병/상해\s*보험금청구")
STEP05_HEADING_PATTERN = re.compile(r"서류등록|서류제출|파일첨부")
STEP06_HEADING_PATTERN = re.compile(r"청구완료|접수가\s*완료|등록되었습니다")
CLAIM_GUIDE_POPUP_ROOT = "#uiPOPBcgah00"
POP_LOADING_SELECTOR = "#popLoading"
VISIBLE_MODAL_SELECTOR = ".modal_popup:visible, .modal_wrap:visible, .pop_wrap:visible, .popup_wrap:visible, .pop_modal1:visible, .pop_modal2:visible, [role='dialog']:visible"
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
CHARGE03_ALL_CONSENT_INPUT_SELECTOR = "#formChk2"
CHARGE03_ALL_CONSENT_LABEL_SELECTOR = 'label[for="formChk2"]'
CHARGE04_OTHER_RADIO_SELECTOR = "#formAccident1_4"
CHARGE04_OTHER_LABEL_SELECTOR = 'label[for="formAccident1_4"]'
CHARGE04_DATE_INPUT_SELECTOR = "#sendDate"
CHARGE04_QUERY_SELECTOR = '#searchBtn a[href="javascript:goSearch();"]'
CHARGE04_CONTENT_TEXTAREA_SELECTOR = "#clmCn"
CHARGE04_NEXT_SELECTOR = 'a[href="javascript:popDetail()"]'
CHARGE05_PRIMARY_UPLOAD_FRAME_SELECTORS = (
    "#dext5uploader_frame_dext5upload4",
    'iframe[title="진료비영수증, 진단서, 수술확인서 등"]',
)
CHARGE05_SECONDARY_UPLOAD_FRAME_SELECTORS = (
    "#dext5uploader_frame_dext5upload9",
    'iframe[title="진료비 세부(산정) 내역서"]',
    'iframe[title="DEXT5 Upload Component"]',
)
CHARGE05_FILE_INPUT_SELECTOR = 'input[type="file"]'
CHARGE05_FILE_ADD_BUTTON_SELECTOR = "button#button_add"
CHARGE05_COMPLETE_SELECTOR = 'a[href="javascript:confirmBtn()"]'
CLAIM_TYPE_NOTICE_PATTERN = re.compile(r"청구유형\s*선택\s*안내")


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


def _wait_for_overlay_to_clear(page, selector: str, timeout_ms: int, description: str) -> None:
    print(f"[wait] Start overlay clear wait: {description} ({timeout_ms} ms)")
    page.wait_for_function(
        """
        overlaySelector => {
            const element = document.querySelector(overlaySelector);
            if (!element) {
                return true;
            }
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            const visible =
                style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                rect.width > 0 &&
                rect.height > 0;
            const open = element.classList.contains('open');
            return !(visible && open);
        }
        """,
        arg=selector,
        timeout=timeout_ms,
    )
    print(f"[wait] End overlay clear wait: {description}")


def _first_visible_selector(page, selector: str, description: str):
    return common.first_visible_locator(page.locator(selector), description)


def _action_locators(root, name_pattern: str | re.Pattern[str]):
    locators = [
        root.get_by_role("button", name=name_pattern),
        root.get_by_role("link", name=name_pattern),
    ]
    if isinstance(name_pattern, str):
        locators.extend(
            [
                root.locator(f'button:has-text("{name_pattern}")'),
                root.locator(f'a:has-text("{name_pattern}")'),
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


def _set_text_field_by_keywords(
    page,
    keywords: tuple[str, ...],
    value: str,
    *,
    prefer_textarea: bool = False,
) -> bool:
    return bool(
        page.evaluate(
            """
            ({ keywords, value, preferTextarea }) => {
                const normalize = (input) => (input || '').replace(/\\s+/g, ' ').trim();
                const isVisible = (element) => {
                    if (!element) {
                        return false;
                    }
                    const style = window.getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const selectorOrder = preferTextarea
                    ? ['textarea', 'input[type="text"]', 'input:not([type])', 'input[type="tel"]']
                    : ['input[type="text"]', 'input:not([type])', 'input[type="tel"]', 'textarea'];
                const containers = Array.from(document.querySelectorAll('tr, li, dl, dd, td, th, div, section, article'))
                    .filter((element) => isVisible(element))
                    .map((element) => ({ element, text: normalize(element.innerText) }))
                    .filter(({ text }) => keywords.every((keyword) => text.includes(keyword)))
                    .sort((left, right) => left.text.length - right.text.length);

                for (const { element } of containers) {
                    for (const selector of selectorOrder) {
                        const fields = Array.from(element.querySelectorAll(selector)).filter((field) => {
                            if (field.disabled) {
                                return false;
                            }
                            if (field.type === 'hidden') {
                                return false;
                            }
                            return isVisible(field);
                        });
                        for (const field of fields) {
                            const hadReadOnly = Boolean(field.readOnly);
                            try {
                                if (hadReadOnly) {
                                    field.readOnly = false;
                                }
                            } catch (error) {}
                            field.scrollIntoView({ block: 'center', inline: 'nearest' });
                            field.focus();
                            field.value = '';
                            field.dispatchEvent(new Event('input', { bubbles: true }));
                            field.value = value;
                            field.dispatchEvent(new Event('input', { bubbles: true }));
                            field.dispatchEvent(new Event('change', { bubbles: true }));
                            field.blur();
                            try {
                                if (hadReadOnly) {
                                    field.readOnly = true;
                                }
                            } catch (error) {}
                            return true;
                        }
                    }
                }
                return false;
            }
            """,
            {
                "keywords": list(keywords),
                "value": value,
                "preferTextarea": prefer_textarea,
            },
        )
    )


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
    values = {
        "compact": target.strftime("%Y%m%d"),
        "dotted": target.strftime("%Y.%m.%d"),
        "dashed": target.strftime("%Y-%m-%d"),
    }
    direct_input = page.locator(CHARGE04_DATE_INPUT_SELECTOR).first
    try:
        if direct_input.is_visible(timeout=1500):
            direct_input.fill(values["compact"])
            normalized_value = direct_input.evaluate(
                """
                (element) => {
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.blur();
                    return element.value;
                }
                """
            )
            if _normalize_text(normalized_value):
                print(f"[step] 사고일을 1개월 전 날짜로 입력: {normalized_value}")
                common.wait_timeout_with_log(page, 400, "사고일 입력 반영 대기")
                return
    except Exception:
        pass
    applied = bool(
        page.evaluate(
            """
            ({ keywords, values }) => {
                const normalize = (input) => (input || '').replace(/\\s+/g, ' ').trim();
                const isVisible = (element) => {
                    if (!element) {
                        return false;
                    }
                    const style = window.getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const chooseFormats = (field) => {
                    const hint = normalize([
                        field.getAttribute('placeholder'),
                        field.getAttribute('title'),
                        field.getAttribute('aria-label'),
                        field.id,
                        field.name,
                        field.className,
                    ].join(' '));
                    if (hint.includes('.')) {
                        return [values.dotted, values.dashed, values.compact];
                    }
                    if (hint.includes('-')) {
                        return [values.dashed, values.dotted, values.compact];
                    }
                    return [values.compact, values.dotted, values.dashed];
                };
                const containers = Array.from(document.querySelectorAll('tr, li, dl, dd, td, th, div, section, article'))
                    .filter((element) => isVisible(element))
                    .map((element) => ({ element, text: normalize(element.innerText) }))
                    .filter(({ text }) => keywords.every((keyword) => text.includes(keyword)))
                    .sort((left, right) => left.text.length - right.text.length);

                for (const { element } of containers) {
                    const trigger = Array.from(element.querySelectorAll('button, a, img, span, label')).find((candidate) => {
                        const hint = normalize([
                            candidate.innerText,
                            candidate.getAttribute('title'),
                            candidate.getAttribute('aria-label'),
                            candidate.className,
                        ].join(' ')).toLowerCase();
                        return hint.includes('달력') || hint.includes('캘린더') || hint.includes('calendar') || hint.includes('datepicker');
                    });
                    if (trigger && isVisible(trigger)) {
                        trigger.click();
                    }
                    const fields = Array.from(
                        element.querySelectorAll('input[type="text"], input:not([type]), input[type="tel"]')
                    ).filter((field) => !field.disabled && field.type !== 'hidden' && isVisible(field));
                    for (const field of fields) {
                        const hadReadOnly = Boolean(field.readOnly);
                        try {
                            if (hadReadOnly) {
                                field.readOnly = false;
                            }
                        } catch (error) {}
                        field.scrollIntoView({ block: 'center', inline: 'nearest' });
                        field.focus();
                        for (const candidate of chooseFormats(field)) {
                            field.value = '';
                            field.dispatchEvent(new Event('input', { bubbles: true }));
                            field.value = candidate;
                            field.dispatchEvent(new Event('input', { bubbles: true }));
                            field.dispatchEvent(new Event('change', { bubbles: true }));
                            if (normalize(field.value)) {
                                field.blur();
                                try {
                                    if (hadReadOnly) {
                                        field.readOnly = true;
                                    }
                                } catch (error) {}
                                return true;
                            }
                        }
                        field.blur();
                        try {
                            if (hadReadOnly) {
                                field.readOnly = true;
                            }
                        } catch (error) {}
                    }
                }
                return false;
            }
            """,
            {
                "keywords": ["사고일"],
                "values": values,
            },
        )
    )
    if not applied:
        raise RuntimeError("사고일 입력 필드를 찾지 못했습니다.")
    print(f"[step] 사고일을 1개월 전 날짜로 입력: {values['dotted']}")
    common.wait_timeout_with_log(page, 400, "사고일 입력 반영 대기")


def _maybe_confirm_claim_type_notice_popup(page) -> bool:
    return _maybe_click_modal_action(
        page,
        CLAIM_TYPE_NOTICE_PATTERN,
        [re.compile(r"^확인$"), "확인"],
        "청구유형 선택 안내 팝업 확인",
    )


def _select_claim_type_other(page) -> None:
    other_radio = page.locator(CHARGE04_OTHER_RADIO_SELECTOR).first
    other_label = page.locator(CHARGE04_OTHER_LABEL_SELECTOR).first
    print("[click] 청구유형: 기타 라벨")
    try:
        if other_label.is_visible(timeout=1500):
            common.click_with_log(other_label, "청구유형: 기타 라벨 클릭")
            if other_radio.is_checked():
                common.wait_timeout_with_log(page, 300, "청구유형 선택 반영 대기")
                return
    except Exception:
        pass
    table = common.first_visible_locator(
        page.get_by_role("table", name=re.compile(r"청구\s*상세내용")),
        "청구 상세내용 표",
    )
    other_radio = common.first_visible_locator(
        table.get_by_role("radio", name="기타"),
        "청구유형 기타 라디오",
    )
    try:
        other_radio.check(timeout=common.MAX_TIMEOUT_MS)
    except Exception:
        other_label.click(force=True, timeout=common.MAX_TIMEOUT_MS)
    common.wait_timeout_with_log(page, 300, "청구유형 선택 반영 대기")


def _click_lookup_and_prepare_claim_content(page, timeout_ms: int) -> None:
    lookup = _first_visible_selector(page, CHARGE04_QUERY_SELECTOR, "청구 상세내용 조회(#searchBtn)")
    common.wait_locator_visible_with_log(lookup, timeout_ms, "청구 상세내용 조회(#searchBtn)")
    common.click_with_log(lookup, "청구 상세내용 조회")
    common.wait_timeout_with_log(page, 3000, "청구 상세내용 조회 완료 대기")
    textarea = page.locator(CHARGE04_CONTENT_TEXTAREA_SELECTOR).first
    for _ in range(max(1, timeout_ms // 400)):
        if _maybe_confirm_claim_type_notice_popup(page):
            continue
        try:
            if textarea.is_visible(timeout=800):
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
                if textarea.input_value(timeout=800) == CLAIM_CONTENT_TEXT:
                    print(f"[step] 청구내용 입력: {CLAIM_CONTENT_TEXT}")
                    return
        except Exception:
            pass
        if _set_text_field_by_keywords(
            page,
            ("청구내용",),
            CLAIM_CONTENT_TEXT,
            prefer_textarea=True,
        ):
            try:
                if textarea.is_visible(timeout=800) and textarea.input_value(timeout=800) == CLAIM_CONTENT_TEXT:
                    print(f"[step] 청구내용 입력: {CLAIM_CONTENT_TEXT}")
                    return
            except Exception:
                pass
        common.wait_timeout_with_log(page, 400, "청구내용 입력 영역 대기")
    raise RuntimeError("청구내용 입력 필드를 찾지 못했습니다.")


def _click_next_and_go_charge05(page, timeout_ms: int) -> None:
    for _ in range(max(1, timeout_ms // 400)):
        if _maybe_confirm_claim_type_notice_popup(page):
            continue
        next_button = page.locator(CHARGE04_NEXT_SELECTOR).first
        try:
            if next_button.is_visible(timeout=500):
                common.click_with_log(next_button, "청구내용 입력 다음 버튼")
                break
        except Exception:
            pass
        common.wait_timeout_with_log(page, 400, "청구내용 입력 다음 버튼 대기")
    else:
        raise RuntimeError("표시 중인 요소를 찾지 못했습니다: 청구내용 입력 다음 버튼")

    for _ in range(max(1, timeout_ms // 400)):
        if "charge05.do" in page.url:
            _wait_url_contains(page, "charge05.do", timeout_ms)
            return
        if _maybe_confirm_claim_type_notice_popup(page):
            continue
        if _maybe_click_modal_action(
            page,
            re.compile(r"청구내용"),
            [re.compile(r"서류등록\s*진행"), "서류등록진행"],
            "청구내용 팝업: 서류등록진행",
        ):
            continue
        common.wait_timeout_with_log(page, 400, "charge05 이동 대기")
    _wait_url_contains(page, "charge05.do", timeout_ms)


def _assert_charge05_landed(page, timeout_ms: int) -> None:
    for _ in range(max(1, timeout_ms // 500)):
        url_ok = "charge05.do" in page.url
        try:
            body_text = page.locator("body").inner_text()
        except Exception:
            body_text = ""
        if url_ok and STEP05_HEADING_PATTERN.search(body_text):
            return
        common.wait_timeout_with_log(page, 400, "charge05 화면 요소 대기")
    raise RuntimeError("보험금청구 charge05 화면(서류등록)을 확인하지 못했습니다.")


def _dismiss_modal_with_close_like_button(page, modal_text_pattern: re.Pattern[str]) -> bool:
    return bool(
        page.evaluate(
            """
            (patternSource) => {
                const pattern = new RegExp(patternSource, 'i');
                const normalize = (input) => (input || '').replace(/\\s+/g, ' ').trim();
                const isVisible = (element) => {
                    if (!element) {
                        return false;
                    }
                    const style = window.getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const clickTarget = (element) => {
                    if (!element || !isVisible(element)) {
                        return false;
                    }
                    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    element.click();
                    return true;
                };
                const roots = Array.from(
                    document.querySelectorAll('.modal_popup, .modal_wrap, .pop_wrap, .popup_wrap, [role="dialog"]')
                ).filter((element) => isVisible(element) && pattern.test(normalize(element.innerText)));
                for (const root of roots) {
                    for (const candidate of root.querySelectorAll('button, a, input, [role="button"]')) {
                        const text = normalize(candidate.innerText);
                        const title = normalize(candidate.getAttribute('title'));
                        const ariaLabel = normalize(candidate.getAttribute('aria-label'));
                        const value = normalize(candidate.getAttribute('value'));
                        const lowerText = text.toLowerCase();
                        const closeLike = (
                            text.includes('닫기') ||
                            title.includes('닫기') ||
                            ariaLabel.includes('닫기') ||
                            value.includes('닫기') ||
                            text === '×' ||
                            lowerText === 'x' ||
                            title.toLowerCase() === 'x' ||
                            ariaLabel.toLowerCase() === 'x'
                        );
                        if (closeLike && clickTarget(candidate)) {
                            return true;
                        }
                    }
                }
                return false;
            }
            """,
            modal_text_pattern.pattern,
        )
    )


def _maybe_close_upload_notice_popup(page) -> None:
    modal_pattern = re.compile(r"서류제출\s*시\s*유의사항|유의사항")
    if _maybe_click_modal_action(
        page,
        modal_pattern,
        [re.compile(r"닫기"), "닫기"],
        "서류제출 시 유의사항 팝업 닫기",
    ):
        return
    if _dismiss_modal_with_close_like_button(page, modal_pattern):
        print("[click] 서류제출 시 유의사항 팝업 닫기 (DOM fallback)")
        common.wait_timeout_with_log(page, 400, "유의사항 팝업 닫기 후 안정화")


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


def _resolve_visible_frame_selector(page, selectors: tuple[str, ...], description: str) -> str:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=1200):
                return selector
        except Exception:
            continue
    joined = ", ".join(selectors)
    raise RuntimeError(f"{description} 업로드 프레임을 찾지 못했습니다: {joined}")


def _wait_for_uploaded_item(page, frame_selector: str, description: str, timeout_ms: int) -> None:
    print(f"[wait] Start upload reflection wait: {description} ({timeout_ms} ms)")
    page.wait_for_function(
        """
        ({ frameSelector }) => {
            const iframe = document.querySelector(frameSelector);
            const doc = iframe?.contentDocument;
            if (!doc) {
                return false;
            }
            const texts = Array.from(doc.querySelectorAll('li, strong, span, p'))
                .map((element) => (element.textContent || '').replace(/\\s+/g, ' ').trim())
                .filter(Boolean);
            const hasUploadedCount = texts.some((text) => {
                const match = text.match(/(\\d+)\\s*개/);
                return Boolean(match) && Number(match[1]) > 0;
            });
            const hasUploadedFileEntry = texts.some((text) => /\\.(png|jpe?g|gif|bmp|pdf)\\b/i.test(text));
            return hasUploadedCount || hasUploadedFileEntry;
        }
        """,
        arg={"frameSelector": frame_selector},
        timeout=timeout_ms,
    )
    print(f"[wait] End upload reflection wait: {description}")


def _upload_file_to_frame(page, frame_selectors: tuple[str, ...], file_path: Path, description: str) -> None:
    frame_selector = _resolve_visible_frame_selector(page, frame_selectors, description)
    frame = page.locator(frame_selector).first
    frame_locator = page.frame_locator(frame_selector)
    add_button = frame_locator.locator(CHARGE05_FILE_ADD_BUTTON_SELECTOR).first
    input_locator = frame_locator.locator(CHARGE05_FILE_INPUT_SELECTOR).first
    print(f"[upload] {description}: {file_path.name}")
    common.wait_locator_visible_with_log(frame, common.MAX_TIMEOUT_MS, f"{description} 업로드 프레임")
    try:
        with page.expect_file_chooser(timeout=3000) as chooser_info:
            add_button.click(timeout=common.MAX_TIMEOUT_MS)
        chooser_info.value.set_files(str(file_path))
    except Exception:
        input_locator.set_input_files(str(file_path))
    _wait_for_uploaded_item(page, frame_selector, f"{description} 업로드 항목 반영", common.MAX_TIMEOUT_MS)
    common.wait_timeout_with_log(page, 1000, f"{description} 업로드 반영 대기")


def _upload_claim_documents(page) -> None:
    primary_file = _pick_random_desktop_screenshot()
    secondary_file = _pick_random_desktop_screenshot()
    _upload_file_to_frame(
        page,
        CHARGE05_PRIMARY_UPLOAD_FRAME_SELECTORS,
        primary_file,
        "진료비영수증/진단서/수술확인서 등 첨부",
    )
    _upload_file_to_frame(
        page,
        CHARGE05_SECONDARY_UPLOAD_FRAME_SELECTORS,
        secondary_file,
        "진료비 세부(산정) 내역서 첨부",
    )


def _submit_documents_and_wait_charge06(page, timeout_ms: int) -> None:
    submit = _first_visible_selector(page, CHARGE05_COMPLETE_SELECTOR, "서류등록/청구완료 링크")
    common.click_with_log(submit, "서류등록/청구완료 클릭")
    for _ in range(max(1, timeout_ms // 400)):
        if "charge06.do" in page.url:
            return
        if _maybe_click_modal_action(
            page,
            re.compile(r"계속 진행하시겠습니까"),
            [re.compile(r"^확인$"), "확인"],
            "계속 진행 확인 팝업",
        ):
            continue
        if _maybe_click_modal_action(
            page,
            re.compile(r"정상적으로 등록되었습니다|등록되었습니다"),
            [re.compile(r"닫기"), "닫기"],
            "등록 완료 알림 닫기",
        ):
            continue
        common.wait_timeout_with_log(page, 400, "charge06 이동 대기")
    _wait_url_contains(page, "charge06.do", timeout_ms)


def _assert_charge06_landed(page, timeout_ms: int) -> None:
    for _ in range(max(1, timeout_ms // 500)):
        url_ok = "charge06.do" in page.url
        try:
            body_text = page.locator("body").inner_text()
        except Exception:
            body_text = ""
        if url_ok and STEP06_HEADING_PATTERN.search(body_text):
            return
        if _maybe_click_modal_action(
            page,
            re.compile(r"정상적으로 등록되었습니다|등록되었습니다"),
            [re.compile(r"닫기"), "닫기"],
            "등록 완료 알림 닫기",
        ):
            continue
        common.wait_timeout_with_log(page, 400, "charge06 화면 요소 대기")
    raise RuntimeError("보험금청구 charge06 화면(청구완료)을 확인하지 못했습니다.")


def _open_charge00_from_menu(page, timeout_ms: int) -> bool:
    common.maybe_close_post_login_popup(page, timeout_ms)
    try:
        bosang = page.get_by_role("link", name=re.compile(r"^보상$")).first
        if not bosang.is_visible(timeout=2000):
            return False
        print("[step] Hover GNB 보상")
        bosang.hover(timeout=timeout_ms)
        common.wait_timeout_with_log(page, 600, "보상 메뉴 펼침 대기")
        link = common.first_visible_locator(
            page.locator(f'a[href*="{CHARGE00_FRAGMENT}"]'),
            "보상 메뉴의 charge00 링크",
        )
        common.click_with_log(link, "보상 > … > 보험금청구 접수(charge00) 메뉴 클릭")
        _wait_url_contains(page, "charge00.do", timeout_ms)
        return True
    except Exception as exc:
        print(f"[warn] 메뉴로 charge00 이동 실패, 직접 URL 시도: {exc}")
        return False


def _goto_charge00(page, config: common.LoginConfig) -> None:
    if not _open_charge00_from_menu(page, config.timeout_ms):
        common.maybe_close_post_login_popup(page, config.timeout_ms)
        base = config.base_url.rstrip("/")
        common.open_url(page, f"{base}{CHARGE00_FRAGMENT}")
        _wait_url_contains(page, "charge00.do", config.timeout_ms)


def _click_first_visible_href(page, href_substring: str, description: str, timeout_ms: int) -> None:
    link = common.first_visible_locator(
        page.locator(f'a[href*="{href_substring}"]'),
        description,
    )
    with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
        common.click_with_log(link, description)


def _open_document_check_popup(page, timeout_ms: int) -> None:
    apply_link = common.first_visible_locator(
        page.get_by_role("link", name=re.compile(r"보험금청구\s*신청")),
        "보험금청구신청(팝업 호출)",
    )
    common.click_with_log(apply_link, "보험금청구신청 클릭 (문서확인 팝업)")
    popup_marker = page.get_by_text(POPUP_CONFIRM_PATTERN).first
    common.wait_locator_visible_with_log(popup_marker, timeout_ms, "필요서류 확인 팝업")


def _confirm_ready_and_go_charge02(page, timeout_ms: int) -> None:
    ready = common.first_visible_locator(
        page.get_by_role("link", name=READY_LINK_PATTERN),
        "팝업: 준비가 된 상태입니다 링크",
    )
    print("[click] 팝업에서 서류 준비 완료 확인(준비가 된 상태)")
    with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
        try:
            ready.click(timeout=timeout_ms)
        except Exception:
            ready.click(force=True, timeout=timeout_ms)
    _wait_url_contains(page, "charge02.do", timeout_ms)


def _assert_charge02_landed(page, timeout_ms: int) -> None:
    for _ in range(max(1, timeout_ms // 500)):
        url_ok = "charge02.do" in page.url
        try:
            body_text = page.locator("body").inner_text()
        except Exception:
            body_text = ""
        text_ok = bool(STEP02_HEADING_PATTERN.search(body_text))
        if url_ok and text_ok:
            return
        common.wait_timeout_with_log(page, 400, "charge02 화면 요소 대기")
    raise RuntimeError(
        "보험금청구 charge02 화면(청구대상자 선택 등)을 확인하지 못했습니다.",
    )


def _select_self_claimant_and_open_contracts(page, timeout_ms: int) -> None:
    table = common.first_visible_locator(
        page.get_by_role("table", name=re.compile(r"청구대상자\s*선택")),
        "청구대상자 선택 표",
    )
    row = table.get_by_role("row").filter(
        has=page.get_by_role("rowheader", name="본인"),
    ).first
    name_cell = common.first_visible_locator(
        row.locator("td"),
        "본인 행의 이름(피보험자) 셀",
    )
    common.click_with_log(
        name_cell,
        "청구대상자: 본인 우측 이름 영역 클릭",
    )
    lookup = common.first_visible_locator(
        page.get_by_role("link", name=re.compile(r"청구가능계약\s*조회")),
        "청구가능계약 조회",
    )
    common.click_with_log(lookup, "청구가능계약 조회 클릭")
    _wait_for_overlay_to_clear(page, POP_LOADING_SELECTOR, timeout_ms, "청구가능계약 조회 popLoading")
    common.wait_timeout_with_log(page, 300, "청구가능계약 조회 결과 안정화")


def _maybe_dismiss_claim_guide_popup(page, timeout_ms: int) -> bool:
    confirm = page.locator(CLAIM_GUIDE_POPUP_ROOT).get_by_role("link", name="확인")
    try:
        if not confirm.is_visible(timeout=min(2800, timeout_ms)):
            return False
    except Exception:
        return False
    try:
        common.click_with_log(confirm, "보험금청구 안내 팝업 확인(닫기)")
    except Exception:
        confirm.click(force=True, timeout=min(timeout_ms, 3000))
    try:
        _wait_for_overlay_to_clear(page, CLAIM_GUIDE_POPUP_ROOT, min(timeout_ms, 4000), "보험금청구 안내 팝업")
    except Exception:
        pass
    try:
        _wait_for_overlay_to_clear(page, POP_LOADING_SELECTOR, min(timeout_ms, 4000), "보험금청구 안내 후 popLoading")
    except Exception:
        pass
    return True


def _open_new_reception_and_confirm_layer(page, timeout_ms: int) -> None:
    last_error: Exception | None = None
    for _ in range(max(1, timeout_ms // 500)):
        try:
            _wait_for_overlay_to_clear(page, POP_LOADING_SELECTOR, min(2000, timeout_ms), "신규접수 전 popLoading")
        except Exception:
            pass
        if _maybe_dismiss_claim_guide_popup(page, min(2200, timeout_ms)):
            continue
        new_rx = common.first_visible_locator(
            page.get_by_role("link", name="신규접수"),
            "신규접수(링크)",
        )
        print("[click] 신규접수 링크 클릭")
        try:
            new_rx.click(timeout=min(1200, timeout_ms))
            break
        except Exception as exc:
            last_error = exc
            common.wait_timeout_with_log(page, 400, "신규접수 링크 재시도 대기")
    else:
        raise RuntimeError(f"신규접수 링크 클릭 실패: {last_error}")

    _wait_for_overlay_to_clear(page, POP_LOADING_SELECTOR, timeout_ms, "신규접수 클릭 후 popLoading")
    common.wait_timeout_with_log(page, 500, "신규·추가접수 안내 레이어 표시 대기")
    btn = page.get_by_role("button", name="신규접수")
    try:
        if btn.is_visible(timeout=min(3500, timeout_ms)):
            common.click_with_log(btn, "신규·추가접수 안내: 신규접수 버튼")
    except Exception:
        pass


def _agree_entire_summary_consent_and_apply(page, timeout_ms: int) -> None:
    chk = page.locator(CHARGE03_ALL_CONSENT_INPUT_SELECTOR).first
    label = page.locator(CHARGE03_ALL_CONSENT_LABEL_SELECTOR).first
    common.wait_locator_visible_with_log(label, timeout_ms, "요약 동의서 전체동의 라벨")
    print("[click] [필수]보험금 청구를 위한 요약 동의서 — 전체동의 라벨")
    try:
        label.click(timeout=timeout_ms)
    except Exception:
        label.evaluate("el => el.click()")
    page.wait_for_function(
        "selector => !!document.querySelector(selector)?.checked",
        arg=CHARGE03_ALL_CONSENT_INPUT_SELECTOR,
        timeout=timeout_ms,
    )


def _click_bottom_claim_apply_and_wait_charge04(page, timeout_ms: int) -> None:
    submit = common.first_visible_locator(
        page.get_by_role("link", name="보험금청구신청"),
        "보험금청구신청(하단)",
    )
    with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
        common.click_with_log(submit, "보험금청구신청 클릭 → charge04")
    _wait_url_contains(page, "charge04.do", timeout_ms)


def run(page, config: common.LoginConfig, screenshot_path: Path) -> str:
    try:
        _goto_charge00(page, config)
        _click_first_visible_href(
            page,
            "charge01.do",
            "charge00 → charge01 (보험금청구신청 단계 진입)",
            config.timeout_ms,
        )
        _open_document_check_popup(page, config.timeout_ms)
        _confirm_ready_and_go_charge02(page, config.timeout_ms)
        _assert_charge02_landed(page, config.timeout_ms)
        _select_self_claimant_and_open_contracts(page, config.timeout_ms)
        _maybe_dismiss_claim_guide_popup(page, config.timeout_ms)
        _open_new_reception_and_confirm_layer(page, config.timeout_ms)
        _wait_url_contains(page, "charge03.do", config.timeout_ms)
        _agree_entire_summary_consent_and_apply(page, config.timeout_ms)
        _click_bottom_claim_apply_and_wait_charge04(page, config.timeout_ms)
        _select_claim_type_other(page)
        _set_accident_date_one_month_ago(page)
        _click_lookup_and_prepare_claim_content(page, config.timeout_ms)
        _click_next_and_go_charge05(page, config.timeout_ms)
        _assert_charge05_landed(page, config.timeout_ms)
        _maybe_close_upload_notice_popup(page)
        _upload_claim_documents(page)
        _submit_documents_and_wait_charge06(page, config.timeout_ms)
        _assert_charge06_landed(page, config.timeout_ms)
        common.save_screenshot(page, screenshot_path)
        return f"보험금청구 접수 프로세스 charge06 도달 성공 ({page.url})"
    except Exception:
        common.save_screenshot(page, screenshot_path)
        raise
