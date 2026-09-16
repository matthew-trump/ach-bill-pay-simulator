== Milestone 1 == 

At this point the app can run locally and the simulated provider API works.

  What you can do now:

  - Open the basic web shell at http://127.0.0.1:3500.
  - Check both service health endpoints:
      - http://127.0.0.1:8501/healthz
      - http://127.0.0.1:8502/healthz
  - Use the provider API to:
      - create simulated provider customers
      - create fictional bank-account tokens
      - verify fictional bank accounts
      - create ACH-like provider transfers
      - retrieve/list transfers
      - cancel early transfers
      - advance transfer state deterministically
      - fail transfers
      - return succeeded transfers with codes like R01
      - test idempotent transfer creation with Idempotency-Key

  What it cannot do yet:

  - No user-facing bill-pay flow.
  - No billers, bills, or payment orders.
  - No bill-pay API domain logic yet.
  - No webhooks yet.
  - No two-leg funding/delivery orchestration yet.
  - No ledger.
  - No reconciliation.
  - The frontend is still just a Milestone shell, not an operational UI.

  So the current usable surface is mostly curl/API testing against the simulated provider on port 8502. Next milestone is provider webhooks.

== Milestone 2 ==

Milestone 2 added provider webhooks.

  New capabilities:

  - Register webhook endpoints:
      - POST /v1/webhook-endpoints
      - GET /v1/webhook-endpoints
      - DELETE /v1/webhook-endpoints/{endpoint_id}
  - Emit immutable provider events when transfer state changes:
      - transfer.pending
      - transfer.processing
      - transfer.succeeded
      - transfer.failed
      - transfer.returned
      - transfer.canceled
  - Deliver signed webhook requests to registered endpoints.
  - Sign each webhook with HMAC-SHA256 headers:
      - X-Mock-Webhook-Timestamp
      - X-Mock-Webhook-Signature
  - Persist webhook delivery attempts, including:
      - request headers
      - request body
      - response status
      - response body
      - delivery error, if the endpoint is unreachable
  - Inspect events and deliveries:
      - GET /v1/events
      - GET /v1/webhook-deliveries
  - Retry a delivery:
      - POST /_sandbox/webhook-deliveries/{delivery_id}/retry
  - Simulate duplicate webhook delivery while keeping the same provider event ID:
      - POST /_sandbox/transfers/{transfer_id}/duplicate-last-webhook
  - Simulate out-of-order events:
      - POST /_sandbox/transfers/{transfer_id}/send-out-of-order-events

  Tests now include a local webhook receiver that verifies signatures and confirms delivery records.

== Milestone 3 ==

Milestone 3 adds the first real bill-pay application behavior.

  New capabilities:

  - Seed fictional bill-pay data:
      - Alice Example user
      - Alice’s saved funding account reference
      - Desert Electric biller
      - Alice’s biller account
      - one fictional bill
  - Submit a bill-pay payment order:
      - POST /v1/payment-orders
  - Create a funding leg through the provider abstraction:
      - bill-pay API calls the simulated provider API
      - provider creates one ACH-like transfer
      - bill-pay stores the funding leg and provider transfer ID
  - Enforce bill-pay idempotency:
      - resubmitting the same payment request with the same idempotency_key returns the original payment order
      - it does not create a second provider transfer
  - Record simulated authorization evidence:
      - authorization text hash
      - accepted timestamp
      - account last4
      - amount
      - local session metadata
  - Ingest provider events:
      - POST /v1/provider-events
  - Update funding leg status from provider events:
      - created
      - pending
      - processing
      - succeeded
      - failed
      - returned
  - Deduplicate provider events:
      - same provider event ID is stored once
      - duplicate event submission has no second effect

  Still not included:

  - no delivery leg yet
  - no automatic webhook receiver/signature verification on bill-pay side yet
  - no ledger
  - no reconciliation
  - frontend still does not expose workflows
  - no completed bill-payment lifecycle yet

  In short: we now have the first bridge between the bill-pay app and the simulated provider: submitting a payment creates exactly one funding transfer.

== Milestone 4 ==

Milestone 4 adds two-leg bill-pay orchestration.

  New capabilities:

  - Funding transfers now debit Alice’s saved funding account and credit a
    simulated bill-pay settlement provider account.
  - A successful funding provider event starts a delivery leg exactly once:
      - source: simulated bill-pay settlement account
      - destination: Desert Electric provider destination account
      - idempotency key: delivery:{payment_order_id}
  - Payment orders now move through explicit two-leg states:
      - funding_pending
      - delivery_pending
      - delivered
      - failed
      - returned
      - action_required
  - Delivery provider events update the delivery leg and payment order.
  - Funding failure before delivery marks the order failed.
  - Funding return before delivery marks the order returned.
  - Delivery failure or delivery return marks the order action_required.
  - A late funding return after delivery is preserved as an exception state:
      - funding leg becomes returned
      - delivery leg remains visible
      - payment order becomes action_required
  - A database uniqueness constraint prevents more than one funding leg or
    delivery leg per payment order.
  - The mock provider seed endpoint now creates the simulated bill-pay
    settlement account.

  Still not included:

  - no automatic webhook receiver/signature verification on bill-pay side yet
  - no ledger
  - no reconciliation
  - frontend still does not expose workflows

  In short: a bill payment now has separate funding and delivery transfers, and
  the app reaches explicit states for the principal success and failure paths.

== Milestone 5 ==

Milestone 5 adds a minimal immutable double-entry ledger.

  New capabilities:

  - Seed ledger accounts:
      - Platform settlement cash
      - Customer bill-payment liability
      - Biller settlement payable
      - Provider clearing
      - Fees revenue
      - Payment loss/receivable
  - Post balanced ledger transactions when funding succeeds:
      - debit Platform settlement cash
      - credit Customer bill-payment liability
  - Post balanced ledger transactions when delivery succeeds:
      - debit Customer bill-payment liability
      - credit Platform settlement cash
  - Store ledger amounts as integer cents.
  - Prevent duplicate ledger posting for retried success events by using a
    unique source key per payment leg outcome.
  - Return ledger transactions and entries with payment-order detail:
      - GET /v1/payment-orders/{payment_order_id}
  - Inspect ledger account balances:
      - GET /v1/ledger/accounts
  - Check ledger balancing invariants:
      - GET /v1/ledger/invariants

  Still not included:

  - no automatic webhook receiver/signature verification on bill-pay side yet
  - no reconciliation
  - frontend still does not expose workflows
  - no ledger correction/reversal workflow beyond the immutable data model

  In short: bill-pay application state is now accompanied by separate ledger
  truth, and successful funding/delivery events produce balanced, explainable,
  idempotent ledger entries.

== Milestone 6 ==

Milestone 6 adds a functional browser UI for the seeded fictional workflow.

  New capabilities:

  - Use the web UI at http://127.0.0.1:3500 to:
      - seed fictional provider and bill-pay data
      - review dashboard counts for due bills and payments
      - view the saved fictional funding account
      - view the seeded biller and bill
      - accept simulated authorization and submit a bill payment
      - inspect payment status, funding/delivery legs, provider events, and
        ledger entries
      - advance, fail, return, duplicate, or reorder provider events for
        visible payment legs
      - inspect provider event processing and ledger invariant status
  - Add local CORS support for the web UI on port 3500.
  - Add UI-supporting bill-pay read endpoints:
      - GET /dev/overview
      - GET /v1/provider-events

  Still not included:

  - no production authentication
  - no real account or biller onboarding
  - no reconciliation
  - no operations workflow for resolving exceptions

  In short: the happy path can now be completed from the browser for seeded
  fictional data, and failure/return states are visible without inspecting the
  database.
