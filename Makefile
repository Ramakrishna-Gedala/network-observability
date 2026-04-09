# NetWatch — dev workflow targets
#
# Force bash on Windows so the recipes (mkdir -p, if [ ... ], curl)
# don't get handed to cmd.exe. Requires Git Bash / WSL / MSYS in PATH.
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c

.PHONY: up down logs test pcap-demo topics reset

up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f

test:
	pytest tests/e2e/ -v

# Stable mirrors of small public sample PCAPs. We try them in order until one works.
# Override with: make pcap-demo PCAP_URL=https://your-host/your.pcap
PCAP_URLS ?= \
	https://github.com/appneta/tcpreplay/raw/master/test/test.pcap \
	https://github.com/automayt/ICS-pcap/raw/master/MODBUS/Modbus%20TCP%20SCADA%20%231/modbus_test_data_part1.pcap \
	https://raw.githubusercontent.com/markofu/pcaps/master/PracticalPacketAnalysis/ppa-capture-files/http_espn.pcap

pcap-demo:
	@mkdir -p zeek/pcap
	@if [ -f zeek/pcap/capture.pcap ]; then \
		echo "[pcap-demo] zeek/pcap/capture.pcap already present, skipping download"; \
	else \
		ok=0; \
		for url in $(PCAP_URLS); do \
			echo "[pcap-demo] trying $$url"; \
			if curl -fsSL "$$url" -o zeek/pcap/capture.pcap; then \
				echo "[pcap-demo] downloaded from $$url"; \
				ok=1; break; \
			fi; \
		done; \
		if [ "$$ok" != "1" ]; then \
			echo "[pcap-demo] all mirrors failed — drop your own PCAP at zeek/pcap/capture.pcap"; \
			exit 1; \
		fi; \
	fi
	docker compose restart zeek
	@echo "[pcap-demo] Zeek restarted — tail logs with: docker exec -it netwatch-zeek tail -f /logs/conn.log"

topics:
	docker compose exec kafka bash /kafka/create-topics.sh

reset:
	docker compose down -v
	docker compose up -d --build
