from __future__ import annotations

from app.core.ops_buffer import OpsEventBuffer


def test_ops_event_buffer_records_and_lists_recent() -> None:
    buffer = OpsEventBuffer(capacity=5)
    buffer.record(event="run.created", message="Run 생성", run_id="run_1")
    buffer.record(event="suite.started", message="Suite 시작", suite_id="suite_1")

    events = buffer.list_recent(limit=10)
    assert len(events) == 2
    assert events[0]["event"] == "run.created"
    assert events[0]["fields"]["run_id"] == "run_1"
    assert events[1]["component"] == "suite"


def test_ops_event_buffer_respects_capacity() -> None:
    buffer = OpsEventBuffer(capacity=3)
    for index in range(5):
        buffer.record(event=f"run.step_{index}", message=f"step {index}")
    events = buffer.list_recent()
    assert len(events) == 3
    assert events[0]["event"] == "run.step_2"
