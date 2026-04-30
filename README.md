# NetWatch — Network Observability Platform

NetWatch is an end-to-end, Dockerized network observability stack: Zeek captures traffic, Kafka buffers it, a Python/FastAPI processor enriches and scores every event, OpenSearch stores it, and Grafana + a React operator dashboard visualize it.

> 👋 **New here? Read [docs/LEARN.md](docs/LEARN.md) first.** It's a 30-minute end-to-end walkthrough of every component, what it does, why it exists, and how to follow a single packet through the entire pipeline. This README is the operator runbook; LEARN.md is the project tour.

## Architecture

```
  +----------+     +----------+     +-------+     +-------------------+
  |  Zeek    | --> | Filebeat | --> | Kafka | --> |  Python Processor |
  |  (IDS)   |     |  (ship)  |     |       |     |  FastAPI+consumers|
  +----------+     +----------+     +-------+     +---------+---------+
       ^                                              |     |     |
       |                                              v     v     v
   pcap/iface                                   OpenSearch  OTEL  Postgres
                                                    |        |
                                                    v        v
                                                 Grafana  (metrics)
                                                    ^
                                                    |
                                             React Operator UI
                                             (via FastAPI /api)
```

---

## 1. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| **Docker Desktop** | 24+ | With Compose v2 (bundled). Allocate **at least 6 GB RAM** in *Settings → Resources*; OpenSearch alone wants ~1 GB. |
| **GNU Make** | any | On Windows, install [Git for Windows](https://git-scm.com/download/win) — it ships `make` and `bash`. |
| **bash** | any | Required by the Makefile recipes. Git Bash / WSL / MSYS all work. |
| **curl** | any | Used by `make pcap-demo` to fetch a sample PCAP. |
| **Python 3.11+** *(optional)* | — | Only needed locally if you want to run the e2e tests outside Docker. |

> ⚠️ **Windows users:** run `make` from **Git Bash** (or WSL), **not** `cmd.exe`. The Makefile pins `SHELL := bash` but `make` itself still has to find bash on `PATH`.

---

## 2. One-time setup

```bash
# 1. Clone the repo
git clone <repo-url> netwatch
cd netwatch

# 2. Copy the env template (edit secrets if you want; defaults are fine for dev)
cp .env.example .env

# 3. Build images and start every container
make up

# 4. Create the Kafka topics (zeek-conn / zeek-dns / zeek-http / zeek-alerts)
make topics

# 5. Feed the pipeline some demo traffic (downloads a small public PCAP)
make pcap-demo

# 6. Run the end-to-end tests to verify everything is wired up
make test
```

After `make up` finishes, give the stack ~30 seconds for healthchecks to settle, then check status:

```bash
docker compose ps
```

You want to see every service in **`Up`** or **`Up (healthy)`** state. If anything is restarting, jump to [Troubleshooting](#7-troubleshooting).

---

## 3. Service URLs

| Service                | URL                              | Default credentials      |
|------------------------|----------------------------------|--------------------------|
| React operator UI      | http://localhost:3000            | none                     |
| FastAPI processor docs | http://localhost:8000/docs       | none                     |
| Grafana                | http://localhost:3001            | `admin` / `admin`        |
| OpenSearch Dashboards  | http://localhost:5601            | none (security disabled) |
| Kafka UI               | http://localhost:8090            | none                     |
| OpenSearch REST        | http://localhost:9200            | none                     |
| OTEL Prometheus output | http://localhost:8889/metrics    | none                     |

### Full port reference

| Port  | Service               |
|-------|-----------------------|
| 3000  | Frontend (React)      |
| 3001  | Grafana               |
| 4317  | OTEL OTLP gRPC        |
| 4318  | OTEL OTLP HTTP        |
| 5432  | Postgres              |
| 5601  | OpenSearch Dashboards |
| 8000  | Python processor API  |
| 8090  | Kafka UI              |
| 8889  | OTEL Prometheus       |
| 9092  | Kafka                 |
| 9200  | OpenSearch REST       |

---

## 4. Validating each service individually

After the demo PCAP has been replayed at least once (give it ~60 seconds after `make pcap-demo`), walk through each service and confirm it's healthy. Each section has a **command-line check** and a **browser check**.

### 4.1 Zeek

**What it does:** Reads `zeek/pcap/capture.pcap` (or sniffs `eth0`) and writes JSON logs to `zeek/logs/`.

**CLI check:**
```bash
# logs should be present and growing
ls -la zeek/logs/
docker exec -it netwatch-zeek tail -n 3 /logs/conn.log
```
You should see one JSON object per line in `conn.log`. If the file doesn't exist yet, wait 30s — Zeek rotates every 60s and emits the file on rotation.

**Browser check:** N/A (file output only).

---

### 4.2 Filebeat

**What it does:** Tails Zeek's JSON logs and publishes each line to the matching Kafka topic.

**CLI check:**
```bash
docker logs netwatch-filebeat --tail 30
# look for: "Connection to broker..." and "Harvester started for paths: [/zeek/logs/conn.log]"
```
There should be **no** `ERROR` entries about Kafka connection failures. If you see them, Kafka isn't healthy yet.

**Browser check:** N/A (use Kafka UI in the next step to confirm messages landed).

---

### 4.3 Kafka & Kafka UI

**What it does:** Buffers per-protocol topics for downstream consumers.

**CLI check:**
```bash
# list topics
docker exec netwatch-kafka kafka-topics --bootstrap-server kafka:9092 --list
# expected: zeek-alerts, zeek-conn, zeek-dns, zeek-http (plus internal __consumer_offsets)

# peek at one message from zeek-conn
docker exec netwatch-kafka kafka-console-consumer \
  --bootstrap-server kafka:9092 \
  --topic zeek-conn --from-beginning --max-messages 1
```

**Browser check:** Open <http://localhost:8090>, click *Topics*. You should see the four `zeek-*` topics, each with a non-zero message count once Filebeat has shipped events.

---

### 4.4 Python processor (FastAPI)

**What it does:** Consumes Kafka, enriches and scores each event, writes to OpenSearch, exposes a control-plane API.

**CLI check:**
```bash
# liveness
curl -s http://localhost:8000/health
# {"status":"ok"}

# pipeline throughput counters
curl -s http://localhost:8000/api/stats | jq
# {
#   "topics": { "zeek-conn": {"ok": 142}, "zeek-dns": {"ok": 31}, ... },
#   "consumers": { "zeek-conn": {"paused": false, "running": true}, ... }
# }

# Prometheus metrics
curl -s http://localhost:8000/metrics | grep events_processed_total | head
```

**Browser check:** Open <http://localhost:8000/docs> — the Swagger UI should list `/health`, `/api/stats`, `/api/alerts`, `/api/search`, `/api/config`, `/api/consumers/{topic}/pause|resume`, and `/api/webhooks/alert`. Click "Try it out" on `/api/stats` and execute it.

**Fire a synthetic alert** to make sure the publish path works end-to-end:
```bash
curl -X POST http://localhost:8000/api/webhooks/alert \
  -H 'content-type: application/json' \
  -d '{"alert_type":"smoketest","severity":"high","src_ip":"10.0.0.99","ts": 0}'
```

---

### 4.5 OpenSearch

**What it does:** Stores enriched events and alerts in date-stamped indices.

**CLI check:**
```bash
# cluster health (status should be "green" or "yellow" — "yellow" is normal for single-node)
curl -s http://localhost:9200/_cluster/health | jq

# all NetWatch indices
curl -s "http://localhost:9200/_cat/indices/netwatch-*?v"

# count of conn events today
curl -s "http://localhost:9200/netwatch-conn-*/_count" | jq

# look at a single enriched document — it should have ip_classification populated
curl -s "http://localhost:9200/netwatch-conn-*/_search?size=1&pretty"
```

**Browser check:** Open <http://localhost:5601> (OpenSearch Dashboards) → *Stack Management → Index Patterns → Create index pattern* → `netwatch-conn-*` → choose `@timestamp`. Then *Discover* to browse events.

---

### 4.6 OpenTelemetry Collector

**What it does:** Scrapes the Python processor's `/metrics` endpoint and re-exposes the data on port 8889 for Grafana to scrape.

**CLI check:**
```bash
curl -s http://localhost:8889/metrics | grep netwatch_events_processed_total
```
You should see one line per `(topic, status)` label combo.

**Browser check:** Open <http://localhost:8889/metrics> directly — it's a plain Prometheus exposition page.

---

### 4.7 Grafana

**What it does:** Visualizes OpenSearch event data and processor metrics; runs alert rules.

**CLI check:**
```bash
curl -s -u admin:admin http://localhost:3001/api/datasources | jq '.[].name'
# "NetWatch-OpenSearch"
# "NetWatch-Prometheus"
```

**Browser check — logging in:**

1. Open <http://localhost:3001/login>.
2. Enter the default credentials:

   | Field    | Value   |
   |----------|---------|
   | Username | `admin` |
   | Password | `admin` |

   These come from `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` in [.env.example](.env.example). If you edited `.env`, use whatever you set there.
3. Grafana will immediately prompt you to set a new password. For local dev, click **Skip** at the bottom of the form. For anything beyond local dev, set a real password.
4. Once inside, navigate to *Dashboards → NetWatch → NetWatch Overview*. You should see eight panels populating with data within ~10 seconds.
5. Navigate to *Alerting → Alert rules* and confirm the three NetWatch rules are listed: `High Volume IP Detected`, `Port Scan Detected`, `DNS Tunneling Pattern Detected`.

**Forgot/changed the password?** Reset it from inside the container:
```bash
docker exec -it netwatch-grafana grafana cli admin reset-admin-password admin
```

---

### 4.8 Postgres

**What it does:** Reserved for stateful control-plane data (config overrides, audit log). Not in the hot event path.

**CLI check:**
```bash
docker exec -it netwatch-postgres psql -U netwatch -d netwatch -c '\dt'
# (no tables yet — that's expected)
docker exec -it netwatch-postgres pg_isready -U netwatch
# /var/run/postgresql:5432 - accepting connections
```

---

### 4.9 React operator dashboard

**What it does:** Operator-facing UI on top of the FastAPI control plane.

**CLI check:**
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000
# 200
```

**Browser check:** Open <http://localhost:3000>.
- **Overview** — four summary cards + recent alerts feed (auto-refreshes every 5s).
- **Alerts** — table of recent alerts; click a row to expand the full JSON.
- **Explorer** — pick `conn`/`dns`/`http`, type `*` (or any Lucene query), click *Search*.
- **Settings** — change the alert threshold and pause/resume consumers.

The pipeline status pill in the sidebar should be **GREEN**.

---

## 5. End-to-end test

```bash
make test
```

This runs `tests/e2e/test_pipeline.py`, which validates: Zeek logs exist, Kafka topics have messages, OpenSearch has enriched documents, the processor responds on `/health` and `/api/stats`, and a synthetic alert can be fired through the webhook.

If any test fails, the output points at the broken stage — start your debugging at the **earliest** failing service in the pipeline order: Zeek → Filebeat → Kafka → Processor → OpenSearch.

---

## 6. Day-to-day operations

```bash
make logs                       # tail all container logs
docker compose logs -f zeek     # tail one service
docker compose restart python-processor   # restart one service
make down                       # stop and remove containers + volumes
make reset                      # full rebuild from scratch
```

---

## 7. Troubleshooting

### "I opened all the URLs but I don't see anything"

This is the most common first-run issue. **Zeek won't produce any logs until you give it traffic**, and the only way to feed it traffic in this dev setup is `make pcap-demo`. The URLs themselves don't need any post-launch configuration — Grafana datasources, dashboards, OpenSearch index templates, and Kafka topics are all auto-provisioned.

Walk this checklist in order. **Stop at the first step that fails — that's where the break is.**

#### Step 1 — Confirm the PCAP exists

```bash
ls -la zeek/pcap/
```

If `capture.pcap` is missing, that's the problem:

```bash
make pcap-demo
```

Then wait ~60 seconds. Zeek replays the file in a 30-second loop and rotates logs every 60 seconds.

#### Step 2 — Confirm Zeek is running and writing logs

```bash
docker compose ps zeek
docker logs netwatch-zeek --tail 30
```

You should see lines like `[zeek] replaying /pcap/capture.pcap`. Then:

```bash
ls -la zeek/logs/
```

After ~60 seconds you should see at least `conn.log` (and probably `dns.log`, `http.log` depending on what's in the PCAP). If `zeek/logs/` is empty, Zeek is failing — check `docker logs netwatch-zeek` for the error.

#### Step 3 — Confirm Filebeat shipped events to Kafka

```bash
docker logs netwatch-filebeat --tail 30
```

Look for `Harvester started for paths: [/zeek/logs/conn.log]`. Then peek at the Kafka topic directly:

```bash
docker exec netwatch-kafka kafka-console-consumer \
  --bootstrap-server kafka:9092 \
  --topic zeek-conn --from-beginning --max-messages 1 --timeout-ms 5000
```

If you see a JSON line printed, Filebeat → Kafka is healthy.

#### Step 4 — Confirm the processor wrote to OpenSearch

```bash
curl -s "http://localhost:9200/_cat/indices/netwatch-*?v"
```

You should see at least `netwatch-conn-YYYY.MM.DD` with `docs.count` > 0. Then check the processor's own counters:

```bash
curl -s http://localhost:8000/api/stats
```

`topics` should show `events_processed_total` counts > 0.

#### Step 5 — Open Grafana

Once OpenSearch has documents, go to <http://localhost:3001> → *Dashboards → NetWatch → NetWatch Overview*. The panels refresh every 10 seconds.

**If Grafana panels still say "No Data" even though OpenSearch has docs**, the cause is almost always the time range. The dashboard defaults to "Last 1 hour", but the events carry the `ts` field from when the PCAP was originally recorded — which could be years ago. Two fixes:

- **Top right of the dashboard → time range picker → "Last 5 years"** (or any range that covers the PCAP's recording date), or
- Use OpenSearch Dashboards at <http://localhost:5601> instead — *Discover* doesn't apply a default time window.

#### One-shot diagnostic

To check every stage at once:

```bash
echo "=== zeek/pcap ===" && ls -la zeek/pcap/ && \
echo "=== zeek/logs ===" && ls -la zeek/logs/ && \
echo "=== kafka topics ===" && docker exec netwatch-kafka kafka-topics --bootstrap-server kafka:9092 --list && \
echo "=== opensearch indices ===" && curl -s "http://localhost:9200/_cat/indices/netwatch-*?v" && \
echo "=== processor stats ===" && curl -s http://localhost:8000/api/stats
```

The first empty section in the output tells you which stage is broken.

### Other common issues

1. **`make pcap-demo` fails with "all mirrors failed".** Network blocked or all sample URLs moved. Drop *any* small `.pcap` file at `zeek/pcap/capture.pcap` and run `docker compose restart zeek`.
2. **Zeek writes no logs.** No live traffic and no PCAP — fix per #1, then `docker exec -it netwatch-zeek tail -f //logs/conn.log` (note the double slash, see issue #10).
3. **Kafka UI shows zero messages.** Check Filebeat logs: `docker logs netwatch-filebeat`. The most common cause is Kafka not being healthy when Filebeat started — `docker compose restart filebeat` after Kafka reports healthy.
4. **OpenSearch container OOMKilled.** Bump Docker Desktop's memory to at least 6 GB (*Settings → Resources*).
5. **`/api/alerts` returns empty.** The `netwatch-alerts` index is created on first write. Fire a test alert with the `curl` command in section 4.4.
6. **Processor can't connect to Kafka.** Inside the container, the bootstrap must be `kafka:9092`, **not** `localhost:9092`. Check `.env`.
7. **Grafana dashboard panels show "No Data".** See the time-range fix in Step 5 above. If the time range is correct and OpenSearch still has no docs, walk steps 1–4.
8. **Windows: `make: *** [Makefile:NN: ...] Error 1`.** You're running `make` from `cmd.exe` instead of Git Bash. Open Git Bash and re-run.
9. **Zeek entrypoint logs `/opt/zeek/bin/zeek: No such file or directory`.** This was an old bug — the upstream `zeek/zeek:lts` image puts the binary on `PATH` but not at `/opt/zeek/bin/zeek`. Fixed by calling `zeek` by name in [zeek/entrypoint.sh](zeek/entrypoint.sh). If you ever swap base images and hit this again: `docker exec netwatch-zeek which zeek` will tell you the real path.
10. **Git Bash on Windows mangles paths starting with `/`.** Symptom: `docker exec netwatch-zeek tail /logs/conn.log` errors with `cannot open 'C:/Tools/Git/logs/conn.log'`. Cause: MSYS auto-converts `/logs/...` into a Windows path before passing it to Docker. **Workarounds:**
    - Double the leading slash: `docker exec netwatch-zeek tail //logs/conn.log`
    - Disable conversion for the command: `MSYS_NO_PATHCONV=1 docker exec netwatch-zeek tail /logs/conn.log`
    - Or just read the host-mounted file: `tail zeek/logs/conn.log`
11. **PCAP timestamps are years old → Grafana panels stay empty.** This is the most common "I see no data" cause. Sample PCAPs (like the appneta tcpreplay test PCAP) were recorded in 2010 — Zeek faithfully preserves the original `ts` field, so all events land in OpenSearch with a timestamp from 2010. Grafana's default time range is "Last 1 hour", which hides them. **Fix:** click the time picker (top right of any dashboard) → "Last 5 years" or "Last 20 years". OpenSearch Dashboards' *Discover* view doesn't apply this filter, so it's a faster sanity check.
12. **Docker Compose warning: `the attribute 'version' is obsolete`.** Harmless. The `version: "3.9"` line at the top of `docker-compose.yml` is no longer used by Compose v2 — already removed in this repo. If you cloned an older copy, just delete the `version:` line.
13. **Zeek picks "live capture" mode and produces no logs.** The entrypoint checks for `zeek/pcap/capture.pcap` **once at container start**. If the file wasn't there at startup, Zeek went into `zeek -i eth0` mode and is sniffing an empty bridge interface. Drop the PCAP into place, then `docker compose restart zeek`. The fix: always run `make pcap-demo` *before* (or restart Zeek after) putting a PCAP in `zeek/pcap/`.
14. **"Why is `dns.log` named `dns.2010-07-07-03-16-20.log`?"** Zeek rotates logs and renames the rotated copy with the timestamp from the events inside it. The rotated file is the historical batch; the un-suffixed `dns.log` is the current open file Filebeat is tailing. Both are valid Zeek output.
15. **Filebeat reads the old rotated logs once, then stops.** Expected. Filebeat's `filestream` input tracks per-file inode + offset. Once it has read a rotated file end-to-end it won't re-read it, even if you restart Filebeat — by design. To force a re-read for testing, delete `data/registry/filebeat/` inside the Filebeat container or `docker compose down -v filebeat`.

---

## 8. Pro tips and gotchas (the things experienced operators wish they'd known on day one)

These aren't bugs — they're recurring "huh, that's weird" moments. Read them once and you'll save yourself an hour of debugging later.

### About time

- **Zeek's `ts` is the event time, not the ingestion time.** When you replay a 2010 PCAP, every doc in OpenSearch has a 2010 timestamp. Always think "what time range will my dashboard need?" before debugging "no data".
- **Grafana time ranges are sticky per dashboard.** If you set "Last 5 years" once, it persists for that dashboard until you change it again.
- **Filebeat normalizes `ts` to `@timestamp`** via the timestamp processor in [filebeat/filebeat.yml](filebeat/filebeat.yml). Both fields exist on every doc — `ts` is Zeek's epoch float, `@timestamp` is the ISO date Grafana sorts on.
- **Wall-clock vs event-clock for detectors.** The Python detectors (`HighVolumeDetector`, `PortScanDetector`) use `time.time()` (wall clock) for windowing, **not** the event's `ts`. This means detectors work fine on live traffic but won't fire correctly on PCAP replay — replayed events all arrive within seconds, blowing through any rate threshold instantly. To test detection logic on a PCAP, lower `ALERT_THRESHOLD_REQUESTS_PER_MINUTE` to something like `5` in `.env` and restart the processor.

### About data flow

- **Zeek logs are buffered in memory and only flush on rotation.** Default rotation is every 60 seconds (set in [zeek/config/local.zeek](zeek/config/local.zeek)). So after a fresh start you may wait up to a minute before *any* JSON appears. If you need it faster for testing, lower `Log::default_rotation_interval` and rebuild Zeek.
- **Filebeat scan frequency is 5 seconds.** Even after Zeek writes a file, Filebeat takes up to 5s to notice it (set in [filebeat/filebeat.yml](filebeat/filebeat.yml) `scan_frequency: 5s`).
- **The Python processor batches OpenSearch writes.** It accumulates 100 events per topic before bulk-indexing (or flushes every 5s, whichever comes first — see [opensearch_exporter.py](python-processor/exporters/opensearch_exporter.py)). If you injected only 10 events you'll wait ~5s before they appear in OpenSearch.
- **End-to-end latency in dev:** Zeek rotation (≤60s) + Filebeat scan (≤5s) + processor batch flush (≤5s) + Grafana refresh (10s) = up to **80 seconds** worst case. Be patient on your first `make up`.
- **Kafka topic auto-creation is enabled** (see `docker-compose.yml`), so even if you forget `make topics`, the topics will be created with default settings the first time something writes to them. `make topics` exists to give them the *correct* partition / retention config.

### About Docker on Windows

- **Always use Git Bash, not `cmd.exe` or PowerShell**, for `make` and any command involving paths. The Makefile pins `SHELL := bash` but the parent `make` process still has to find bash.
- **MSYS path conversion is the #1 footgun on Windows.** See troubleshooting #10. Burn it into your reflexes: any `docker exec` command that takes a `/path/inside/container` argument needs `//path/inside/container` in Git Bash.
- **Volume mounts with Windows paths can be slow** for high-throughput files. Not an issue here (Zeek logs are tiny), but be aware if you scale up.
- **Docker Desktop memory matters.** OpenSearch alone is pinned to 512 MB heap and wants ~1 GB resident. Plus Kafka, Grafana, the processor, the frontend, postgres, OTEL — give Docker at least 6 GB in *Settings → Resources*.

### About each component's defaults

- **Zeek runs as a non-root `netwatch` user** inside the container. If you mount a PCAP file with restrictive permissions on the host, the container may not be able to read it. The default `make pcap-demo` PCAP is world-readable so this never bites you in dev.
- **OpenSearch has security disabled** in this dev setup (`DISABLE_SECURITY_PLUGIN=true`). Do **not** copy this config to production. Real deployments need TLS, role-based access, and a real admin password.
- **Grafana ships with a static `admin/admin` password.** Same caveat — fine for dev, must be changed for anything else.
- **The frontend ships built and served by `serve`** (a tiny static-file server). It's not running Vite dev mode, so hot-reload doesn't work; rebuild with `docker compose up -d --build frontend` after changes, or run Vite directly on the host (`cd frontend && npm install && npm run dev`).
- **Postgres is reserved space, not used yet.** The processor opens no DB connection. It exists for future control-plane state (config overrides, audit log).
- **The `netwatch-alerts` index has no template applied** by default — its mapping is dynamic. The other three (`conn`, `dns`, `http`) use strict mappings from [opensearch/index-templates.json](opensearch/index-templates.json).

### About debugging

- **Always check the earliest broken stage first.** A "no data in Grafana" symptom can have its root cause in Zeek (no PCAP), Filebeat (Kafka unhealthy), the processor (parsing error), OpenSearch (mapping rejection), or Grafana (wrong time range). Walking the pipeline top-down is dramatically faster than poking at Grafana.
- **`docker compose ps` is your best friend.** It tells you the health status of every service in one shot. If anything is `unhealthy` or `restarting`, fix that first.
- **`docker logs <container> --tail 50`** is the right amount of context for almost everything. Jumping straight to `--tail 1000` buries the signal.
- **Use Kafka UI (<http://localhost:8090>) as a non-CLI debugging surface.** You can browse messages, inspect consumer-group lag, and see exactly what Filebeat is producing.
- **OpenSearch Dashboards (<http://localhost:5601>) is more flexible than Grafana for ad-hoc queries.** Use *Discover* to walk through every doc in an index without writing a Lucene query.

### About this repo's design choices

- **Kafka sits between Zeek and the processor on purpose.** It buys us replay, backpressure, and parallelism. Direct file tail would lose all three.
- **Detection logic is in Python because it's easy to iterate on**, not because Python is fast. At >20k events/sec the enrichment hot path would need to move to Go or Rust. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the scaling story.
- **The frontend talks only to the FastAPI processor**, never directly to Kafka or OpenSearch. This is a deliberate boundary — operators get a stable HTTP contract, and the storage backend can change without touching the UI.
- **Grafana is for analytics, the React UI is for control.** They are not redundant. Grafana shows "what is happening?"; the React UI shows "what should I tune?"

### Quick command reference card

```bash
# Bring everything up
make up

# Get logs
docker compose logs -f               # all services
docker compose logs -f zeek          # one service
docker logs netwatch-zeek --tail 30  # one container, no follow

# Restart one service after changing its config
docker compose restart filebeat

# Rebuild one service after changing its Dockerfile or code
docker compose up -d --build python-processor

# Open a shell in a container
docker exec -it netwatch-processor bash    # or sh

# Inspect Kafka manually
docker exec netwatch-kafka kafka-topics --bootstrap-server kafka:9092 --list
docker exec netwatch-kafka kafka-console-consumer --bootstrap-server kafka:9092 --topic zeek-conn --from-beginning --max-messages 5 --timeout-ms 5000

# Inspect OpenSearch manually
curl -s "http://localhost:9200/_cat/indices?v"
curl -s "http://localhost:9200/netwatch-conn-*/_count"
curl -s "http://localhost:9200/netwatch-conn-*/_search?size=1&pretty"

# Tear down
make down            # remove containers + volumes
make reset           # full rebuild from scratch
```

---

## 8. Pipeline overview

1. **Zeek** watches a live interface (or replays `capture.pcap`) and produces `conn.log`, `dns.log`, `http.log`, `ssl.log` as JSON.
2. **Filebeat** tails those files and publishes each line to a per-protocol Kafka topic (`zeek-conn`, `zeek-dns`, `zeek-http`).
3. **Python processor** consumes each topic in its own consumer group, validates with Pydantic, enriches (`ip_classification`), runs detectors (high-volume, port-scan, DNS-tunneling), and bulk-indexes into date-stamped OpenSearch indices.
4. **Detectors** publish alerts back to `zeek-alerts` and into the `netwatch-alerts` OpenSearch index.
5. **Grafana** reads OpenSearch and Prometheus (via OTEL collector) to drive dashboards and alert rules.
6. **React dashboard** talks only to the FastAPI control plane (`/api/*`).

See [docs/LEARN.md](docs/LEARN.md) for the full walkthrough, [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the deep dive, and [docs/INTERVIEW_GUIDE.md](docs/INTERVIEW_GUIDE.md) for talking points.

---

## 9. Adding a new detector

1. Create a class in [python-processor/detectors/](python-processor/detectors/) that inherits from [`BaseDetector`](python-processor/detectors/base_detector.py) and implements `inspect(event) -> list[dict]`.
2. Export it from [python-processor/detectors/__init__.py](python-processor/detectors/__init__.py).
3. Instantiate it inside the relevant consumer (e.g. [ConnConsumer](python-processor/consumers/conn_consumer.py)) and call it from `process()`.
4. Publish each alert via `self._alert_publisher.publish_alert(...)` — this keeps Grafana rules and the React dashboard updated automatically.
5. Restart the processor: `docker compose restart python-processor`.
