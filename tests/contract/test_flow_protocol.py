"""Contract tests — all registered Flow classes explicitly implement the Flow port."""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest

from app.automation.ports import Flow
from app.automation.wiring import _ENGINE_BUILDERS


def _flow_classes() -> list[type]:
    classes: list[type] = []
    package = importlib.import_module("app.automation.flows")
    for _finder, name, _ispkg in pkgutil.walk_packages(
        package.__path__, prefix=f"{package.__name__}."
    ):
        if name.endswith(".flows") or name.endswith("_flow") or name.endswith("_flow.py"):
            module = importlib.import_module(name)
            for _attr_name, obj in inspect.getmembers(module, inspect.isclass):
                if obj.__module__ == module.__name__ and obj.__name__.endswith("Flow"):
                    classes.append(obj)
    # access_flow is a module not matching *_flow.py pattern in walk
    from app.automation.flows.access.access_flow import AccessMainFlow

    if AccessMainFlow not in classes:
        classes.append(AccessMainFlow)
    return sorted(classes, key=lambda c: c.__name__)


@pytest.mark.parametrize("flow_cls", _flow_classes(), ids=lambda c: c.__name__)
def test_flow_class_inherits_flow_protocol(flow_cls: type) -> None:
    assert issubclass(flow_cls, Flow), f"{flow_cls.__name__} must inherit Flow"


@pytest.mark.parametrize("builder", list(_ENGINE_BUILDERS.values()), ids=lambda b: b.__name__)
def test_registered_flows_satisfy_flow_protocol(builder) -> None:
    engine = builder()
    for step in engine._flows:
        flow = engine.get_flow(step)
        assert flow is not None
        assert isinstance(flow, Flow)
