SHELL := /bin/bash

# Paths (Makefile lives at repo root)
ROOT_DIR := $(shell pwd)
BACKEND_DIR := $(ROOT_DIR)

# Prefer repo venv's python if available; fallback to python3/python
PY := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; \
		elif command -v python3 >/dev/null 2>&1; then echo python3; \
		else echo python; fi)

.PHONY: help run run-prod check install venv311 seed seed_ids9_tm seed_library_r2

help:
	@echo "Targets disponibles:"
	@echo "  make run        - Ejecuta el backend con reload (desarrollo)"
	@echo "  make run-prod   - Ejecuta el backend sin reload (producción local)"
	@echo "  make check      - Verifica /health y /ping en el backend"
	@echo "  make install    - Instala dependencias del backend"
	@echo "  make venv311    - Crea un .venv con Python 3.11"
	@echo "  make seed_ids9_tm - Ejecuta script de seed académico de ejemplo"
	@echo "  make seed_library_r2 DIR=./assets/library PREFIX=formats/ - Sube a R2 y guarda URL"

run:
	@PYTHON=$(PY) bash scripts/run_backend.sh

run-prod:
	@RELOAD=false PYTHON=$(PY) bash scripts/run_backend.sh

# Prefix de la API (por defecto /api). Se puede sobreescribir: make check API_PREFIX=/api
API_PREFIX ?= /api

check:
	@echo "Chequeando backend en http://127.0.0.1:8000$(API_PREFIX)"
	@code=$$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000$(API_PREFIX)/health"); \
	 if [ "$$code" = "200" ]; then echo "OK  /health"; else echo "FAIL /health ($$code)"; exit 1; fi
	@code=$$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000$(API_PREFIX)/ping"); \
	 if [ "$$code" = "200" ]; then echo "OK  /ping"; else echo "FAIL /ping ($$code)"; exit 1; fi

install:
	@$(PY) -m pip install -U pip
	@$(PY) -m pip install -r "$(BACKEND_DIR)/requirements.txt"

# Create a Python 3.11 venv at repo root
venv311:
	@which python3.11 >/dev/null || (echo "python3.11 not found. Install it (e.g., brew install python@3.11)" && exit 1)
	@python3.11 -m venv .venv
	@echo "Run: source .venv/bin/activate"

seed:
	@echo "No default seed script. Use 'make seed_ids9_tm' or run the script directly."

seed_ids9_tm:
	@PYTHONPATH="$(BACKEND_DIR)" $(PY) "$(BACKEND_DIR)/scripts/seed_ids9_tm_2025II.py"

seed_library_r2:
	@if [ -z "$(DIR)" ]; then echo "Usa: make seed_library_r2 DIR=/ruta [PREFIX=dir/]" && exit 1; fi
	@PYTHONPATH="$(BACKEND_DIR)" $(PY) "$(BACKEND_DIR)/scripts/seed_library_to_r2.py" "$(DIR)" --prefix="$(PREFIX)"
