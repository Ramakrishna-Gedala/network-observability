# frontend/

**What lives here:** The ReactJS operator dashboard (Vite + TypeScript + Tailwind + shadcn/ui) that provides control-plane views — overview, alerts, log explorer, settings.

**Why it exists:** Grafana handles deep analytics; the operator dashboard handles day-to-day operation — pausing consumers, tuning thresholds, browsing recent alerts, and checking pipeline health at a glance.

**How it connects to the next stage:** Talks only to the [../python-processor/](../python-processor/) FastAPI over HTTP (`/api/*`). It does not touch Kafka or OpenSearch directly.
