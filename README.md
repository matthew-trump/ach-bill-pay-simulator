# Mock ACH Bill Pay

Local-only educational application for simulating ACH-like bill-pay flows.

This repository is currently at **Milestone 0: Repository foundation**. It does
not move money, connect to providers, tokenize real accounts, create transfers,
send webhooks, post ledger entries, or reconcile payments yet.

## Safety Boundary

Simulation only. Enter fictional test data. Never enter a real bank account or
routing number.

The system must not connect to Plaid, Stripe, Dwolla, Moov, a bank, an ACH
operator, a biller, or any real financial account.

## Local Ports

| Component | URL |
|---|---|
| Web UI | `http://127.0.0.1:3500` |
| Bill-pay API | `http://127.0.0.1:8501` |
| Mock provider API | `http://127.0.0.1:8502` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |

Port `8080` is intentionally unused.

## Prerequisites

- Python 3.12+
- Node.js 22+
- Docker Desktop or compatible Docker Compose runtime

## First-Time Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
make install
```

Start local infrastructure:

```bash
make infra-up
```

## Run The Services

Use three separate terminals.

Terminal 1:

```bash
source .venv/bin/activate
make dev-billpay
```

Bill-pay API health check:

```bash
curl http://127.0.0.1:8501/healthz
```

Terminal 2:

```bash
source .venv/bin/activate
make dev-provider
```

Mock provider API health check:

```bash
curl http://127.0.0.1:8502/healthz
```

Terminal 3:

```bash
make dev-web
```

Open:

```text
http://127.0.0.1:3500
```

## Local Checks

Run all Milestone 0 checks:

```bash
source .venv/bin/activate
make check
npm run build --prefix apps/web
docker compose config
```

Individual checks:

```bash
make lint
make typecheck
make test
make port-check
```

## Milestone 0 Acceptance

- Both APIs boot on local ports and expose `/healthz`.
- The frontend boots on port `3500`.
- Lint and empty/foundation test suites pass.
- No service uses port `8080`.

## Repository Layout

```text
apps/
  billpay_api/      FastAPI shell for the bill-pay application
  mock_provider/    FastAPI shell for the mock ACH provider
  web/              React + TypeScript + Vite shell
packages/
  provider_contract/
docs/
docker/
```
