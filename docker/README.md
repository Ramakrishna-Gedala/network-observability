# docker/

**What lives here:** Shared Docker assets — the `.env.example` template, any reusable base-image fragments, and network/volume helpers referenced by the root `docker-compose.yml`.

**Why it exists:** Centralizes cross-service Docker concerns so individual service folders stay focused on their own code and config.

**How it connects to the next stage:** Consumed by the root `docker-compose.yml`, which in turn brings up every other folder's service on the shared `netwatch-net` bridge network.
