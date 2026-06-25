"""Gemini 구조화 출력용 Pydantic 스키마.

이메일 보고서 AI 콘텐츠 spec — ``report_renderer`` 는 이 dict 만 소비한다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class FailureAnalysisGeminiOutput(BaseModel):
    category: str
    probable_cause: str
    retryable: bool
    user_summary: str
    developer_details: str
    recommended_action: str


_NARRATIVE_BLEED_MARKERS = (
    '","module_findings"',
    '","failure_details"',
    ',"module_findings"',
    ',"failure_details"',
)


def clean_narrative_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    for marker in _NARRATIVE_BLEED_MARKERS:
        marker_index = cleaned.find(marker)
        if marker_index >= 0:
            cleaned = cleaned[:marker_index].rstrip('",').rstrip('"').rstrip(",")
    if cleaned.startswith(("{", "[")):
        return ""
    if '"module_id"' in cleaned and '"screen_observation"' in cleaned:
        return ""
    return cleaned


class ModuleFinding(BaseModel):
    module_id: str
    screen_observation: str = ""
    log_observation: str = ""

    @field_validator("module_id", mode="before")
    @classmethod
    def _strip_module_id(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("screen_observation", "log_observation", mode="before")
    @classmethod
    def _clean_observation(cls, value: Any) -> str:
        return clean_narrative_text(str(value or ""))

    @model_validator(mode="after")
    def _require_module_id(self) -> ModuleFinding:
        if not self.module_id:
            raise ValueError("module_id is required")
        return self


class FailureDetail(BaseModel):
    module_id: str
    symptom: str = ""
    evidence: str = ""
    probable_cause: str = ""
    recommended_action: str = ""

    @field_validator("module_id", mode="before")
    @classmethod
    def _strip_module_id(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator(
        "symptom",
        "evidence",
        "probable_cause",
        "recommended_action",
        mode="before",
    )
    @classmethod
    def _clean_fields(cls, value: Any) -> str:
        return clean_narrative_text(str(value or ""))

    @model_validator(mode="after")
    def _require_module_id(self) -> FailureDetail:
        if not self.module_id:
            raise ValueError("module_id is required")
        return self


class RunReportContent(BaseModel):
    headline: str
    comparison_comment: str = ""
    module_findings: list[ModuleFinding] = Field(default_factory=list)
    failure_details: list[FailureDetail] = Field(default_factory=list)

    @field_validator("headline", "comparison_comment", mode="before")
    @classmethod
    def _clean_text_fields(cls, value: Any) -> str:
        return clean_narrative_text(str(value or ""))

    def to_wire_dict(self) -> dict[str, Any]:
        return self.model_dump()


class SuiteSystemContent(BaseModel):
    system_code: str
    summary: str = ""
    module_findings: list[ModuleFinding] = Field(default_factory=list)
    failure_details: list[FailureDetail] = Field(default_factory=list)

    @field_validator("system_code", mode="before")
    @classmethod
    def _normalize_code(cls, value: Any) -> str:
        return str(value or "").strip().upper()

    @field_validator("summary", mode="before")
    @classmethod
    def _clean_summary(cls, value: Any) -> str:
        return clean_narrative_text(str(value or ""))

    @model_validator(mode="after")
    def _require_system_code(self) -> SuiteSystemContent:
        if not self.system_code:
            raise ValueError("system_code is required")
        return self


class SuiteReportContent(BaseModel):
    headline: str
    systems: list[SuiteSystemContent] = Field(default_factory=list)

    @field_validator("headline", mode="before")
    @classmethod
    def _clean_headline(cls, value: Any) -> str:
        return clean_narrative_text(str(value or ""))

    def to_wire_dict(self) -> dict[str, Any]:
        return self.model_dump()
