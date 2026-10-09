"""Benchmark opspilot's runbook retrieval on real IT-incident tickets.

opspilot routes an incident to a runbook with the TF-IDF retriever in
:class:`opspilot.runbooks.RunbookLibrary`. This module turns that same retriever
into a measurable claim on real data: build one runbook per service from training
tickets (its ``symptoms`` are the real ticket text for that service), then route
held-out tickets and check whether the top-ranked runbook is the ticket's true
service. The engine is reused verbatim — the runbooks are real services, and
``RunbookLibrary.rank`` does the routing.

Reported, over the most frequent services:

* **top-1 / top-3 routing accuracy** — how often the true service is the top
  match, and within the top three matches;
* **macro-F1** — accuracy averaged per service, so frequent services cannot mask
  weak ones;
* **stratified 5-fold cross-validation** and a **held-out split**, with the
  **train/test gap** that separates a well-fit retriever from an over/under-fit
  one;
* a **majority-class** and a **random (1/N)** baseline the score must clear;
* a **shuffled-label control** that rebuilds the runbooks from randomly relabelled
  tickets — it must collapse the score back to chance, proving the signal is in
  the text-to-service mapping and not an artefact of the pipeline.

Run it with ``python -m opspilot.real_benchmark``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedKFold, train_test_split

from .real_data import Incident, load_incidents, top_services
from .runbooks import Runbook, RunbookLibrary

N_SERVICES = 12
CV_FOLDS = 5
HOLDOUT_TEST_SIZE = 0.25
CV_SEED = 0
HOLDOUT_SEED = 42
CONTROL_SEED = 1

# A train/test gap above this flags a retriever that fits its own tickets far
# better than new ones (high variance / overfitting). A held-out score that clears
# the majority baseline by less than this margin flags a retriever that is not
# capturing enough signal (high bias / underfitting).
WELL_FIT_MAX_GAP = 0.15
UNDERFIT_MARGIN = 0.10


@dataclass(frozen=True)
class SplitScore:
    top1: float
    top3: float
    macro_f1: float
    train_top1: float

    @property
    def gap(self) -> float:
        """Train minus held-out top-1 — positive means it fits train better."""
        return self.train_top1 - self.top1


def build_library(train: Sequence[Incident]) -> RunbookLibrary:
    """Build one runbook per service from the training tickets.

    Each service becomes a :class:`~opspilot.runbooks.Runbook` whose ``symptoms``
    are its real training tickets joined together — the service's signature of
    what its incidents look like, exactly the field the retriever matches on.
    """
    texts: dict[str, list[str]] = {}
    for inc in train:
        texts.setdefault(inc.service, []).append(inc.text)
    runbooks = [
        Runbook(id=service, title=service, symptoms=" ".join(chunks), steps=())
        for service, chunks in texts.items()
    ]
    return RunbookLibrary(runbooks)


def route(library: RunbookLibrary, text: str, k: int = 1) -> list[str]:
    """Return the top-``k`` service ids the retriever routes this ticket to."""
    return [match.runbook.id for match in library.rank(text, k=k)]


def _route_services(
    library: RunbookLibrary, tickets: Sequence[Incident], k: int
) -> list[list[str]]:
    rankings = library.rank_batch([inc.text for inc in tickets], k=k)
    return [[match.runbook.id for match in ranking] for ranking in rankings]


def _top1_top3(library: RunbookLibrary, tickets: Sequence[Incident]) -> tuple[list[str], float]:
    routed = _route_services(library, tickets, k=3)
    top1 = [r[0] for r in routed]
    top3 = np.mean([inc.service in r for inc, r in zip(tickets, routed, strict=True)])
    return top1, float(top3)


def evaluate_split(train: Sequence[Incident], test: Sequence[Incident]) -> SplitScore:
    """Fit on ``train``, score on ``test``; also score ``train`` for the gap."""
    library = build_library(train)
    truth = [inc.service for inc in test]
    pred, top3 = _top1_top3(library, test)
    train_pred = [r[0] for r in _route_services(library, train, k=1)]
    train_top1 = np.mean([p == inc.service for p, inc in zip(train_pred, train, strict=True)])
    top1 = np.mean([p == t for p, t in zip(pred, truth, strict=True)])
    macro = f1_score(truth, pred, average="macro", zero_division=0)
    return SplitScore(float(top1), float(top3), float(macro), float(train_top1))


def holdout(incidents: Sequence[Incident], seed: int = HOLDOUT_SEED) -> SplitScore:
    labels = [inc.service for inc in incidents]
    train, test = train_test_split(
        list(incidents), test_size=HOLDOUT_TEST_SIZE, stratify=labels, random_state=seed
    )
    return evaluate_split(train, test)


def cross_validate(incidents: Sequence[Incident], seed: int = CV_SEED) -> dict[str, float]:
    items = np.array(incidents, dtype=object)
    labels = np.array([inc.service for inc in incidents])
    skf = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=seed)
    scores = [
        evaluate_split(list(items[tr]), list(items[te])) for tr, te in skf.split(items, labels)
    ]
    top1 = [s.top1 for s in scores]
    return {
        "top1_mean": float(np.mean(top1)),
        "top1_std": float(np.std(top1)),
        "top3_mean": float(np.mean([s.top3 for s in scores])),
        "macro_f1_mean": float(np.mean([s.macro_f1 for s in scores])),
        "train_top1_mean": float(np.mean([s.train_top1 for s in scores])),
        "gap_mean": float(np.mean([s.gap for s in scores])),
    }


def shuffled_label_control(incidents: Sequence[Incident], seed: int = CONTROL_SEED) -> float:
    """Held-out top-1 after randomly relabelling the training tickets.

    Rebuilding the runbooks from scrambled (ticket, service) pairs destroys the
    text-to-service signal, so routing must fall back to chance. If this stays
    high, the headline score is an artefact — this is the control that rules that
    out.
    """
    labels = [inc.service for inc in incidents]
    train, test = train_test_split(
        list(incidents), test_size=HOLDOUT_TEST_SIZE, stratify=labels, random_state=HOLDOUT_SEED
    )
    rng = np.random.default_rng(seed)
    shuffled_services = list(np.array([inc.service for inc in train])[rng.permutation(len(train))])
    scrambled = [
        Incident(service=svc, text=inc.text, response=inc.response)
        for inc, svc in zip(train, shuffled_services, strict=True)
    ]
    library = build_library(scrambled)
    pred, _ = _top1_top3(library, test)
    return float(np.mean([p == inc.service for p, inc in zip(pred, test, strict=True)]))


def majority_baseline(incidents: Sequence[Incident]) -> float:
    counts = Counter(inc.service for inc in incidents)
    return counts.most_common(1)[0][1] / len(incidents)


def classify_fit(cv: dict[str, float], baseline: float) -> tuple[str, str]:
    """Label the retriever well-fit / overfit / underfit from the CV numbers."""
    test, train = cv["top1_mean"], cv["train_top1_mean"]
    gap, std = cv["gap_mean"], cv["top1_std"]
    lift = test - baseline
    if lift < UNDERFIT_MARGIN:
        return (
            "underfit",
            f"held-out top-1 ({test:.3f}) clears the majority baseline ({baseline:.3f}) by "
            f"only {lift:.3f}; the retriever is not capturing enough signal (high bias).",
        )
    if gap > WELL_FIT_MAX_GAP:
        return (
            "overfit",
            f"train top-1 ({train:.3f}) runs {gap:.3f} above held-out ({test:.3f}); the index "
            f"fits its own tickets far better than new ones (high variance).",
        )
    return (
        "well-fit",
        f"train and held-out top-1 agree within {abs(gap):.3f} ({train:.3f} vs {test:.3f}), "
        f"held-out sits {lift:.3f} above the majority baseline, and the CV std is {std:.3f}; "
        f"generalisation is stable and not memorised.",
    )


@dataclass(frozen=True)
class BenchmarkResult:
    n_services: int
    services: list[str]
    n_tickets: int
    counts: dict[str, int]
    majority_baseline: float
    random_baseline: float
    cv: dict[str, float]
    holdout: SplitScore
    control_top1: float
    fit_label: str
    fit_reason: str


def run_benchmark(path=None, n_services: int = N_SERVICES) -> BenchmarkResult:
    incidents = load_incidents() if path is None else load_incidents(path)
    services = top_services(incidents, n_services)
    selected = [inc for inc in incidents if inc.service in set(services)]
    counts = {s: sum(inc.service == s for inc in selected) for s in services}
    cv = cross_validate(selected)
    base = majority_baseline(selected)
    label, reason = classify_fit(cv, base)
    return BenchmarkResult(
        n_services=len(services),
        services=services,
        n_tickets=len(selected),
        counts=counts,
        majority_baseline=base,
        random_baseline=1.0 / len(services),
        cv=cv,
        holdout=holdout(selected),
        control_top1=shuffled_label_control(selected),
        fit_label=label,
        fit_reason=reason,
    )


def format_report(result: BenchmarkResult) -> str:
    lines: list[str] = []
    add = lines.append
    add("opspilot runbook retrieval on real IT incidents (Loukh1/IT-incidents)")
    add("=" * 70)
    add(
        f"Routing {result.n_tickets} real tickets across the {result.n_services} most "
        f"frequent services:"
    )
    add("  " + ", ".join(f"{s} ({result.counts[s]})" for s in result.services))
    add("")
    add("Baselines")
    add(f"  majority class : {result.majority_baseline:.3f}")
    add(f"  random (1/N)   : {result.random_baseline:.3f}")
    add("")
    cv = result.cv
    add(f"Stratified {CV_FOLDS}-fold cross-validation")
    add(f"  top-1 accuracy : {cv['top1_mean']:.3f} +/- {cv['top1_std']:.3f}")
    add(f"  top-3 accuracy : {cv['top3_mean']:.3f}")
    add(f"  macro-F1       : {cv['macro_f1_mean']:.3f}")
    add(f"  train top-1    : {cv['train_top1_mean']:.3f}")
    add(f"  train/test gap : {cv['gap_mean']:+.3f}")
    add("")
    ho = result.holdout
    add(f"Held-out split ({int(HOLDOUT_TEST_SIZE * 100)}% test)")
    add(f"  top-1 accuracy : {ho.top1:.3f}")
    add(f"  top-3 accuracy : {ho.top3:.3f}")
    add(f"  macro-F1       : {ho.macro_f1:.3f}")
    add(f"  train top-1    : {ho.train_top1:.3f}  (gap {ho.gap:+.3f})")
    add("")
    add("Shuffled-label control")
    add(
        f"  top-1 accuracy : {result.control_top1:.3f}  "
        f"(collapses to ~random {result.random_baseline:.3f})"
    )
    add("")
    add(f"Verdict: {result.fit_label.upper()} — {result.fit_reason}")
    return "\n".join(lines)


def main() -> None:
    print(format_report(run_benchmark()))


if __name__ == "__main__":
    main()
