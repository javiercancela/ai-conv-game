"""Structured execution logs for service calls and authoritative game decisions."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from uuid import uuid4


_logger = logging.getLogger("convgame.trace")
_logger.setLevel(logging.INFO)
_logger.propagate = False
_logger.addHandler(logging.NullHandler())
_context: ContextVar[dict] = ContextVar("convgame_trace_context", default={})


def record(event: str, reason: str, **details) -> None:
    """Describe an actual call or branch, using its inputs rather than model reasoning."""
    _logger.info(event, extra={"trace": {**_context.get(), "event": event,
                                        "reason": reason, **details}})


@contextmanager
def log_context(**fields):
    token = _context.set({**_context.get(), **fields})
    try:
        yield
    finally:
        _context.reset(token)


class _JsonFormatter(logging.Formatter):
    def format(self, entry: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(entry.created, timezone.utc).isoformat()
        return json.dumps({"timestamp": timestamp, **entry.trace}, ensure_ascii=False)


@contextmanager
def file_log(path: str | Path):
    """Append UTF-8 JSON Lines, flush each entry, and close the file on every exit."""
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(_JsonFormatter())
    _logger.addHandler(handler)
    try:
        with log_context(session=uuid4().hex):
            yield path
    finally:
        _logger.removeHandler(handler)
        handler.close()
