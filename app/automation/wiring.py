"""시스템별 ScenarioEngine 팩토리."""

from __future__ import annotations

from app.automation.flows.access.access_flow import AccessMainFlow
from app.automation.flows.chbot.flows import ChbotContractListFlow, ChbotSimpleAuthFlow
from app.automation.flows.fp.flows import FpDocumentWritingFlow, FpIdentityVerificationFlow
from app.automation.flows.hrp.flows import (
    HrpLoginFlow,
    HrpSalvageBidDetailFlow,
    HrpSalvageBidListFlow,
)
from app.automation.flows.hwtc.flows import (
    HwtcMainAccessFlow,
    HwtcPhoneAuthFlow,
    HwtcVideoPlaybackFlow,
)
from app.automation.flows.rep_homepage import build_rep_homepage_engine
from app.automation.scenario_engine import ScenarioEngine


def build_access_engine() -> ScenarioEngine:
    engine = ScenarioEngine()
    engine.register("main_access", AccessMainFlow())
    return engine


def build_fp_engine() -> ScenarioEngine:
    engine = build_access_engine()
    engine.register("identity_verification", FpIdentityVerificationFlow())
    engine.register("document_writing", FpDocumentWritingFlow())
    return engine


def build_hrp_engine() -> ScenarioEngine:
    engine = build_access_engine()
    engine.register("login", HrpLoginFlow())
    engine.register("salvage_bid_inquiry_list", HrpSalvageBidListFlow())
    engine.register("salvage_bid_inquiry_detail", HrpSalvageBidDetailFlow())
    return engine


def build_hwtc_engine() -> ScenarioEngine:
    engine = ScenarioEngine()
    engine.register("main_access", HwtcMainAccessFlow())
    engine.register("phone_auth", HwtcPhoneAuthFlow())
    engine.register("video_playback", HwtcVideoPlaybackFlow())
    return engine


def build_chbot_engine() -> ScenarioEngine:
    engine = build_access_engine()
    engine.register("simple_auth", ChbotSimpleAuthFlow())
    engine.register("contract_list", ChbotContractListFlow())
    return engine


_ENGINE_BUILDERS = {
    "hom_workflow_step": build_rep_homepage_engine,
    "mhm_workflow_step": build_rep_homepage_engine,
    "fp_workflow_step": build_fp_engine,
    "hrp_workflow_step": build_hrp_engine,
    "hwtc_workflow_step": build_hwtc_engine,
    "chbot_workflow_step": build_chbot_engine,
}


def build_engine_for_execution_mode(execution_mode: str) -> ScenarioEngine | None:
    builder = _ENGINE_BUILDERS.get(execution_mode)
    if builder is None:
        return None
    return builder()
