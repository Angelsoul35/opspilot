"""Functional tests for the real-data loader, retrieval engine, and benchmark.

These assert behaviour, not formatting: the vendored corpus really is the public
dataset (counts and labels), the engine ranks correctly, the routing metric beats
the right baselines on held-out data while staying below a leak-free ceiling, the
shuffled-label control collapses it to chance, and the fetch path parses and
paginates a stand-in rows API without a network call.
"""

from __future__ import annotations

import io
import json
from urllib.parse import parse_qs, urlparse

import pytest

from opspilot import real_benchmark, real_data
from opspilot.real_benchmark import (
    build_library,
    classify_fit,
    format_report,
    route,
    run_benchmark,
)
from opspilot.real_data import (
    MAX_INPUT_CHARS,
    Incident,
    fetch_incidents,
    load_incidents,
    service_counts,
    top_services,
    vendor_dataset,
)
from opspilot.runbooks import RunbookLibrary

# A handful of services known to be in Loukh1/IT-incidents.
KNOWN_SERVICES = {"Docker", "Kubernetes", "MySQL", "OpenShift", "MongoDB"}


# --------------------------------------------------------------------------- #
# Shared, expensive fixtures (loaded / computed once).
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def incidents() -> list[Incident]:
    return load_incidents()


@pytest.fixture(scope="module")
def result():
    return run_benchmark()


# --------------------------------------------------------------------------- #
# The vendored corpus is the real dataset.
# --------------------------------------------------------------------------- #
def test_loader_returns_the_real_dataset(incidents):
    # 3252 real tickets across 26 services — the published size of the dataset.
    assert len(incidents) == 3252
    counts = service_counts(incidents)
    assert len(counts) == 26
    assert KNOWN_SERVICES <= set(counts)
    # Every ticket carries a routable service label and real ticket text.
    assert all(inc.service and inc.text for inc in incidents)


def test_ticket_text_is_truncated_real_text(incidents):
    # Real, non-trivial text, truncated to keep the checked-in file small.
    assert all(len(inc.text) <= MAX_INPUT_CHARS for inc in incidents)
    assert max(len(inc.text) for inc in incidents) > 100


def test_top_services_are_the_most_frequent(incidents):
    counts = service_counts(incidents)
    selected = top_services(incidents, 12)
    assert len(selected) == 12
    # Each selected service is at least as frequent as every unselected one.
    least_selected = min(counts[s] for s in selected)
    rest = [c for s, c in counts.items() if s not in set(selected)]
    assert least_selected >= max(rest)
    # Docker is the single most frequent service in this dataset.
    assert selected[0] == "Docker"


def test_loader_filters_to_requested_services(incidents):
    subset = load_incidents(services={"Docker", "MySQL"})
    assert {inc.service for inc in subset} == {"Docker", "MySQL"}
    assert 0 < len(subset) < len(incidents)


# --------------------------------------------------------------------------- #
# The retrieval engine: top-k ranking and batching.
# --------------------------------------------------------------------------- #
def test_rank_is_sorted_and_agrees_with_match():
    lib = RunbookLibrary()
    ranked = lib.rank("tls certificate expired, handshake failing", k=4)
    assert [m.runbook.id for m in ranked][0] == "rb-cert-expiry"
    scores = [m.score for m in ranked]
    assert scores == sorted(scores, reverse=True)
    assert lib.rank("tls certificate expired")[0].runbook.id == lib.match(
        "tls certificate expired"
    ).runbook.id


def test_rank_batch_equals_per_incident_rank():
    lib = RunbookLibrary()
    queries = ["web node at 100% cpu", "no space left on device", "502 bad gateway from upstream"]
    batched = lib.rank_batch(queries, k=2)
    assert [[m.runbook.id for m in row] for row in batched] == [
        [m.runbook.id for m in lib.rank(q, k=2)] for q in queries
    ]
    assert all(len(row) == 2 for row in batched)


def test_build_library_makes_one_runbook_per_service():
    sample = [
        Incident("Docker", "container keeps restarting crashloop"),
        Incident("Docker", "image pull backoff registry timeout"),
        Incident("MySQL", "query timeouts and deadlocks on the primary"),
    ]
    lib = build_library(sample)
    assert {rb.id for rb in lib.runbooks} == {"Docker", "MySQL"}
    # The MySQL runbook is routed to for a MySQL-flavoured incident.
    assert lib.match("deadlock detected, mysql query timed out").runbook.id == "MySQL"


# --------------------------------------------------------------------------- #
# The routing metric beats the baselines and generalises.
# --------------------------------------------------------------------------- #
def test_holdout_beats_baselines_without_leaking_to_perfect(result):
    ho = result.holdout
    # Comfortably above both baselines...
    assert ho.top1 > result.majority_baseline + 0.30
    assert ho.top1 > result.random_baseline + 0.30
    # ...but not a suspicious perfect score: 12 real services do not separate 1.0.
    assert ho.top1 < 0.99
    # Top-3 can only help, and macro-F1 confirms it is not a frequent-class trick.
    assert ho.top3 >= ho.top1
    assert ho.macro_f1 > result.majority_baseline + 0.30


def test_cross_validation_is_stable_and_above_baseline(result):
    cv = result.cv
    assert cv["top1_mean"] > result.majority_baseline + 0.30
    assert cv["top1_std"] < 0.05  # low variance across folds
    assert cv["top3_mean"] >= cv["top1_mean"]
    # Train and held-out agree closely: a small, leak-free generalisation gap.
    assert abs(cv["gap_mean"]) < 0.10


def test_shuffled_label_control_collapses_to_chance(result):
    # Relabelling the training tickets at random must destroy the signal.
    assert result.control_top1 < result.majority_baseline + 0.05
    assert result.control_top1 < result.cv["top1_mean"] - 0.50


def test_verdict_is_well_fit(result):
    assert result.fit_label == "well-fit"


def test_route_wraps_rank():
    lib = build_library(
        [Incident("Docker", "crashloop restart"), Incident("MySQL", "deadlock timeout")]
    )
    expected = [m.runbook.id for m in lib.rank("mysql deadlock", k=2)]
    assert route(lib, "mysql deadlock", k=2) == expected
    assert len(route(lib, "anything", k=2)) == 2


def test_report_reflects_the_measured_numbers(result):
    text = format_report(result)
    assert "real IT incidents" in text
    assert "WELL-FIT" in text
    assert f"{result.cv['top1_mean']:.3f}" in text
    assert "Shuffled-label control" in text


def test_main_prints_the_report(result, monkeypatch, capsys):
    monkeypatch.setattr(real_benchmark, "run_benchmark", lambda: result)
    real_benchmark.main()
    out = capsys.readouterr().out
    assert "WELL-FIT" in out
    assert "top-1 accuracy" in out


def test_classify_fit_distinguishes_the_three_regimes():
    base = 0.14
    well = {"top1_mean": 0.89, "train_top1_mean": 0.90, "gap_mean": 0.01, "top1_std": 0.01}
    over = {"top1_mean": 0.60, "train_top1_mean": 0.99, "gap_mean": 0.39, "top1_std": 0.02}
    under = {"top1_mean": 0.20, "train_top1_mean": 0.22, "gap_mean": 0.02, "top1_std": 0.02}
    assert classify_fit(well, base)[0] == "well-fit"
    assert classify_fit(over, base)[0] == "overfit"
    assert classify_fit(under, base)[0] == "underfit"


# --------------------------------------------------------------------------- #
# The fetch path, with a stand-in urlopen (no network).
# --------------------------------------------------------------------------- #
def _make_fake_rows(total: int) -> list[dict]:
    return [
        {
            "service": f"svc{i % 3}",
            "input": f"Ticket {i}: something broke on host {i}",
            "response": f"Diagnosis {i}. Resolution: restart {i}.",
        }
        for i in range(total)
    ]


def _fake_urlopen_factory(
    all_rows: list[dict], fail_times: int = 0, claimed_total: int | None = None
):
    state = {"fails": fail_times}

    def fake_urlopen(request, timeout=60):
        if state["fails"] > 0:
            state["fails"] -= 1
            raise OSError("transient network error")
        query = parse_qs(urlparse(request.full_url).query)
        offset = int(query["offset"][0])
        length = int(query["length"][0])
        page = all_rows[offset : offset + length]
        body = {
            "rows": [{"row": row} for row in page],
            "num_rows_total": len(all_rows) if claimed_total is None else claimed_total,
        }
        return io.BytesIO(json.dumps(body).encode("utf-8"))

    return fake_urlopen


def test_fetch_incidents_paginates(monkeypatch):
    rows = _make_fake_rows(7)
    monkeypatch.setattr(real_data, "urlopen", _fake_urlopen_factory(rows))
    fetched = fetch_incidents(page_size=3)
    assert len(fetched) == 7
    assert [r["service"] for r in fetched] == [r["service"] for r in rows]
    assert fetched[0]["input"].startswith("Ticket 0:")


def test_fetch_incidents_respects_limit(monkeypatch):
    rows = _make_fake_rows(50)
    monkeypatch.setattr(real_data, "urlopen", _fake_urlopen_factory(rows))
    fetched = fetch_incidents(limit=5, page_size=3)
    assert len(fetched) == 5


def test_fetch_incidents_retries_then_succeeds(monkeypatch):
    rows = _make_fake_rows(4)
    monkeypatch.setattr(real_data, "urlopen", _fake_urlopen_factory(rows, fail_times=2))
    fetched = fetch_incidents(page_size=10, retries=4, sleep=lambda _: None)
    assert len(fetched) == 4


def test_fetch_incidents_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(real_data, "urlopen", _fake_urlopen_factory([], fail_times=99))
    with pytest.raises(RuntimeError):
        fetch_incidents(page_size=10, retries=3, sleep=lambda _: None)


def test_fetch_incidents_stops_on_empty_page(monkeypatch):
    # The API claims more rows than it actually serves; an empty page ends paging.
    rows = _make_fake_rows(4)
    monkeypatch.setattr(real_data, "urlopen", _fake_urlopen_factory(rows, claimed_total=1000))
    assert len(fetch_incidents(page_size=4)) == 4


def test_fetch_incidents_zero_limit_returns_nothing(monkeypatch):
    monkeypatch.setattr(real_data, "urlopen", _fake_urlopen_factory(_make_fake_rows(5)))
    assert fetch_incidents(limit=0) == []


def test_loader_skips_blank_lines(tmp_path):
    path = tmp_path / "d.jsonl"
    path.write_text(
        '{"service": "A", "text": "foo", "response": "r"}\n'
        "\n"
        '{"service": "B", "text": "bar"}\n'
    )
    loaded = load_incidents(path)
    assert [inc.service for inc in loaded] == ["A", "B"]
    assert loaded[1].response == ""


def test_vendor_dataset_writes_truncated_jsonl(monkeypatch, tmp_path):
    rows = _make_fake_rows(6)
    rows[0]["input"] = "X " * 1000  # a very long ticket to force truncation
    rows[1]["input"] = "   "  # an empty ticket: must be dropped, not written
    monkeypatch.setattr(real_data, "urlopen", _fake_urlopen_factory(rows))
    out = tmp_path / "sub.jsonl"
    written = vendor_dataset(out, max_input=50, max_response=40)
    assert written == 5  # the empty ticket was skipped
    records = [json.loads(line) for line in out.read_text().splitlines()]
    assert {r["service"] for r in records} == {"svc0", "svc1", "svc2"}
    assert all(len(r["text"]) <= 50 for r in records)
    assert all(len(r["response"]) <= 40 for r in records)
    # The loader round-trips what the vendor wrote.
    loaded = load_incidents(out)
    assert len(loaded) == 5
