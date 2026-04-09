"""Horizontal port-scan detector (conn.log)."""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from .base_detector import BaseDetector


class PortScanDetector(BaseDetector):
    alert_type = "port_scan"

    def __init__(self, distinct_port_threshold: int = 20, window_seconds: int = 30) -> None:
        self.threshold = distinct_port_threshold
        self.window = window_seconds
        # src_ip -> list[(ts, dst_port)]
        self._history: dict[str, list[tuple[float, int]]] = defaultdict(list)
        self._last_alert_at: dict[str, float] = {}
        self._alert_cooldown = 60.0

    def inspect(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        src_ip = event.get("src_ip")
        dst_port = event.get("dst_port")
        if not src_ip or dst_port is None:
            return []

        now = time.time()
        history = self._history[src_ip]
        history.append((now, int(dst_port)))
        cutoff = now - self.window
        # prune
        self._history[src_ip] = [(t, p) for (t, p) in history if t >= cutoff]

        distinct_ports = {p for _, p in self._history[src_ip]}
        if len(distinct_ports) < self.threshold:
            return []

        last = self._last_alert_at.get(src_ip, 0.0)
        if now - last < self._alert_cooldown:
            return []
        self._last_alert_at[src_ip] = now

        return [
            {
                "alert_type": self.alert_type,
                "src_ip": src_ip,
                "distinct_ports": len(distinct_ports),
                "window_seconds": self.window,
                "severity": "high",
                "ts": now,
            }
        ]
