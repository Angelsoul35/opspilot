"""The human-in-the-loop action gate.

opspilot proposes; a human disposes. This gate decides, for each step of a plan,
what would happen given the set of steps a human has explicitly approved. It is a
**dry run**: it never executes a real command. Steps that change the system
(``requires_approval``) are only ever marked as approved-to-run when their index
is in the approved set; everything else is advisory. This keeps a system-changing
action impossible without an explicit, recorded human decision.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from .assistant import IncidentPlan


class StepOutcome(StrEnum):
    ADVISORY = "advisory"  # informational or diagnostic; nothing to approve
    AWAITING_APPROVAL = "awaiting_approval"  # a system-changing action, not approved
    APPROVED_DRY_RUN = "approved_dry_run"  # approved by a human; shown as a dry run


@dataclass
class GatedStep:
    index: int
    description: str
    command: str | None
    outcome: StepOutcome


def apply(plan: IncidentPlan, approved: Iterable[int] = ()) -> list[GatedStep]:
    approved_set = set(approved)
    gated: list[GatedStep] = []
    for step in plan.steps:
        if not step.requires_approval:
            outcome = StepOutcome.ADVISORY
        elif step.index in approved_set:
            outcome = StepOutcome.APPROVED_DRY_RUN
        else:
            outcome = StepOutcome.AWAITING_APPROVAL
        gated.append(GatedStep(step.index, step.description, step.command, outcome))
    return gated


def pending_approvals(plan: IncidentPlan) -> list[int]:
    """Indices of steps that change the system and therefore need approval."""
    return [s.index for s in plan.steps if s.requires_approval]
