"""opspilot command-line demo."""

from __future__ import annotations

import argparse

from .gate import apply, pending_approvals
from .service import OpsPilotService

# In-domain incidents, each matching a different runbook.
INCIDENTS = [
    "Pager: web nodes at 100% CPU, latency climbing, load average pegged.",
    "Database host alert: no space left on device, writes failing.",
    "TLS handshake failures: the certificate appears to have expired.",
]
# An incident no runbook covers: it must be flagged for a human, not matched.
OUT_OF_DOMAIN = "Users report the SSO login redirect is looping and nobody can sign in."

_TAGS = {
    "advisory": "   ",
    "awaiting_approval": "APPROVE?",
    "approved_dry_run": "APPROVED",
}


def _print_plan(plan, approved=()) -> None:
    for g in apply(plan, approved=approved):
        cmd = f"  $ {g.command}" if g.command else ""
        print(f"        [{_TAGS[g.outcome.value]:8}] {g.description}{cmd}")


def demo() -> None:
    service = OpsPilotService()

    print("1) Triaging incidents against the runbook library")
    print("   (LLM triage summary -> extractive fallback; actions need approval)\n")
    for incident in INCIDENTS:
        plan = service.triage(incident)
        print(f'   Incident: "{incident}"')
        flag = " [LOW MATCH -> human triage]" if plan.needs_human_triage else ""
        print(f"   -> runbook: {plan.title} (confidence {plan.confidence:.2f}){flag}")
        print(f"      triage [{plan.summary_source}]: {plan.summary}")
        _print_plan(plan)
        print()

    print("2) An incident no runbook covers is flagged, not force-matched")
    plan = service.triage(OUT_OF_DOMAIN)
    print(f'   Incident: "{OUT_OF_DOMAIN}"')
    flag = " [LOW MATCH -> human triage]" if plan.needs_human_triage else ""
    print(f"   -> nearest runbook: {plan.title} (confidence {plan.confidence:.2f}){flag}")
    print("      The low score means retrieval found no runbook that really fits, so")
    print("      opspilot hands the incident to a human instead of acting on a bad match.\n")

    print("3) The action gate: nothing system-changing runs until a human approves it")
    plan = service.triage(INCIDENTS[2])  # the TLS certificate incident
    actions = pending_approvals(plan)
    print(f"   runbook: {plan.title}  (approvals needed for steps {actions})")
    print(f"   Before approval — step {actions[0]} is withheld:")
    _print_plan(plan, approved=())
    print(f"   After a human approves step {actions[0]} — it becomes an explicit dry run:")
    _print_plan(plan, approved=(actions[0],))

    print("\nNote: system-changing steps show [APPROVE?] and never run until a human")
    print("approves them; opspilot only ever performs a dry run, never a live command.")


def main() -> None:
    parser = argparse.ArgumentParser(description="opspilot CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="triage sample incidents against the runbooks")
    args = parser.parse_args()
    if args.command == "demo":
        demo()


if __name__ == "__main__":
    main()
