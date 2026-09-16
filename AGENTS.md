# Repository Guidance

This project is a fully local, simulated ACH-like bill-pay educational system.

- Work on one milestone at a time.
- Do not connect to real banks, payment processors, ACH operators, billers, or financial accounts.
- Do not accept or store real bank credentials or plausible real account data.
- Keep the bill-pay app and mock provider logically separate.
- Use ports `3500`, `8501`, and `8502` for the application services.
- Do not use port `8080`.
- Treat submitted transfers as asynchronous until later milestones explicitly implement state handling.
- Preserve clear boundaries between provider truth, bill-pay state, and ledger truth.
