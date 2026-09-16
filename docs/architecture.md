# Architecture

Milestone 0 establishes the local repository foundation only.

The intended MVP has three local application services:

- Web UI on port `3500`
- Bill-pay API on port `8501`
- Mock provider API on port `8502`

PostgreSQL and Redis run locally through Docker Compose. The bill-pay app and
mock provider are separate services and must communicate through HTTP in later
milestones.
