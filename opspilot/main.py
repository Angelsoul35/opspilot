"""opspilot HTTP API."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .service import OpsPilotService

app = FastAPI(
    title="opspilot",
    version="1.0.0",
    summary="Incident assistant over runbooks, with human-in-the-loop actions.",
)

_service: OpsPilotService | None = None


def get_service() -> OpsPilotService:
    global _service
    if _service is None:
        _service = OpsPilotService()
    return _service


class TriageRequest(BaseModel):
    incident: str = Field(min_length=1)


class PlanRequest(BaseModel):
    incident: str = Field(min_length=1)
    approved: list[int] = Field(default_factory=list)


@app.get("/health", tags=["ops"])
def health() -> dict:
    return {"status": "ok"}


@app.post("/triage", tags=["triage"])
def triage(request: TriageRequest) -> dict:
    return get_service().triage_as_dict(request.incident)


@app.post("/plan", tags=["triage"])
def plan(request: PlanRequest) -> dict:
    # Returns what WOULD run given the approved step indices (dry run only).
    return get_service().plan_with_approvals(request.incident, request.approved)
