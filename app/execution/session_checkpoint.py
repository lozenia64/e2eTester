"""세션 체크포인트 — Phase C 모듈 경계 내구 상태(포트 + SQLite 어댑터).

라이브 Playwright 세션은 프로세스-로컬이라 재기동/워커 교체 시 소실된다. 각 모듈 완료(성공/
실패 공통)와 OTP 일시정지 시 ``context.storage_state()`` 를 캡처해 이 체크포인트에 저장하면,
임의의 재개 워커가 ``browser.new_context(storage_state=...)`` 로 세션을 복원해 ``module_index+1``
부터 이어받을 수 있다. 복원 상태가 무효(로그인 만료)면 ``RunStateMachine.decide_rehydration``
이 로그인 모듈부터 재실행하도록 결정한다.

``storage_state`` 는 인증 쿠키를 포함하므로 입력 스토어와 동일하게 **암호화**해 보관한다(어댑터에
암호화 협력자를 주입; 미주입 시 평문 저장은 개발/테스트 전용).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class SessionCheckpoint:
    """한 Run 의 모듈 경계 재개 지점."""

    run_id: str
    system_code: str
    execution_mode: str
    module_index: int
    session_id: str | None = None
    worker_id: str | None = None
    workflow_step: str | None = None
    storage_state: str | None = None
    runtime_config: dict | None = None
    updated_at: datetime | None = None


class SessionCheckpointStorePort(Protocol):
    """모듈 경계 세션 체크포인트 저장/조회 포트."""

    async def save(self, checkpoint: SessionCheckpoint) -> None: ...

    async def get(self, run_id: str) -> SessionCheckpoint | None: ...

    async def delete(self, run_id: str) -> None: ...


class _Cipher(Protocol):
    def encrypt(self, plaintext: str) -> str: ...

    def decrypt(self, ciphertext: str) -> str: ...


class InMemorySessionCheckpointStore:
    """테스트/개발용 인메모리 어댑터."""

    def __init__(self) -> None:
        self._by_run: dict[str, SessionCheckpoint] = {}

    async def save(self, checkpoint: SessionCheckpoint) -> None:
        self._by_run[checkpoint.run_id] = checkpoint

    async def get(self, run_id: str) -> SessionCheckpoint | None:
        return self._by_run.get(run_id)

    async def delete(self, run_id: str) -> None:
        self._by_run.pop(run_id, None)
