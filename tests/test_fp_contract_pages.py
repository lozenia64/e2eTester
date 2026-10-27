from urllib.parse import urlparse

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from app.automation.page_objects.fp import document_writing, identity_verification


@pytest.fixture(scope="module")
def fp_browser():
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            if "Executable doesn't exist" not in str(exc):
                raise
            pytest.skip("Chromium이 설치되지 않아 로컬 DOM 브라우저 검증을 생략합니다.")
        yield browser
        browser.close()


@pytest.fixture
def contract_page(fp_browser):
    page = fp_browser.new_page()
    page.route("https://fp.example/**", lambda route: route.fulfill(body="<html></html>"))
    yield page
    page.close()


@pytest.mark.parametrize("path", ["sales02.do", "sales02_tm1.do"])
def test_identity_accepts_both_contract_routes(contract_page, path, monkeypatch):
    monkeypatch.setattr(identity_verification.browser, "MAX_TIMEOUT_MS", 200)
    contract_page.goto(f"https://fp.example/fp/loan/{path}")
    identity_verification._wait_for_contract_write_page(contract_page)


def test_document_preserves_tm_route(contract_page):
    contract_page.goto("https://fp.example/fp/loan/sales02_tm1.do")
    document_writing._ensure_contract_write_page(contract_page, "https://fp.example")
    assert urlparse(contract_page.url).path == "/fp/loan/sales02_tm1.do"


def _manager_form(page, valid=True):
    page.set_content("""
      <table><tr><td><input id="managerStfno" maxlength="7"></td>
      <td><button onclick="setTimeout(() => {window.checkManagerNameFlag = window.validManager}, 20)">확인</button></td></tr></table>
      <script>window.checkManagerNameFlag = false;</script>
    """)
    page.evaluate("valid => window.validManager = valid", valid)


def test_tm_confirms_manager(contract_page):
    contract_page.goto("https://fp.example/fp/loan/sales02_tm1.do")
    _manager_form(contract_page)
    document_writing._ensure_manager_verified(contract_page, "1234567", [])
    assert contract_page.locator("#managerStfno").input_value() == "1234567"
    assert contract_page.evaluate("checkManagerNameFlag") is True


@pytest.mark.parametrize("manager_id", ["", "1234567"])
def test_document_checks_manager_before_opening_oz(contract_page, manager_id, monkeypatch):
    contract_page.goto("https://fp.example/fp/loan/sales02_tm1.do")
    _manager_form(contract_page)
    opened = []
    monkeypatch.setattr(document_writing.browser, "maybe_close_popup", lambda page: None)
    monkeypatch.setattr(
        document_writing,
        "_open_and_submit_information_security_pledge",
        lambda page: opened.append(page.evaluate("checkManagerNameFlag")),
    )
    monkeypatch.setattr(document_writing, "_wait_for_form_complete", lambda page: None)
    monkeypatch.setattr(document_writing, "_open_phone_auth_section", lambda page, dialogs: None)
    monkeypatch.setattr(document_writing, "_request_sms_code", lambda page, dialogs: None)
    if not manager_id:
        with pytest.raises(RuntimeError, match="관리자사번"):
            document_writing.request_otp(
                contract_page, base_url="https://fp.example", dialog_messages=[]
            )
        assert opened == []
    else:
        document_writing.request_otp(
            contract_page,
            base_url="https://fp.example",
            dialog_messages=[],
            manager_employee_id=manager_id,
        )
        assert opened == [True]


def test_document_flow_forwards_manager_and_clears_first_otp(monkeypatch):
    from types import SimpleNamespace

    from app.automation.flows.fp.flows import FpDocumentWritingFlow
    from app.runner.step_outcome import StepNeedsInput

    calls = []
    runtime = SimpleNamespace(
        page=object(),
        base_url="https://fp.example",
        manager_employee_id="1234567",
        dialog_messages=[],
        document_sms_requested=False,
        otp_code="111111",
    )

    def request(page, **kwargs):
        assert runtime.otp_code == ""
        calls.append(kwargs["manager_employee_id"])
        return "휴대폰 인증문자 발송 성공"

    monkeypatch.setattr(document_writing, "request_otp", request)
    result = FpDocumentWritingFlow().run(SimpleNamespace(runtime=runtime))
    assert isinstance(result, StepNeedsInput)
    assert calls == ["1234567"]
    assert runtime.document_sms_requested is True


def test_executor_restores_manager_from_run_input(monkeypatch, tmp_path):
    from app.platform.artifact_manager import ArtifactManager
    from app.systems.access_common.executor import AccessRuntime, AccessWorkflowExecutor
    from app.systems.fp.executor import create_executor

    base = AccessRuntime(
        base_url="https://fp.example",
        mobile=False,
        playwright_manager=object(),
        context=object(),
        page=object(),
        dialog_messages=[],
    )
    monkeypatch.setattr(AccessWorkflowExecutor, "build_runtime", lambda *args: base)
    runtime = create_executor(ArtifactManager(tmp_path)).build_runtime(
        {"manager_employee_id": " 1234567 "}, "run-test", "fp.document.writing"
    )
    assert runtime.manager_employee_id == "1234567"


@pytest.mark.parametrize("path", ["sales02.do", "sales02_tm1.do"])
def test_document_otp_submission_accepts_both_routes(contract_page, path, monkeypatch):
    monkeypatch.setattr(document_writing, "OZ_POPUP_TIMEOUT_MS", 200)
    complete_path = "sales03_tm1.do" if path == "sales02_tm1.do" else "sales03.do"
    contract_page.goto(f"https://fp.example/fp/loan/{path}")
    contract_page.set_content(f"""
      <input id="smsCertNo">
      <button id="btnSave" onclick="location.href='/fp/loan/{complete_path}'">제출하기</button>
    """)
    assert (
        document_writing.submit_otp_and_complete(
            contract_page, otp_code="123456", dialog_messages=[]
        )
        == "FP 서류작성 성공"
    )
    assert urlparse(contract_page.url).path == f"/fp/loan/{complete_path}"


@pytest.mark.parametrize("new_alert", ["", "인증이 완료되었습니다. [확인] 버튼을 클릭하십시오."])
def test_document_timeout_reports_navigation_not_normal_alert(
    contract_page, monkeypatch, new_alert
):
    monkeypatch.setattr(document_writing, "OZ_POPUP_TIMEOUT_MS", 100)
    contract_page.goto("https://fp.example/fp/loan/sales02_tm1.do")
    contract_page.set_content('<input id="smsCertNo"><button id="btnSave">제출하기</button>')
    dialogs = ["인증이 완료되었습니다. [확인] 버튼을 클릭하십시오."]
    if new_alert:
        contract_page.locator("#btnSave").evaluate(
            "(button, message) => button.onclick = () => alert(message)", new_alert
        )
        contract_page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.accept()))
    with pytest.raises(RuntimeError) as error:
        document_writing.submit_otp_and_complete(
            contract_page, otp_code="123456", dialog_messages=dialogs
        )
    message = str(error.value)
    assert "완료 화면" in message
    assert "sales03.do" in message and "sales03_tm1.do" in message
    assert "현재 URL: https://fp.example/fp/loan/sales02_tm1.do" in message
    assert "인증이 완료되었습니다" not in message


def test_document_timeout_preserves_current_failure_alert(contract_page, monkeypatch):
    monkeypatch.setattr(document_writing, "OZ_POPUP_TIMEOUT_MS", 100)
    contract_page.goto("https://fp.example/fp/loan/sales02_tm1.do")
    contract_page.set_content("""
      <input id="smsCertNo">
      <button id="btnSave" onclick="alert('인증 오류: 인증번호를 확인해 주세요.')">제출하기</button>
    """)
    dialogs = ["이전 단계 오류"]
    contract_page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.accept()))
    with pytest.raises(RuntimeError, match="인증 오류: 인증번호를 확인해 주세요"):
        document_writing.submit_otp_and_complete(
            contract_page, otp_code="123456", dialog_messages=dialogs
        )


@pytest.mark.parametrize("value", ["", "123", "abcdefg"])
def test_tm_requires_seven_digit_manager(contract_page, value):
    contract_page.goto("https://fp.example/fp/loan/sales02_tm1.do")
    _manager_form(contract_page)
    with pytest.raises(RuntimeError, match="관리자사번.*7자리"):
        document_writing._ensure_manager_verified(contract_page, value, [])
    assert contract_page.evaluate("checkManagerNameFlag") is False


def test_standard_route_needs_no_manager(contract_page):
    contract_page.goto("https://fp.example/fp/loan/sales02.do")
    document_writing._ensure_manager_verified(contract_page, "", [])


def test_tm_rejects_unconfirmed_manager(contract_page, monkeypatch):
    monkeypatch.setattr(document_writing.browser, "MAX_TIMEOUT_MS", 100)
    contract_page.goto("https://fp.example/fp/loan/sales02_tm1.do")
    _manager_form(contract_page, valid=False)
    with pytest.raises(RuntimeError, match="관리자사번 확인"):
        document_writing._ensure_manager_verified(contract_page, "1234567", [])


@pytest.mark.parametrize("status", ["작성완료", "제출완료"])
def test_accepts_completed_pledge_status(contract_page, status, monkeypatch):
    monkeypatch.setattr(document_writing, "FORM_SUBMIT_SETTLE_MS", 0)
    monkeypatch.setattr(document_writing.browser, "MAX_TIMEOUT_MS", 100)
    contract_page.set_content(
        "<table><tr><td>(신)정보보호서약서_설계사대리점</td>"
        f'<td><button id="btnGroup9">양식보기</button></td><td id="check9">{status}</td></tr></table>'
    )
    document_writing._wait_for_form_complete(contract_page)
