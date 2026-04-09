"""High-volume (per-source-IP rate) detector."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from .base_detector import BaseDetector


class HighVolumeDetector(BaseDetector):
    alert_type = "high_volume"

    def __init__(self, threshold_per_minute: int, window_seconds: int = 60) -> None:
        self.threshold = threshold_per_minute
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._last_alert_at: dict[str, float] = {}
        self._alert_cooldown = 30.0  # seconds

    def inspect(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        src_ip = event.get("src_ip")
        if not src_ip:
            return []

        now = time.time()
        bucket = self._events[src_ip]
        bucket.append(now)

        # evict anything older than the window
        cutoff = now - self.window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        count = len(bucket)
        if count < self.threshold:
            return []

        # cooldown so we don't fire continuously for the same IP
        last = self._last_alert_at.get(src_ip, 0.0)
        if now - last < self._alert_cooldown:
            return []
        self._last_alert_at[src_ip] = now

        severity = "high" if count > self.threshold * 2 else "medium"
        return [
            {
                "alert_type": self.alert_type,
                "src_ip": src_ip,
                "count": count,
                "window_seconds": self.window,
                "severity": severity,
                "ts": now,
            }
        ]
