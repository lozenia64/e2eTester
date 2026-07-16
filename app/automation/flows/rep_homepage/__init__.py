"""대표홈페이지 시나리오 ScenarioEngine 팩토리."""

from __future__ import annotations

from app.automation.flows.rep_homepage.access_flow import MainAccessFlow
from app.automation.flows.rep_homepage.compensation_flow import (
    CompensationCancelFlow,
    CompensationChargeFlow,
    CompensationResultFlow,
    LongTermPolicyCertificateFlow,
)
from app.automation.flows.rep_homepage.contract_flow import ContractDetailFlow, ContractListFlow
from app.automation.flows.rep_homepage.login_flow import LoginFlow
from app.automation.flows.rep_homepage.marketing_consent_flow import (
    MarketingConsentApplyFlow,
    MarketingConsentWithdrawFlow,
)
from app.automation.scenario_engine import ScenarioEngine


def build_rep_homepage_engine() -> ScenarioEngine:
    engine = ScenarioEngine()
    engine.register("main_access", MainAccessFlow())
    engine.register("login", LoginFlow())
    engine.register("contract_list", ContractListFlow())
    engine.register("contract_detail", ContractDetailFlow())
    engine.register("compensation_charge", CompensationChargeFlow())
    engine.register("compensation_result", CompensationResultFlow())
    engine.register("compensation_cancel", CompensationCancelFlow())
    engine.register("long_term_policy_certificate", LongTermPolicyCertificateFlow())
    engine.register("marketing_consent_apply", MarketingConsentApplyFlow())
    engine.register("marketing_consent_withdraw", MarketingConsentWithdrawFlow())
    return engine
