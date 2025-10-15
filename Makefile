SHELL := /bin/bash

# Paths
ROOT_DIR := $(shell pwd)
BACKEND_DIR := AURA/aura-backend

# Prefer repo venv's python if available; fallback to python3/python
PY := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; \
		elif command -v python3 >/dev/null 2>&1; then echo python3; \
		else echo python; fi)

.PHONY: run install venv311 seed

run:
	@bash scripts/run_backend.sh

install:
	@$(PY) -m pip install -U pip
	@$(PY) -m pip install -r $(BACKEND_DIR)/requirements.txt

# Create a Python 3.11 venv at repo root
venv311:
	@which python3.11 >/dev/null || (echo "python3.11 not found. Install it (e.g., brew install python@3.11)" && exit 1)
	@python3.11 -m venv .venv
	@echo "Run: source .venv/bin/activate"

seed:
	@PYTHONPATH=$(BACKEND_DIR) $(PY) $(BACKEND_DIR)/scripts/seed.py
