# Post-MVP Backlog

The local MVP is complete through Milestone 7. The items below are deliberately
deferred and should not be implemented without a new scoped plan.

## Local Simulator Hardening

- Add a workflow for marking reconciliation exceptions resolved.
- Add ledger correction and reversal workflows beyond the immutable data model.
- Add broader return-code handling and user-facing explanations.
- Add recurring payments and authorization revocation.
- Add same-day versus standard processing windows.
- Add fees, refunds, and loss-recovery scenarios.
- Add synthetic NACHA file generation for educational inspection.
- Add more complete operations workflows for webhook failures and reconciliation
  exceptions.
- Add structured logging, metrics, and local observability.

## Product Scope

- Add production authentication and multi-tenancy.
- Add real account and biller onboarding screens for a non-simulated product.
- Add additional delivery rails such as virtual-card or paper-check simulation.
- Add microdeposit verification workflow.

## Productionization

- Add Alembic migrations for managed database changes.
- Add deployment packaging and environment management.
- Add AWS or other cloud deployment.
- Add a provider adapter for a real sandbox only in a separately reviewed
  project.

## Still Out Of Scope

- Real bank credentials.
- Real bank accounts.
- Real ACH operators, payment processors, billers, or financial accounts.
- Production payment movement.
- Real compliance work.
