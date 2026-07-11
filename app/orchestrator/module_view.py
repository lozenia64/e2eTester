from __future__ import annotations

from pydantic import BaseModel

from app.core.enums import RunStatus
from app.core.models import Run, RunModule


class ModuleView(BaseModel):
    """RunModule 의 **읽기 모델(프레젠테이션 프로젝션)**.

    WebSocket ``module_*`` 이벤트 payload 에서 모듈 본문을 엔티티 ``model_dump`` 없이
    명시적으로 투영한다(``RunView`` 와 동일한 경계 규율).
    """

    module: RunModule
    run_status: RunStatus

    @classmethod
    def from_module(cls, module: RunModule, run: Run) -> ModuleView:
        return cls(module=module, run_status=run.status)

    @classmethod
    def dump(cls, module: RunModule, run: Run) -> dict:
        view = cls.from_module(module, run)
        return {
            "module": view.module.model_dump(mode="json"),
            "run_status": view.run_status,
        }
