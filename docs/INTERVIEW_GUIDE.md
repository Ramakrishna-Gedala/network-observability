# NetWatch — Interview Preparation Guide

## Section 1 — The 60-second pitch

> NetWatch is a full-stack network observability platform I built end-to-end. It captures live traffic (or replays PCAPs) with Zeek, ships the structured logs through Kafka for buffering, then runs a Python/FastAPI processor that enriches every event with IP classification and runs three anomaly detectors — high-volume, port-scan, and DNS-tunneling. Enriched events land in OpenSearch, metrics flow through an OpenTelemetry collector, and Grafana plus a React operator dashboard give SOC engineers real-time visibility and alerting. The whole stack comes up with `make up` — twelve containers, one shared Docker network, zero manual glue. The interesting engineering is in the trade-offs: why Kafka between Zeek and the processor, how the detectors stay lightweight, and how the pipeline would fail first at 10 Gbps.

## Section 2 — System design questions

### Why Kafka between Zeek and the processor instead of direct file processing?

Three reasons: **buffering**, **replay**, and **independent scaling**. If the processor crashes for 30 minutes, Kafka holds the events and the processor catches up on restart — a direct file tail would drop events or, worse, silently lose the offset. Replay lets me re-run detectors against historical traffic when I tune thresholds. And because topics are partitioned per protocol, I can horizontally scale the `conn` consumer independently of `dns`, which matters because `conn.log` is typically 10x the volume.

### How would you scale this to 10 Gbps of traffic?

Four parallel moves:

1. **Zeek cluster mode.** Single-threaded Zeek tops out around 1 Gbps. I'd deploy a manager + proxy + worker nodes with PF_RING or AF_PACKET fanout, load-balancing flows by 5-tuple hash so each worker sees a consistent slice.
2. **Drop Filebeat; use Zeek's Kafka output directly.** Removes a disk round-trip and an extra process.
3. **Rewrite the hot path of the processor in Go or Rust.** Python's per-event GIL overhead becomes the bottleneck around 20k events/sec; enrichment and schema validation are the parts to port first, keeping detection logic in Python for iteration speed.
4. **Move detector state to Redis.** The in-process sliding-window counters don't survive a restart and don't share state between consumer replicas. Redis with per-IP TTL keys fixes both.

### How do you handle late-arriving or out-of-order log events?

The processor treats each event as idempotent — indexing the same doc twice is fine because OpenSearch uses `uid` as the doc ID. For detection windows, I use wall-clock time rather than event time, which tolerates small clock skew but loses accuracy under huge backlogs. A production fix is to use the `ts` field as the window key and accept a small "grace period" (e.g. 30 seconds) before sealing a window.

### What happens if the Python processor crashes mid-batch?

Offsets are committed only after a successful `process()` call (auto-commit disabled). On restart the consumer resumes from the last committed offset, so it replays the in-flight batch — idempotent indexing makes this safe. If a specific event can't be processed after 3 retries, the base consumer pushes it to `zeek-alerts` as a `processing_error` dead-letter entry and commits past it, so a single poison pill can't block the pipeline.

### How would you add authentication to this pipeline?

Layered:

- **Processor → OpenSearch**: OpenSearch security plugin, mTLS, role-based index access.
- **Kafka**: SASL/SCRAM or mTLS with ACLs on topics (`zeek-*` producer-only for Filebeat, consumer-only for processor).
- **FastAPI**: OAuth2/OIDC (Keycloak or Auth0), JWT bearer on every `/api/*` route.
- **React dashboard**: Silent login flow, access token in memory (not localStorage), refresh via HTTP-only cookie.
- **Grafana**: Proxy auth behind the same OIDC provider.

### How would you detect a zero-day exploit pattern you've never seen before?

Signatures can't by definition — you need **behavior**. Three approaches, layered:

1. **Baseline + z-score.** Build a rolling baseline of per-host request rates, protocol mixes, and destination entropy. Score new behavior against the baseline; high z-score + unusual combination fires a low-confidence alert.
2. **Beacon detection.** Periodic outbound connections with tight inter-arrival variance are a strong C2 signal; doesn't depend on knowing the specific malware.
3. **Unsupervised ML on conn.log features.** An isolation forest or autoencoder trained on "normal" flows can flag statistical outliers. Keep it low-precision and use it only to prioritize human review.

## Section 3 — Code walkthrough talking points

### Walk me through the enrichment pipeline for a single conn.log event

A JSON line hits Kafka. `ConnConsumer.process()` validates it against the Pydantic `ConnEvent` model — this gives me schema enforcement and aliasing (Zeek uses `id.orig_h`, I store `src_ip`). Then `classify_ip()` runs the source IP through an `lru_cache`-wrapped CIDR check — 10k-entry cache, stdlib `ipaddress` module, zero external calls so the hot path stays cache-friendly. The enriched doc goes into the OpenSearch buffer. Two detectors run in parallel on the same event: `HighVolumeDetector` updates a per-IP deque (minute window, 30s cooldown on duplicate alerts) and `PortScanDetector` tracks distinct destination ports per source. Any fired alert is published back to `zeek-alerts` and mirrored into the alerts index.

### How does your anomaly detection avoid false positives?

Three mechanisms. First, **cooldowns** — after an IP trips the threshold, we suppress further alerts for that IP for 30–60 seconds so a single burst doesn't spam the alerts board. Second, **thresholds are configurable** via `ALERT_THRESHOLD_REQUESTS_PER_MINUTE` so the operator can tune for their baseline. Third, **severity tiers** — the high-volume detector only fires `severity: high` when the count is 2x the threshold, so medium alerts are for triage and high alerts are for paging.

### What would you do differently in production?

- Persist detector state to Redis so restarts don't reset the sliding windows.
- Replace in-process flush loop with a managed batch writer that tracks back-pressure from OpenSearch.
- Add a real PostgreSQL-backed config store so `/api/config` writes are durable across restarts.
- Wire OIDC auth through the FastAPI and the React dashboard.
- Add Zeek Intel framework for IOC enrichment (feed in a threat-intel list, mark matching flows).
- Replace the hand-rolled dashboard JSON with a versioned IaC tool (Grafonnet or Terraform).

## Section 4 — Metrics to mention

- **Throughput:** sustained ~2–3k events/sec per topic on a laptop (single processor, 3-partition topics). Scales roughly linearly with consumer replicas until OpenSearch bulk indexing saturates.
- **End-to-end latency:** Zeek log write → Grafana dashboard refresh: ~10–15 seconds. Breakdown: Zeek rotation ≤60s in dev (5s in prod), Filebeat scan 5s, Kafka → processor <100ms, OpenSearch bulk flush ≤5s, Grafana refresh 10s.
- **Memory footprint:** Python processor ~150 MB resident, OpenSearch ~1 GB, Kafka+ZK ~800 MB, Grafana ~200 MB, everything else <100 MB each.
