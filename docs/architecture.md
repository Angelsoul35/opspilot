# Architecture

opspilot triages an incident against runbooks and gates any system-changing step
behind human approval. This document describes the pieces, the data flow, and the
safety model.

## The pieces

| Layer     | Module                 | Responsibility                                        |
| --------- | ---------------------- | ----------------------------------------------------- |
| Runbooks  | `opspilot/runbooks.py` | The runbook library and TF-IDF retrieval              |
| Assistant | `opspilot/assistant.py`| Ground a plan in the matched runbook + triage summary |
| Gate      | `opspilot/gate.py`     | Resolve each step against the set of human approvals  |
| LLM       | `opspilot/llm/`        | Provider-agnostic client with a fallback cascade      |
| Orchestration | `opspilot/service.py`| Triage and apply approvals                           |
| HTTP API  | `opspilot/main.py`     | `/triage` and `/plan`                                 |
| CLI       | `opspilot/cli.py`      | Demo                                                  |

## Data flow

```
 incident ─▶ library.match ─▶ runbook + confidence
          ─▶ assistant.triage ─▶ plan (steps from runbook, actions flagged) + summary
          ─▶ gate.apply(plan, approved) ─▶ advisory / awaiting_approval / approved_dry_run
```

## Two safety properties, by construction

opspilot is designed so that two things are structurally true, not merely
intended:

1. **Advice is grounded.** The plan's steps are copied from the matched runbook;
   the assistant never adds a step. The LLM is given the incident and the runbook
   and asked only to *summarise* — it is explicitly told not to invent steps, and
   even if it tried, its output is the `summary` field, not the `steps`. So a
   hallucinated command cannot enter the plan.
2. **Nothing changes without approval.** A step is marked `requires_approval` iff
   it is an action carrying a command. The gate turns a step into
   `approved_dry_run` only when its index is in the human-approved set; otherwise
   it is `awaiting_approval`. There is no code path that runs an action without an
   explicit, indexed human decision — and the gate performs a dry run regardless.

## Retrieval and the confidence flag

`RunbookLibrary` fits TF-IDF over each runbook's title, symptoms and step
descriptions, and matches an incident by cosine similarity. The match carries a
score. When the score is below `OP_MIN_CONFIDENCE`, the plan sets
`needs_human_triage`: the best guess is still returned (it may help), but the
assistant signals that it is not confident the right runbook was found, so a human
should decide rather than trust the match. This is the same posture as the other
retrieval tools in the portfolio — surface uncertainty, do not hide it.

## The gate is the whole safety model

`gate.apply` is tiny on purpose: given a plan and a set of approved indices, it
classifies each step. The simplicity is the point — the rule that "a
system-changing step runs only if a human approved its index" is a few lines that
can be read and trusted in full, rather than buried in a larger execution engine.
`pending_approvals` lists exactly which steps need a decision, so a UI or a chat
flow can ask for them.

## Why execution is out of scope

opspilot deliberately stops at the dry run. Actually executing an approved step
needs production credentials, an audit log, RBAC, and a change record — a
security-critical executor that is a separate system. Keeping it out means the
assistant never holds the keys to production; it proposes and enforces approval,
and hands an approved, explicit plan to whatever does hold them. That separation
is safer than a single component that both advises and executes.

## Extension points

- **Runbooks.** Add `Runbook`s with symptoms and steps; retrieval and gating pick
  them up unchanged.
- **Retrieval.** TF-IDF can be swapped for a dense retriever behind the same
  `match` interface.
- **Executor.** An audited executor can consume an approved plan from the gate,
  outside this library.
