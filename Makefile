.PHONY: help setup run run-module test generate-data validate import-export clean-data

help:
	@echo "Available targets:"
	@echo "  make setup        - Create venv and upgrade pip"
	@echo "  make run          - Run main Medici banking demo"
	@echo "  make run-module   - Run module entrypoint"
	@echo "  make test         - Run test suite using .venv"
	@echo "  make generate-data- Generate historical datasets in data/"
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

test:
	@test -x .venv/bin/python || (echo "Virtual environment missing. Run 'make setup' first." && exit 1)
	. .venv/bin/activate && python -m pytest -q

generate-data:
	python3 generate_historical_data.py
	python3 generate_additional_data.py

validate:
	python3 validate_transactions.py

import-export:
	python3 demo_import_export.py

clean-data:
	rm -f data/exported_transactions.csv data/exported_transactions.json
