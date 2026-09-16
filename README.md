# ACH Bill Pay Simulator

Local-only educational application for simulating ACH-like bill-pay flows.

This repository is currently at **Milestone 2: Provider webhooks**. It can
create simulated provider customers, tokenize fictional bank accounts, create
provider transfers, enforce provider idempotency, and move transfers through
deterministic sandbox states. It can also register webhook endpoints, create
immutable transfer events, sign webhook delivery attempts, record responses, and
retry or duplicate deliveries through sandbox controls.

It does not move money, connect to real providers, post ledger entries,
orchestrate bill payments, or reconcile payments yet.

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
| Simulated provider API | `http://127.0.0.1:8502` |
| PostgreSQL | `localhost:5433` |
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

Simulated provider API health check:

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

Run all local checks:

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

## Simulated Provider Smoke Test

Provider endpoints under `/v1` require the development bearer token from
`.env.example`.

```bash
export PROVIDER=http://127.0.0.1:8502
export PROVIDER_AUTH="Authorization: Bearer dev_mock_provider_key_do_not_use_for_real_systems"

curl -sS -X POST "$PROVIDER/v1/customers" \
  -H "$PROVIDER_AUTH" \
  -H "Content-Type: application/json" \
  -d '{"external_user_id":"user_alice_example","name":"Alice Example","email":"alice@example.test"}'
```

The simulated provider supports:

- `POST /v1/customers`
- `GET /v1/customers/{customer_id}`
- `POST /v1/customers/{customer_id}/bank-accounts`
- `GET /v1/bank-accounts/{bank_account_id}`
- `POST /v1/bank-accounts/{bank_account_id}/verify`
- `POST /v1/transfers`
- `GET /v1/transfers/{transfer_id}`
- `GET /v1/transfers`
- `POST /v1/transfers/{transfer_id}/cancel`
- `POST /v1/webhook-endpoints`
- `GET /v1/webhook-endpoints`
- `DELETE /v1/webhook-endpoints/{endpoint_id}`
- `GET /v1/events`
- `GET /v1/webhook-deliveries`
- `POST /_sandbox/transfers/{transfer_id}/advance`
- `POST /_sandbox/transfers/{transfer_id}/fail`
- `POST /_sandbox/transfers/{transfer_id}/return`
- `POST /_sandbox/transfers/{transfer_id}/duplicate-last-webhook`
- `POST /_sandbox/transfers/{transfer_id}/send-out-of-order-events`
- `POST /_sandbox/webhook-deliveries/{delivery_id}/retry`

`POST /v1/transfers` requires an `Idempotency-Key` header.

Webhook delivery requests are signed with HMAC-SHA256 over:

```text
timestamp + "." + raw_request_body
```

The provider sends:

```text
X-Mock-Webhook-Timestamp
X-Mock-Webhook-Signature
```

## Milestone 2 Acceptance

- Both APIs boot on local ports and expose `/healthz`.
- The frontend boots on port `3500`.
- Simulated provider customers, fictional bank accounts, and transfers can be created and retrieved.
- Transfer creation is idempotent for matching requests and rejects changed request bodies with `409`.
- Sandbox controls advance, fail, and return transfers deterministically.
- Webhook endpoints can be registered, listed, and disabled.
- Transfer state changes create immutable provider events.
- Webhook deliveries are signed and persisted with response status or error details.
- Failed deliveries can be retried.
- Duplicate webhook simulation reuses the same provider event ID.
- Out-of-order webhook simulation emits deterministic event order.
- Illegal transfer state transitions return `409`.
- Lint and tests pass.
- No service uses port `8080`.

## Repository Layout

```text
apps/
  billpay_api/      FastAPI shell for the bill-pay application
  mock_provider/    FastAPI shell for the simulated ACH provider
  web/              React + TypeScript + Vite shell
packages/
  provider_contract/
docs/
docker/
```
