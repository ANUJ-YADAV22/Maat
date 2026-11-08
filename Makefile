PY ?= python3

.PHONY: install data web web-check api lint test scenarios eval-smoke eval demo ci clean

install:
	$(PY) -m pip install -e ".[dev]"

data:
	$(PY) scripts/build_data.py

web:
	cd web && npm install && npm run build

api:
	uvicorn maat.api.app:create_app --factory --reload

lint:
	ruff check src tests scripts
	ruff format --check src tests scripts

test:
	pytest tests/unit tests/integration

scenarios:
	pytest tests/scenarios; s=$$?; [ $$s -eq 0 ] || [ $$s -eq 5 ]

eval-smoke:
	$(PY) -m maat.eval.harness --smoke

eval:
	$(PY) -m maat.eval.harness --full

demo:
	$(PY) scripts/seed_demo.py
	$(PY) scripts/run_demo.py

web-check:
	cd web && npm run typecheck

ci: lint test scenarios

clean:
	rm -rf .pytest_cache .ruff_cache build *.egg-info maat.db
