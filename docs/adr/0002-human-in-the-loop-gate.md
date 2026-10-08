# ADR 0002: A human-in-the-loop gate for system-changing steps

## Status

Accepted.

## Context

Incident remediation includes steps that change production — scaling, restarting,
rolling back, extending volumes. Automating those without human judgement is how a
small incident becomes a large one. But diagnostics (read-only) should not need
ceremony. The assistant needs to treat the two kinds of step differently.

## Decision

Mark each step `requires_approval` iff it is an **action** carrying a command. The
gate resolves every step against the set of indices a human has **explicitly
approved**: an action becomes runnable only if its index is approved; otherwise it
is `awaiting_approval`; non-actions are `advisory`. And the gate performs a **dry
run** only — it never executes a live command.

## Consequences

- **No silent state changes.** A system-changing step cannot proceed without an
  explicit, indexed human decision; this is enforced in a few lines, not assumed.
- **Diagnostics flow freely.** Read-only steps are advisory and never block the
  on-call engineer with needless approvals.
- **Auditable intent.** The approved set is an explicit record of what a human
  authorised, suitable for an incident timeline.
- **Trade-off.** Requiring approval per action is slower than full automation.
  During an incident that friction is a feature, not a bug — and the gate makes
  the safe path (approve what you mean, see the rest as advisory) the easy one.
