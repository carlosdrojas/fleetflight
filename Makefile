SHELL := /bin/bash
PYTHON ?= python3
VENV ?= .venv
export VENV
SUT ?= $(shell cat scripts/ci_sut.txt)
DEPTH ?= 120
INJECTIONS ?= 3
HORIZON_MS ?= 4000
OUT ?= out/check
PORT ?= 8765

.PHONY: setup test check demo demo-fast ui serve regress site-data
setup:
	@$(PYTHON) -c 'import sys; sys.exit("Python 3.12+ required") if sys.version_info < (3, 12) else None'
	$(PYTHON) -m venv "$(VENV)"
	"$(VENV)/bin/python" -m pip install -e '.[dev]'
	@bash scripts/ui.sh install

test:
	"$(VENV)/bin/python" -m pytest -q tests scripts/test_automation.py

check:
	bash scripts/check.sh "$(SUT)" "$(DEPTH)" "$(INJECTIONS)" "$(HORIZON_MS)" "$(OUT)"

demo:
	bash scripts/demo.sh

demo-fast:
	bash scripts/demo_fast.sh

regress:
	bash scripts/regress.sh

ui:
	bash scripts/ui.sh build

serve: ui
	bash scripts/serve.sh "$(PORT)"

# Export the newest out/demo.* run as the hosted site's data (ui/public/data/); commit the result.
site-data:
	"$(VENV)/bin/python" scripts/export_site.py $(OUT_DIR)
