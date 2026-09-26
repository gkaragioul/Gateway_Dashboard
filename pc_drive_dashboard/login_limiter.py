"""In-memory backoff for failed password / setup-code attempts, per client address."""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _ClientRecord:
    failures: int = 0
    lockouts: int = 0
    last_failure: float = 0.0
    locked_until: float = 0.0


class LoginRateLimiter:
    """Lock a client out after `max_failures` wrong attempts; each further lockout doubles, up to a cap.

    A successful login clears the client's record. Records are forgotten after a quiet period, and the
    table is bounded so a flood of addresses cannot grow memory without limit. Restarting the app clears it.
    """

    def __init__(
        self,
        max_failures: int = 5,
        base_lockout_seconds: float = 30.0,
        max_lockout_seconds: float = 15 * 60.0,
        forget_after_seconds: float = 60 * 60.0,
        max_clients: int = 4096,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_failures = max_failures
        self.base_lockout_seconds = base_lockout_seconds
        self.max_lockout_seconds = max_lockout_seconds
        self.forget_after_seconds = forget_after_seconds
        self.max_clients = max_clients
        self.clock = clock
        self._records: dict[str, _ClientRecord] = {}

    def retry_after(self, client: str) -> int:
        """Seconds the client must still wait, or 0 when it may try again."""
        record = self._records.get(client)
        if record is None:
            return 0
        remaining = record.locked_until - self.clock()
        return math.ceil(remaining) if remaining > 0 else 0

    def record_failure(self, client: str) -> int:
        """Count a failed attempt; returns the new lockout in seconds (0 when not locked out yet)."""
        now = self.clock()
        record = self._records.get(client)
        if record is None or self._is_stale(record, now):
            record = _ClientRecord()
            self._remember(client, record, now)
        record.failures += 1
        record.last_failure = now
        if record.failures >= self.max_failures:
            record.failures = 0
            record.lockouts += 1
            delay = self.base_lockout_seconds * (2 ** min(record.lockouts - 1, 16))
            record.locked_until = now + min(delay, self.max_lockout_seconds)
        return self.retry_after(client)

    def reset(self, client: str) -> None:
        self._records.pop(client, None)

    def _is_stale(self, record: _ClientRecord, now: float) -> bool:
        return record.locked_until <= now and now - record.last_failure > self.forget_after_seconds

    def _remember(self, client: str, record: _ClientRecord, now: float) -> None:
        self._records.pop(client, None)
        if len(self._records) >= self.max_clients:
            for key in [key for key, value in self._records.items() if self._is_stale(value, now)]:
                del self._records[key]
        while len(self._records) >= self.max_clients:
            del self._records[next(iter(self._records))]
        self._records[client] = record
