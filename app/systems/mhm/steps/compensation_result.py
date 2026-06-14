from __future__ import annotations

from pathlib import Path
import re

from . import compensation_result_common as result_common
from . import login_common as common

PREVIEW_SHEET_HEADING_PATTERN = re.compile(r"제출\s*서류\s*확인")
PREVIEW_MIN_DOCUMENT_COUNT = 2
PREVIEW_SHEET_SELECTOR = ".dialog.bottom.show, .dialog.full.show, .dialog.show, [role='dialog']"
PREVIEW_SWIPE_SELECTOR = ".hgismt_paper_swipe"
PREVIEW_IMAGE_LOAD_TIMEOUT_MS = 30000


def _assert_result_detail(page, timeout_ms: int, expected_receipt_number: str) -> None:
    result_common.wait_for_result02_detail_ready(page, timeout_ms, expected_receipt_number)

    receipt_number = result_common.normalize_receipt_number(
        result_common.detail_value(page, None, "접수번호")
    )
    claim_date = result_common.detail_value(page, None, "보험금청구일자")
    accident_date = result_common.detail_value(page, None, "발병(사고)일")
    claim_type = result_common.detail_value(page, None, "청구 유형")
    claim_content = result_common.detail_value(page, None, "청구 내용")

    expected = result_common.normalize_receipt_number(expected_receipt_number)
    if receipt_number != expected:
        raise RuntimeError(f"상세 화면 접수번호 불일치: expected={expected}, actual={receipt_number}")
    if claim_date != result_common.today_display():
        raise RuntimeError(f"상세 화면 보험금청구일자가 오늘 날짜가 아닙니다: {claim_date}")
    if not result_common.RESULT_DATE_PATTERN.fullmatch(accident_date):
        raise RuntimeError(f"상세 화면 발병(사고)일을 확인하지 못했습니다: {accident_date}")
    if not claim_type:
        raise RuntimeError("상세 화면 청구 유형을 확인하지 못했습니다.")
    if claim_content != result_common.TARGET_CLAIM_TEXT:
        raise RuntimeError(f"상세 화면 청구내용 불일치: {claim_content}")

    common.wait_locator_visible_with_log(
        page.get_by_role("button", name=result_common.DETAIL_PREVIEW_BUTTON_PATTERN),
        timeout_ms,
        "상세 화면 제출서류 확인하기",
    )
    common.wait_locator_visible_with_log(
        page.locator(result_common.DETAIL_CANCEL_SELECTOR),
        timeout_ms,
        "상세 화면 접수취소",
    )


def _preview_sheet_root(page):
    return page.locator(PREVIEW_SHEET_SELECTOR).filter(has_text=PREVIEW_SHEET_HEADING_PATTERN).first


def _preview_swipe_root(page):
    return _preview_sheet_root(page).locator(PREVIEW_SWIPE_SELECTOR).first


def _read_preview_slide_count(page) -> int:
    swipe = _preview_swipe_root(page)
    try:
        total = swipe.locator(".swiper-pagination-total").first
        if total.count() > 0:
            value = int(result_common.normalize_text(total.inner_text(timeout=1000)))
            if value > 0:
                return value
    except Exception:
        pass

    try:
        list_total = swipe.locator(".list_total").first
        if list_total.count() > 0:
            match = re.search(
                r"총\s*([0-9,]+)\s*건",
                result_common.normalize_text(list_total.inner_text(timeout=1000)),
            )
            if match:
                return int(match.group(1).replace(",", ""))
    except Exception:
        pass
    return 0


def _read_active_slide_index(page) -> int:
    swipe = _preview_swipe_root(page)
    try:
        current = swipe.locator(".swiper-pagination-current").first
        if current.count() > 0:
            return int(result_common.normalize_text(current.inner_text(timeout=1000)))
    except Exception:
        pass
    return 1


def _read_active_slide_title(page) -> str:
    sheet = _preview_sheet_root(page)
    try:
        title = sheet.locator(".swiper-slide-active .hgismt_list_tit").first
        if title.count() > 0:
            return result_common.normalize_text(title.inner_text(timeout=1000))
    except Exception:
        pass
    return ""


def _wait_for_active_slide_image(page, timeout_ms: int) -> dict:
    wait_ms = max(timeout_ms, PREVIEW_IMAGE_LOAD_TIMEOUT_MS)
    print(f"[wait] Start active slide image load wait ({wait_ms} ms)")
    page.wait_for_function(
        """
        () => {
            const isSheet = (root) => {
                const text = (root.innerText || '').replace(/\\s+/g, ' ');
                return text.includes('제출 서류 확인') || text.includes('제출서류 확인');
            };
            const sheets = Array.from(document.querySelectorAll(
                '.dialog.full.show, .dialog.bottom.show, .dialog.show'
            )).filter(isSheet);
            const sheet = sheets[0];
            if (!sheet) {
                return false;
            }
            const activeSlide = sheet.querySelector('.swiper-slide-active');
            if (!activeSlide) {
                return false;
            }
            const img = activeSlide.querySelector('img');
            if (!img) {
                return false;
            }
            const style = window.getComputedStyle(img);
            const rect = img.getBoundingClientRect();
            if (style.display === 'none' || style.visibility === 'hidden' || rect.width <= 0) {
                return false;
            }
            return img.naturalWidth > 0 && img.naturalHeight > 0;
        }
        """,
        timeout=wait_ms,
    )
    preview_meta = page.evaluate(
        """
        () => {
            const isSheet = (root) => {
                const text = (root.innerText || '').replace(/\\s+/g, ' ');
                return text.includes('제출 서류 확인') || text.includes('제출서류 확인');
            };
            const sheets = Array.from(document.querySelectorAll(
                '.dialog.full.show, .dialog.bottom.show, .dialog.show'
            )).filter(isSheet);
            const sheet = sheets[0];
            if (!sheet) {
                return null;
            }
            const activeSlide = sheet.querySelector('.swiper-slide-active');
            if (!activeSlide) {
                return null;
            }
            const img = activeSlide.querySelector('img');
            if (!img) {
                return null;
            }
            return {
                alt: img.getAttribute('alt') || '',
                src: img.getAttribute('src') || '',
                naturalWidth: img.naturalWidth || 0,
                naturalHeight: img.naturalHeight || 0,
            };
        }
        """
    )
    if not preview_meta:
        raise RuntimeError("제출 서류 확인 시트에서 활성 슬라이드 이미지를 확인하지 못했습니다.")
    print(
        "[wait] End active slide image load wait: "
        f"{preview_meta.get('alt') or '(제목 없음)'} "
        f"({preview_meta['naturalWidth']}x{preview_meta['naturalHeight']})"
    )
    return preview_meta


def _advance_preview_slide(page, timeout_ms: int) -> None:
    before_index = _read_active_slide_index(page)
    expected_index = before_index + 1
    next_button = _preview_swipe_root(page).locator("button.hgismt_next").first
    common.click_with_log(next_button, f"제출 서류 다음 슬라이드 ({expected_index})")
    page.wait_for_function(
        """
        (expectedIndex) => {
            const isSheet = (root) => {
                const text = (root.innerText || '').replace(/\\s+/g, ' ');
                return text.includes('제출 서류 확인') || text.includes('제출서류 확인');
            };
            const sheets = Array.from(document.querySelectorAll(
                '.dialog.full.show, .dialog.bottom.show, .dialog.show'
            )).filter(isSheet);
            const sheet = sheets[0];
            if (!sheet) {
                return false;
            }
            const current = sheet.querySelector('.swiper-pagination-current');
            return current && current.textContent.trim() === String(expectedIndex);
        }
        """,
        arg=expected_index,
        timeout=min(max(timeout_ms, 5000), 15000),
    )


def _verify_preview_slides(page, timeout_ms: int) -> None:
    slide_count = _read_preview_slide_count(page)
    if slide_count < PREVIEW_MIN_DOCUMENT_COUNT:
        raise RuntimeError(f"제출 서류 확인 시트 파일 개수가 부족합니다: {slide_count}")

    verified_titles: list[str] = []
    for slide_index in range(slide_count):
        if slide_index > 0:
            _advance_preview_slide(page, timeout_ms)

        preview_meta = _wait_for_active_slide_image(page, timeout_ms)
        title = _read_active_slide_title(page) or preview_meta.get("alt", "")
        if not title:
            raise RuntimeError(
                f"제출 서류 슬라이드 {slide_index + 1}/{slide_count} 제목을 확인하지 못했습니다."
            )
        if preview_meta["naturalWidth"] <= 0 or preview_meta["naturalHeight"] <= 0:
            raise RuntimeError(
                "제출 서류 확인 시트에서 미리보기 이미지를 확인하지 못했습니다: "
                f"{title} ({preview_meta['naturalWidth']}x{preview_meta['naturalHeight']})"
            )
        verified_titles.append(title)
        print(
            f"[step] 제출 서류 슬라이드 {slide_index + 1}/{slide_count} 확인: "
            f"{title} ({preview_meta['naturalWidth']}x{preview_meta['naturalHeight']})"
        )

    print(f"[step] 제출 서류 미리보기 슬라이드 {len(verified_titles)}건 검증 완료")


def _verify_preview_sheet(page, timeout_ms: int) -> None:
    preview_button = common.first_visible_locator(
        page.get_by_role("button", name=result_common.DETAIL_PREVIEW_BUTTON_PATTERN),
        "상세 화면 제출서류 확인하기",
    )
    common.click_with_log(preview_button, "제출서류 확인하기 클릭")
    heading = page.get_by_role("heading", name=PREVIEW_SHEET_HEADING_PATTERN).first
    common.wait_locator_visible_with_log(heading, timeout_ms, "제출 서류 확인 시트")
    common.wait_locator_visible_with_log(_preview_swipe_root(page), timeout_ms, "제출 서류 슬라이드 영역")

    _verify_preview_slides(page, timeout_ms)

    sheet = _preview_sheet_root(page)
    confirm = sheet.get_by_role("button", name="확인", exact=True).first
    try:
        common.click_with_log(confirm, "제출 서류 확인 시트 닫기")
    except Exception as exc:
        print(f"[warn] 제출 서류 확인 시트 닫기 일반 클릭 실패: {exc}")
        confirm.click(force=True, timeout=3000)
    common.wait_timeout_with_log(page, 400, "제출 서류 확인 시트 닫힘 대기")
    print("[step] 제출 서류 확인 시트 검증 완료")


def run(page, config: common.LoginConfig, screenshot_path: Path) -> str:
    try:
        result_common.goto_result01(page, config)
        result_common.select_results_tab(page, "", "진행중", config.timeout_ms)
        row = result_common.find_processing_claim_row(page, config.timeout_ms)
        receipt_number = result_common.receipt_number_from_row(row)
        result_common.open_claim_detail(page, row, config.timeout_ms)
        _assert_result_detail(page, config.timeout_ms, receipt_number)
        _verify_preview_sheet(page, config.timeout_ms)
        common.save_screenshot(page, screenshot_path)
        return f"보험금청구 결과 조회 성공 ({receipt_number})"
    except Exception:
        common.save_screenshot(page, screenshot_path)
        raise
