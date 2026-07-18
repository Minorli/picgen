from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .auth import AuthStore
from .storage import storage_is_writable

_READINESS_CACHE_SECONDS = 5.0


@dataclass(frozen=True)
class StorageReadiness:
    storage_writable: bool
    database_writable: bool


class ReadinessProbe:
    """Cache durable storage probes to bound health-check write amplification."""

    def __init__(self, cache_seconds: float = _READINESS_CACHE_SECONDS) -> None:
        self._cache_seconds = cache_seconds
        self._lock = threading.Lock()
        self._checked_at = 0.0
        self._cached: StorageReadiness | None = None

    def check(
        self,
        *,
        outputs_dir: Path,
        auth_enabled: bool,
        auth_store: AuthStore,
    ) -> StorageReadiness:
        now = time.monotonic()
        with self._lock:
            if self._cached is not None and now - self._checked_at < self._cache_seconds:
                return self._cached
            storage_writable = storage_is_writable(outputs_dir)
            try:
                database_writable = not auth_enabled or auth_store.is_ready()
            except Exception:
                database_writable = False
            result = StorageReadiness(
                storage_writable=storage_writable,
                database_writable=database_writable,
            )
            self._cached = result
            self._checked_at = time.monotonic()
            return result
