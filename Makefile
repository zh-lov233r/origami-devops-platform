# 中文：常用开发命令入口，封装 lint、smoke、scenario、test、benchmark、quality 和部署 mock 命令。
# English: Common developer command entrypoint wrapping lint, smoke, scenario, test, benchmark, quality, and deployment mock commands.

PYTHONPATH ?= src
PYTHON ?= .venv/bin/python

.PHONY: lint smoke scenario test benchmark quality export edge-mock audit-verify

lint:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m ruff check src tests

smoke:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main smoke

scenario:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main scenario

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest

benchmark:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main benchmark

quality: lint test scenario benchmark audit-verify

export:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main export

edge-mock:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main edge-mock

audit-verify:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main audit-verify
