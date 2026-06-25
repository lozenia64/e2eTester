"""API 계층 의존성 주입(DI) 제공자.

라우트/WebSocket 핸들러가 ``request.app.state.<service>`` 서비스 로케이터로 직접
끌어오던 패턴을 ``Depends`` 기반 주입으로 바꾼다. 각 제공자는 컴포지션 루트
(``app/main.py`` 의 lifespan)가 ``app.state`` 에 심어 둔 단일 인스턴스를 꺼내 주는 얇은
어댑터다. 핸들러 시그니처에 의존성이 드러나므로 의존 관계가 명시적이고, 테스트에서는
``app.dependency_overrides`` 로 손쉽게 대체할 수 있다.

``HTTPConnection`` 을 받으므로 HTTP 라우트와 WebSocket 엔드포인트 양쪽에서 동작한다
(``Request`` / ``WebSocket`` 의 공통 상위 타입).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.requests import HTTPConnection

if TYPE_CHECKING:
    from app.core.settings import E2ESettings
    from app.execution.run_queue import RunExecutionQueue
    from app.orchestrator.ops_service import OpsService
    from app.orchestrator.run_service import RunService
    from app.orchestrator.stats_service import StatsService
    from app.orchestrator.suite_service import SuiteService
    from app.registry.loader import ModuleRegistry
    from app.scheduling.scheduler import SchedulerService
    from app.storage.ports import ScheduleRepositoryPort, SuiteRepositoryPort


def get_run_service(connection: HTTPConnection) -> "RunService":
    return connection.app.state.run_service


def get_suite_service(connection: HTTPConnection) -> "SuiteService":
    return connection.app.state.suite_service


def get_stats_service(connection: HTTPConnection) -> "StatsService":
    return connection.app.state.stats_service


def get_schedule_service(connection: HTTPConnection) -> "SchedulerService":
    return connection.app.state.schedule_service


def get_run_queue(connection: HTTPConnection) -> "RunExecutionQueue":
    return connection.app.state.run_queue


def get_ops_service(connection: HTTPConnection) -> "OpsService":
    return connection.app.state.ops_service


def get_registry(connection: HTTPConnection) -> "ModuleRegistry":
    return connection.app.state.registry


def get_suite_repository(connection: HTTPConnection) -> "SuiteRepositoryPort":
    return connection.app.state.suite_repository


def get_schedule_repository(connection: HTTPConnection) -> "ScheduleRepositoryPort":
    return connection.app.state.schedule_repository


def get_module_settings_repo(connection: HTTPConnection):
    return connection.app.state.module_settings_repo


def get_app_settings(connection: HTTPConnection) -> "E2ESettings":
    return connection.app.state.settings


def get_otp_relay_token(connection: HTTPConnection) -> str | None:
    """SMS 중계 인바운드 OTP 엔드포인트의 기기 인증 토큰(미설정 시 None = 기능 비활성)."""
    return getattr(connection.app.state, "otp_relay_token", None)


def get_otp_relay_regex(connection: HTTPConnection) -> str | None:
    """SMS 원문에서 OTP 를 추출할 정규식(미설정 시 None → 라우트의 기본 정규식 사용)."""
    return getattr(connection.app.state, "otp_relay_regex", None)
