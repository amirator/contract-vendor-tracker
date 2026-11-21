# Contract and Vendor Tracker. Run `make help` for targets.
VENV   ?= .venv
PYTHON := $(VENV)/bin/python

.PHONY: help venv demo test verify screenshots clean

help:
	@echo "make venv         create .venv and install pinned dependencies"
	@echo "make demo         run everything on the bundled SAMPLE data -> outputs/"
	@echo "make test         run the pytest suite"
	@echo "make verify       recalculate the workbook in LibreOffice and compare with Python"
	@echo "make screenshots  render docs/*.png from the real outputs (needs LibreOffice, poppler, Chrome)"
	@echo "make clean        remove outputs/ and caches"

$(PYTHON):
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip -q
	$(VENV)/bin/pip install -q -r requirements-dev.txt -c constraints.txt

venv: $(PYTHON)

demo: $(PYTHON)
	$(PYTHON) -m cvtrack demo

test: $(PYTHON)
	$(PYTHON) -m pytest -q

verify: $(PYTHON)
	$(PYTHON) -m cvtrack verify

screenshots: demo
	$(PYTHON) scripts/make_screenshots.py

clean:
	rm -rf outputs .pytest_cache **/__pycache__
