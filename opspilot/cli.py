"""opspilot command-line demo."""

from __future__ import annotations

import argparse

from .gate import apply
from .service import OpsPilotService

INCIDENTS = [
    "Pager: web nodes at 100% CPU, latency climbing, load average pegged.",
    "Database host alert: no space left on device, writes failing.",
    "TLS handshake failures: the certificate appears to have expired.",
]


def demo() -> None:
    print("1) Triaging incidents against the runbook library")
    print("   (LLM triage summary -> extractive fallback; actions need approval)\n")
    service = OpsPilotService()
    for incident in INCIDENTS:
        plan = service.triage(incident)
        print(f'   Incident: "{incident}"')
        flag = " [LOW MATCH -> human triage]" if plan.needs_human_triage else ""
        print(f"   -> runbook: {plan.title} (confidence {plan.confidence:.2f}){flag}")
        print(f"      triage [{plan.summary_source}]: {plan.summary}")
        for g in apply(plan, approved=()):
            tag = {"advisory": "   ", "awaiting_approval": "APPROVE?",
                   "approved_dry_run": "APPROVED"}[g.outcome.value]
            cmd = f"  $ {g.command}" if g.command else ""
            print(f"        [{tag:8}] {g.description}{cmd}")
        print()
    print("Note: system-changing steps show [APPROVE?] and never run until a human")
    print("approves them; opspilot only ever performs a dry run.")


def main() -> None:
    parser = argparse.ArgumentParser(description="opspilot CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="triage sample incidents against the runbooks")
    args = parser.parse_args()
    if args.command == "demo":
        demo()


if __name__ == "__main__":
    main()
