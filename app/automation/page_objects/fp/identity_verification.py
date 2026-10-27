from __future__ import annotations

import re

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.automation.page_objects.fp.contract_pages import (
    is_contract_write_page,
)
from app.runner.step_logging import log
from app.systems.access_common import browser

SALES_PAGE_PATH = "/fp/loan/sales01.do"
CONTRACT_WRITE_LINK = 'a[href="/fp/loan/sales01.do"]'

AGREE_ALL_LABEL = "label:has(#agreeAll)"
PHONE_RADIO_LABEL = "label:has(#name_cert02)"

NAME_INPUT = "#name"
SSN1_INPUT = "#ssn1"
SSN2_INPUT = "#ssn2"
CARRIER_SELECT = "#hpCom"
PHONE_PREFIX_SELECT = "#hndphTlano"
PHONE_MIDDLE_INPUT = "#hndphTltno"
PHONE_LAST_INPUT = "#hndphTlsno"
SMS_REQUEST_LINK = "#btnSendAuth"
OTP_INPUT = "#smsCertNo"
OTP_CONFIRM_BUTTON = "#btnSmsConfirm"
SUBMIT_CONTRACT_BUTTON = "#submitBtn"

PRIVACY_CONSENT_HEADING = "개인정보처리동의"
PHONE_AUTH_HEADING = "휴대폰인증"

CARRIER_VALUES: dict[str, str] = {
    "01": "01",
    "skt": "01",
    "sk": "01",
    "02": "02",
    "kt": "02",
    "03": "03",
    "lgu": "03",
    "lgu+": "03",
    "lguplus": "03",
    "lg": "03",
    "05": "05",
    "skt_mvno": "05",
    "skt-mvno": "05",
    "sktmvno": "05",
    "06": "06",
    "kt_mvno": "06",
    "kt-mvno": "06",
    "ktmvno": "06",
    "07": "07",
    "lgu_mvno": "07",
    "lgu-mvno": "07",
    "lgumvno": "07",
    "lguplus_mvno": "07",
    "lguplus-mvno": "07",
    "lguplusmvno": "07",
}

SSN1_PATTERN = re.compile(r"^\d{6}$")
SSN2_PATTERN = re.compile(r"^\d{7}$")
OTP_PATTERN = re.compile(r"^\d{4,8}$")

# nfilter: readonly 필드는 fill 불가. 키패드 showType 8 은 세션마다 숫자 위치가 섞인다.
# nFilterClick("1") 은 숨김 dummy map(#num_no_secretmap) 을 눌러 nFilterSecElement="1234567" 처럼
# 잘못된 값이 들어가고 decode-ssn-register.json 이 500 으로 실패한다.
# 올바른 입력: 섞인 키패드의 area id(10자)를 nFilterClick(areaId) 로 호출한다.
NFILTER_KEYPAD_MAIN = "#nfilter_main"
NFILTER_KEYPAD_ENTER = "#nfilter_num_content #nfilter_enter_num"
NFILTER_REFERENCE_IMAGE_FALLBACK = (
    "/nfilter/sample/nFilter_image_manager.jsp"
    "?nfilter_type=8&nfilter_imgsec=num_no_secret&postfix=246"
)
NFILTER_KEY_CELL_WIDTH = 31
NFILTER_KEY_CELL_HEIGHT = 29
NFILTER_REFERENCE_POSITIONS: dict[str, str] = {
    "1": "0,0",
    "2": "35,0",
    "3": "70,0",
    "4": "105,0",
    "5": "140,0",
    "6": "35,33",
    "7": "70,33",
    "8": "105,33",
    "9": "140,33",
    "0": "175,33",
}
NFILTER_KEY_CLICK_PAUSE_MS = 150
NFILTER_KEY_CLICK_RETRY_MAX = 3
NFILTER_FILL_ATTEMPTS_MAX = 3

NFILTER_COLLECT_AREA_IDS_JS = """
() => {
  const hiddenMapIds = new Set(['num_no_secretmap', 'charl_no_secretmap', 'charu_no_secretmap']);
  const visibleMap = [...document.querySelectorAll('#nfilter_main map')]
    .find((map) => !hiddenMapIds.has(map.id));
  if (!visibleMap) {
    throw new Error('nfilter scrambled keypad map not found');
  }
  return [...visibleMap.querySelectorAll('area')]
    .filter((area) => area.id !== 'dummy' && !area.id.startsWith('nfilter_'))
    .map((area) => area.id);
}
"""

NFILTER_PROBE_DIGIT_PAIRS_JS = """
async () => {
  const hiddenMapIds = new Set(['num_no_secretmap', 'charl_no_secretmap', 'charu_no_secretmap']);
  const visibleMap = [...document.querySelectorAll('#nfilter_main map')]
    .find((map) => !hiddenMapIds.has(map.id));
  if (!visibleMap) {
    throw new Error('nfilter scrambled keypad map not found');
  }
  const imgEl = visibleMap.parentElement?.querySelector('img');
  if (!imgEl?.src) {
    throw new Error('nfilter scrambled keypad image not found');
  }
  const digitAreas = [...visibleMap.querySelectorAll('area')]
    .filter((area) => area.id !== 'dummy' && !area.id.startsWith('nfilter_'));
  if (digitAreas.length < 10) {
    throw new Error(`nfilter digit area count mismatch: ${digitAreas.length}`);
  }
  const loadImage = (src) => new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`nfilter image load failed: ${src}`));
    img.src = src;
  });
  const resolveReferenceImageUrl = () => {
    const mergedRef = document.getElementById('num_no_secretmerged');
    if (mergedRef?.src) {
      return mergedRef.src;
    }
    const refByQuery = document.querySelector('#nfilter_main img[src*="num_no_secret"]');
    if (refByQuery?.src) {
      return refByQuery.src;
    }
    return %(reference_fallback)r;
  };
  const resolveReferencePositions = () => {
    const positions = {};
    const hiddenMap = document.getElementById('num_no_secretmap');
    if (hiddenMap) {
      for (const area of hiddenMap.querySelectorAll('area')) {
        if (/^\\d$/.test(area.id)) {
          const [x, y] = area.coords.split(',').map(Number);
          positions[area.id] = `${x},${y}`;
        }
      }
    }
    if (Object.keys(positions).length >= 10) {
      return positions;
    }
    return %(ref_positions)r;
  };
  const merged = await loadImage(imgEl.src);
  const ref = await loadImage(resolveReferenceImageUrl());
  const refPositions = resolveReferencePositions();
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  const diff = (left, right) => {
    let score = 0;
    for (let i = 0; i < left.length; i += 4) {
      const dr = left[i] - right[i];
      const dg = left[i + 1] - right[i + 1];
      const db = left[i + 2] - right[i + 2];
      score += dr * dr + dg * dg + db * db;
    }
    return score;
  };
  const refData = {};
  for (const [digit, coords] of Object.entries(refPositions)) {
    const [x, y] = coords.split(',').map(Number);
    const [x1, y1, x2, y2] = digitAreas[0].coords.split(',').map(Number);
    const cellW = x2 - x1 + 1;
    const cellH = y2 - y1 + 1;
    canvas.width = cellW;
    canvas.height = cellH;
    ctx.drawImage(ref, x, y, cellW, cellH, 0, 0, cellW, cellH);
    refData[digit] = ctx.getImageData(0, 0, cellW, cellH).data;
  }
  const pairs = [];
  for (const area of digitAreas) {
    const [x1, y1, x2, y2] = area.coords.split(',').map(Number);
    const cellW = x2 - x1 + 1;
    const cellH = y2 - y1 + 1;
    canvas.width = cellW;
    canvas.height = cellH;
    ctx.drawImage(merged, x1, y1, cellW, cellH, 0, 0, cellW, cellH);
    const cell = ctx.getImageData(0, 0, cellW, cellH).data;
    for (const [digit, refCell] of Object.entries(refData)) {
      pairs.push({ areaId: area.id, digit, score: diff(cell, refCell) });
    }
  }
  return pairs;
}
"""

NFILTER_CLEAR_SSN2_JS = """
() => {
  for (let i = 0; i < 16; i++) {
    if (!document.getElementById('ssn2').value) {
      break;
    }
    nFilterClick('nfilter_backspace_num');
  }
  if (typeof nFilterSecElement !== 'undefined') {
    nFilterSecElement = '';
  }
  const sec = document.getElementById('ssn2_nfilter_sec');
  if (sec) {
    sec.value = '';
  }
}
"""

NFILTER_DECODE_VERIFY_JS = """
async (ssn1) => {
  const data = 'nonFilter=nonFilter&ssn1=' + ssn1
    + '&ssn2=' + document.getElementById('ssn2').value
    + '&nfilterPwd=' + nFilterEncrypted();
  return await new Promise((resolve) => {
    $.ajax({
      method: 'POST',
      url: '/cmcom/decode-ssn-register.json',
      data,
      dataType: 'json',
    }).done((payload) => {
      resolve({ ok: true, result: String(payload.result || '') });
    }).fail((xhr) => {
      resolve({ ok: false, status: xhr.status });
    });
  });
}
"""

NFILTER_ENABLE_SSN2_JS = """
() => {
  const ssn2 = document.getElementById('ssn2');
  if (!ssn2) {
    return;
  }
  ssn2.disabled = false;
  ssn2.removeAttribute('disabled');
}
"""

NFILTER_FOCUS_SSN2_JS = """
() => {
  const ssn2 = document.getElementById('ssn2');
  if (!ssn2) {
    return;
  }
  ssn2.disabled = false;
  ssn2.removeAttribute('disabled');
  ssn2.focus();
  ssn2.dispatchEvent(new MouseEvent('click', { bubbles: true }));
}
"""
DECODE_SSN_REGISTER_PATH = "decode-ssn-register.json"
HP_SMS_REQUEST_PATH = "hp-sms-request.json"

FAILURE_DIALOG_KEYWORDS: tuple[str, ...] = (
    "오류",
    "실패",
    "지연",
    "다시 시도",
    "넣어주세요",
    "입력해",
)


def _ssn2_display_length(page: Page) -> int:
    return len(page.locator(SSN2_INPUT).input_value())


def _ensure_ssn2_keypad_focusable(page: Page) -> None:
    page.evaluate(NFILTER_ENABLE_SSN2_JS)


def _open_nfilter_keypad(page: Page) -> None:
    keypad_main = page.locator(NFILTER_KEYPAD_MAIN)
    if keypad_main.is_visible():
        log("[wait] nfilter keypad already open")
        return
    ssn2 = page.locator(SSN2_INPUT)
    ssn2.scroll_into_view_if_needed()
    log("[step] Focus resident registration number back field (open nfilter keypad)")
    _ensure_ssn2_keypad_focusable(page)
    try:
        ssn2.click(timeout=browser.MAX_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        log("[warn] ssn2 click blocked (disabled); blur via name field and JS focus")
        page.locator(NAME_INPUT).click()
        page.wait_for_timeout(200)
        page.evaluate(NFILTER_FOCUS_SSN2_JS)
    try:
        keypad_main.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        log("[warn] nfilter keypad not visible after first focus; force click ssn2")
        _ensure_ssn2_keypad_focusable(page)
        ssn2.click(force=True)
        keypad_main.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    log("[wait] nfilter keypad ready")


def _visible_ssn_back_from_decode(result: str, ssn_front: str) -> str:
    front_digits = re.sub(r"\D", "", ssn_front)
    compact = result.replace("-", "")
    if not compact.startswith(front_digits):
        return ""
    visible: list[str] = []
    for char in compact[len(front_digits) :]:
        if char == "*":
            break
        if char.isdigit():
            visible.append(char)
    return "".join(visible)


def _hungarian_assign(cost: list[list[float]]) -> list[int]:
    """Return column index assigned to each row (minimum total cost)."""
    n = len(cost)
    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [float("inf")] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = float("inf")
            j1 = 0
            for j in range(1, n + 1):
                if used[j]:
                    continue
                cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    assignment = [0] * n
    for j in range(1, n + 1):
        if p[j] != 0:
            assignment[p[j] - 1] = j - 1
    return assignment


def _assign_digit_map_from_pairs(pairs: list[dict]) -> dict[str, str]:
    areas = sorted({str(pair["areaId"]) for pair in pairs})
    digits = list("0123456789")
    if len(areas) < 10:
        raise RuntimeError(f"nfilter digit area count mismatch: {len(areas)}")
    lookup = {(str(pair["areaId"]), str(pair["digit"])): float(pair["score"]) for pair in pairs}
    big = 1e15
    n = len(areas)
    cost = [[big] * n for _ in range(n)]
    for row, area in enumerate(areas):
        for col, digit in enumerate(digits):
            cost[row][col] = lookup.get((area, digit), big)
    assignment = _hungarian_assign(cost)
    return {digits[col]: areas[row] for row, col in enumerate(assignment)}


def _probe_nfilter_digit_pairs(page: Page) -> list[dict]:
    probe_js = NFILTER_PROBE_DIGIT_PAIRS_JS % {
        "reference_fallback": NFILTER_REFERENCE_IMAGE_FALLBACK,
        "ref_positions": NFILTER_REFERENCE_POSITIONS,
    }
    return page.evaluate(probe_js)


def _decode_prefix_matches(visible: str, ssn_back: str) -> bool:
    if not visible:
        return False
    return visible == ssn_back[: len(visible)]


def _visible_decode_after_full_entry(
    page: Page,
    *,
    ssn_front: str,
    ssn_back: str,
    digit_map: dict[str, str],
) -> str:
    _clear_nfilter_ssn2(page)
    _open_nfilter_keypad(page)
    _type_ssn_back_digits(page, ssn_back, digit_map=digit_map)
    _close_nfilter_keypad(page)
    payload = page.evaluate(NFILTER_DECODE_VERIFY_JS, ssn_front)
    if not payload.get("ok"):
        return ""
    return _visible_ssn_back_from_decode(str(payload.get("result") or ""), ssn_front)


def _refine_digit_map_with_full_decode(
    page: Page,
    *,
    ssn_front: str,
    ssn_back: str,
    digit_map: dict[str, str],
) -> dict[str, str]:
    refined = dict(digit_map)
    area_ids: list[str] = page.evaluate(NFILTER_COLLECT_AREA_IDS_JS)
    priority = [ssn_back[0]] + [d for d in dict.fromkeys(ssn_back) if d != ssn_back[0]]
    visible = _visible_decode_after_full_entry(
        page, ssn_front=ssn_front, ssn_back=ssn_back, digit_map=refined
    )
    if _decode_prefix_matches(visible, ssn_back):
        return refined

    log(
        "[step] Refine nfilter digit map via full-entry decode "
        f"(visible={visible!r}, expected prefix={ssn_back[: len(visible) or 1]!r})"
    )
    for digit in priority:
        current = refined.get(digit)
        for area_id in area_ids:
            if area_id == current:
                continue
            trial = dict(refined)
            trial[digit] = area_id
            visible = _visible_decode_after_full_entry(
                page, ssn_front=ssn_front, ssn_back=ssn_back, digit_map=trial
            )
            if _decode_prefix_matches(visible, ssn_back):
                log(f"[step] nfilter decode refine: digit {digit} -> {area_id[:4]}")
                refined = trial
                if visible == ssn_back:
                    return refined
                break
        visible = _visible_decode_after_full_entry(
            page, ssn_front=ssn_front, ssn_back=ssn_back, digit_map=refined
        )
        if _decode_prefix_matches(visible, ssn_back):
            return refined
    return refined


def _probe_nfilter_digit_map(page: Page, *, ssn_front: str, ssn_back: str) -> dict[str, str]:
    log("[step] Probe scrambled nfilter keypad (pixel match + Hungarian)")
    pairs = _probe_nfilter_digit_pairs(page)
    digit_map = _assign_digit_map_from_pairs(pairs)
    refined = _refine_digit_map_with_full_decode(
        page, ssn_front=ssn_front, ssn_back=ssn_back, digit_map=digit_map
    )
    _clear_nfilter_ssn2(page)
    return refined


def _clear_nfilter_ssn2(page: Page) -> None:
    keypad = page.locator(NFILTER_KEYPAD_MAIN)
    if not keypad.is_visible():
        _open_nfilter_keypad(page)
    page.evaluate(NFILTER_CLEAR_SSN2_JS)
    page.wait_for_timeout(200)


def _verify_decoded_ssn_back(page: Page, *, ssn_front: str, ssn_back: str) -> None:
    payload = page.evaluate(NFILTER_DECODE_VERIFY_JS, ssn_front)
    if not payload.get("ok"):
        status = payload.get("status", "unknown")
        raise RuntimeError(f"주민등록번호 서버 검증 요청 실패: HTTP {status}")
    result = str(payload.get("result") or "")
    visible = _visible_ssn_back_from_decode(result, ssn_front)
    if not visible:
        raise RuntimeError(
            f"주민등록번호 서버 검증 응답에 뒷자리 확인값이 없습니다: result={result!r}"
        )
    expected = ssn_back[: len(visible)]
    if visible != expected:
        raise RuntimeError(
            "주민등록번호 뒷자리 서버 검증 불일치: "
            f"기대 {expected!r}, decode {visible!r} (result={result!r})"
        )
    if len(visible) < len(ssn_back):
        log(
            f"[wait] decode-ssn-register verified {len(visible)}/{len(ssn_back)} "
            f"visible digit(s) of ssn back (masked response)"
        )
    else:
        log(f"[wait] decode-ssn-register verified all {len(ssn_back)} digit(s) of ssn back")


def _click_nfilter_digit(page: Page, digit: str, *, digit_map: dict[str, str]) -> None:
    if not digit.isdigit():
        raise ValueError(f"지원하지 않는 nfilter 숫자입니다: {digit!r}")
    area_id = digit_map.get(digit)
    if not area_id:
        raise RuntimeError(f"nfilter 키패드에서 숫자 {digit!r} 위치를 찾지 못했습니다.")
    page.evaluate("(areaId) => nFilterClick(areaId)", area_id)
    page.wait_for_timeout(NFILTER_KEY_CLICK_PAUSE_MS)


def _type_ssn_back_digits(page: Page, ssn_back: str, *, digit_map: dict[str, str]) -> None:
    for digit in ssn_back:
        before = _ssn2_display_length(page)
        for attempt in range(1, NFILTER_KEY_CLICK_RETRY_MAX + 1):
            _click_nfilter_digit(page, digit, digit_map=digit_map)
            after = _ssn2_display_length(page)
            if after > before:
                break
            log(f"[warn] nfilter digit {digit!r} retry {attempt}/{NFILTER_KEY_CLICK_RETRY_MAX}")
        else:
            raise RuntimeError(f"nfilter 숫자 {digit!r} 입력에 실패했습니다.")


def _fill_ssn_back_via_nfilter(page: Page, *, ssn_front: str, ssn_back: str) -> None:
    log("[step] Fill resident registration number back via nfilter")
    _open_nfilter_keypad(page)
    last_error: RuntimeError | None = None
    for attempt in range(1, NFILTER_FILL_ATTEMPTS_MAX + 1):
        if attempt > 1:
            log(f"[warn] nfilter ssn back refill attempt {attempt}/{NFILTER_FILL_ATTEMPTS_MAX}")
            _clear_nfilter_ssn2(page)
        digit_map = _probe_nfilter_digit_map(page, ssn_front=ssn_front, ssn_back=ssn_back)
        sample = " ".join(f"{digit}->{digit_map[digit][:4]}" for digit in ssn_back)
        log(f"[step] nfilter digit map for input: {sample}")
        _type_ssn_back_digits(page, ssn_back, digit_map=digit_map)

        entered_len = _ssn2_display_length(page)
        if entered_len != len(ssn_back):
            last_error = RuntimeError(
                f"주민등록번호 뒷자리 입력 실패: 기대 {len(ssn_back)}자리, 실제 {entered_len}자리"
            )
            continue

        _close_nfilter_keypad(page)
        try:
            _verify_nfilter_sec_registered(page, expected_digits=len(ssn_back))
            _verify_decoded_ssn_back(page, ssn_front=ssn_front, ssn_back=ssn_back)
            return
        except RuntimeError as exc:
            last_error = exc
            _open_nfilter_keypad(page)

    if last_error is not None:
        raise last_error
    raise RuntimeError("주민등록번호 뒷자리 nfilter 입력에 실패했습니다.")


def _close_nfilter_keypad(page: Page) -> None:
    keypad = page.locator(NFILTER_KEYPAD_MAIN)
    if not keypad.is_visible():
        return
    log("[step] Confirm nfilter keypad (enter)")
    page.evaluate(
        """() => {
            const enter = document.querySelector('#nfilter_num_content #nfilter_enter_num');
            if (enter) enter.click();
        }"""
    )
    page.wait_for_timeout(200)
    if keypad.is_visible():
        log("[warn] nfilter keypad still open; blur via name field")
        page.locator(NAME_INPUT).click()
    try:
        keypad.wait_for(state="hidden", timeout=browser.MAX_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        if keypad.is_visible():
            raise RuntimeError("nfilter 키패드를 닫지 못했습니다.")
    _ensure_ssn2_keypad_focusable(page)
    log("[wait] nfilter keypad closed")


def _verify_nfilter_sec_registered(page: Page, *, expected_digits: int) -> None:
    sec_state = page.evaluate(
        """(expectedDigits) => {
            const secLen = (document.getElementById('ssn2_nfilter_sec')?.value || '').length;
            const tokenLen = typeof nFilterRandomIdLength === 'number' ? nFilterRandomIdLength : 10;
            const secElement = typeof nFilterSecElement === 'string' ? nFilterSecElement : '';
            return { secLen, tokenLen, secElementLen: secElement.length, expected: expectedDigits * tokenLen };
        }""",
        expected_digits,
    )
    if sec_state["secLen"] <= 0:
        raise RuntimeError("주민등록번호 뒷자리 nfilter 암호화 값이 비어 있습니다.")
    if sec_state["secElementLen"] != sec_state["expected"]:
        raise RuntimeError(
            "주민등록번호 뒷자리 nfilter 내부 토큰 길이가 올바르지 않습니다. "
            f"기대 {sec_state['expected']}자, 실제 {sec_state['secElementLen']}자"
        )


def _new_dialogs(dialog_messages: list[str], start_index: int) -> list[str]:
    return dialog_messages[start_index:]


def _ensure_no_failure_dialogs(
    dialog_messages: list[str], start_index: int, step_name: str
) -> None:
    failures = [
        message
        for message in _new_dialogs(dialog_messages, start_index)
        if any(keyword in message for keyword in FAILURE_DIALOG_KEYWORDS)
    ]
    if failures:
        joined = " | ".join(failures)
        raise RuntimeError(f"{step_name} 실패: {joined}")


def _normalize_carrier(raw: str) -> str:
    key = (raw or "").strip().lower()
    if key not in CARRIER_VALUES:
        allowed = ", ".join(sorted({"skt", "kt", "lgu+", "skt_mvno", "kt_mvno", "lgu_mvno"}))
        raise ValueError(f"지원하지 않는 통신사입니다: {raw!r}. 허용 값: {allowed}")
    return CARRIER_VALUES[key]


def _normalize_ssn_front(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if not SSN1_PATTERN.fullmatch(digits):
        raise ValueError("주민등록번호 앞자리는 6자리 숫자여야 합니다.")
    return digits


def _normalize_ssn_back(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if not SSN2_PATTERN.fullmatch(digits):
        raise ValueError("주민등록번호 뒷자리는 7자리 숫자여야 합니다.")
    return digits


def _parse_phone_number(raw_phone: str) -> tuple[str, str, str]:
    digits = re.sub(r"\D", "", raw_phone or "")
    if len(digits) != 11:
        raise ValueError("휴대폰 번호는 11자리 숫자(예: 01012345678)여야 합니다.")
    prefix = digits[:3]
    if prefix not in {"010", "011"}:
        raise ValueError("휴대폰 번호 앞자리는 010 또는 011이어야 합니다.")
    if len(digits[3:]) == 8:
        middle = digits[3:7]
        last = digits[7:]
    else:
        middle = digits[3:6]
        last = digits[6:]
    return prefix, middle, last


def _resolve_otp_code(otp_code: str) -> str:
    candidate = (otp_code or "").strip()
    if not OTP_PATTERN.fullmatch(candidate):
        raise RuntimeError("인증번호는 4~8자리 숫자여야 합니다.")
    return candidate


def _ensure_sales_page(page: Page, base_url: str) -> None:
    if SALES_PAGE_PATH in page.url:
        log(f"[wait] Reuse contract page: {page.url}")
        return
    target = f"{browser.normalize_base_url(base_url, base_url)}{SALES_PAGE_PATH}"
    log(f"[step] Open sales contract page: {target}")
    link = page.locator(CONTRACT_WRITE_LINK)
    if link.count() > 0 and link.first.is_visible():
        link.first.click()
    else:
        page.goto(target, wait_until="domcontentloaded", timeout=browser.MAX_TIMEOUT_MS)
    page.wait_for_url(lambda url: SALES_PAGE_PATH in url, timeout=browser.MAX_TIMEOUT_MS)
    log(f"[wait] Contract page ready: {page.url}")


def _verify_privacy_consent_heading(page: Page) -> None:
    log(f"[step] Verify heading: {PRIVACY_CONSENT_HEADING!r}")
    page.get_by_role("heading", name=PRIVACY_CONSENT_HEADING, exact=True).wait_for(
        state="visible",
        timeout=browser.MAX_TIMEOUT_MS,
    )


def _agree_all_terms(page: Page) -> None:
    checkbox = page.locator("#agreeAll")
    if checkbox.is_checked():
        log("[step] Terms already fully agreed")
        return
    log("[step] Agree to all privacy terms (label click; span overlays checkbox)")
    page.locator(AGREE_ALL_LABEL).click()
    if not checkbox.is_checked():
        raise RuntimeError("개인정보처리동의 전체동의 선택에 실패했습니다.")


def _fill_identity_fields(page: Page, *, name: str, ssn_front: str, ssn_back: str) -> None:
    log("[step] Fill name and resident registration number")
    page.locator(NAME_INPUT).fill(name)
    page.locator(SSN1_INPUT).fill(ssn_front)
    _fill_ssn_back_via_nfilter(page, ssn_front=ssn_front, ssn_back=ssn_back)


def _select_phone_auth(page: Page) -> None:
    log("[step] Select phone authentication")
    phone_radio = page.locator("#name_cert02")
    if phone_radio.is_checked():
        log("[step] Phone auth already selected")
    else:
        page.locator(PHONE_RADIO_LABEL).click()
    page.get_by_role("heading", name=PHONE_AUTH_HEADING, exact=True).wait_for(
        state="visible",
        timeout=browser.MAX_TIMEOUT_MS,
    )


def _fill_phone_fields(
    page: Page,
    *,
    carrier_code: str,
    phone_prefix: str,
    phone_middle: str,
    phone_last: str,
) -> None:
    log("[step] Fill carrier and phone number")
    page.locator(CARRIER_SELECT).select_option(carrier_code)
    page.locator(PHONE_PREFIX_SELECT).select_option(phone_prefix)
    page.locator(PHONE_MIDDLE_INPUT).fill(phone_middle)
    page.locator(PHONE_LAST_INPUT).fill(phone_last)


def _request_sms_code(page: Page, dialog_messages: list[str]) -> None:
    log("[step] Request SMS verification code")
    dialog_index = len(dialog_messages)
    timeout_ms = browser.MAX_TIMEOUT_MS
    log(f"[wait] Start response wait: {DECODE_SSN_REGISTER_PATH} ({timeout_ms} ms)")
    with page.expect_response(
        lambda response: DECODE_SSN_REGISTER_PATH in response.url,
        timeout=timeout_ms,
    ) as decode_info:
        with page.expect_response(
            lambda response: HP_SMS_REQUEST_PATH in response.url,
            timeout=timeout_ms,
        ) as sms_info:
            page.locator(SMS_REQUEST_LINK).click()

    decode_response = decode_info.value
    log(
        f"[wait] End response wait: {DECODE_SSN_REGISTER_PATH} -> "
        f"{decode_response.status} {decode_response.url}"
    )
    if not decode_response.ok:
        detail = (
            _new_dialogs(dialog_messages, dialog_index)[-1]
            if len(dialog_messages) > dialog_index
            else f"HTTP {decode_response.status}"
        )
        raise RuntimeError(f"주민등록번호 서버 등록 실패({DECODE_SSN_REGISTER_PATH}): {detail}")

    sms_response = sms_info.value
    log(
        f"[wait] End response wait: {HP_SMS_REQUEST_PATH} -> "
        f"{sms_response.status} {sms_response.url}"
    )
    if not sms_response.ok:
        detail = (
            _new_dialogs(dialog_messages, dialog_index)[-1]
            if len(dialog_messages) > dialog_index
            else f"HTTP {sms_response.status}"
        )
        raise RuntimeError(f"SMS 인증번호 요청 실패({HP_SMS_REQUEST_PATH}): {detail}")

    _ensure_no_failure_dialogs(dialog_messages, dialog_index, "SMS 인증번호 요청")
    page.wait_for_timeout(1000)

    otp_input = page.locator(OTP_INPUT)
    otp_input.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    if not otp_input.is_enabled():
        raise RuntimeError("인증번호 입력란이 비활성 상태입니다. SMS 발급을 다시 시도해 주세요.")
    log("[wait] SMS auth input ready")


def _wait_for_contract_write_page(page: Page) -> None:
    log("[wait] 계약서 작성 화면 대기: sales02.do 또는 sales02_tm1.do")
    page.wait_for_url(
        is_contract_write_page,
        timeout=browser.MAX_TIMEOUT_MS,
    )
    log(f"[wait] Contract write page ready: {page.url}")


def request_otp(
    page: Page,
    *,
    base_url: str,
    name: str,
    ssn_front: str,
    ssn_back: str,
    carrier: str,
    phone_number: str,
    dialog_messages: list[str],
) -> str:
    """영업가족 계약서 본인확인 화면에서 휴대폰 인증번호를 요청한다."""
    resolved_name = (name or "").strip()
    if not resolved_name:
        raise RuntimeError("이름을 입력해 주세요.")

    resolved_ssn_front = _normalize_ssn_front(ssn_front)
    resolved_ssn_back = _normalize_ssn_back(ssn_back)
    carrier_code = _normalize_carrier(carrier)
    phone_prefix, phone_middle, phone_last = _parse_phone_number(phone_number)

    browser.maybe_close_popup(page)
    _ensure_sales_page(page, base_url)
    _verify_privacy_consent_heading(page)
    _agree_all_terms(page)
    _fill_identity_fields(
        page, name=resolved_name, ssn_front=resolved_ssn_front, ssn_back=resolved_ssn_back
    )
    _select_phone_auth(page)
    _fill_phone_fields(
        page,
        carrier_code=carrier_code,
        phone_prefix=phone_prefix,
        phone_middle=phone_middle,
        phone_last=phone_last,
    )
    _request_sms_code(page, dialog_messages)
    return "휴대폰 인증문자 발송 성공"


def submit_otp_and_complete(
    page: Page,
    *,
    otp_code: str,
    dialog_messages: list[str],
) -> str:
    """인증번호 확인 후 계약서 체결하기까지 진행한다."""
    if SALES_PAGE_PATH not in page.url:
        raise RuntimeError(
            "본인인증 화면(/fp/loan/sales01.do)이 아닙니다. 이전 모듈부터 다시 실행해 주세요."
        )

    resolved = _resolve_otp_code(otp_code)
    log("[step] Submit SMS verification code")
    otp_input = page.locator(OTP_INPUT)
    otp_input.wait_for(state="visible", timeout=browser.MAX_TIMEOUT_MS)
    otp_input.fill(resolved)
    page.locator(OTP_CONFIRM_BUTTON).click()
    page.wait_for_timeout(1000)

    log("[step] Submit contract signing")
    dialog_index = len(dialog_messages)
    page.locator(SUBMIT_CONTRACT_BUTTON).click()

    try:
        _wait_for_contract_write_page(page)
    except PlaywrightTimeoutError:
        _ensure_no_failure_dialogs(dialog_messages, dialog_index, "계약서 체결")
        if dialog_messages:
            raise RuntimeError(f"계약서 체결 실패: {dialog_messages[-1]}")
        raise RuntimeError(
            "계약서 체결 후 계약서 작성 화면(sales02.do 또는 sales02_tm1.do)으로 이동하지 못했습니다."
        )

    _ensure_no_failure_dialogs(dialog_messages, dialog_index, "계약서 체결")
    return "FP 본인인증 성공"
