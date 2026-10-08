from __future__ import annotations

from opspilot.assistant import Assistant
from opspilot.llm.fake import FailingLLM, FakeLLM
from opspilot.runbooks import RunbookLibrary


def test_match_finds_correct_runbook():
    lib = RunbookLibrary()
    assert lib.match("web node at 100% cpu, load average pegged").runbook.id == "rb-high-cpu"
    assert lib.match("no space left on device on the db host").runbook.id == "rb-disk-full"
    assert lib.match("tls certificate expired, handshake failing").runbook.id == "rb-cert-expiry"


def test_plan_flags_action_steps_for_approval():
    plan = Assistant(llm=None).triage("elevated 5xx errors, bad gateway from upstream")
    assert plan.runbook_id == "rb-5xx"
    # The rollback step changes the system and must require approval.
    rollback = [s for s in plan.steps if "roll back" in s.description.lower()][0]
    assert rollback.requires_approval is True
    # A diagnostic (read-only) step does not.
    diag = [s for s in plan.steps if "error logs" in s.description.lower()][0]
    assert diag.requires_approval is False


def test_low_confidence_flags_human_triage():
    plan = Assistant(llm=None, min_confidence=0.5).triage("zzz qqq unrelated gibberish")
    assert plan.needs_human_triage is True


def test_summary_llm_path():
    plan = Assistant(llm=FakeLLM("Likely a CPU regression; confirm the hot process first.")).triage(
        "web node at 100% cpu"
    )
    assert plan.summary_source == "llm"
    assert "CPU" in plan.summary


def test_summary_extractive_fallback():
    plan = Assistant(llm=FailingLLM()).triage("web node at 100% cpu")
    assert plan.summary_source == "extractive"
    assert "High CPU" in plan.summary
