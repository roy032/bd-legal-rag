"""Logging: plain text on a laptop, one JSON object per line in a container.

`LOG_FORMAT=json` makes every log line machine-readable for Loki, CloudWatch or
`jq`, and stamps it with the id of the request that produced it. The id travels
in a context variable, so code deep in the pipeline logs it without being passed
the request (Starlette copies the context into the worker thread that runs it).
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
import time

request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

# Echoed in headers and logs, so a caller-supplied id must be short and plain:
# no newlines to forge log lines, no quotes to break a JSON consumer.
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def safe_request_id(raw: str | None) -> str | None:
    return raw if raw and _SAFE_ID.match(raw) else None


class JsonFormatter(logging.Formatter):
    """{"ts", "level", "logger", "msg", "request_id", ...}. A message that is
    itself a JSON object (the service's access and trace lines) is merged in
    rather than nested as a string."""

    def format(self, record: logging.LogRecord) -> str:
        out: dict = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                     + f".{int(record.msecs):03d}Z",
                     "level": record.levelname.lower(), "logger": record.name}
        msg = record.getMessage()
        parsed = None
        if msg.startswith("{"):
            try:
                parsed = json.loads(msg)
            except ValueError:
                parsed = None
        if isinstance(parsed, dict):
            out.update(parsed)
        else:
            out["msg"] = msg
        rid = request_id.get()
        if rid and "request_id" not in out:
            out["request_id"] = rid
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False, default=str)


def configure(level: str = "INFO", fmt: str = "text") -> None:
    """Set up the root logger once. `fmt` is "text" or "json"."""
    handler = logging.StreamHandler()
    if fmt.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
