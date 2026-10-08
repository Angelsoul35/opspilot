"""Orchestrate triage and the approval gate."""

from __future__ import annotations

from collections.abc import Iterable

from .assistant import Assistant, IncidentPlan
from .config import Settings, get_settings
from .gate import apply, pending_approvals
from .llm.base import LLMClient
from .llm.factory import build_llm
from .runbooks import RunbookLibrary


class OpsPilotService:
    def __init__(
        self,
        settings: Settings | None = None,
        llm: LLMClient | None = None,
        assistant: Assistant | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm = llm if llm is not None else build_llm(self.settings.llm_spec)
        self.assistant = assistant or Assistant(
            library=RunbookLibrary(),
            llm=self.llm,
            min_confidence=self.settings.min_confidence,
            max_tokens=self.settings.llm_max_tokens,
        )

    def triage(self, incident: str) -> IncidentPlan:
        return self.assistant.triage(incident)

    def triage_as_dict(self, incident: str) -> dict:
        plan = self.triage(incident)
        return {
            "runbook_id": plan.runbook_id,
            "title": plan.title,
            "confidence": plan.confidence,
            "needs_human_triage": plan.needs_human_triage,
            "summary": plan.summary,
            "summary_source": plan.summary_source,
            "pending_approvals": pending_approvals(plan),
            "steps": [
                {
                    "index": s.index,
                    "description": s.description,
                    "command": s.command,
                    "requires_approval": s.requires_approval,
                }
                for s in plan.steps
            ],
        }

    def plan_with_approvals(self, incident: str, approved: Iterable[int]) -> dict:
        plan = self.triage(incident)
        gated = apply(plan, approved)
        return {
            "runbook_id": plan.runbook_id,
            "title": plan.title,
            "steps": [
                {
                    "index": g.index,
                    "description": g.description,
                    "command": g.command,
                    "outcome": g.outcome.value,
                }
                for g in gated
            ],
        }
