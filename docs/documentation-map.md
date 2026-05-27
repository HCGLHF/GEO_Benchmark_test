# Documentation Map

Use this file as the entry point for understanding how the project documents relate to each other.

## Start Here

1. `README.md`: short project overview and the top-level collaboration model.
2. `CONTEXT.md`: domain vocabulary, project goals, non-goals, and constraints.
3. `docs/cloud-database.md`: AWS RDS/S3 data ownership, team setup, environment variables, and database responsibilities.
4. `docs/ec2-server-runbook.md`: internal EC2 server setup, service management, SSH tunnel access, and deployment checks.
5. `docs/architecture.md`: module responsibilities, data flow, and implementation boundaries.
6. `docs/risks.md`: current technical, operational, and cloud risks.
7. `docs/next.md`: completed work, learned facts, risks, and next actions.

## Document Roles

`README.md` is the public front door. Keep it short and point readers to deeper docs.

`CONTEXT.md` defines the project language. When a new durable concept appears, add it there before scattering the term across scripts and docs.

`docs/cloud-database.md` is the cloud operations source of truth. It explains what lives in Git, what lives in RDS, what lives in S3, how industry registry rows are created, and how remote team members connect.

`docs/ec2-server-runbook.md` records the internal EC2 application host, how the UI service runs, how to reach it through an SSH tunnel, and how to verify cloud access from the server.

`docs/architecture.md` explains how code modules fit together. It should name scripts, data flow, and boundaries, but should not become a runbook.

`docs/risks.md` tracks things that can mislead analysis, break operations, expose data, or create expensive mistakes.

`docs/next.md` is the working project memory. Update it after development tasks so future work starts from current facts instead of old chat context.

`docs/adr/` records durable decisions that should not be re-litigated casually. Use an ADR when changing a long-lived architecture or collaboration rule.

`docs/superpowers/plans/` stores implementation plans. These are execution checklists, not canonical architecture. After implementation, summarize the durable result in `docs/architecture.md`, `docs/risks.md`, and `docs/next.md`.

`docs/run-full-api-client-acquisition.md` and `docs/single-model-parallel-full-api.md` explain benchmark execution. They should reference the cloud database only when a run depends on a specific corpus version or artifact.

`sql/001_initial_schema.sql` is the executable PostgreSQL schema. Describe table intent in docs, but make schema changes in SQL first.

## Update Rules

- New cloud resource, table, credential rule, or team onboarding step: update `docs/cloud-database.md`.
- New script, module, or data-flow dependency: update `docs/architecture.md`.
- New blocker, operational hazard, or misleading benchmark condition: update `docs/risks.md`.
- Finished task or newly learned fact: update `docs/next.md`.
- New durable decision that future agents should not reopen without cause: add an ADR.
- New user-facing workflow: link it from `README.md` if it helps a fresh teammate.

## Git Boundary

Commit these:

- scripts
- tests
- docs
- SQL schema
- config templates
- `.env.example`

Do not commit these:

- `.env`
- `data/`
- `runs/`
- `output/`
- `reports/`
- `vector_db/`
- `.deps/`
- SQLite, DuckDB, pickle, and cache artifacts
