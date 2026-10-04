"""Readable execution logs for service calls and authoritative game decisions."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
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


def _text(value) -> str:
    """Keep Unicode readable and prevent control characters from altering the terminal."""
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return "".join(f"\\x{ord(char):02x}" if (ord(char) < 32 and char != "\n") or ord(char) == 127
                   else char for char in str(value))


def _detail_lines(label: str, value, indent: int = 2) -> list[str]:
    prefix = " " * indent
    if isinstance(value, (dict, list, tuple)):
        if not value:
            return [f"{prefix}{label}: empty"]
        lines = [f"{prefix}{label}:"]
        fields = value.items() if isinstance(value, dict) else enumerate(value, start=1)
        for key, item in fields:
            lines.extend(_detail_lines(_text(key).replace("\n", "\\n"), item, indent + 2))
        return lines
    text = _text(value)
    if "\n" in text:
        return [f"{prefix}{label}:", *(f"{prefix}  {line}" for line in text.split("\n"))]
    return [f"{prefix}{label}: {text}"]


class _TextFormatter(logging.Formatter):
    def format(self, entry: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(entry.created, timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        trace = entry.trace
        context = " ".join(f"{key}={_text(trace[key])}" for key in ("session", "turn", "attempt") if key in trace)
        reason = _text(trace["reason"]).replace("\n", "\\n")
        lines = [f"{timestamp} UTC [{context}] {trace['event']}: {reason}"]
        for key, value in trace.items():
            if key not in {"session", "turn", "attempt", "event", "reason"}:
                lines.extend(_detail_lines(key, value))
        return "\n".join(lines)


@contextmanager
def file_log(path: str | Path):
    """Append readable UTF-8 text, flush each entry, and close the file on every exit."""
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(_TextFormatter())
    _logger.addHandler(handler)
    try:
        with log_context(session=uuid4().hex):
            yield path
    finally:
        _logger.removeHandler(handler)
        handler.close()
