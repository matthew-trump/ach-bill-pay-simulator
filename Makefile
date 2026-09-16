PYTHON ?= python3.12

.PHONY: install install-python install-web infra-up infra-down dev-billpay dev-provider dev-web lint typecheck test check port-check

install: install-python install-web

install-python:
	$(PYTHON) -m pip install -e ".[dev]"

install-web:
	npm install --prefix apps/web

infra-up:
	docker compose up -d postgres redis

infra-down:
	docker compose down

dev-billpay:
	uvicorn billpay_api.main:app --host 127.0.0.1 --port 8501 --reload

dev-provider:
	uvicorn mock_provider.main:app --host 127.0.0.1 --port 8502 --reload

dev-web:
	npm run dev --prefix apps/web -- --host 127.0.0.1 --port 3500

lint:
	ruff check .
	npm run lint --prefix apps/web

typecheck:
	mypy apps/billpay_api/src apps/mock_provider/src packages/provider_contract
	npm run typecheck --prefix apps/web

test:
	pytest

port-check:
	! rg "8080" docker-compose.yml apps

check: lint typecheck test port-check
