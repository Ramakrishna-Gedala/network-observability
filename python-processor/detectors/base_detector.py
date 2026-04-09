"""Abstract anomaly detector base class."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseDetector(ABC):
    """A detector inspects an enriched event and optionally yields alerts.

    Detectors are intentionally stateless at the interface level — any
    sliding-window / counter state lives as instance attributes on the
    subclass. Implementations must be safe to call from a single asyncio
    task (no cross-task locking required).
    """

    alert_type: str = "base"

    @abstractmethod
    def inspect(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Return zero or more alert dicts for this event."""
        raise NotImplementedError
