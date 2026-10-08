"""Triage an incident: match a runbook, ground a plan, summarise.

The assistant never invents procedure. It matches the incident to the most
relevant runbook and builds the plan from that runbook's steps, flagging the ones
that change the system as requiring human approval. An LLM writes a short triage
summary grounded in the matched runbook; offline, an extractive summary is used.
A weak retrieval match is flagged for human triage rather than acted on.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .llm.base import LLMClient, LLMError
from .runbooks import RunbookLibrary

_SYSTEM = (
    "You are a site-reliability on-call assistant. Given an incident and the "
    "matched runbook, write a two-sentence triage: the likely cause and the first "
    "safe action. Be concise; do not invent steps outside the runbook."
)


@dataclass
class PlanStep:
    index: int
    description: str
    command: str | None
    requires_approval: bool


@dataclass
class IncidentPlan:
    runbook_id: str
    title: str
    confidence: float
    needs_human_triage: bool
    summary: str
    summary_source: str
    steps: list[PlanStep] = field(default_factory=list)


class Assistant:
    def __init__(
        self,
        library: RunbookLibrary | None = None,
        llm: LLMClient | None = None,
        min_confidence: float = 0.25,
        max_tokens: int = 200,
    ) -> None:
        self.library = library or RunbookLibrary()
        self.llm = llm
        self.min_confidence = min_confidence
        self.max_tokens = max_tokens

    def _summary(self, incident: str, runbook) -> tuple[str, str]:
        if self.llm is not None:
            steps = "; ".join(s.description for s in runbook.steps)
            prompt = f"Incident: {incident}\nRunbook: {runbook.title}\nSteps: {steps}"
            try:
                result = self.llm.complete(_SYSTEM, prompt, max_tokens=self.max_tokens)
                text = result.text.strip()
                if text:
                    return text, "llm"
            except LLMError:
                pass
        # Extractive fallback: the runbook title and its first step.
        first = runbook.steps[0].description if runbook.steps else ""
        return f"Likely matches '{runbook.title}'. First step: {first}", "extractive"

    def triage(self, incident: str) -> IncidentPlan:
        match = self.library.match(incident)
        rb = match.runbook
        summary, source = self._summary(incident, rb)
        steps = [
            PlanStep(
                index=i,
                description=s.description,
                command=s.command,
                requires_approval=bool(s.action and s.command),
            )
            for i, s in enumerate(rb.steps)
        ]
        return IncidentPlan(
            runbook_id=rb.id,
            title=rb.title,
            confidence=match.score,
            needs_human_triage=match.score < self.min_confidence,
            summary=summary,
            summary_source=source,
            steps=steps,
        )
