# ACH Bill Pay Simulator

Local-only educational application for simulating ACH-like bill-pay flows.

This repository is currently at **Milestone 7: Reconciliation and hardening**. It can
create simulated provider customers, tokenize fictional bank accounts, create
provider transfers, enforce provider idempotency, and move transfers through
deterministic sandbox states. It can also register webhook endpoints, create
immutable transfer events, sign webhook delivery attempts, record responses, and
retry or duplicate deliveries through sandbox controls. The bill-pay API can now
seed fictional user/biller/bill data, submit a payment order, create exactly one
funding transfer through the provider abstraction, process provider events into
an inbox without duplicate effects, and start a separate delivery transfer after
the funding leg succeeds. It also posts immutable balanced ledger transactions
for successful funding and delivery events. The browser UI can drive the seeded
happy path, inspect payment details, run sandbox state changes, and show ledger
and provider-event status. The bill-pay API can run reconciliation against
provider transfer truth, ledger truth, and payment-leg state, then persist
unresolved operational exceptions.

It does not move money, connect to real providers, provide production
authentication, or perform real account/biller onboarding.

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

## Bill-Pay API Smoke Test

Seed fictional bill-pay data:

```bash
export BILLPAY=http://127.0.0.1:8501
export PROVIDER=http://127.0.0.1:8502

curl -sS -X POST "$PROVIDER/_sandbox/seed-billpay-accounts"
curl -sS -X POST "$BILLPAY/dev/seed"
```

Submit a payment order using the returned `user_id`, `bill_id`, and
`funding_account_id`:

```bash
curl -sS -X POST "$BILLPAY/v1/payment-orders" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_alice_example",
    "bill_id": "bill_desert_electric_001",
    "funding_account_id": "ba_ref_alice_checking",
    "idempotency_key": "demo-payment-001",
    "authorization_text": "I authorize this simulated ACH debit."
  }'
```

Milestone 7 bill-pay endpoints:

- `POST /dev/seed`
- `GET /dev/overview`
- `POST /v1/payment-orders`
- `GET /v1/payment-orders/{payment_order_id}`
- `POST /v1/provider-events`
- `GET /v1/provider-events`
- `GET /v1/ledger/accounts`
- `GET /v1/ledger/invariants`
- `POST /v1/reconciliation-runs`
- `GET /v1/reconciliation-runs`
- `GET /v1/reconciliation-exceptions`

`POST /v1/provider-events` records provider events in an inbox and updates the
matching payment leg. A funding success starts exactly one delivery transfer
from the simulated bill-pay settlement account to the biller account. Reposting
the same provider event ID is treated as a harmless duplicate. Successful funding
and delivery events post balanced ledger transactions once per payment leg
outcome, even if the provider sends a retried success event.

The web UI on `http://127.0.0.1:3500` includes dashboard, bank-account, biller,
bill, pay-bill, payment-detail, sandbox-control, and operations views for the
seeded fictional scenario. The operations view can run reconciliation and show
unresolved reconciliation exceptions.

## Milestone 7 Acceptance

- Both APIs boot on local ports and expose `/healthz`.
- The frontend boots on port `3500`.
- Local browser requests from the Vite UI are allowed by both APIs.
- Simulated provider customers, fictional bank accounts, and transfers can be created and retrieved.
- Transfer creation is idempotent for matching requests and rejects changed request bodies with `409`.
- Sandbox controls advance, fail, and return transfers deterministically.
- Webhook endpoints can be registered, listed, and disabled.
- Transfer state changes create immutable provider events.
- Webhook deliveries are signed and persisted with response status or error details.
- Failed deliveries can be retried.
- Duplicate webhook simulation reuses the same provider event ID.
- Out-of-order webhook simulation emits deterministic event order.
- Bill-pay seed data creates fictional user, funding account, biller, biller account, and bill records.
- Submitting a bill-pay payment order creates exactly one funding transfer.
- Funding transfers land in the simulated bill-pay settlement provider account.
- Repeating payment submission with the same idempotency key returns the original order.
- Provider events update payment legs without duplicate effects.
- A successful funding event starts exactly one delivery transfer.
- Delivery success marks the payment order `delivered`.
- Funding failure before delivery marks the payment order `failed`.
- Delivery failure or a late funding return after delivery marks the payment order `action_required`.
- Ledger accounts are seeded for settlement cash, customer liability, biller payable, provider clearing, fees revenue, and payment loss/receivable.
- Funding success posts a balanced debit to platform settlement cash and credit to customer bill-payment liability.
- Delivery success posts a balanced debit to customer bill-payment liability and credit to platform settlement cash.
- Retried success events cannot double-post ledger transactions.
- Payment-order detail responses include ledger transactions and entries.
- Ledger account balance and invariant endpoints expose current ledger truth.
- The dashboard shows bills due, pending payments, and completed payments.
- The browser can seed data, submit the seeded bill payment, advance the funding leg, advance the delivery leg, and inspect the delivered payment.
- Payment detail shows order status, both legs, provider events, and ledger entries.
- Sandbox controls expose advance, fail, return, duplicate-event, and out-of-order simulations for visible payment legs.
- Operations shows provider event processing failures, ledger balance status, and unresolved reconciliation exceptions.
- Reconciliation runs compare internal payment legs with provider transfers.
- Reconciliation detects internal legs missing provider transfers, provider transfers missing internal legs, status mismatches, amount mismatches, missing ledger postings, duplicate ledger postings, unbalanced ledger transactions, and returned funding after completed delivery.
- Reconciliation runs and exceptions are persisted.
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
