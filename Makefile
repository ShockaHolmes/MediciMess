.PHONY: help setup run run-module start test generate-data transform-data serve-data run-api benford-analysis vendor-concentration duplicate-detection round-clustering validate import-export clean-data

help:
	@echo "Available targets:"
	@echo "  make setup        - Create venv and upgrade pip"
	@echo "  make run          - Run main Medici banking demo"
	@echo "  make run-module   - Run module entrypoint"
	@echo "  make start        - Start API server + UI server together"
	@echo "  make test         - Run test suite using .venv"
	@echo "  make generate-data- Generate historical datasets in data/"
	@echo "  make transform-data- Build cleaned analytics-ready transaction dataset"
	@echo "  make serve-data   - Build serving-layer analytics and API payloads"
	@echo "  make run-api      - Start the serving-layer HTTP API"
	@echo "  make benford-analysis - Run Benford's Law anomaly detection"
	@echo "  make vendor-concentration - Run vendor concentration anomaly detection"
	@echo "  make duplicate-detection - Run duplicate transaction anomaly detection"
	@echo "  make round-clustering - Run round-number clustering anomaly detection"
	@echo "  make validate     - Validate historical datasets"
	@echo "  make import-export- Run import/export demonstration"
	@echo "  make clean-data   - Remove demo export files from data/"

setup:
	python3 -m venv .venv
	. .venv/bin/activate && python3 -m pip install --upgrade pip

run:
	python3 medici-banking.py

run-module:
	python3 -m medici_banking

start:
	./start.sh

test:
	@test -x .venv/bin/python || (echo "Virtual environment missing. Run 'make setup' first." && exit 1)
	. .venv/bin/activate && python -m pytest -q

generate-data:
	python3 generate_historical_data.py
	python3 generate_additional_data.py

transform-data:
	python3 transform_transactions.py

serve-data:
	python3 transform_transactions.py
	python3 build_serving_layer.py

run-api:
	python3 pipeline_api_server.py

benford-analysis:
	python3 benford_analysis.py

vendor-concentration:
	python3 vendor_concentration_analysis.py

duplicate-detection:
	python3 duplicate_transaction_analysis.py

round-clustering:
	python3 round_number_clustering_analysis.py

validate:
	python3 validate_transactions.py

import-export:
	python3 demo_import_export.py

clean-data:
	rm -f data/exported_transactions.csv data/exported_transactions.json
