from contextvars import ContextVar

TRACE_ID: ContextVar[str | None] = ContextVar("emilia_trace_id", default=None)
