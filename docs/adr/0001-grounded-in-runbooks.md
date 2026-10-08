# ADR 0001: Advice grounded in runbooks, never invented

## Status

Accepted.

## Context

An LLM asked "how do I fix this outage?" will happily produce plausible-sounding
commands — including ones that are wrong, dangerous, or hallucinated. During an
incident, acting on an invented `kubectl delete` or `DROP TABLE` is exactly the
failure mode that must be impossible.

## Decision

Ground every plan in a **vetted runbook**. The assistant retrieves the most
relevant runbook and builds the plan's steps **from that runbook**. The LLM is
given the incident and the runbook and asked only to write a short triage
*summary*; it is told not to invent steps, and structurally its output lands in
the `summary` field, never in `steps`.

## Consequences

- **No hallucinated steps.** A command can only appear in a plan if it is in a
  runbook a human wrote and reviewed.
- **The LLM stays in a safe lane.** It improves readability (a concise triage)
  without being trusted to decide what to do.
- **Advice is as good as the runbooks.** Coverage comes from writing runbooks, a
  reviewed artefact, not from prompting — which is where operational knowledge
  should live anyway.
- **Trade-off.** An incident with no matching runbook gets only a weak,
  low-confidence match. That is surfaced (see ADR 0003) as "needs human triage"
  rather than papered over with an invented plan — the honest and safe behaviour.
