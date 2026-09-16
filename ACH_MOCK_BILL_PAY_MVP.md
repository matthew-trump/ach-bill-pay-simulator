# Mock ACH Bill-Pay MVP

## Project brief for a local Codex build

## 1. Purpose

Build a completely local, self-contained web application that simulates paying a bill from a personal checking account through ACH-like payment rails.

This is an educational system. It must not connect to a real bank, payment processor, biller, ACH operator, or financial account. It must use only fictional users, fictional accounts, synthetic balances, and opaque mock tokens.

The project should teach the engineering problems that appear in real payment systems:

- Tokenized bank-account references
- Asynchronous payment processing
- ACH debit and credit legs
- Idempotent API requests
- Signed and retryable webhooks
- Duplicate and out-of-order events
- Returns such as insufficient funds
- Double-entry ledger accounting
- Reconciliation
- Operational exception handling

The goal is not to reproduce every ACH rule or generate production-ready NACHA files. The goal is to build a small system whose behavior resembles a modern application integrating with an external ACH provider.

## 2. Product scenario

A fictional user signs in, links a simulated checking account, adds a biller account, and pays a bill.

The system performs two simulated money-movement legs:

1. **Funding leg:** debit the user's checking account and move funds into a platform settlement account.
2. **Delivery leg:** credit the biller's receiving account from the platform settlement account.

The biller receives a customer reference so it can apply the payment to the correct fictional customer account.

```text
User checking account
        |
        | ACH-like debit
        v
Platform settlement account
        |
        | ACH-like credit
        v
Biller receiving account
```

The delivery leg begins only after the funding leg succeeds. This intentionally favors clarity and lower simulated risk over speed.

## 3. Non-goals and safety boundaries

The MVP must not:

- Accept or store real bank credentials
- Connect to Plaid, Stripe, Dwolla, Moov, a bank, or any other financial provider
- Move real money
- Present itself as a real payment service
- Implement real customer identity verification
- Claim legal, regulatory, Nacha, PCI, AML, or money-transmission compliance
- Support international payments
- Support cards, wires, RTP, FedNow, or paper checks
- Generate or transmit real NACHA files in the initial MVP
- Use floating-point numbers for money
- Treat a submitted transfer as a completed payment

Every screen that displays bank-account entry should state clearly:

> Simulation only. Enter fictional test data. Never enter a real bank account or routing number.

Use reserved, visibly fake values in seeds and examples. Do not use plausible real customer data.

## 4. Recommended technology

Use a monorepo with:

- Python 3.12+
- FastAPI for both backend services
- SQLAlchemy 2.x
- Alembic migrations
- PostgreSQL for persistent data
- Redis for background jobs, or a lightweight broker supported by the selected worker
- Celery for asynchronous processing
- React with TypeScript and Vite for the web UI
- Pydantic v2 for API schemas and settings
- `httpx` for service-to-service HTTP
- Docker Compose for local infrastructure
- `pytest`, `pytest-asyncio`, and HTTP test clients
- Ruff and mypy for Python quality checks
- ESLint and TypeScript strict mode for the frontend

If reducing initial setup is important, SQLite may be used for Milestones 1 and 2, but PostgreSQL should be introduced before implementing concurrent webhook handling and ledger posting.

Avoid port 8080. Suggested local ports:

| Component | Port |
|---|---:|
| Web UI | 3000 |
| Bill-pay API | 8001 |
| Mock provider API | 8002 |
| PostgreSQL | 5432 |
| Redis | 6379 |

## 5. Repository layout

```text
mock-ach-bill-pay/
├── AGENTS.md
├── README.md
├── docker-compose.yml
├── pyproject.toml
├── .env.example
├── docs/
│   ├── architecture.md
│   ├── state-machines.md
│   └── test-scenarios.md
├── apps/
│   ├── billpay_api/
│   │   ├── app/
│   │   │   ├── api/
│   │   │   ├── domain/
│   │   │   ├── providers/
│   │   │   ├── services/
│   │   │   ├── persistence/
│   │   │   ├── workers/
│   │   │   └── main.py
│   │   └── tests/
│   ├── mock_provider/
│   │   ├── app/
│   │   │   ├── api/
│   │   │   ├── services/
│   │   │   ├── persistence/
│   │   │   ├── workers/
│   │   │   └── main.py
│   │   └── tests/
│   └── web/
│       ├── src/
│       └── tests/
└── packages/
    └── provider_contract/
        ├── models.py
        └── events.py
```

The two services should remain logically separate even if they initially share one PostgreSQL server. Give each service its own database or schema. The bill-pay application must never read provider tables directly.

## 6. System components

### 6.1 Bill-pay application

The customer-facing application owns:

- Users
- Saved provider bank-account references
- Billers
- User-to-biller account relationships
- Bills
- Payment orders
- Funding and delivery payment legs
- ACH authorization evidence
- Internal ledger
- Provider-event inbox
- Reconciliation results
- User-visible payment history

It communicates with the provider only through HTTP and webhooks.

### 6.2 Mock ACH provider

The provider simulator owns:

- Mock provider customers
- Fictional bank accounts and balances
- Opaque bank-account tokens
- Transfers
- Idempotency records
- Transfer state transitions
- Return codes
- Webhook endpoints
- Webhook delivery attempts
- Scenario controls

It behaves like an external provider. It does not share its database models with the bill-pay application.

### 6.3 Background workers

Background work includes:

- Advancing provider transfers through states
- Delivering and retrying webhooks
- Applying provider events in the bill-pay application
- Starting the delivery leg after funding succeeds
- Running reconciliation

## 7. Domain terminology

Use these terms consistently:

- **Payment order:** the user's request to pay one bill.
- **Payment leg:** one provider transfer belonging to the order.
- **Funding leg:** user checking account to platform settlement account.
- **Delivery leg:** platform settlement account to biller receiving account.
- **Funding source:** provider-tokenized fictional bank account.
- **Provider transfer:** the mock provider's representation of one money movement.
- **Provider event:** immutable notification emitted by the provider.
- **Return:** a transfer that fails or reverses with an ACH-style return code.
- **Ledger transaction:** a balanced collection of immutable debit and credit entries.
- **Reconciliation:** comparison of internal payment and ledger records with provider records.

## 8. Internal provider interface

The bill-pay domain must depend on an application-owned abstraction rather than provider-specific response models.

```python
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol


class TransferStatus(StrEnum):
    CREATED = "created"
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETURNED = "returned"
    CANCELED = "canceled"


@dataclass(frozen=True)
class BankAccountRef:
    provider_account_id: str
    bank_name: str
    account_type: str
    last4: str
    verification_status: str


@dataclass(frozen=True)
class TransferResult:
    provider_transfer_id: str
    status: TransferStatus
    return_code: str | None = None


class AchProvider(Protocol):
    async def create_customer(
        self,
        *,
        external_user_id: str,
        name: str,
        email: str,
    ) -> str: ...

    async def tokenize_bank_account(
        self,
        *,
        customer_id: str,
        routing_number: str,
        account_number: str,
        account_type: str,
    ) -> BankAccountRef: ...

    async def create_transfer(
        self,
        *,
        source_account_id: str,
        destination_account_id: str,
        amount: Decimal,
        idempotency_key: str,
        metadata: dict[str, str],
    ) -> TransferResult: ...

    async def get_transfer(
        self,
        provider_transfer_id: str,
    ) -> TransferResult: ...

    async def cancel_transfer(
        self,
        provider_transfer_id: str,
    ) -> TransferResult: ...
```

Implement `MockAchProviderClient` as the HTTP adapter. Domain services should not import mock-provider database models or HTTP response schemas directly.

## 9. Mock-provider API

All endpoints live under `/v1`. Use bearer authentication with a fixed development-only API key loaded from the environment.

### Customers

```text
POST /v1/customers
GET  /v1/customers/{customer_id}
```

### Bank accounts

```text
POST /v1/customers/{customer_id}/bank-accounts
GET  /v1/bank-accounts/{bank_account_id}
POST /v1/bank-accounts/{bank_account_id}/verify
```

Creating an account accepts only synthetic data and returns an opaque ID such as `ba_01J...`. The bill-pay application stores only the provider ID, institution label, account type, last four digits, and status.

### Transfers

```text
POST /v1/transfers
GET  /v1/transfers/{transfer_id}
POST /v1/transfers/{transfer_id}/cancel
GET  /v1/transfers
```

Example request:

```json
{
  "source": "ba_user_123",
  "destination": "ba_platform_settlement",
  "amount": {
    "currency": "USD",
    "value": "142.67"
  },
  "metadata": {
    "payment_order_id": "pay_937",
    "leg": "funding"
  }
}
```

The endpoint must require an `Idempotency-Key` header.

### Webhook endpoints

```text
POST   /v1/webhook-endpoints
GET    /v1/webhook-endpoints
DELETE /v1/webhook-endpoints/{endpoint_id}
```

### Sandbox controls

Sandbox controls must be clearly separated from the provider's normal interface:

```text
POST /_sandbox/transfers/{transfer_id}/advance
POST /_sandbox/transfers/{transfer_id}/fail
POST /_sandbox/transfers/{transfer_id}/return
POST /_sandbox/transfers/{transfer_id}/duplicate-last-webhook
POST /_sandbox/transfers/{transfer_id}/send-out-of-order-events
POST /_sandbox/webhook-deliveries/{delivery_id}/retry
```

These endpoints make test behavior deterministic. Do not depend on randomness for automated tests.

## 10. Opaque tokens

Use prefixed opaque identifiers:

```text
cus_...   provider customer
ba_...    provider bank account
tr_...    provider transfer
evt_...   provider event
we_...    webhook endpoint
wd_...    webhook delivery
pay_...   bill-pay payment order
leg_...   bill-pay payment leg
```

ULIDs are a good choice because they remain opaque while sorting approximately by creation time.

Tokens are provider-local identifiers, not authentication credentials and not a universal ACH standard.

## 11. Idempotency

Persist provider idempotency records with:

```text
client_id
HTTP method
endpoint identity
idempotency key
canonical request hash
response status
response body
created timestamp
```

Required behavior:

- Same key and same request: return the original response.
- Same key and different request: return `409 Conflict`.
- Transfer creation committed but HTTP response lost: a retry returns the original transfer.
- Idempotency keys are scoped to the API client and operation.

The bill-pay application must also enforce its own idempotency when creating payment orders.

## 12. Transfer state machine

Normal provider flow:

```text
created -> pending -> processing -> succeeded
```

Failure flow:

```text
created -> pending -> processing -> failed
```

Late-return flow:

```text
created -> pending -> processing -> succeeded -> returned
```

Cancellation is allowed only from defined early states. Centralize allowed transitions in one state-machine module and reject illegal transitions.

Initial simulated return codes:

| Code | Meaning |
|---|---|
| R01 | Insufficient funds |
| R02 | Account closed |
| R03 | No account or unable to locate account |
| R08 | Payment stopped |
| R10 | Customer advises unauthorized entry |

The provider should store a structured return code and description. The bill-pay application maps these to safe user-facing messages.

## 13. Webhook contract

Example event:

```json
{
  "id": "evt_01J777",
  "type": "transfer.returned",
  "created_at": "2026-09-18T12:05:00Z",
  "data": {
    "transfer": {
      "id": "tr_01JXYZ",
      "status": "returned",
      "return_code": "R01",
      "amount": {
        "currency": "USD",
        "value": "142.67"
      },
      "metadata": {
        "payment_order_id": "pay_937",
        "leg": "funding"
      }
    }
  }
}
```

Sign webhooks with HMAC-SHA256 over:

```text
timestamp + "." + raw_request_body
```

Send headers resembling:

```text
X-Mock-Webhook-Timestamp: 1789742700
X-Mock-Webhook-Signature: sha256=<hex digest>
```

The bill-pay endpoint must:

1. Read the raw body.
2. Verify the signature using constant-time comparison.
3. Reject timestamps outside a configured tolerance.
4. Insert the event into an inbox table with a unique provider event ID.
5. Enqueue event processing.
6. Respond quickly with a 2xx status.

The worker must process duplicate events harmlessly and prevent stale events from regressing state.

The provider retries unsuccessful webhook deliveries with a short development schedule, for example 2, 5, 15, and 30 seconds. Record every delivery attempt and response status.

## 14. Bill-pay data model

Minimum entities:

### User

```text
id
email
name
provider_customer_id
status
created_at
```

### BankAccount

```text
id
user_id
provider_account_id
bank_name
account_type
last4
verification_status
created_at
disabled_at
```

### Biller

```text
id
name
provider_destination_account_id
customer_reference_pattern
status
```

### BillerAccount

```text
id
user_id
biller_id
customer_reference
display_mask
nickname
```

### Bill

```text
id
biller_account_id
amount
due_date
description
status
```

### PaymentOrder

```text
id
user_id
bill_id
funding_account_id
amount
requested_date
status
idempotency_key
created_at
updated_at
```

### PaymentLeg

```text
id
payment_order_id
leg_type: funding | delivery
provider_transfer_id
source_provider_account_id
destination_provider_account_id
amount
status
return_code
provider_created_at
settled_at
```

### AuthorizationRecord

```text
id
payment_order_id
authorization_version
authorization_text_hash
accepted_at
account_last4
amount
simulated_session_metadata
```

### ProviderEventInbox

```text
id
provider_event_id (unique)
event_type
payload_json
received_at
processed_at
processing_error
```

## 15. Payment-order state machine

Suggested customer-visible states:

```text
draft
awaiting_authorization
funding_pending
funded
delivery_pending
delivered
failed
returned
action_required
```

Important rules:

- Creating a provider transfer changes the order to `funding_pending`, not `paid`.
- Funding success starts the delivery leg exactly once.
- Delivery success changes the order to `delivered`.
- Funding failure before delivery changes the order to `failed`.
- Delivery failure after funding changes the order to `action_required`.
- A late funding return after delivery is a special exception and must not silently change the order as though delivery never happened.

Use row locking or optimistic concurrency to prevent two workers from starting the delivery leg twice.

## 16. Double-entry ledger

Implement a minimal immutable ledger with:

```text
ledger_accounts
ledger_transactions
ledger_entries
```

Each ledger transaction contains at least two entries, and:

```text
sum(debits) == sum(credits)
```

Store amounts as integer cents or fixed-precision decimals. Prefer integer cents in ledger entries.

Initial ledger accounts:

- Platform settlement cash
- Customer bill-payment liability
- Biller settlement payable
- Provider clearing
- Fees revenue, reserved for later
- Payment loss/receivable, used for late-return scenarios

When funding succeeds:

| Ledger account | Debit | Credit |
|---|---:|---:|
| Platform settlement cash | $142.67 | |
| Customer bill-payment liability | | $142.67 |

When delivery succeeds:

| Ledger account | Debit | Credit |
|---|---:|---:|
| Customer bill-payment liability | $142.67 | |
| Platform settlement cash | | $142.67 |

Ledger entries are never edited or deleted. Corrections use reversing or compensating transactions.

## 17. Reconciliation

Provide a reconciliation job that compares:

- Bill-pay payment legs
- Mock-provider transfers
- Internal ledger transactions
- Mock-provider account balances

Detect at least:

- Internal leg missing a provider transfer
- Provider transfer missing an internal leg
- Status mismatch
- Amount mismatch
- Missing ledger posting
- Duplicate ledger posting
- Unbalanced ledger transaction
- Returned funding after completed delivery

Persist reconciliation runs and exceptions. Create a simple operations page for reviewing unresolved exceptions.

## 18. User interface

Build a functional interface rather than a visually elaborate one.

Required pages:

1. **Dashboard** — bills due, pending payments, completed payments.
2. **Bank accounts** — add a fictional account and show its masked tokenized representation.
3. **Billers** — select a seeded biller and add a fictional customer reference.
4. **Bills** — create a fictional bill.
5. **Pay bill** — select funding account, review amount, accept simulated authorization, and submit.
6. **Payment detail** — show order status, both legs, provider events, and ledger entries.
7. **Sandbox controls** — advance, fail, return, duplicate, or reorder events.
8. **Operations** — webhook failures and reconciliation exceptions.

For the MVP, use one seeded user or a development-only user selector instead of building full authentication. Keep the application boundary ready for authentication later.

## 19. Seed data

Seed:

- One fictional user: Alice Example
- One fictional checking account with a $2,000 simulated balance
- One platform settlement account
- Two fictional billers, such as Desert Electric and Sonoran Water
- One receiving account for each biller
- Two fictional bills

No seed value should resemble real personal data. Display a persistent simulation banner.

## 20. Testing strategy

### Unit tests

- Money parsing and serialization
- State-machine transition rules
- Return-code mapping
- Webhook signature creation and verification
- Ledger balancing
- Idempotency request hashing
- Biller customer-reference validation

### Provider contract tests

Run the same behavioral tests against any `AchProvider` implementation:

- Create a customer
- Tokenize a fictional account
- Create and retrieve a transfer
- Repeat a request with the same idempotency key
- Reject changed parameters with a reused key
- Cancel an eligible transfer
- Reject an invalid state transition

### Integration tests

- Successful two-leg payment
- Funding R01 failure
- Funding success followed by late return
- Delivery failure after funding
- Duplicate webhook delivery
- Out-of-order webhook delivery
- Provider commits transfer but HTTP response times out
- Worker crashes and retries after ledger posting
- Two workers attempt to create the delivery leg
- Reconciliation finds a deliberately introduced mismatch

### End-to-end test

From the browser:

1. Add a fictional bank account.
2. Add a seeded biller account.
3. Create and authorize a payment.
4. Advance funding through the sandbox UI.
5. Observe automatic creation of the delivery leg.
6. Advance delivery to success.
7. Confirm the payment, ledger, events, and reconciliation view agree.

## 21. Observability

Use structured JSON logs with correlation fields:

```text
request_id
payment_order_id
payment_leg_id
provider_transfer_id
provider_event_id
webhook_delivery_id
```

Never log raw account or routing numbers, even though the values are fictional. This reinforces correct engineering habits.

Expose development metrics or counters for:

- Transfers created
- Transfers succeeded, failed, and returned
- Webhook attempts and failures
- Duplicate events ignored
- Payment orders completed
- Reconciliation exceptions

## 22. Milestone plan

### Milestone 0: Repository foundation

- Initialize the monorepo and Git.
- Add `AGENTS.md`, README, formatting, linting, testing, and Docker Compose.
- Start PostgreSQL and Redis locally.
- Add health endpoints to both APIs.
- Add CI commands that can run locally.

Acceptance criteria:

- Both APIs boot.
- The frontend boots.
- Lint and empty test suites pass.
- No service uses port 8080.

### Milestone 1: Mock-provider core

- Implement provider customers and fictional bank accounts.
- Implement opaque tokens.
- Implement transfers and state machine.
- Implement required idempotency.
- Implement sandbox state controls.

Acceptance criteria:

- A transfer can be created, retrieved, advanced, failed, and returned.
- Repeating transfer creation with the same key cannot create a duplicate.

### Milestone 2: Provider webhooks

- Register webhook endpoints.
- Create immutable provider events.
- Sign webhook requests.
- Retry failed deliveries.
- Add duplicate and out-of-order simulation controls.

Acceptance criteria:

- A test receiver verifies signatures.
- Delivery attempts and responses are visible.
- Duplicate events keep the same event ID.

### Milestone 3: Bill-pay domain

- Implement users, linked bank-account references, billers, biller accounts, and bills.
- Add the `AchProvider` interface and HTTP adapter.
- Implement payment orders, authorization records, and funding legs.
- Add provider-event inbox processing.

Acceptance criteria:

- Submitting a payment creates exactly one funding transfer.
- Provider events update the funding leg without duplicate effects.

### Milestone 4: Two-leg orchestration

- Start delivery only after funding succeeds.
- Add concurrency protection.
- Handle funding and delivery failures.
- Handle late funding returns.

Acceptance criteria:

- Successful funding starts exactly one delivery transfer.
- All principal failure paths end in an explicit, explainable state.

### Milestone 5: Ledger

- Implement immutable double-entry accounting.
- Post funding and delivery transactions.
- Add balance queries and invariant checks.

Acceptance criteria:

- Every ledger transaction balances.
- Retried events cannot double-post entries.
- The UI can explain a payment using ledger entries.

### Milestone 6: Web UI

- Implement the required customer and sandbox pages.
- Clearly label all data as fictional.
- Show timelines for order, leg, and event status.

Acceptance criteria:

- The happy path can be completed entirely through the browser.
- Failure and return states are understandable without inspecting the database.

### Milestone 7: Reconciliation and hardening

- Implement reconciliation runs and exception records.
- Add operations UI.
- Complete integration and end-to-end tests.
- Add structured logging and metrics.

Acceptance criteria:

- The system detects deliberately introduced mismatches.
- All documented scenarios have automated coverage.

## 23. Definition of done for the MVP

The MVP is complete when:

- It runs locally from documented commands.
- It uses no real money, accounts, or provider connections.
- A user can complete a successful fictional bill payment.
- A payment contains separate funding and delivery legs.
- Transfers are asynchronous.
- Idempotency prevents duplicate payment effects.
- Webhooks are signed, retried, and deduplicated.
- Failures and late returns can be simulated deterministically.
- Ledger postings are immutable and balanced.
- Reconciliation detects mismatches.
- Automated tests cover the main happy and unhappy paths.
- The README explains the architecture, limitations, and safety boundary.

## 24. Instructions for Codex

When implementing this project:

1. Work on only one milestone at a time.
2. Before changing code, inspect the repository and restate the milestone's current acceptance criteria.
3. Prefer explicit application code over a large framework abstraction.
4. Keep the bill-pay domain independent of the mock provider's models.
5. Add tests with each behavior rather than postponing tests.
6. Use database constraints for uniqueness and financial invariants where practical.
7. Make all external-style operations retry-safe.
8. Never introduce real provider credentials, real bank data, or production payment code.
9. Do not silently broaden scope into authentication, subscriptions, mobile apps, cloud deployment, or real compliance work.
10. Stop at the end of each milestone, run its checks, summarize what changed, and propose the next milestone.
11. If a design choice changes a financial invariant or funds flow, explain it before implementing it.
12. Preserve a visible distinction between provider truth, bill-pay application state, and ledger truth.

## 25. Suggested first Codex prompt

After placing this document in a new project directory, begin with:

> Read `ACH_MOCK_BILL_PAY_MVP.md` completely. We are starting Milestone 0 only. Propose the concrete repository scaffold, dependency choices, local commands, and acceptance checks. Keep the system entirely local and simulated, use ports 3500, 8501, and 8502, and do not implement later milestones yet. After I approve the plan, create the scaffold, run the checks, and update the README with exact startup instructions.

## 26. Possible post-MVP extensions

These are deliberately deferred:

- Recurring payments and revocation
- Microdeposit verification workflow
- Same-day versus standard processing windows
- Fees and refunds
- More complete return-code handling
- Synthetic NACHA file generation for educational inspection
- Additional delivery rails such as virtual card or paper-check simulation
- Provider adapter for a real sandbox, only in a separately reviewed project
- Authentication and multi-tenancy
- AWS deployment

Do not implement these until the core MVP is working and reconciles correctly.
