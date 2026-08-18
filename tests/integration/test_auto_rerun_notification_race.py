"""R4 — 자동 재실행 대기 표식과 ``RunFinished`` 사이의 알림 경합 회귀 테스트.

``OutboxRelay`` 는 **같은 프로세스의 asyncio 태스크**이고(기본 0.5초 폴링), 청구한 아웃박스
행을 **정확히 한 번만** 디스패치한다(``mark_published`` 이후 재처리 없음). 디스패치 시점에
쓰기 저장소에서 Run 을 **새로 하이드레이션**하므로, ``RunFinished`` 가 보이는 순간의 Run
스냅샷이 알림 판정의 입력이 된다.

따라서 두 가지가 동시에 성립해야 한다.

1. **성공 경로** — 자동 재실행을 걸기로 결정했다면, ``RunFinished`` 가 릴레이에 보이는
   그 순간 이미 ``auto_rerun_pending=True`` 여야 한다. 그렇지 않으면 릴레이가 재실행 이전
   상태로 운영자 알림을 보내고 dedup 키를 선점해, 진짜 최종 결과가 영원히 통보되지 않는다.
2. **실패 경로** — 그 뒤 큐잉이 실패하면 원본 Run 의 알림이 반드시 되살아나야 한다.
   플래그를 되돌리는 것만으로는 부족하다(이미 발행된 아웃박스 행은 다시 디스패치되지
   않는다) — 종료 사실을 한 번 더 발행해야 릴레이가 지금 상태로 다시 하이드레이션한다.

이 파일은 실제 SQLite 쓰기 저장소·아웃박스·릴레이·EventBus·알림 구독자·알림기를 그대로
쓰고, SMTP 전송(``GmailEmailSender``)만 대체한다.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.contexts.run.application.service import RunService
from app.contexts.run.domain.aggregate import RunAggregate
from app.contexts.run.domain.events import RunEventRecord
from app.contexts.run.infrastructure.in_memory_run_input_store import InMemoryRunInputStore
from app.contexts.run.infrastructure.in_memory_run_log_store import InMemoryRunLogStore
from app.contexts.run.infrastructure.in_memory_run_repository import InMemoryRunRepository
from app.contexts.run.infrastructure.in_memory_run_summary_query import InMemoryRunSummaryQuery
from app.contexts.run.infrastructure.sqlite_run_control_store import SqliteRunControlStore
from app.contexts.run.infrastructure.sqlite_run_summary_query import SqliteRunSummaryQuery
from app.contexts.run.infrastructure.sqlite_run_write_repository import SqliteRunWriteRepository
from app.contexts.suite.infrastructure.sqlite_suite_write_repository import (
    SqliteSuiteWriteRepository,
)
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.core.settings import E2ESettings
from app.core.system_models import ModuleDefinition, SystemDefinition
from app.execution.composite_gateway import CompositeExecutionGateway
from app.execution.in_memory_job_queue import InMemoryJobQueue
from app.execution.job_queue_port import RunJobDescriptor
from app.execution.run_queue import RunExecutionQueue
from app.execution.simulated_gateway import SimulatedExecutionGateway
from app.notifications.infrastructure.sqlite_email_notification_dedup import (
    SqliteEmailNotificationDedupStore,
)
from app.notifications.run_completion_email import (
    EmailNotificationConfig,
    RunCompletionEmailNotifier,
)
from app.platform.eventing.bus import EventBus, RunFinished
from app.platform.eventing.subscribers.email_notification import EmailNotificationSubscriber
from app.platform.eventing.support import SqliteDatabase, ensure_schema
from app.realtime.adapter import RealtimeNotificationAdapter, SuiteRealtimeNotificationAdapter
from app.realtime.projector import RealtimeProjector
from tests.eventing_helpers import make_outbox_relay, make_projection_handlers


class _FakeRegistry:
    def __init__(self, system: SystemDefinition) -> None:
        self._system = system

    def get_system(self, system_code: str) -> SystemDefinition:
        return self._system

    def get_execution_profile(self, system_code: str) -> str:
        return self._system.execution_profile


def _failing_module(*, partial_rerun_allowed: bool = True) -> ModuleDefinition:
    # max_retries 를 크게 잡아 SimulatedExecutionGateway 가 ERROR 를 PASSED 로 뒤집지 않게 한다
    # (RunModule.max_attempts=1 이 실제 재시도를 막으므로 첫 ERROR 가 그대로 최종 결과다).
    return ModuleDefinition(
        module_id="sim.fail",
        system_code="sim",
        name="Always fails",
        description="",
        group="test",
        order=10,
        execution_mode="simulated",
        simulated_duration_ms=1,
        simulated_outcome="ERROR",
        max_retries=5,
        partial_rerun_allowed=partial_rerun_allowed,
    )


def _system(*, partial_rerun_allowed: bool = True) -> SystemDefinition:
    return SystemDefinition(
        system_code="sim",
        name="Sim",
        description="",
        modules=[_failing_module(partial_rerun_allowed=partial_rerun_allowed)],
        execution_profile="light",
    )


def _pending_run() -> Run:
    return Run(
        run_id=f"run_{uuid4().hex[:8]}",
        system_code="sim",
        system_name="Sim",
        status=RunStatus.PENDING,
        requested_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="sim.fail",
                name="Always fails",
                group="test",
                order=10,
                status=ModuleStatus.PENDING,
                max_attempts=1,
            )
        ],
        selected_module_ids=["sim.fail"],
        triggered_by="schedule",
    )


# --- 1) 성공 경로: 같은 persist 안에서 플래그가 서 있는가 -----------------------


class _RecordingRepo(InMemoryRunRepository):
    """``save_run`` 호출마다 (발행 이벤트, 상태, 대기 플래그)를 기록하는 관찰용 래퍼."""

    def __init__(self) -> None:
        super().__init__()
        self.writes: list[tuple[list[str], RunStatus, bool]] = []

    async def save_run(self, run: Run, *, events: list[RunEventRecord] | None = None) -> Run:
        self.writes.append(
            (
                [type(record.event).__name__ for record in (events or [])],
                run.status,
                run.auto_rerun_pending,
            )
        )
        return await super().save_run(run, events=events)


async def _drive_with_recording_repo(tmp_path, *, partial_rerun_allowed: bool) -> _RecordingRepo:
    system = _system(partial_rerun_allowed=partial_rerun_allowed)
    run = _pending_run()
    write_repo = _RecordingRepo()
    await write_repo.create_run(run, events=RunAggregate.for_new_run(run).pull_events())
    input_store = InMemoryRunInputStore()
    await input_store.put(run.run_id, {})

    queue = RunExecutionQueue(worker_count=1, backend=InMemoryJobQueue())
    service = RunService(
        registry=_FakeRegistry(system),
        write_repo=write_repo,
        summary_query=InMemoryRunSummaryQuery(write_repo),
        realtime=RealtimeNotificationAdapter(),
        log_store=InMemoryRunLogStore(),
        execution_gateway=CompositeExecutionGateway([SimulatedExecutionGateway()]),
        event_bus=EventBus(),
        control_store=SqliteRunControlStore(str(tmp_path / "control.db")),
        input_store=input_store,
        run_queue=queue,
        settings=E2ESettings(_env_file=None, E2E_AUTO_RERUN_ENABLED="true"),
    )
    # 재실행 잡은 기록만 하고 실제로 돌리지 않는다 — 원본 종료 직후의 영속 상태를 관찰한다.
    queued: list[RunJobDescriptor] = []
    queue.set_run_job_handler(lambda descriptor: _record(queued, descriptor))
    queue.start()

    await service._execute_run(run.run_id, {"browser_mode": "headless"}, start_index=0, handle=None)
    await queue.join()
    await queue.stop()
    return write_repo


async def _record(sink: list, descriptor: RunJobDescriptor) -> None:
    sink.append(descriptor)


@pytest.mark.asyncio
async def test_run_finished_and_auto_rerun_pending_land_in_one_persist(tmp_path):
    """``RunFinished`` 를 실은 persist 가 이미 ``auto_rerun_pending=True`` 를 담고 있어야 한다.

    ``SqliteRunWriteRepository._persist`` 는 도메인 이벤트·아웃박스 행·스냅샷을 **한
    트랜잭션**으로 쓴다. 따라서 "같은 save_run 호출"은 곧 "같은 트랜잭션"이고, 그 사이를
    읽는 리더는 존재할 수 없다 — ``status=ERROR, auto_rerun_pending=False`` 조합을 관측할
    수 있는 코드 경로가 없다는 뜻이다.
    """
    write_repo = await _drive_with_recording_repo(tmp_path, partial_rerun_allowed=True)

    finished_writes = [w for w in write_repo.writes if "RunFinished" in w[0]]
    assert finished_writes, "RunFinished 를 발행한 persist 가 없다"
    event_names, status, pending = finished_writes[0]

    assert status is RunStatus.ERROR
    assert pending is True, "RunFinished 가 보이는 순간 대기 플래그가 아직 서 있지 않다(R4 경합)"
    # 큐잉 표시 감사 이벤트도 같은 트랜잭션에 실려야 한다(중간 상태가 영속되지 않는다).
    assert event_names[-2:] == ["RunFinished", "RunAutoRerunTriggered"]


@pytest.mark.asyncio
async def test_no_persisted_state_shows_terminal_error_without_pending_flag(tmp_path):
    """자동 재실행이 걸린 Run 은, 재실행이 시작되기 전까지 '종료 + 대기 아님' 으로 보이지 않는다."""
    write_repo = await _drive_with_recording_repo(tmp_path, partial_rerun_allowed=True)

    # 부분 재실행이 Run 을 RUNNING 으로 되돌리기(=알림 판정이 '아직 안 끝남'으로 바뀌기) 전까지,
    # 종료 상태이면서 대기 플래그가 내려간 스냅샷은 하나도 영속되지 않아야 한다.
    before_rerun: list[tuple[list[str], RunStatus, bool]] = []
    for write in write_repo.writes:
        if "RunPartialRerunStarted" in write[0]:
            break
        before_rerun.append(write)

    assert not [w for w in before_rerun if w[1] is RunStatus.ERROR and w[2] is False]


@pytest.mark.asyncio
async def test_blocked_partial_rerun_keeps_normal_notification_path(tmp_path):
    """부분 재실행이 애초에 불가능하면 대기 표식을 세우지 않는다(정상 알림 경로 유지).

    ``partial_rerun_allowed=False`` 는 실제 매니페스트(hom/fp/chbot)에 존재하는 설정이다.
    이 경우 자동 재실행은 결코 큐잉될 수 없으므로, 대기 표식을 세웠다가 되돌리는 대신
    처음부터 세우지 않아야 원본 Run 의 완료/운영자 알림이 그대로 나간다.
    """
    write_repo = await _drive_with_recording_repo(tmp_path, partial_rerun_allowed=False)

    finished_writes = [w for w in write_repo.writes if "RunFinished" in w[0]]
    assert len(finished_writes) == 1
    event_names, status, pending = finished_writes[0]
    assert status is RunStatus.ERROR
    assert pending is False
    assert "RunAutoRerunTriggered" not in event_names


# --- 2) 실제 파이프라인(SQLite + 아웃박스 + 릴레이 + 알림) ---------------------


def _email_config() -> EmailNotificationConfig:
    return EmailNotificationConfig(
        enabled=True,
        gmail_account="sender@gmail.com",
        gmail_app_password="app-password",
        recipients_by_system={"sim": ("user@company.com",)},
        operator_recipients=("ops@company.com",),
        gemini_enabled=False,
        gemini_api_key=None,
        gemini_models=(),
    )


class _RelayOnFinishRepo(SqliteRunWriteRepository):
    """``RunFinished`` 가 커밋되는 **즉시** 릴레이를 한 번 돌리는 쓰기 저장소.

    프로덕션에서 ``OutboxRelay`` 는 같은 프로세스의 태스크로 0.5초마다 폴링하므로,
    ``_finalize_run`` 의 persist 직후·``_enqueue_auto_rerun`` 이전에 끼어들 수 있다.
    폴링 타이밍에 의존하는 비결정적 테스트 대신, **최악의 타이밍을 결정적으로** 재현한다.
    """

    def __init__(self, db: SqliteDatabase) -> None:
        super().__init__(db)
        self.relay = None

    async def save_run(self, run: Run, *, events: list[RunEventRecord] | None = None) -> Run:
        result = await super().save_run(run, events=events)
        if self.relay is not None and any(
            type(record.event).__name__ == "RunFinished" for record in (events or [])
        ):
            await self.relay.process_once()
            await asyncio.sleep(0.05)  # EventBus 는 핸들러를 태스크로 디스패치한다.
        return result


async def _build_real_pipeline(tmp_path, *, start_queue: bool):
    db = SqliteDatabase(tmp_path / "race.db")
    await ensure_schema(db)
    write_repo = _RelayOnFinishRepo(db)
    suite_write_repo = SqliteSuiteWriteRepository(db)
    projector = RealtimeProjector(
        RealtimeNotificationAdapter(),
        SuiteRealtimeNotificationAdapter(),
        run_loader=write_repo.get_run,
        suite_loader=suite_write_repo.get_suite,
    )
    event_bus = EventBus()
    relay = make_outbox_relay(
        __import__("app.platform.eventing.outbox", fromlist=["SqliteOutbox"]).SqliteOutbox(db),
        make_projection_handlers(db, write_repo),
        write_repo,
        event_bus,
        projector,
    )
    write_repo.relay = relay

    # 릴레이가 실제로 디스패치한 RunFinished 의 (상태, 대기 플래그) 관찰자.
    dispatched: list[tuple[RunStatus, bool]] = []

    async def _observe(event: RunFinished) -> None:
        dispatched.append((event.run.status, event.run.auto_rerun_pending))

    event_bus.subscribe(RunFinished, _observe)

    notifier = RunCompletionEmailNotifier(
        _email_config(), dedup_store=SqliteEmailNotificationDedupStore(db)
    )
    mock_sender = MagicMock()
    notifier._sender = mock_sender
    EmailNotificationSubscriber(
        ["sim"], dedup_store=SqliteEmailNotificationDedupStore(db)
    ).register(event_bus)

    run = _pending_run()
    await write_repo.create_run(run, events=RunAggregate.for_new_run(run).pull_events())
    input_store = InMemoryRunInputStore()
    await input_store.put(run.run_id, {})

    queue = RunExecutionQueue(worker_count=1, backend=InMemoryJobQueue())
    service = RunService(
        registry=_FakeRegistry(_system()),
        write_repo=write_repo,
        summary_query=SqliteRunSummaryQuery(db),
        realtime=RealtimeNotificationAdapter(),
        log_store=InMemoryRunLogStore(),
        execution_gateway=CompositeExecutionGateway([SimulatedExecutionGateway()]),
        event_bus=event_bus,
        control_store=SqliteRunControlStore(str(tmp_path / "control.db")),
        input_store=input_store,
        run_queue=queue,
        settings=E2ESettings(_env_file=None, E2E_AUTO_RERUN_ENABLED="true"),
    )
    queued: list[RunJobDescriptor] = []
    if start_queue:
        queue.set_run_job_handler(lambda descriptor: _record(queued, descriptor))
        queue.start()

    return service, run, relay, dispatched, mock_sender, notifier, queued, queue


@pytest.mark.asyncio
async def test_relay_winning_the_race_does_not_send_premature_operator_alert(tmp_path, monkeypatch):
    """릴레이가 경합에서 이겨도(=finalize persist 직후 즉시 디스패치) 조기 알림이 나가지 않는다.

    수정 전에는 이 시점의 하이드레이션이 ``auto_rerun_pending=False`` 를 봤고, 운영자 알림이
    ``run_operator`` dedup 키를 선점해 재실행의 진짜 최종 결과가 영원히 통보되지 않았다.
    """
    (
        service,
        run,
        _relay,
        dispatched,
        mock_sender,
        notifier,
        queued,
        queue,
    ) = await _build_real_pipeline(tmp_path, start_queue=True)
    monkeypatch.setattr(
        "app.platform.eventing.subscribers.email_notification.RunCompletionEmailNotifier.from_env",
        lambda *_args, **_kwargs: notifier,
    )

    await service._execute_run(run.run_id, {"browser_mode": "headless"}, start_index=0, handle=None)
    await queue.join()
    await queue.stop()
    await asyncio.sleep(0.05)

    assert dispatched, "릴레이가 RunFinished 를 디스패치하지 않았다(테스트 하네스 문제)"
    assert dispatched[0] == (RunStatus.ERROR, True)
    mock_sender.send.assert_not_called()
    # 재실행은 실제로 큐잉됐다(플래그가 거짓 억제가 아님을 함께 못박는다).
    assert [descriptor.run_id for descriptor in queued] == [run.run_id]


@pytest.mark.asyncio
async def test_failed_auto_rerun_enqueue_still_delivers_operator_alert(tmp_path, monkeypatch):
    """큐잉이 실패하면 원본 Run 의 운영자 알림이 반드시 되살아난다.

    큐를 기동하지 않아 ``enqueue_run_job`` 이 ``RuntimeError`` 를 던지게 한다 — 부분 재실행
    준비(persist)까지는 성공하고 큐잉에서 실패하는, 보상이 가장 까다로운 실제 경로다.
    아웃박스는 이미 발행한 행을 다시 처리하지 않으므로, 플래그만 되돌려서는 알림이 영영
    나가지 않는다.
    """
    (
        service,
        run,
        _relay,
        dispatched,
        mock_sender,
        notifier,
        _queued,
        _queue,
    ) = await _build_real_pipeline(tmp_path, start_queue=False)
    monkeypatch.setattr(
        "app.platform.eventing.subscribers.email_notification.RunCompletionEmailNotifier.from_env",
        lambda *_args, **_kwargs: notifier,
    )

    await service._execute_run(run.run_id, {"browser_mode": "headless"}, start_index=0, handle=None)
    await asyncio.sleep(0.05)

    # 첫 디스패치는 대기 상태를 보고 알림을 건너뛰었다(경합이 실제로 발생했다는 증거).
    assert dispatched[0] == (RunStatus.ERROR, True)
    # 보상 발행 덕분에 '종료 + 대기 아님' 상태가 다시 디스패치됐다.
    assert (RunStatus.ERROR, False) in dispatched[1:]
    # 그리고 운영자 알림이 정확히 한 번 나갔다(진짜 최종 결과가 삼켜지지 않았다).
    mock_sender.send.assert_called_once()

    final = await service._write_repo.get_run(run.run_id)
    assert final.status is RunStatus.ERROR
    assert final.auto_rerun_pending is False
