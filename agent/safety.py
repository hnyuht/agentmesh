"""Safety rails that sit outside the LLM loop: audit log, kill switch,
control-plane pause/resume, and a rate limit on command execution.

None of this judges *what* a command does (no denylist, per project decision)
-- it only makes sure every action is recorded and can be stopped.
"""

from __future__ import annotations

import json
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, tool: str, args: dict, result: dict, rationale: str = "") -> dict:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "args": args,
            "result": result,
            "llm_rationale": rationale,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry


class RateLimiter:
    def __init__(self, max_calls: int, per_seconds: float = 60.0) -> None:
        self.max_calls = max_calls
        self.per_seconds = per_seconds
        self._calls: deque[float] = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        while self._calls and now - self._calls[0] > self.per_seconds:
            self._calls.popleft()
        if len(self._calls) >= self.max_calls:
            return False
        self._calls.append(now)
        return True


class KillSwitch:
    """Deterministic pause state. Never routed through the LLM: the relay's
    /pause and /resume control messages, and a local pause file, are both
    checked directly in the transport/dispatch layer."""

    def __init__(self, pause_file: Path) -> None:
        self.pause_file = pause_file
        self._remote_paused = False

    def set_remote_paused(self, paused: bool) -> None:
        self._remote_paused = paused

    def is_paused(self) -> bool:
        return self._remote_paused or self.pause_file.exists()
