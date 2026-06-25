"""structlog 기반 운영 로깅 — Run/Suite/스케줄 관측성."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog

from app.core.ops_buffer import ops_event_buffer

_OPS_EVENT_PREFIXES = ("run.", "suite.", "schedule.", "queue.", "startup.", "retention.", "event_bus.")


def _level_name_to_int(level: str) -> int:
    normalized = (level or "INFO").strip().upper()
    return getattr(logging, normalized, logging.INFO)


def _ops_buffer_processor(
    _logger: logging.Logger,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    log_event = event_dict.get("log_event")
    if isinstance(log_event, str) and log_event.startswith(_OPS_EVENT_PREFIXES):
        component = log_event.split(".", 1)[0]
        message = str(event_dict.get("event") or log_event)
        fields = {
            key: value
            for key, value in event_dict.items()
            if key not in {"event", "message", "level", "timestamp", "logger", "log_event"}
        }
        ops_event_buffer.record(
            event=log_event,
            message=message,
            level=str(event_dict.get("level") or _method_name),
            component=component,
            **fields,
        )
    return event_dict


def configure_logging(*, log_level: str = "INFO", log_format: str = "console") -> None:
    level = _level_name_to_int(log_level)
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _ops_buffer_processor,
    ]
    if log_format.strip().lower() == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=renderer,
            foreign_pre_chain=shared_processors,
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    for noisy in ("httpx", "httpcore", "urllib3", "google_genai", "google.auth"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


@contextmanager
def log_context(**fields: Any) -> Iterator[None]:
    bound = {key: value for key, value in fields.items() if value is not None}
    if bound:
        structlog.contextvars.bind_contextvars(**bound)
    try:
        yield
    finally:
        if bound:
            structlog.contextvars.unbind_contextvars(*bound.keys())


def bind_log_context(**fields: Any) -> None:
    bound = {key: value for key, value in fields.items() if value is not None}
    if bound:
        structlog.contextvars.bind_contextvars(**bound)


def clear_log_context(*keys: str) -> None:
    if keys:
        structlog.contextvars.unbind_contextvars(*keys)
