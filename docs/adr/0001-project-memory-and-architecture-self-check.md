# ADR 0001: Project Memory And Architecture Self-Check

## Status

Accepted

## Context

The project is evolving across crawler development, resource library expansion, indexing, model evaluation, and reporting. Without durable project memory, future work can lose track of goals, module boundaries, risks, and why specific trade-offs were made.

## Decision

Every development task must begin by reading:

- `CONTEXT.md`
- `docs/architecture.md`
- `docs/risks.md`
- `docs/next.md`
- existing ADRs in `docs/adr/`

If these files are missing, create a minimal version before changing code. Each task must consider which project goal it serves, what module boundaries it touches, whether it violates existing ADRs, whether a smaller implementation is safer, and whether a new ADR is needed.

At task completion, update `docs/next.md` with:

- `Done`
- `Learned`
- `Risks`
- `Next`

## Alternatives Considered

- Keep project memory only in chat history. This fails because chat context is fragile and hard to audit.
- Put all notes in one README. This would mix project goals, architecture, risks, and decisions without clear ownership.
- Require ADRs for every change. This would create too much overhead for routine edits.

## Consequences

- Future work has a stable memory layer and clearer architecture boundaries.
- Development has a small documentation cost at the start and end of each task.
- Important architectural shifts become easier to review because they are recorded as ADRs when needed.
