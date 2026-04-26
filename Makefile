# 中文：常用开发命令入口，封装 smoke、test、benchmark、export、edge mock 和 audit verify。
# English: Common developer command entrypoint wrapping smoke, test, benchmark, export, edge mock, and audit verification.

PYTHONPATH := src
PYTHON := python3

.PHONY: smoke test benchmark export edge-mock audit-verify

smoke:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main smoke

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest

benchmark:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main benchmark

export:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main export

edge-mock:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main edge-mock

audit-verify:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m origami.cli.main audit-verify
