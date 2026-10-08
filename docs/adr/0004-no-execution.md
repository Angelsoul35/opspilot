# ADR 0004: The assistant proposes; it does not execute

## Status

Accepted.

## Context

It is tempting to let opspilot run the approved commands itself. But doing so means
the assistant holds production credentials and becomes the component that can
change the world — a large, security-critical responsibility (audit logging, RBAC,
change records, rollback) that is a whole system in its own right.

## Decision

Stop at a **dry run**. The gate reports what *would* run given the approvals;
actually executing an approved step is delegated to a separate, audited executor
outside this library. opspilot never executes a real command and never needs
production credentials.

## Consequences

- **Small, trustworthy blast radius.** A bug in the assistant cannot change
  production, because the assistant has no ability to; it only produces plans and
  enforces the approval rule.
- **Clean separation of concerns.** Advising (and gating) is separate from
  executing, so each can be built, reviewed and secured on its own terms.
- **Composable.** The approved plan is a clear handoff to any executor with the
  right controls.
- **Trade-off.** It is not a one-click "fix it" button; a human or a separate
  executor still has to run the approved steps. For a tool that touches production
  during incidents, not holding the credentials is the responsible default, and
  the executor is a deliberate, separately-audited future component rather than an
  afterthought bolted onto the advisor.
