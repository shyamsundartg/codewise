"""Structured logging and per-question traces.

Every question produces one JSON trace (route, retrieved chunks with the
rank each signal gave them, latency per stage, token estimate, citation
check). Traces go to stdout and to ``data/traces.jsonl``, so they can be
grepped locally or shipped to CloudWatch / Langfuse / OTel later.
"""

from contextlib import contextmanager
from pathlib import Path
import json
import logging
import sys
import threading
import time

_RESERVED = set(vars(logging.makeLogRecord({})).keys()) | {"message"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": round(record.created, 3),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update({k: v for k, v in vars(record).items() if k not in _RESERVED})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


class Trace:
    def __init__(self, **fields):
        self.data: dict = dict(fields)
        self.timings: dict[str, float] = {}
        self._t0 = time.perf_counter()

    @contextmanager
    def stage(self, name: str):
        t = time.perf_counter()
        try:
            yield
        finally:
            self.timings[name] = round((time.perf_counter() - t) * 1000, 1)

    def finish(self) -> dict:
        self.data["timings_ms"] = self.timings
        self.data["total_ms"] = round((time.perf_counter() - self._t0) * 1000, 1)
        return self.data


class TraceSink:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "traces.jsonl"
        self._lock = threading.Lock()
        self.log = logging.getLogger("trace")

    def write(self, trace: dict) -> None:
        self.log.info("question answered", extra={"trace": trace})
        with self._lock, self.path.open("a") as f:
            f.write(json.dumps(trace, default=str) + "\n")
