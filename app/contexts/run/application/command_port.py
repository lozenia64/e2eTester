from __future__ import annotations

from typing import Protocol

from app.core.run_models import Run


class RunCommandPort(Protocol):
    """Suite Saga 가 하위 Run 을 구동하기 위해 의존하는 **명령 포트(의존성 역전)**.

    과거 ``SuiteService`` 는 구체 클래스 ``RunService`` 를 직접 import 해, 사가가 애플리케이션
    서비스에 **용접** 돼 있었다(테스트가 무거워지고 두 책임이 함께 굳었다). 이 포트로 의존을
    역전하면 사가는 "Run 을 검증/시작/취소/재개/조회한다"는 *능력* 에만 의존하고, 구체 구현
    (``RunService``)은 컴포지션 루트(``app/main.py``)가 주입한다.

    ``RunService`` 는 이 메서드들을 이미 그대로 구현하므로 구조적으로(structural typing) 이
    포트를 만족한다 — 별도 상속 선언이 필요 없다. 테스트는 이 포트만 흉내 내는 가벼운 더블로
    사가를 검증할 수 있다.
    """

    def validate_run_request(
        self,
        system_code: str,
        input_data: dict[str, str] | None = None,
        selected_module_ids: list[str] | None = None,
    ) -> tuple[dict[str, str], list[str]]: ...

    async def start_run(
        self,
        system_code: str,
        input_data: dict[str, str] | None = None,
        selected_module_ids: list[str] | None = None,
        triggered_by: str = "manual",
        schedule_id: str | None = None,
        suite_id: str | None = None,
        user_id: str | None = None,
        user_name: str | None = None,
    ) -> Run: ...

    async def cancel_run(self, run_id: str) -> Run: ...

    async def submit_otp(self, run_id: str, otp_code: str) -> Run: ...

    async def get_run(self, run_id: str) -> Run: ...

    async def rerun_from_module(
        self,
        run_id: str,
        from_module_id: str,
        *,
        user_id: str | None = None,
        user_name: str | None = None,
    ) -> Run: ...
