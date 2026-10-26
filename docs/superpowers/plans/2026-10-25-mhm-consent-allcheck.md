# MHM 보험금청구 동의 안내 모달(allCheck) 대응 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `mhm.compensation.charge` 가 변경된 '동의 안내' 모달(`#allCheck` "전체 동의")을 체크한 뒤에만 '다음'으로 진행하도록 고쳐, 1052 진입 시 시스템 오류 팝업으로 실패하는 문제를 없앤다.

**Architecture:** `_handle_consent_flow` 맨 앞에 "새 구조(`input#allCheck` 존재)" 분기를 추가한다. 이 분기는 Playwright 실클릭으로 체크를 보장·검증하고 '다음'만 누른 뒤 반환한다. 기존(레거시) 경로는 건드리지 않는다.

**Tech Stack:** Python 3.13, Playwright sync API, pytest (실 Chromium + `page.set_content` 픽스처)

**Spec:** 별도 설계 문서 없음 — 아래 "근거" 절이 스펙이다 (2026-10-25 라이브 단계별 재현 결과).

## 근거 (라이브 재현, 2026-10-25)

- 실패 run: `run_20261025_111448_5367cc` / `mhm.compensation.charge` — `[error] 청구 상세 유형: 기타 진단 요소를 찾지 못했습니다.`
- 1050 '청구사유 입력완료' 후 뜨는 '동의 안내' 모달의 현재 DOM:
  - `input#allCheck` + `label[for="allCheck"]` 텍스트 `전체 동의`
  - `input[id="[필수] 보험금 청구 동의"]`, `input[id="[선택] 상품소개를 위한 상세 동의서"]`(숨김)
  - 버튼 `다음`. 본문에 `보험금청구를 위한 동의입니다.`
- 기존 코드(`app/automation/page_objects/mhm/compensation_charge.py`)가 기대하는 `label[for="[필수] 전체동의"]` 는 없고, 패턴 `\[?\s*필수\s*\]?\s*전체\s*동의` 는 '필수' 문자가 필수라 `전체 동의` 에 매칭되지 않는다 → 아무것도 체크하지 않은 채 '다음' 클릭.
- 미체크 '다음' → `POST /smt/cla/agr/save-agre-spc` **400** `{"code":"99102","message":"유효하지 않은 파라미터입니다."}` → 1052 에 `.dialog.modal.error_modal.show` ("시스템 오류로 서비스가 중단되었습니다") → 진단비 클릭이 가로막혀 위 RuntimeError.
- `label[for=allCheck]` Playwright 클릭 → `#allCheck`·`[필수] 보험금 청구 동의` 둘 다 checked → '다음' → `save-agre-spc` **200**, 1052 정상, 기존 `_complete_detail_step` 그대로 1070 도달. **1052 이후 셀렉터는 변경 없음.**

## Global Constraints

- automation 코드 위치: `app/automation/`
- UI·로그·예외 문자열은 한국어
- 작업 브랜치: `main` 에서 `fix/mhm-consent-allcheck` 생성 (현재 `feat/presets-promotion` 은 무관)
- PR 전: `python3 scripts/ci/run_all_gates.py --profile full`
- 기존 JS 헬퍼 `_click_label_in_modal` / `_click_button_in_modal` 은 `dispatchEvent(click)` + `element.click()` **이중 클릭**이다. 체크박스 라벨에 쓰면 토글이 상쇄될 수 있으므로 **새 분기에서 체크박스 클릭에 사용 금지** (버튼 '다음'에는 기존 헬퍼 사용 가능).
- 새 모달 본문 `보험금청구를 위한` 은 `CONSENT_SUMMARY_PATTERN` 에도 매칭된다 → 새 분기는 요약 동의서 로직에 도달하기 **전에** 반환해야 한다 (같은 모달 재클릭으로 체크 해제 방지).

## Review Focus

1. `_handle_consent_flow` 는 루프에서 반복 호출된다 — 이미 체크된 상태에서 재호출 시 체크가 해제되면 안 된다 (멱등). → Task 1 `test_new_consent_modal_is_idempotent`
2. 라벨 클릭 후에도 체크가 안 되는 경우(사이트가 또 바뀜) — '다음'을 누르지 말고 명확한 한국어 RuntimeError. → Task 1 `test_new_consent_modal_raises_when_not_checked`
3. 동의 모달이 없는 화면에서는 기존처럼 `False` 반환 (루프의 다른 분기 진행). → Task 1 `test_no_consent_modal_returns_false`
4. 체크된 뒤 '다음'이 실제로 눌린다. → Task 1 `test_new_consent_modal_checks_all_then_clicks_next`
5. 1070 이후(서류 업로드·제출)는 실청구라 라이브 미검증 — 이 계획 범위 밖, Task 2 수동 검증에서 사용자 판단.

---

### Task 1: 새 동의 안내 모달 분기 + 회귀 테스트

**Files:**
- Modify: `app/automation/page_objects/mhm/compensation_charge.py` (상수 78행 부근, `_handle_consent_flow` 1135행 부근, 새 헬퍼 1개)
- Test (Create): `tests/automation/test_mhm_consent_flow.py`

**Interfaces:**
- Produces:
  - 상수 `CONSENT_ALL_CHECK_ID = "allCheck"` (기존 `CONSENT_FULL_AGREE_FOR` 는 레거시 경로용으로 그대로 둔다)
  - `_ensure_consent_all_checked(modal) -> None` — `modal.locator('input[id="allCheck"]')` 가 체크 안 돼 있으면 `modal.locator('label[for="allCheck"]').first.click()` (Playwright 실클릭 1회) 후 재확인. 여전히 미체크면 `RuntimeError("동의 안내: 전체 동의 체크를 확인하지 못했습니다.")`. 체크 시 `log("[click] 동의 안내: 전체 동의")`.
  - `_handle_consent_flow(page, timeout_ms) -> bool` 시그니처 불변. 기존 history-popup 체크 직후, `consent_modal` 을 찾은 다음 `consent_modal.locator('input[id="allCheck"]').count() > 0` 이면: `_ensure_consent_all_checked(consent_modal)` → `return _click_button_in_modal(consent_modal, names=["다음", re.compile(r"^다음$")], description="동의 안내: 다음")`. 그 외는 기존 코드 그대로.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/automation/test_mhm_consent_flow.py`

`tests/test_dashboard_viewport.py:245-264` 의 `browser`/`page` 픽스처 패턴(Chromium 미설치 시 `pytest.skip`)을 그대로 쓴다. `pytest.importorskip("playwright")` 포함.

픽스처 HTML (라이브 DOM 축약):

```python
CONSENT_HTML = """
<div class="dialog full show">
  <h2>동의 안내</h2><p>보험금청구를 위한 동의입니다.</p>
  <input type="checkbox" id="allCheck"
         onchange="document.querySelectorAll('.sub').forEach(c => c.checked = this.checked)">
  <label for="allCheck">전체 동의</label>
  <input type="checkbox" class="sub" id="[필수] 보험금 청구 동의">
  <label for="[필수] 보험금 청구 동의">[필수] 보험금 청구 동의</label>
  <button type="button" onclick="document.body.dataset.next = (+(document.body.dataset.next||0)+1)">다음</button>
</div>
"""
```

테스트 4개 (`from app.automation.page_objects.mhm import compensation_charge as cc`):

```python
def test_new_consent_modal_checks_all_then_clicks_next(page):
    page.set_content(CONSENT_HTML)
    assert cc._handle_consent_flow(page, 5000) is True
    assert page.locator("#allCheck").is_checked()
    assert page.locator('input[id="[필수] 보험금 청구 동의"]').is_checked()
    assert int(page.evaluate("document.body.dataset.next || 0")) >= 1


def test_new_consent_modal_is_idempotent(page):
    page.set_content(CONSENT_HTML)
    page.locator("#allCheck").check()
    cc._handle_consent_flow(page, 5000)
    assert page.locator("#allCheck").is_checked()


def test_new_consent_modal_raises_when_not_checked(page):
    page.set_content(CONSENT_HTML.replace('id="allCheck"', 'id="allCheck" onclick="return false"'))
    with pytest.raises(RuntimeError, match="전체 동의 체크를 확인하지 못했습니다"):
        cc._handle_consent_flow(page, 5000)
    assert page.evaluate("document.body.dataset.next || ''") == ""


def test_no_consent_modal_returns_false(page):
    page.set_content("<main>청구사유</main>")
    assert cc._handle_consent_flow(page, 5000) is False
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/automation/test_mhm_consent_flow.py -v`
Expected: `test_new_consent_modal_checks_all_then_clicks_next`, `test_new_consent_modal_raises_when_not_checked` FAIL (현재 코드는 체크 없이 '다음'만 누름). `test_no_consent_modal_returns_false` 는 PASS 여도 무방.

- [ ] **Step 3: 구현** — 위 Interfaces 의 상수·`_ensure_consent_all_checked`·`_handle_consent_flow` 분기 추가. 레거시 경로(라벨 `[필수] 전체동의`, 요약 동의서)는 수정하지 않는다.

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/automation/test_mhm_consent_flow.py tests/contract/test_rep_homepage_page_objects.py -v`
Expected: 전부 PASS

- [ ] **Step 5: Commit**

```bash
git add app/automation/page_objects/mhm/compensation_charge.py tests/automation/test_mhm_consent_flow.py docs/superpowers/plans/2026-10-25-mhm-consent-allcheck.md
git commit -m "fix(mhm): 보험금청구 동의 안내 모달 전체 동의(allCheck) 체크 후 진행"
```

### Task 2: 게이트 + 라이브 확인

**Files:** 없음 (검증만)

- [ ] **Step 1: 전체 게이트**

Run: `python3 scripts/ci/run_all_gates.py --profile full`
Expected: 모든 게이트 PASS

- [ ] **Step 2: 라이브 확인 (사용자 협조 — 로그인/OTP 필요)**

앱에서 `mhm.compensation.charge` 1회 실행. 실행 로그에서 확인:
- `[click] 동의 안내: 전체 동의` 와 `[click] 동의 안내: 다음` 이 순서대로 존재
- `[error] 청구 상세 유형: 기타 진단 요소를 찾지 못했습니다.` 가 **없음**
- URL 이 `/cmp/dii/IbnfDmRcp1070` 이상 진행

1070 이후(서류 업로드·제출)에서 새 실패가 나면 별도 이슈로 분리한다.

## 범위 밖 (후속 과제 후보)

- `app/runner/page_diagnostic.py` 가 `.dialog.modal.error_modal.show` 를 `no visible overlay/modal HTML detected` 로 놓침.
- 자가치유(SPEC-HEAL-001)는 page object 자체 `RuntimeError` 메시지에서 셀렉터를 파싱하지 못해 건너뜀.
- hom(PC) `compensation_charge.py` 는 별도 셀렉터(`#formChk2`)를 써서 이번 변경과 무관 — 수정 없음.
- `docs/scenarios/mhm.md` 는 동의 단계를 서술하지 않으며 manifest·flow 변경도 없어 갱신 불필요.
