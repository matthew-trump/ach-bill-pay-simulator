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

== Milestone 3==

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