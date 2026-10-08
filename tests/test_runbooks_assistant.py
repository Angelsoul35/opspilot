from __future__ import annotations

from opspilot.assistant import Assistant
from opspilot.llm.fake import FailingLLM, FakeLLM
from opspilot.runbooks import RunbookLibrary


def test_match_finds_correct_runbook():
    lib = RunbookLibrary()
    assert lib.match("web node at 100% cpu, load average pegged").runbook.id == "rb-high-cpu"
    assert lib.match("no space left on device on the db host").runbook.id == "rb-disk-full"
    assert lib.match("tls certificate expired, handshake failing").runbook.id == "rb-cert-expiry"


def test_match_is_robust_to_reworded_incident():
    # An operator writes "503s" (plural), not the runbook's "503"; a word-only
    # matcher shares no token and misroutes. The character n-gram view aligns
    # "503s" with "503" so the 5xx runbook is still the top match.
    lib = RunbookLibrary()
    assert lib.match("the api is returning lots of 503s after the deploy").runbook.id == "rb-5xx"


def test_match_scores_in_domain_above_out_of_domain():
    # The confidence score must separate incidents a runbook genuinely covers from
    # ones it does not, so the triage gate can flag the latter. This is the
    # property the min_confidence default relies on — asserted, not assumed.
    lib = RunbookLibrary()
    in_domain = [
        "web node at 100% cpu, load average pegged",
        "database volume is full, writes are failing",
        "elevated 5xx errors, bad gateway from upstream",
        "tls certificate expired, handshake failing",
    ]
    out_of_domain = [
        "users cannot log in, the SSO redirect loops",
        "the mobile app crashes on startup",
        "oom killer terminated the java process",
        "what is the on-call rotation this week",
    ]
    worst_in = min(lib.match(q).score for q in in_domain)
    best_out = max(lib.match(q).score for q in out_of_domain)
    # A real gap, with the 0.30 default sitting inside it.
    assert best_out < 0.30 < worst_in


def test_plan_flags_action_steps_for_approval():
    plan = Assistant(llm=None).triage("elevated 5xx errors, bad gateway from upstream")
    assert plan.runbook_id == "rb-5xx"
    # The rollback step changes the system and must require approval.
    rollback = [s for s in plan.steps if "roll back" in s.description.lower()][0]
    assert rollback.requires_approval is True
    # A diagnostic (read-only) step does not.
    diag = [s for s in plan.steps if "error logs" in s.description.lower()][0]
    assert diag.requires_approval is False


def test_out_of_domain_incident_flags_human_triage_at_default_threshold():
    # At the DEFAULT threshold (no override), an incident no runbook covers is
    # flagged for a human instead of being silently matched to the nearest book.
    plan = Assistant(llm=None).triage("users cannot log in, the SSO redirect loops")
    assert plan.needs_human_triage is True


def test_gibberish_flags_human_triage_at_default_threshold():
    plan = Assistant(llm=None).triage("zzz qqq unrelated gibberish")
    assert plan.needs_human_triage is True


def test_in_domain_incident_is_confident_at_default_threshold():
    # A clearly in-domain incident clears the default threshold and is NOT flagged
    # for triage — the gate must not cry wolf on every incident.
    plan = Assistant(llm=None).triage("database volume is full, writes are failing")
    assert plan.runbook_id == "rb-disk-full"
    assert plan.needs_human_triage is False


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
