#!/usr/bin/env bash
set -euo pipefail

PCAP_FILE="/pcap/capture.pcap"
CONFIG="/zeek-config/local.zeek"

cd /logs

if [[ -f "${PCAP_FILE}" ]]; then
    echo "[zeek] capture.pcap detected — running in offline replay loop"
    while true; do
        echo "[zeek] replaying ${PCAP_FILE}"
        /opt/zeek/bin/zeek -r "${PCAP_FILE}" "${CONFIG}" || true
        sleep 30
    done
else
    echo "[zeek] no capture.pcap — running live capture on eth0"
    exec /opt/zeek/bin/zeek -i eth0 "${CONFIG}"
fi
