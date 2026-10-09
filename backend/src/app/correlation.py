"""Correlation id shared by the API, the agent and the logs."""

from contextvars import ContextVar

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
request_id: ContextVar[str] = ContextVar("request_id", default="")


def get_correlation_id() -> str:
    return correlation_id.get()


def get_request_id() -> str:
    return request_id.get()
