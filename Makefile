.PHONY: install frontend-install build package test acceptance dev-api dev-web serve

install:
	python3.12 -m venv .venv
	.venv/bin/python -m pip install -e './backend[opend,web,test]'
	$(MAKE) frontend-install

frontend-install:
	cd frontend && npm ci

build:
	cd frontend && npm run build

package: build
	rm -rf backend/build backend/dist backend/*.egg-info
	.venv/bin/python -m build --wheel backend
	.venv/bin/python backend/scripts/verify_wheel.py

test:
	PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v
	cd frontend && npm run lint && npm run typecheck && npm run test

acceptance: build
	.venv/bin/python backend/scripts/acceptance.py

dev-api:
	PYTHONPATH=backend .venv/bin/python -m uvicorn stock_strategy.web:create_app --factory --host 127.0.0.1 --port 8000 --reload

dev-web:
	cd frontend && npm run dev

serve: build
	PYTHONPATH=backend .venv/bin/python -m stock_strategy.web
