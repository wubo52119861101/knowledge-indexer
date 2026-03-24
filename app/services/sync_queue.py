from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import asdict, dataclass
from threading import Condition
from typing import Any, Protocol

from app.core.config import Settings
from app.core.logger import get_logger
from app.core.redis import create_redis_client

logger = get_logger(__name__)


@dataclass(slots=True)
class SyncQueueMessage:
    job_id: str
    source_id: str

    def dumps(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def loads(cls, payload: str) -> "SyncQueueMessage":
        data = json.loads(payload)
        return cls(job_id=data["job_id"], source_id=data["source_id"])


class SyncQueue(Protocol):
    def enqueue(self, message: SyncQueueMessage) -> None: ...

    def dequeue(self, timeout_seconds: float = 1.0) -> SyncQueueMessage | None: ...

    def acquire_source_lock(self, source_id: str, owner: str) -> bool: ...

    def release_source_lock(self, source_id: str, owner: str) -> None: ...

    def get_source_lock_owner(self, source_id: str) -> str | None: ...


class InMemorySyncQueue:
    def __init__(self, *, lock_ttl_seconds: int = 1800) -> None:
        self._messages: deque[str] = deque()
        self._locks: dict[str, tuple[str, float | None]] = {}
        self._condition = Condition()
        self._lock_ttl_seconds = max(lock_ttl_seconds, 1)

    def enqueue(self, message: SyncQueueMessage) -> None:
        with self._condition:
            self._messages.append(message.dumps())
            self._condition.notify()

    def dequeue(self, timeout_seconds: float = 1.0) -> SyncQueueMessage | None:
        deadline = time.monotonic() + max(timeout_seconds, 0.0)
        with self._condition:
            while not self._messages:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
            return SyncQueueMessage.loads(self._messages.popleft())

    def acquire_source_lock(self, source_id: str, owner: str) -> bool:
        with self._condition:
            self._purge_expired_lock(source_id)
            current = self._locks.get(source_id)
            if current is not None:
                return current[0] == owner
            self._locks[source_id] = (owner, time.monotonic() + self._lock_ttl_seconds)
            return True

    def release_source_lock(self, source_id: str, owner: str) -> None:
        with self._condition:
            current = self._locks.get(source_id)
            if current is not None and current[0] == owner:
                self._locks.pop(source_id, None)

    def get_source_lock_owner(self, source_id: str) -> str | None:
        with self._condition:
            self._purge_expired_lock(source_id)
            current = self._locks.get(source_id)
            return current[0] if current is not None else None

    def _purge_expired_lock(self, source_id: str) -> None:
        current = self._locks.get(source_id)
        if current is None:
            return
        _, expires_at = current
        if expires_at is not None and expires_at <= time.monotonic():
            self._locks.pop(source_id, None)


class RedisSyncQueue:
    def __init__(self, client: Any, *, queue_name: str, lock_ttl_seconds: int = 1800) -> None:
        self._client = client
        self._queue_name = queue_name
        self._lock_ttl_seconds = max(lock_ttl_seconds, 1)

    def enqueue(self, message: SyncQueueMessage) -> None:
        self._client.rpush(self._queue_name, message.dumps())

    def dequeue(self, timeout_seconds: float = 1.0) -> SyncQueueMessage | None:
        timeout = max(int(timeout_seconds), 1)
        result = self._client.blpop(self._queue_name, timeout=timeout)
        if result is None:
            return None
        _, payload = result
        return SyncQueueMessage.loads(payload)

    def acquire_source_lock(self, source_id: str, owner: str) -> bool:
        return bool(
            self._client.set(
                self._lock_key(source_id),
                owner,
                nx=True,
                ex=self._lock_ttl_seconds,
            )
        )

    def release_source_lock(self, source_id: str, owner: str) -> None:
        lock_key = self._lock_key(source_id)
        if self._client.get(lock_key) == owner:
            self._client.delete(lock_key)

    def get_source_lock_owner(self, source_id: str) -> str | None:
        return self._client.get(self._lock_key(source_id))

    def _lock_key(self, source_id: str) -> str:
        return f"{self._queue_name}:lock:{source_id}"


def build_sync_queue(settings: Settings) -> SyncQueue:
    if not settings.redis_url:
        return InMemorySyncQueue(lock_ttl_seconds=settings.sync_lock_ttl_seconds)

    try:
        client = create_redis_client(settings)
    except Exception as exc:
        logger.warning("failed to build redis sync queue, fallback to inmemory: %s", exc)
        return InMemorySyncQueue(lock_ttl_seconds=settings.sync_lock_ttl_seconds)

    return RedisSyncQueue(
        client,
        queue_name=f"{settings.app_name}:sync-jobs",
        lock_ttl_seconds=settings.sync_lock_ttl_seconds,
    )
