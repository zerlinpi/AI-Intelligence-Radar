PYTHON=python

.PHONY: test check run

test:
	pytest -v --tb=short

check:
	$(PYTHON) -m app.cli check

run:
	$(PYTHON) -m app.cli
