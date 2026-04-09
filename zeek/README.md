# zeek/

**What lives here:** Zeek IDS configuration, custom policy scripts, the container Dockerfile, and runtime log output under `logs/`. Sample PCAP files for offline replay live under `pcap/`.

**Why it exists:** Zeek is the traffic-capture brain of NetWatch. It observes a network interface (or replays a PCAP) and produces structured, protocol-aware logs (`conn.log`, `dns.log`, `http.log`, `ssl.log`) in JSON.

**How it connects to the next stage:** Filebeat (see [../filebeat/](../filebeat/)) tails the JSON files Zeek writes to `logs/` and publishes each line to the appropriate Kafka topic (`zeek-conn`, `zeek-dns`, `zeek-http`). Zeek never talks to Kafka directly — the file-tail boundary keeps Zeek simple and lets Filebeat handle retries and backpressure.

## Offline replay with a sample PCAP

1. Download a sample PCAP from [malware-traffic-analysis.net](https://www.malware-traffic-analysis.net) (or any public source).
2. Place it at `./zeek/pcap/capture.pcap`.
3. Restart the container: `docker compose restart zeek`.

The entrypoint detects the file and replays it in a 30-second loop so Grafana always has fresh data to chart.

## Live capture

If no `capture.pcap` is present, the container attempts `zeek -i eth0 local` on the container's network interface.

## Verifying logs

```
docker exec -it netwatch-zeek tail -f /logs/conn.log
```

You should see one JSON object per connection. If nothing appears, check that Zeek is actually reading packets (`docker logs netwatch-zeek`).
