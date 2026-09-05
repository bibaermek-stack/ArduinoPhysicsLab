"""In-memory live measurement hub: publisher/viewer fan-out and short buffer."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

SendFn = Callable[[dict], None]


class LiveHub:
    def __init__(
        self,
        *,
        max_buffer_seconds: float = 120.0,
        max_points_per_sec: float = 20.0,
    ) -> None:
        self._max_buffer_seconds = max_buffer_seconds
        self._max_points_per_sec = max_points_per_sec
        self._publishers: dict[str, SendFn] = {}
        self._viewers: dict[str, tuple[frozenset[str], SendFn]] = {}
        self._buffers: dict[str, deque[tuple[float, dict]]] = {}
        self._rate: dict[str, tuple[float, int]] = {}
        self._status: dict[str, str] = {}

    def reset(self) -> None:
        self._publishers.clear()
        self._viewers.clear()
        self._buffers.clear()
        self._rate.clear()
        self._status.clear()

    def set_publisher(self, account_id: str, send: SendFn | None) -> SendFn | None:
        previous = self._publishers.get(account_id)
        if send is None:
            self._publishers.pop(account_id, None)
            self._emit_presence(account_id, state="offline", experiment_id="")
        else:
            self._publishers[account_id] = send
        return previous

    def add_viewer(self, viewer_id: str, watch_ids: frozenset[str], send: SendFn) -> None:
        self._viewers[viewer_id] = (watch_ids, send)

    def remove_viewer(self, viewer_id: str) -> None:
        self._viewers.pop(viewer_id, None)

    def publish_samples(
        self,
        account_id: str,
        *,
        experiment_id: str,
        session_id: str,
        points: list[dict],
    ) -> int:
        remaining = self._rate_remaining(account_id)
        take = min(remaining, 50, len(points))
        if take <= 0:
            return 0
        accepted = points[:take]
        self._rate_consume(account_id, take)
        frame = {
            "type": "samples",
            "account_id": account_id,
            "experiment_id": experiment_id,
            "session_id": session_id,
            "points": accepted,
        }
        self._buffer_frame(account_id, frame)
        self._fanout(account_id, frame)
        return take

    def publish_status(
        self,
        account_id: str,
        *,
        state: str,
        experiment_id: str = "",
    ) -> None:
        self._status[account_id] = state
        self._emit_presence(account_id, state=state, experiment_id=experiment_id)

    def buffer_for(self, account_id: str) -> list[dict]:
        self._prune_buffer(account_id)
        buf = self._buffers.get(account_id)
        if not buf:
            return []
        return [frame for _, frame in buf]

    def publisher_state(self, account_id: str) -> str:
        if account_id not in self._publishers:
            return "offline"
        return self._status.get(account_id, "idle")

    def _rate_remaining(self, account_id: str) -> int:
        limit = int(self._max_points_per_sec)
        now = time.monotonic()
        window_start, count = self._rate.get(account_id, (now, 0))
        if now - window_start >= 1.0:
            return limit
        return max(0, limit - count)

    def _rate_consume(self, account_id: str, n: int) -> None:
        now = time.monotonic()
        window_start, count = self._rate.get(account_id, (now, 0))
        if now - window_start >= 1.0:
            self._rate[account_id] = (now, n)
        else:
            self._rate[account_id] = (window_start, count + n)

    def _prune_buffer(self, account_id: str) -> None:
        buf = self._buffers.get(account_id)
        if not buf:
            return
        cutoff = time.monotonic() - self._max_buffer_seconds
        while buf and buf[0][0] < cutoff:
            buf.popleft()

    def _buffer_frame(self, account_id: str, frame: dict) -> None:
        now = time.monotonic()
        buf = self._buffers.setdefault(account_id, deque())
        cutoff = now - self._max_buffer_seconds
        while buf and buf[0][0] < cutoff:
            buf.popleft()
        buf.append((now, frame))

    def _fanout(self, account_id: str, frame: dict) -> None:
        for watch_ids, send in self._viewers.values():
            if account_id in watch_ids:
                send(frame)

    def _emit_presence(
        self,
        account_id: str,
        *,
        state: str,
        experiment_id: str,
    ) -> None:
        frame = {
            "type": "presence",
            "account_id": account_id,
            "state": state,
            "experiment_id": experiment_id,
        }
        self._buffer_frame(account_id, frame)
        self._fanout(account_id, frame)
