"""인증 프리셋(내 점검 세트) 도메인 엔티티."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AuthPreset(BaseModel):
    """사용자별·시스템별 **인증 프리셋**(자주 쓰는 인증 수단·정보 저장 세트).

    매번 점검 폼에 인증 정보를 다시 입력하는 반복을 없애기 위해, 사용자가 이름을 붙여 저장한
    인증 수단 + 인증 정보(+선택 모듈)를 담는다. 개별 점검에서는 프리셋 클릭 한 번으로 폼을
    채우고, 전체 점검에서는 시스템별로 프리셋을 골라 인증 정보를 공급한다.

    ``input_data`` 에는 이름·생년월일·휴대폰 등 **PII 가 포함**될 수 있다 — 프리셋의 존재
    목적 자체가 인증 정보의 영속 저장이므로, Run/Suite 의 휘발성 입력 스토어와 달리 SQLite 에
    영속한다. 대신 소유자(``user_id``)만 조회/수정/삭제할 수 있도록 서비스·라우트가 엄격히
    소유권을 강제하고, 응답에는 소유자 본인에게만 ``input_data`` 를 돌려준다.
    """

    preset_id: str
    user_id: str
    system_code: str
    system_name: str
    name: str
    auth_method: str = ""
    input_data: dict[str, str] = Field(default_factory=dict)
    selected_module_ids: list[str] | None = None
    created_at: datetime
    updated_at: datetime

    def to_public(self) -> dict:
        """소유자 화면용 프로젝션. 폼 자동 채움을 위해 ``input_data`` 를 포함한다(소유자 전용)."""
        return {
            "preset_id": self.preset_id,
            "system_code": self.system_code,
            "system_name": self.system_name,
            "name": self.name,
            "auth_method": self.auth_method,
            "input_data": dict(self.input_data),
            "selected_module_ids": list(self.selected_module_ids)
            if self.selected_module_ids is not None
            else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
