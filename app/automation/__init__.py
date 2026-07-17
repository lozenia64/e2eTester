"""Automation bounded context — Flow/PageObject 4-layer site automation."""

from app.automation.ports import AutomationContext, AutomationPort, Flow
from app.automation.scenario_engine import ScenarioEngine

__all__ = ["AutomationContext", "AutomationPort", "Flow", "ScenarioEngine"]
