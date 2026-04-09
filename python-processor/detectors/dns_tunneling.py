"""DNS tunneling heuristic detector."""
from __future__ import annotations

import time
from typing import Any

from .base_detector import BaseDetector


class DnsTunnelingDetector(BaseDetector):
    alert_type = "dns_tunneling_suspect"

    def __init__(self, max_name_length: int = 50, max_subdomains: int = 4) -> None:
        self.max_name_length = max_name_length
        self.max_subdomains = max_subdomains

    def inspect(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        query = event.get("query")
        if not query:
            return []

        length = len(query)
        subdomain_count = query.count(".")

        if length <= self.max_name_length and subdomain_count <= self.max_subdomains:
            return []

        return [
            {
                "alert_type": self.alert_type,
                "src_ip": event.get("src_ip"),
                "query": query,
                "query_length": length,
                "subdomain_count": subdomain_count,
                "severity": "medium",
                "ts": time.time(),
            }
        ]
