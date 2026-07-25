.PHONY: install frontend-install doctor build package test quality backend-lint backend-typecheck backend-coverage backend-security acceptance api-schema api-schema-check dev-api dev-web serve

PYTHON ?= .venv/bin/python

install:
	python3.12 -m venv .venv
	.venv/bin/python -m pip install -e './backend[opend,web,test]'
	$(MAKE) frontend-install

frontend-install:
	cd frontend && npm ci

doctor:
	PYTHONPATH=backend .venv/bin/python -m stock_strategy.doctor

build:
	cd frontend && npm run build

package: build
	rm -rf backend/build backend/dist backend/*.egg-info
	.venv/bin/python -m build --wheel backend
	.venv/bin/python backend/scripts/verify_wheel.py

test:
	PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v
	cd frontend && npm run lint && npm run typecheck && npm run test

backend-lint:
	cd backend && ../.venv/bin/ruff check stock_strategy tests scripts
	cd backend && ../.venv/bin/ruff format --check stock_strategy tests scripts

backend-typecheck:
	cd backend && ../.venv/bin/mypy stock_strategy

backend-coverage:
	cd backend && ../.venv/bin/coverage run -m unittest discover -s tests
	cd backend && ../.venv/bin/coverage report

backend-security:
	cd backend && ../.venv/bin/bandit -q -r stock_strategy -c pyproject.toml
	.venv/bin/python -m pip_audit --local --skip-editable

quality: backend-lint backend-typecheck backend-coverage backend-security

acceptance: build
	.venv/bin/python backend/scripts/acceptance.py

api-schema:
	PYTHONPATH=backend $(PYTHON) backend/scripts/export_openapi.py frontend/openapi.json
	cd frontend && npm run generate:api

api-schema-check: api-schema
	git diff --exit-code -- frontend/openapi.json frontend/src/api/generated

dev-api:
	PYTHONPATH=backend .venv/bin/python -m uvicorn stock_strategy.web:create_app --factory --host 127.0.0.1 --port 8000 --reload

dev-web:
	cd frontend && npm run dev

serve: build
	PYTHONPATH=backend .venv/bin/python -m stock_strategy.web
