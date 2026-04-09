# NetWatch — dev workflow targets
.PHONY: up down logs test pcap-demo topics reset

up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f

test:
	pytest tests/e2e/ -v

pcap-demo:
	@echo "Drop your PCAP at zeek/pcap/capture.pcap, then:"
	docker compose restart zeek

topics:
	docker compose exec kafka bash /kafka/create-topics.sh

reset:
	docker compose down -v
	docker compose up -d --build
