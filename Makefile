# Makefile — Release Readiness Results (RRR)
# Runs the full quality gate (lint + type + test) via the project .venv.
# Requires: GNU Make + Git for Windows (sh.exe on PATH).
# Alternative: use make.ps1 for PowerShell-native usage without GNU Make.

PYTHON = .venv/Scripts/python.exe
RUFF   = .venv/Scripts/ruff.exe

.PHONY: lint type test fix check all

lint:
	$(RUFF) check src tests
	$(RUFF) format --check src tests

type:
	$(PYTHON) -m mypy src

test:
	$(PYTHON) -m pytest

fix:
	$(RUFF) format src tests
	$(RUFF) check --fix src tests

check: lint type test

all: check
