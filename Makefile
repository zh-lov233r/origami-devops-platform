# 中文：常用开发命令入口，封装 lint、smoke、scenario、test、benchmark、dashboard、quality 和部署 mock 命令。
# English: Common developer command entrypoint wrapping lint, smoke, scenario, test, benchmark, dashboard, quality, and deployment mock commands.

PYTHONPATH ?= src
PYTHON ?= .venv/bin/python

.PHONY: lint smoke scenario multistep-scenario test benchmark dashboard observability observability-build quality export edge-mock audit-verify sso-dry-run staging-host-preflight staging-sso-smoke

lint:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m ruff check src tests

smoke:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main smoke

scenario:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main scenario

multistep-scenario:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main multistep-scenario

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest

benchmark:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main benchmark

dashboard:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m uvicorn origami.api.app:app --host 127.0.0.1 --port 8000

observability:
	docker compose up api prometheus grafana

observability-build:
	docker compose build api

quality: lint test scenario benchmark audit-verify

export:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main export

edge-mock:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main edge-mock

audit-verify:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main audit-verify

sso-dry-run:
	PYTHON=$(PYTHON) scripts/sso_dry_run_smoke.sh

staging-host-preflight:
	scripts/staging_host_preflight.sh

staging-sso-smoke:
	scripts/staging_sso_smoke.sh
