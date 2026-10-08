from __future__ import annotations

from fastapi.testclient import TestClient

from opspilot import cli
from opspilot.assistant import Assistant
from opspilot.gate import StepOutcome, apply, pending_approvals
from opspilot.llm.fake import FailingLLM
from opspilot.service import OpsPilotService


def _plan(incident="web node at 100% cpu, load average pegged"):
    return Assistant(llm=FailingLLM()).triage(incident)


def test_gate_requires_approval_for_actions():
    plan = _plan()
    pending = pending_approvals(plan)
    assert pending  # there are system-changing steps

    # With nothing approved, every action step is awaiting approval.
    gated = apply(plan, approved=())
    outcomes = {g.index: g.outcome for g in gated}
    assert all(outcomes[i] is StepOutcome.AWAITING_APPROVAL for i in pending)

    # Approving one action turns only that one into an approved dry run.
    gated = apply(plan, approved=[pending[0]])
    outcomes = {g.index: g.outcome for g in gated}
    assert outcomes[pending[0]] is StepOutcome.APPROVED_DRY_RUN
    for i in pending[1:]:
        assert outcomes[i] is StepOutcome.AWAITING_APPROVAL


def test_non_action_steps_are_advisory():
    gated = apply(_plan(), approved=())
    advisory = [g for g in gated if g.outcome is StepOutcome.ADVISORY]
    assert advisory  # diagnostics are advisory, never gated


def _service():
    return OpsPilotService(llm=FailingLLM())


def test_service_dicts():
    svc = _service()
    triage = svc.triage_as_dict("no space left on device on db host")
    assert triage["runbook_id"] == "rb-disk-full"
    assert triage["pending_approvals"]

    planned = svc.plan_with_approvals("no space left on device on db host", approved=[])
    assert any(s["outcome"] == "awaiting_approval" for s in planned["steps"])


def test_api():
    import opspilot.main as main

    main._service = _service()
    client = TestClient(main.app)
    assert client.get("/health").json() == {"status": "ok"}

    triage = client.post("/triage", json={"incident": "tls certificate expired"})
    assert triage.status_code == 200
    assert triage.json()["runbook_id"] == "rb-cert-expiry"

    plan = client.post("/plan", json={"incident": "tls certificate expired", "approved": []})
    assert plan.status_code == 200
    assert any(s["outcome"] == "awaiting_approval" for s in plan.json()["steps"])

    assert client.post("/triage", json={"incident": ""}).status_code == 422


def test_cli_demo(capsys):
    cli.demo()
    out = capsys.readouterr().out
    assert "APPROVE?" in out
    assert "High CPU" in out


def test_cli_main_dispatch(monkeypatch):
    called = {"demo": False}
    monkeypatch.setattr(cli, "demo", lambda: called.__setitem__("demo", True))
    monkeypatch.setattr("sys.argv", ["opspilot", "demo"])
    cli.main()
    assert called["demo"] is True
