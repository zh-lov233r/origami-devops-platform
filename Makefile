# 中文：常用开发命令入口，封装 lint、smoke、scenario、test、benchmark、dashboard、quality 和部署 mock 命令。
# English: Common developer command entrypoint wrapping lint, smoke, scenario, test, benchmark, dashboard, quality, and deployment mock commands.

PYTHONPATH ?= src
PYTHON ?= .venv/bin/python
UV ?= .venv/bin/uv
UV_CACHE_DIR ?= artifacts/.cache/uv
PIP_AUDIT ?= .venv/bin/pip-audit
PIP_AUDIT_ARGS ?= --disable-pip --cache-dir artifacts/.cache/pip-audit

.PHONY: lint smoke scenario multistep-scenario test benchmark dashboard observability observability-build quality export edge-mock audit-verify dependency-scan artifact-backup artifact-restore sso-dry-run staging-host-preflight staging-sso-smoke staging-acceptance-report

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

dependency-scan:
	mkdir -p artifacts/security artifacts/.cache
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) export --locked --no-dev --format requirements-txt --output-file artifacts/security/requirements.txt
	$(PIP_AUDIT) --requirement artifacts/security/requirements.txt --format json --output artifacts/security/pip-audit.json $(PIP_AUDIT_ARGS)

artifact-backup:
	PYTHON=$(PYTHON) scripts/artifact_backup.sh

artifact-restore:
	PYTHON=$(PYTHON) scripts/artifact_restore.sh

sso-dry-run:
	PYTHON=$(PYTHON) scripts/sso_dry_run_smoke.sh

staging-host-preflight:
	scripts/staging_host_preflight.sh

staging-sso-smoke:
	scripts/staging_sso_smoke.sh

staging-acceptance-report:
	$(PYTHON) scripts/write_staging_acceptance_report.py
