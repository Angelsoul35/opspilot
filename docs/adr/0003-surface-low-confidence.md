# ADR 0003: Surface a weak runbook match instead of trusting it

## Status

Accepted.

## Context

Retrieval always returns a best match, even for an incident no runbook covers. If
the assistant presented that best guess with the same confidence as a strong
match, an on-call engineer could follow a runbook meant for a different problem —
worse than having no runbook at all.

## Decision

Keep the retrieval **confidence** (cosine score) and, when it is below
`OP_MIN_CONFIDENCE`, set `needs_human_triage` on the plan. The best-guess runbook
is still returned — it may be a useful lead — but the plan explicitly says the
match is weak and a human should decide.

## Consequences

- **No false confidence.** A weak match is labelled as such, so it is not followed
  blindly.
- **Still helpful.** The best guess and its steps are available as a starting
  point rather than withheld entirely.
- **Tunable.** The threshold is one configurable number, trading more automation
  against more human triage to suit a team's runbook coverage.
- **Trade-off.** A fixed cosine threshold is coarse and corpus-dependent — it may
  flag a genuine match as weak or vice versa near the boundary. Erring toward
  flagging is the safe direction, and the threshold is where a team calibrates it
  as their runbook library grows.
