from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from app.core.enums import ModuleStatus, RunStatus
from app.core.logging import get_logger, log_context
from app.core.models import DashboardEvent, Run, RunModule
from app.domain.events import run_deleted as domain_run_deleted
from app.domain.execution_policy import module_policy_from_definition
from app.domain.run_aggregate import RunAggregate
from app.domain.run_state_machine import (
    BlockModule,
    CancelRemaining,
    CompleteStep,
    ExecuteModule,
    PauseForInput,
    RejectInvalidResumePoint,
    RejectUnexpectedInput,
    ResumeFromModule,
    RetryModule,
    RunStateMachine,
)
from app.events.bus import EventBus
from app.execution.gateway import ExecutionGateway, ExecutionHandle
from app.execution.session_checkpoint import SessionCheckpoint, SessionCheckpointStorePort
from app.orchestrator.run_comparator import RunComparator
from app.orchestrator.run_planner import RunPlanner
from app.realtime.ports import RealtimeNotificationPort
from app.registry.loader import ModuleRegistry
from app.runner.artifact_manager import ArtifactManager
from app.storage.ports import (
    RunControlStorePort,
    RunInputStorePort,
    RunLogStorePort,
    RunSummaryQueryPort,
    RunWriteRepositoryPort,
)
from app.storage.query_rows import Page, RunSummaryFilter

if TYPE_CHECKING:
    from app.execution.job_queue_port import JobQueuePort
    from app.execution.redis_session_registry import RedisSessionRegistry
    from app.healing.ports import HealingRecorderPort as HealingRecorder

from app.execution.job_queue_port import RunJobDescriptor

logger = get_logger(__name__)


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


class RunService:
    """Run 의 생명주기를 관장하는 오케스트레이터(**커맨드 전용** 애플리케이션 서비스).

    책임은 *실행 순서*와 *부작용 조율*(영속·이벤트 발행·게이트웨이 호출)로 한정한다. "무엇이
    합법한 상태 전이인가"라는 규칙·불변식·상태 변경은 도메인 애그리거트 ``RunAggregate``
    (``app/domain/run_aggregate.py``)에 위임한다 — 그 결정/변경은 I/O 없이 단독으로 단위
    테스트된다. 실제 브라우저 구동·스레드 모델·런타임 수명은 ``ExecutionGateway`` 포트에,
    검증·계획은 ``RunPlanner`` 에, 이력 비교는 ``RunComparator`` 에, AI 실패 분석·종료 메일
    같은 부수 관심사는 ``EventBus`` 구독자에게 위임한다. 외부로 나가는 Run 본문은 ``RunView``
    프로젝션을 거친다. 이 클래스는 Playwright/스레드/Gemini/SMTP 를 전혀 import 하지 않는다.

    **목록/대시보드 질의는 이 서비스의 책임이 아니다** — 라우트는
    ``app/orchestrator/queries/`` 의 질의 핸들러(``RunQueries``/``DailyDashboardQueries``)를
    직접 주입받는다. 이 서비스가 요약 질의 포트를 쓰는 곳은 커맨드 내부 판단(정리 대상
    선별·OTP 대기 Run 탐색)뿐이며, 그마저 blob 이 아니라 프로젝션 행/ID 만 읽는다.
    """

    def __init__(
        self,
        registry: ModuleRegistry,
        write_repo: RunWriteRepositoryPort,
        summary_query: RunSummaryQueryPort,
        realtime: RealtimeNotificationPort,
        log_store: RunLogStorePort,
        execution_gateway: ExecutionGateway,
        event_bus: EventBus,
        control_store: RunControlStorePort,
        input_store: RunInputStorePort,
        run_queue: JobQueuePort,
        comparator: RunComparator | None = None,
        planner: RunPlanner | None = None,
        artifact_manager: ArtifactManager | None = None,
        healing_recorder: HealingRecorder | None = None,
        session_registry: RedisSessionRegistry | None = None,
        session_checkpoint_store: SessionCheckpointStorePort | None = None,
    ) -> None:
        self._registry = registry
        self._write_repo = write_repo
        self._summary_query = summary_query
        self._realtime = realtime
        self._log_store = log_store
        self._gateway = execution_gateway
        self._event_bus = event_bus
        # 실행 코루틴은 더 이상 fire-and-forget asyncio.create_task 가 아니라, 감독되는 작업
        # 큐(워커 풀 · 예외 격리 · 동시성 제한 · 수명 관리)에 제출한다.
        self._run_queue = run_queue
        self._comparator = comparator or RunComparator(summary_query, write_repo)
        self._planner = planner or RunPlanner()
        self._artifact_manager = artifact_manager or ArtifactManager()
        # 제어 상태(취소 의도·OTP 재개 컨텍스트)는 더 이상 서비스-인스턴스 메모리 dict 가 아니라
        # 영속 스토어(권위 있는 단일 출처)가 소유한다. PII 입력값도 전용 스토어로 분리한다.
        # 둘 다 Run blob 에 들어가지 않아 WebSocket/응답 payload 로 새지 않는다. 두 스토어 모두
        # 포트로만 의존하며 구체 어댑터 선택은 컴포지션 루트(app/main.py)가 독점한다(코어는
        # 어떤 구체 어댑터도 import 하지 않는다).
        self._control_store = control_store
        self._input_store = input_store
        # 자가 치유 이벤트 기록자(선택 협력자). 실행 어댑터는 치유 시도 '사실'만
        # StepExecutionResult 에 실어 보고하고, 영속·패치 제안은 여기서 위임한다.
        self._healing_recorder = healing_recorder
        # 원격 모드 OTP 교차 재기동: 워커 세션 리스가 살아 있으면 WAITING_INPUT 을 봉인하지 않는다.
        self._session_registry = session_registry
        # Phase C: 모듈 경계·OTP 일시정지 시 세션 storage_state 를 내구 체크포인트로 저장하는
        # 선택 협력자. 미주입/게이트웨이 미지원이면 캡처는 no-op(None)이라 기존 흐름과 동일하다.
        self._session_checkpoint_store = session_checkpoint_store

    # --- 조회 -------------------------------------------------------------

    def list_systems(self):
        return self._registry.list_systems()

    def get_system(self, system_code: str):
        return self._registry.get_system(system_code)

    async def get_run(self, run_id: str) -> Run:
        """단일 Run 의 **읽기 모델**(상태 + 로그 하이드레이션)을 돌려준다.

        영속 Run blob 에는 로그가 없으므로(별도 로그 스토어 소유), 여기서 ``RunLogStorePort``
        의 로그를 모듈에 채워 넣어 스냅샷/상세 화면/실패 분석이 기대하는 형태로 조립한다.
        내부 쓰기 경로는 이 메서드가 아니라 ``self._write_repo.get_run`` 을 직접 써서 로그
        하이드레이션 비용을 치르지 않는다(write-model).
        """
        run = await self._write_repo.get_run(run_id)
        await self._attach_logs(run)
        return run

    async def _attach_logs(self, run: Run) -> None:
        """로그 스토어의 로그를 Run 의 각 모듈에 하이드레이션한다(읽기 모델 조립)."""
        logs_by_module = await self._log_store.get_all(run.run_id)
        RunAggregate(run).hydrate_logs(logs_by_module)

    async def delete_run(self, run_id: str) -> None:
        run = await self._write_repo.get_run(run_id)
        if run.status in {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT}:
            raise ValueError("진행 중인 Run은 삭제할 수 없습니다. 먼저 취소해 주세요.")
        if await self._control_store.get_pending(run_id) is not None:
            raise ValueError("진행 중인 Run은 삭제할 수 없습니다. 먼저 취소해 주세요.")

        await self._log_store.delete_by_run_id(run_id)
        await self._write_repo.delete_run(run_id)
        # 프로젝션의 파생 행(이력 인덱스·이상건 인박스 등)도 함께 정리되도록 삭제 사실을
        # 이벤트로 발행한다(아웃박스 경유 — 리빌드 재생 시에도 같은 순서로 재적용된다).
        await self._write_repo.append_events([domain_run_deleted(run_id)])
        self._artifact_manager.delete_run_artifacts(run_id)
        await self._input_store.delete(run_id)
        await self._control_store.delete(run_id)

    async def purge_runs(
        self,
        *,
        statuses: frozenset[RunStatus],
        requested_before: datetime | None = None,
    ) -> list[str]:
        """지정 상태의 종료 Run 을 일괄 삭제한다(보존 정리 배치용).

        ``requested_before`` 가 있으면 해당 시각 이전에 요청된 Run 만 대상으로 한다.
        진행 중(PENDING/RUNNING/WAITING_INPUT) Run 과 OTP 대기 중인 Run 은 건너뛴다.
        """
        deleted: list[str] = []
        active = frozenset({RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT})
        cutoff_utc = None
        if requested_before is not None:
            cutoff_utc = (
                requested_before
                if requested_before.tzinfo is not None
                else requested_before.replace(tzinfo=UTC)
            )
        run_ids = await self._summary_query.list_run_ids(
            RunSummaryFilter(statuses=statuses - active, requested_before=cutoff_utc)
        )
        for run_id in run_ids:
            if await self._control_store.get_pending(run_id) is not None:
                continue
            await self._log_store.delete_by_run_id(run_id)
            await self._write_repo.delete_run(run_id)
            await self._write_repo.append_events([domain_run_deleted(run_id)])
            self._artifact_manager.delete_run_artifacts(run_id)
            await self._input_store.delete(run_id)
            await self._control_store.delete(run_id)
            deleted.append(run_id)
        return deleted

    async def reconcile_interrupted_runs(self) -> int:
        """재기동 시 비종료 상태로 남은 Run 을 CANCELLED 로 정리한다.

        영속 저장소(SQLite)를 쓰면 서버가 내려갈 때 RUNNING/WAITING_INPUT 이던 Run 이
        그대로 복원된다. 로컬 모드에서는 브라우저 세션이 프로세스와 함께 사라지므로 봉인한다.
        원격 모드에서는 ``RedisSessionRegistry`` 하트비트가 살아 있는 WAITING_INPUT Run 은
        OTP 교차 재기동을 위해 봉인하지 않는다.
        """
        count = 0
        active_statuses = frozenset({RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT})
        run_ids = await self._summary_query.list_run_ids(RunSummaryFilter(statuses=active_statuses))
        for run_id in run_ids:
            # 봉인은 쓰기 경로 — 단건 애그리거트 로드가 합법이다.
            run = await self._write_repo.get_run(run_id)
            if run.status not in active_statuses:
                continue
            if run.status == RunStatus.WAITING_INPUT and self._session_registry is not None:
                pending = await self._control_store.get_pending(run.run_id)
                if pending is not None and await self._session_registry.is_alive(
                    pending.session_id
                ):
                    continue
            # Phase C: 내구 체크포인트가 있으면 봉인하지 않는다(임의 워커가 이어받을 수 있음).
            # WAITING_INPUT 은 그대로 두어 submit_otp 가 체크포인트로 재개하게 하고, 그 외
            # 진행 중 Run 은 체크포인트 다음 모듈부터 재개 잡을 재발행한다. 봉인은 체크포인트조차
            # 없는 스트림에만 적용된다(로컬/시뮬 모드는 체크포인트를 캡처하지 않아 종전대로 봉인).
            if await self._resume_from_checkpoint_if_available(run):
                continue
            aggregate = RunAggregate(run)
            if not aggregate.seal_interrupted():
                continue
            await self._persist(run, aggregate)
            # 재기동으로 죽은 브라우저를 가리키던 dangling 세션 토큰을 정리한다(영속 제어 스토어
            # 사용 시 재기동 후에도 남아 있을 수 있다). 입력값은 보존돼 rerun 에 쓰인다.
            await self._control_store.clear_pending(run.run_id)
            count += 1
        return count

    async def _resume_from_checkpoint_if_available(self, run: Run) -> bool:
        """내구 체크포인트가 있으면 재기동 후 이어받는다(있으면 True — 봉인하지 않음).

        WAITING_INPUT 은 재개 잡을 발행하지 않고 그대로 두어(OTP 아직 미제출) 이후 ``submit_otp``
        가 체크포인트로 재개하게 한다. 그 외 진행 중 Run 은 체크포인트 다음 모듈부터 재개 잡을
        재발행한다. 체크포인트가 없으면 False(호출자가 봉인).
        """
        if self._session_checkpoint_store is None:
            return False
        checkpoint = await self._session_checkpoint_store.get(run.run_id)
        if checkpoint is None:
            return False
        if run.status == RunStatus.WAITING_INPUT:
            return True  # OTP 대기 유지 — submit_otp 가 재개.
        await self._run_queue.enqueue_run_job(
            RunJobDescriptor(
                run_id=run.run_id,
                kind="resume",
                start_index=checkpoint.module_index + 1,
                label=f"run:{run.run_id}:checkpoint-resume",
                execution_profile=self._registry.get_execution_profile(run.system_code),
            )
        )
        logger.info(
            "체크포인트에서 Run 재개 잡 재발행",
            log_event="run.checkpoint_resume",
            run_id=run.run_id,
            module_index=checkpoint.module_index,
        )
        return True

    async def dispatch_run_job(self, descriptor: RunJobDescriptor) -> None:
        """직렬화된 Run 작업 설명자를 실행한다(워커·로컬 큐 공용 진입점)."""
        input_data = await self._input_store.get(descriptor.run_id)
        if input_data is None:
            raise KeyError(f"Run inputs are no longer available: {descriptor.run_id}")
        if descriptor.kind == "resume":
            pending = await self._control_store.get_pending(descriptor.run_id)
            if pending is None:
                raise KeyError(f"Run is not waiting for OTP: {descriptor.run_id}")
            handle = ExecutionHandle(
                execution_mode=pending.execution_mode,
                session_id=pending.session_id,
            )
            # submit_otp 가 큐에 넣기 전에 pending 을 지우면 워커가 세션을 복원할 수 없다.
            await self._control_store.clear_pending(descriptor.run_id)
            await self._execute_run(
                descriptor.run_id,
                input_data,
                pending.resume_index,
                handle,
            )
            return
        await self._execute_run(descriptor.run_id, input_data, descriptor.start_index, None)

    async def subscribe(self, run_id: str):
        return await self._realtime.subscribe(run_id)

    async def unsubscribe(self, run_id: str, queue):
        await self._realtime.unsubscribe(run_id, queue)

    async def _persist(self, run: Run, aggregate: RunAggregate | None = None) -> None:
        events = aggregate.pull_events() if aggregate is not None else []
        await self._write_repo.save_run(run, events=events)

    # --- 명령(요청 처리) --------------------------------------------------

    def validate_run_request(
        self,
        system_code: str,
        input_data: dict[str, str] | None = None,
        selected_module_ids: list[str] | None = None,
    ) -> tuple[dict[str, str], list[str]]:
        """Run 을 실제로 만들지 않고 입력값·모듈 선택·인증 수단만 검증한다.

        예약(Schedule)/Suite 등록 시 잘못된 조합을 등록 단계에서 거르기 위해 쓴다.
        """
        system = self.get_system(system_code)
        return self._planner.prepare(system, input_data, selected_module_ids)

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
    ) -> Run:
        system = self.get_system(system_code)
        run_id = f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        sanitized_input, resolved_selected_module_ids = self._planner.prepare(
            system, input_data, selected_module_ids
        )
        run = Run(
            run_id=run_id,
            system_code=system.system_code,
            system_name=system.name,
            status=RunStatus.PENDING,
            requested_at=datetime.now(UTC),
            modules=self._planner.build_run_modules(system, resolved_selected_module_ids),
            selected_module_ids=resolved_selected_module_ids,
            triggered_by=triggered_by,
            schedule_id=schedule_id,
            suite_id=suite_id,
            created_by_user_id=user_id,
            created_by_user_name=user_name,
        )
        await self._input_store.put(run_id, dict(sanitized_input))
        aggregate = RunAggregate.for_new_run(run)
        await self._write_repo.create_run(run, events=aggregate.pull_events())
        logger.info(
            "Run 생성",
            log_event="run.created",
            run_id=run.run_id,
            system_code=run.system_code,
            triggered_by=run.triggered_by,
            suite_id=run.suite_id,
            schedule_id=run.schedule_id,
            user_name=run.created_by_user_name,
        )
        await self._run_queue.enqueue_run_job(
            RunJobDescriptor(
                run_id=run.run_id,
                kind="execute",
                label=f"run:{run.run_id}",
                execution_profile=system.execution_profile,
            )
        )
        return run

    async def submit_otp(self, run_id: str, otp_code: str) -> Run:
        run = await self._write_repo.get_run(run_id)
        pending = await self._control_store.get_pending(run_id)
        if pending is None:
            raise KeyError(f"Run is not waiting for OTP: {run_id}")
        input_data = await self._input_store.get(run_id)
        if input_data is None:
            # 입력값이 사라진 경우(예: 재기동 후 인메모리 스토어가 비었음). 이어받을 수 없다.
            raise KeyError(f"Run inputs are no longer available: {run_id}")
        # 핸들은 직렬화 토큰이라 pending 컨텍스트로 그대로 복원한다. OTP 는 입력값 dict 에
        # 담지 않고 게이트웨이로 런타임에 직접 주입한다(재개 시 OTP 는 runtime.config 에서 읽힘).
        handle = ExecutionHandle(
            execution_mode=pending.execution_mode, session_id=pending.session_id
        )
        await self._gateway.submit_input(handle, otp_code.strip())
        aggregate = RunAggregate(run)
        waiting_module = aggregate.module(pending.module_id)
        aggregate.resume_after_input(waiting_module)
        await self._persist(run, aggregate)
        logger.info(
            "Run OTP 재개", log_event="run.resumed", run_id=run_id, module_id=pending.module_id
        )
        await self._run_queue.enqueue_run_job(
            RunJobDescriptor(
                run_id=run_id,
                kind="resume",
                start_index=pending.resume_index,
                label=f"run:{run_id}:resume",
                execution_profile=self._registry.get_execution_profile(run.system_code),
            )
        )
        return run

    async def submit_otp_to_waiting(self, otp_code: str) -> Run:
        """현재 OTP 입력 대기 중인 Run 을 찾아 OTP 를 제출하고 재개한다.

        SMS 중계기는 ``run_id`` 를 모르고 코드만 보내므로, 서버가 "지금 OTP 를 기다리는 Run"
        을 찾아 기존 ``submit_otp`` 로 위임한다. 제어 스토어의 pending(=OTP 대기)이 권위 있는
        단일 출처이므로, ``WAITING_INPUT`` Run 중 pending 이 살아 있는 것만 후보로 본다(상태와
        제어 스토어가 어긋난 경합 상황을 배제). 무인 자동화는 본래 순차 실행이라 보통 1건이며,
        여러 건이면 **가장 최근에 OTP 대기에 들어간 Run**(방금 도착한 SMS 에 대응 —
        ``PendingExecution.paused_at``)을 고른다. Run 생성 시각(``requested_at``)은 잘못된
        프록시라 정렬 키로 쓰지 않는다(먼저 생성됐지만 나중에 멈춘 Run 이 오주입되는 문제);
        ``paused_at`` 이 없는 레거시 pending 행만 생성 시각으로 폴백한다.
        """
        waiting_rows = await self._summary_query.list_summaries(
            RunSummaryFilter(statuses=frozenset({RunStatus.WAITING_INPUT})),
            Page(limit=200),
        )
        candidates: list[tuple[str, datetime]] = []
        for row in waiting_rows:
            pending = await self._control_store.get_pending(row.run_id)
            if pending is None:
                continue
            candidates.append((row.run_id, _as_utc(pending.paused_at or row.requested_at)))
        if not candidates:
            raise KeyError("OTP 입력을 기다리는 Run이 없습니다.")

        candidates.sort(key=lambda item: item[1], reverse=True)
        target_run_id = candidates[0][0]
        if len(candidates) > 1:
            logger.warning(
                "OTP 대기 Run 다건 — 최근 요청 Run 에 제출",
                log_event="run.otp_relay_ambiguous",
                candidate_count=len(candidates),
                selected_run_id=target_run_id,
            )
        return await self.submit_otp(target_run_id, otp_code)

    async def cancel_run(self, run_id: str) -> Run:
        run = await self._write_repo.get_run(run_id)
        if run.status in {
            RunStatus.PASSED,
            RunStatus.ANOMALY,
            RunStatus.ERROR,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            raise ValueError("이미 종료된 Run은 취소할 수 없습니다.")
        await self._control_store.set_cancel_requested(run_id)
        logger.info(
            "Run 취소 요청",
            log_event="run.cancel_requested",
            run_id=run_id,
            status=run.status.value,
        )
        pending = await self._control_store.get_pending(run_id)
        if pending is not None:
            # OTP 입력 대기 중에는 실행 루프가 돌고 있지 않으므로 여기서 직접 정리·종료한다.
            await self._control_store.clear_pending(run_id)
            handle = ExecutionHandle(
                execution_mode=pending.execution_mode, session_id=pending.session_id
            )
            await self._cancel_waiting_run(run, handle)
        # 실행 중/대기열 상태에서는 실행 루프가 다음 모듈로 넘어가기 전에 취소 플래그를 확인해
        # 협력적으로 중단한다. (진행 중인 단계는 끝나거나 timeout 된 뒤 중단된다.)
        return run

    async def rerun_run(
        self,
        run_id: str,
        user_id: str | None = None,
        user_name: str | None = None,
        *,
        from_module_id: str | None = None,
    ) -> Run:
        if from_module_id is not None:
            return await self.rerun_from_module(
                run_id,
                from_module_id,
                user_id=user_id,
                user_name=user_name,
            )
        original = await self._write_repo.get_run(run_id)
        stored_input = await self._input_store.get(run_id)
        if stored_input is None:
            raise ValueError(
                "재실행에 필요한 입력 정보를 찾을 수 없습니다. 홈에서 새로 실행해 주세요."
            )
        selected_module_ids = list(original.selected_module_ids) or None
        return await self.start_run(
            original.system_code,
            dict(stored_input),
            selected_module_ids,
            user_id=user_id or original.created_by_user_id,
            user_name=user_name or original.created_by_user_name,
        )

    async def rerun_from_module(
        self,
        run_id: str,
        from_module_id: str,
        *,
        user_id: str | None = None,
        user_name: str | None = None,
    ) -> Run:
        run = await self._write_repo.get_run(run_id)
        if run.status in {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT}:
            raise ValueError("진행 중인 Run 은 부분 재실행할 수 없습니다.")
        if await self._control_store.get_pending(run_id) is not None:
            raise ValueError("진행 중인 Run 은 부분 재실행할 수 없습니다.")

        system = self._registry.get_system(run.system_code)
        definitions = {module.module_id: module for module in system.modules}
        if from_module_id not in definitions:
            raise ValueError(f"알 수 없는 모듈입니다: {from_module_id}")

        ordered_modules = self._planner.ordered_selected_run_modules(run)
        module_ids = [module.module_id for module in ordered_modules]
        definition = definitions[from_module_id]
        decision = RunStateMachine.decide_partial_rerun(
            from_module_id=from_module_id,
            module_ids_in_order=module_ids,
            partial_rerun_allowed=definition.partial_rerun_allowed,
        )
        if isinstance(decision, RejectInvalidResumePoint):
            raise ValueError("이 모듈부터 부분 재실행할 수 없습니다.")

        assert isinstance(decision, ResumeFromModule)
        aggregate = RunAggregate(run)
        aggregate.prepare_partial_rerun(decision.from_index, ordered_modules)
        if user_id is not None:
            run.created_by_user_id = user_id
        if user_name is not None:
            run.created_by_user_name = user_name
        await self._persist(run, aggregate)
        await self._run_queue.enqueue_run_job(
            RunJobDescriptor(
                run_id=run_id,
                kind="execute",
                start_index=decision.from_index,
                label=f"run:{run_id}:partial-rerun",
                execution_profile=system.execution_profile,
            )
        )
        return run

    # --- 실행 루프(상태머신) ----------------------------------------------

    async def _execute_run(
        self,
        run_id: str,
        input_data: dict[str, str],
        start_index: int = 0,
        handle: ExecutionHandle | None = None,
    ) -> None:
        run = await self._write_repo.get_run(run_id)
        with log_context(
            run_id=run.run_id,
            system_code=run.system_code,
            suite_id=run.suite_id,
            schedule_id=run.schedule_id,
            triggered_by=run.triggered_by,
        ):
            await self._execute_run_inner(
                run,
                input_data,
                start_index=start_index,
                handle=handle,
            )

    async def _execute_run_inner(
        self,
        run: Run,
        input_data: dict[str, str],
        *,
        start_index: int = 0,
        handle: ExecutionHandle | None = None,
    ) -> None:
        should_finalize = True
        # OTP 입력 대기로 일시정지하며 빠져나갈 때만 True. finally 의 세션 종료를 건너뛰는
        # 판단을 더 이상 메모리 dict(_pending_otp) 멤버십이 아니라 이 로컬 플래그로 한다.
        paused = False
        current_module: RunModule | None = None
        aggregate = RunAggregate(run)
        if start_index == 0:
            aggregate.begin()
            await self._persist(run, aggregate)
            logger.info(
                "Run 시작", log_event="run.started", run_id=run.run_id, system_code=run.system_code
            )

        system = self._registry.get_system(run.system_code)
        definitions = {module.module_id: module for module in system.modules}
        ordered_modules = self._planner.ordered_selected_run_modules(run)

        forced_status: RunStatus | None = None
        try:
            for index, module in enumerate(ordered_modules[start_index:], start=start_index):
                current_module = module
                # 결정(무엇을 할지)은 순수 상태머신이, 효과(I/O)는 이 루프가 책임진다.
                entry = RunStateMachine.decide_module_entry(
                    cancel_requested=await self._control_store.is_cancel_requested(run.run_id),
                    dependencies_satisfied=aggregate.dependencies_satisfied(module),
                )
                if isinstance(entry, CancelRemaining):
                    forced_status = RunStatus.CANCELLED
                    await self._mark_modules_cancelled(run, ordered_modules[index:])
                    break
                if isinstance(entry, BlockModule):
                    aggregate.block_for_dependencies(module)
                    await self._persist(run, aggregate)
                    continue
                assert isinstance(entry, ExecuteModule)

                await self._transition_to_queued(run, module)
                await asyncio.sleep(0.6)
                await self._transition_to_running(run, module)

                definition = definitions[module.module_id]
                module_policy = module_policy_from_definition(definition)
                # 실행은 전적으로 ExecutionGateway 포트 뒤에서 일어난다. 실제 브라우저
                # 실행과 시뮬레이션의 구분은 더 이상 코어에 없다(합성 게이트웨이가 모드로 라우팅).
                # 지원하지 않는 execution_mode 면 open_session 이 예외를 던져 모듈이 명확히 실패한다.
                if handle is None:
                    try:
                        handle = await self._gateway.open_session(
                            definition.execution_mode,
                            input_data,
                            run.run_id,
                            module.module_id,
                        )
                        if start_index > 0 and index == start_index and definition.workflow_step:
                            await self._gateway.resume_from_step(
                                handle,
                                index,
                                definition.workflow_step,
                            )
                    except Exception as exc:
                        await self._fail_module(run, module, exc)
                        continue

                async def on_log(line: str, current_module=module, current_run=run) -> None:
                    await self._handle_module_log(current_run, current_module, line)

                while True:
                    execution_result = await self._gateway.run_step(
                        handle, run.run_id, definition, on_log
                    )

                    # 자가 치유 시도가 보고되면 감사 이벤트로 영속하고 패치 제안을 만든다.
                    # 기록 실패가 점검 자체를 실패시키지 않도록 격리한다.
                    if execution_result.healing_events and self._healing_recorder is not None:
                        try:
                            await self._healing_recorder.record_step_healing(
                                run, module, definition, execution_result.healing_events
                            )
                        except Exception:
                            logger.exception(
                                "자가 치유 이벤트 기록 실패",
                                log_event="healing.record_failed",
                                run_id=run.run_id,
                                module_id=module.module_id,
                            )

                    if execution_result.status == ModuleStatus.WAITING_INPUT:
                        cancel_requested = await self._control_store.is_cancel_requested(run.run_id)
                        post = RunStateMachine.decide_post_step(
                            step_status=execution_result.status,
                            cancel_requested=cancel_requested,
                            module_requires_user_input=definition.requires_user_input,
                        )
                    elif execution_result.status == ModuleStatus.PASSED:
                        post = CompleteStep()
                    else:
                        cancel_requested = await self._control_store.is_cancel_requested(run.run_id)
                        post = RunStateMachine.decide_post_step_failure(
                            step_status=execution_result.status,
                            cancel_requested=cancel_requested,
                            current_attempt=module.attempt,
                            max_attempts=module.max_attempts,
                            retryable_on=module_policy.retryable_on,
                            backoff_ms=module_policy.retry_backoff_ms,
                        )

                    if isinstance(post, CancelRemaining):
                        forced_status = RunStatus.CANCELLED
                        await self._mark_modules_cancelled(run, ordered_modules[index:])
                        break
                    if isinstance(post, PauseForInput):
                        await self._pause_for_input(
                            run, module, index, definition, handle, execution_result
                        )
                        should_finalize = False
                        paused = True
                        return
                    if isinstance(post, RejectUnexpectedInput):
                        await self._fail_module(
                            run,
                            module,
                            RuntimeError(
                                "모듈이 사용자 입력을 요구했으나 매니페스트에 "
                                "requires_user_input 이 선언되지 않았습니다."
                            ),
                        )
                        break
                    if isinstance(post, RetryModule):
                        aggregate.record_retry(module)
                        await self._persist(run, aggregate)
                        await asyncio.sleep(post.backoff_ms / 1000)
                        await self._transition_to_running(run, module)
                        continue
                    assert isinstance(post, CompleteStep)

                    self._record_module_result(aggregate, module, execution_result)
                    aggregate.finish_timing(module)
                    await self._persist(run, aggregate)
                    break

                if forced_status == RunStatus.CANCELLED:
                    break
                if isinstance(post, RejectUnexpectedInput):
                    continue
        except Exception as exc:
            forced_status = RunStatus.ERROR
            await self._mark_unexpected_run_failure(run, current_module, ordered_modules, exc)
        finally:
            if handle is not None and not paused:
                try:
                    await self._gateway.close_session(handle)
                except Exception as exc:
                    if forced_status is None:
                        forced_status = RunStatus.ERROR
                        await self._mark_unexpected_run_failure(
                            run, current_module, ordered_modules, exc
                        )
                    else:
                        logger.exception(
                            "Run runtime 정리 오류",
                            log_event="run.cleanup_failed",
                            run_id=run.run_id,
                            error=str(exc),
                        )

        if not should_finalize:
            return
        await self._finalize_run(run, forced_status)

    # --- 모듈 상태 전이 보조 ----------------------------------------------

    async def _transition_to_queued(self, run: Run, module: RunModule) -> None:
        aggregate = RunAggregate(run)
        aggregate.mark_queued(module)
        await self._persist(run, aggregate)

    async def _transition_to_running(self, run: Run, module: RunModule) -> None:
        aggregate = RunAggregate(run)
        aggregate.mark_running(module)
        await self._persist(run, aggregate)

    def _record_module_result(
        self, aggregate: RunAggregate, module: RunModule, execution_result
    ) -> None:
        # 로그는 별도 스토어가 소유하므로 집합체로 복사하지 않는다(읽기 시 하이드레이션).
        aggregate.record_result(
            module,
            status=execution_result.status,
            message=execution_result.message,
            artifacts=execution_result.artifacts,
            current_url=execution_result.current_url,
            dialog_messages=execution_result.dialog_messages,
        )

    async def _fail_module(self, run: Run, module: RunModule, exc: Exception) -> None:
        """세션 기동 실패 등 단계 진입 전에 난 오류로 모듈을 실패 처리한다."""
        await self._handle_module_log(run, module, f"[error] {exc}")
        aggregate = RunAggregate(run)
        aggregate.fail_module(module, str(exc))
        await self._persist(run, aggregate)

    async def _pause_for_input(
        self,
        run: Run,
        module: RunModule,
        index: int,
        definition,
        handle: ExecutionHandle,
        execution_result,
    ) -> None:
        aggregate = RunAggregate(run)
        aggregate.mark_waiting_input(module, execution_result.message, execution_result.artifacts)
        await self._persist(run, aggregate)
        # 재개 컨텍스트(직렬화 토큰 + resume index)는 메모리 dict 가 아니라 제어 스토어가 소유한다.
        # 입력값(PII)은 start_run 에서 이미 input_store 에 보관됐다.
        await self._control_store.set_pending(
            run.run_id,
            session_id=handle.session_id,
            execution_mode=handle.execution_mode,
            resume_index=index,
            module_id=module.module_id,
        )
        # Phase C: OTP 일시정지는 내구 시그널 포인트 — 세션 storage_state 를 체크포인트로 확정해
        # 재기동/워커 교체 후 임의 워커가 이어받을 수 있게 한다(게이트웨이 미지원 시 no-op).
        await self._save_checkpoint(run, module_index=index, handle=handle)
        logger.info(
            "Run OTP 대기",
            log_event="run.waiting_input",
            run_id=run.run_id,
            module_id=module.module_id,
        )

    async def _save_checkpoint(
        self, run: Run, *, module_index: int, handle: ExecutionHandle
    ) -> None:
        """세션 storage_state 를 내구 체크포인트로 저장한다(Phase C, 실패는 실행을 막지 않음)."""
        if self._session_checkpoint_store is None:
            return
        try:
            storage_state = await self._gateway.capture_storage_state(handle)
            if storage_state is None:
                return  # 게이트웨이가 체크포인트를 지원하지 않음(예: in-process 레거시).
            await self._session_checkpoint_store.save(
                SessionCheckpoint(
                    run_id=run.run_id,
                    system_code=run.system_code,
                    execution_mode=handle.execution_mode,
                    module_index=module_index,
                    session_id=handle.session_id,
                    storage_state=storage_state,
                )
            )
        except Exception as exc:
            logger.warning(
                "세션 체크포인트 저장 실패(무시하고 진행)",
                log_event="run.checkpoint_failed",
                run_id=run.run_id,
                error=str(exc),
            )

    # --- 취소 / 종료 ------------------------------------------------------

    async def _cancel_waiting_run(self, run: Run, handle: ExecutionHandle) -> None:
        try:
            await self._gateway.close_session(handle)
        except Exception as exc:
            logger.exception(
                "Run 취소 중 runtime 정리 오류",
                log_event="run.cancel_cleanup_failed",
                run_id=run.run_id,
                error=str(exc),
            )
        await self._mark_modules_cancelled(run, self._planner.ordered_selected_run_modules(run))
        # awaiting_input_* 정리는 _finalize_run → RunAggregate.finalize 가 책임진다(직접 변이 금지).
        await self._finalize_run(run, RunStatus.CANCELLED)

    async def _mark_modules_cancelled(self, run: Run, modules: list[RunModule]) -> None:
        aggregate = RunAggregate(run)
        changed = aggregate.cancel_modules(modules)
        if changed:
            await self._persist(run, aggregate)

    async def _mark_unexpected_run_failure(
        self,
        run: Run,
        current_module: RunModule | None,
        ordered_modules: list[RunModule],
        exc: Exception,
    ) -> None:
        aggregate = RunAggregate(run)
        target_module = aggregate.select_failure_target(current_module, ordered_modules)
        if target_module is None:
            logger.error(
                "Run 예상치 못한 실행 오류",
                log_event="run.unexpected_error",
                run_id=run.run_id,
                error=str(exc),
            )
            return

        await self._handle_module_log(run, target_module, f"[fatal] {exc}")
        aggregate.mark_fatal(target_module, f"예상하지 못한 실행 오류: {exc}")
        await self._persist(run, aggregate)

    async def _finalize_run(self, run: Run, forced_status: RunStatus | None = None) -> None:
        aggregate = RunAggregate(run)
        # 비교 결과를 finalize **이전**에 부착해, RunFinished 이벤트의 run_summary 가 comparison
        # 을 함께 실어 나가게 한다(실시간 프로젝터가 run_finished WS payload 를 blob 없이 조립).
        # compute_final_status 는 순수 판정(변이 없음)이라 미리 확인해도 안전하다.
        final_status = aggregate.compute_final_status(forced_status)
        if final_status in {RunStatus.PASSED, RunStatus.ANOMALY, RunStatus.ERROR, RunStatus.FAILED}:
            aggregate.attach_comparison(await self._comparator.compute(run))
        final_status = aggregate.finalize(forced_status)
        await self._persist(run, aggregate)
        # 종료된 Run 의 제어 상태(취소 플래그·재개 컨텍스트)는 더 이상 필요 없다. 입력값은
        # input_store 가 따로 보관하므로 rerun 에는 영향이 없다.
        await self._control_store.delete(run.run_id)
        # 부수 관심사(AI 실패 분석·종료 메일)는 OutboxRelay → EventBus 가 처리한다.
        logger.info(
            "Run 종료",
            log_event="run.finished",
            run_id=run.run_id,
            system_code=run.system_code,
            status=final_status.value,
            suite_id=run.suite_id,
            schedule_id=run.schedule_id,
        )

    # --- 로그 기록 --------------------------------------------------------

    async def _handle_module_log(self, run: Run, module: RunModule, line: str) -> None:
        """로그 한 줄을 로그 스토어에 적재하고 실시간 채널로 직행 발행한다.

        로그는 **도메인 이벤트가 아니다**(WP-B5): 이벤트 스토어/아웃박스/프로젝션 어떤 것도
        바꾸지 않고, 유실 허용 가능한 고빈도 스트림이다. 따라서 ``ModuleLogAppended`` 이벤트를
        발행해 릴레이→프로젝터를 거치는 대신, 영속은 로그 스토어가 책임지고 UI 전달은
        ``module_log`` DashboardEvent 로 실시간 채널에 직접 넣는다(쓰기 핫패스 경량화).
        모듈의 최신 메시지 갱신은 애그리거트(유일한 변이자)를 거치되 이벤트는 내지 않는다.
        """
        trimmed = line.strip()
        if not trimmed:
            return
        RunAggregate(run).note_module_message(module, trimmed)
        await self._log_store.append(run.run_id, module.module_id, trimmed)
        await self._realtime.publish(
            DashboardEvent(
                event_type="module_log",
                run_id=run.run_id,
                system_code=run.system_code,
                run_status=run.status,
                payload={"module_id": module.module_id, "message": trimmed},
            )
        )
