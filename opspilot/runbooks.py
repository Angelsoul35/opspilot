"""Runbooks and a TF-IDF retriever that matches an incident to one.

A runbook is a titled set of symptoms and ordered steps; a step may carry a
command and be marked as an *action* (something that changes the system). The
retriever matches an incident description to the most relevant runbook by cosine
similarity over its title and symptoms — what the incident *looks like* — so the
assistant's advice is grounded in a vetted procedure rather than invented.
"""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.pipeline import FeatureUnion


@dataclass(frozen=True)
class RunStep:
    description: str
    command: str | None = None
    action: bool = False  # True = changes the system -> needs human approval


@dataclass(frozen=True)
class Runbook:
    id: str
    title: str
    symptoms: str
    steps: tuple[RunStep, ...]


@dataclass(frozen=True)
class Match:
    runbook: Runbook
    score: float


# A small synthetic runbook library for an SRE/ops team.
RUNBOOKS: list[Runbook] = [
    Runbook(
        "rb-high-cpu",
        "High CPU on a web node",
        "high cpu usage load average pegged node slow latency saturation",
        (
            RunStep("Confirm the alert and identify the hottest process.", "top -b -n1 | head -20"),
            RunStep("Check recent deploys that could have caused a regression."),
            RunStep(
                "Scale out the service to shed load.",
                "kubectl scale deploy/web --replicas=6",
                action=True,
            ),
            RunStep(
                "If a runaway process, restart the affected pod.",
                "kubectl delete pod <pod>",
                action=True,
            ),
        ),
    ),
    Runbook(
        "rb-disk-full",
        "Disk full on a database host",
        "disk full no space left on device database volume full write failures",
        (
            RunStep("Identify what is consuming the disk.", "du -xh / | sort -h | tail -20"),
            RunStep(
                "Rotate and compress old logs.", "logrotate -f /etc/logrotate.conf", action=True
            ),
            RunStep(
                "Extend the volume if growth is legitimate.",
                "lvextend -L +20G /dev/vg0/data",
                action=True,
            ),
        ),
    ),
    Runbook(
        "rb-5xx",
        "Elevated 5xx error rate",
        "elevated 5xx errors http 500 502 503 bad gateway error rate spike upstream",
        (
            RunStep("Check the error budget and the failing upstream."),
            RunStep(
                "Inspect recent error logs for a stack trace.",
                "kubectl logs deploy/api --since=10m | grep -i error",
            ),
            RunStep(
                "Roll back the last deploy if it correlates.",
                "kubectl rollout undo deploy/api",
                action=True,
            ),
        ),
    ),
    Runbook(
        "rb-cert-expiry",
        "TLS certificate expiring or expired",
        "tls certificate expired expiry ssl handshake failure cert not valid",
        (
            RunStep(
                "Confirm the certificate's expiry.",
                "openssl x509 -enddate -noout -in /etc/ssl/cert.pem",
            ),
            RunStep("Renew the certificate.", "certbot renew --force-renewal", action=True),
            RunStep(
                "Reload the web server to pick up the new cert.",
                "systemctl reload nginx",
                action=True,
            ),
        ),
    ),
]


class RunbookLibrary:
    def __init__(self, runbooks: list[Runbook] | None = None) -> None:
        self.runbooks = runbooks if runbooks is not None else RUNBOOKS
        corpus = [self._doc(rb) for rb in self.runbooks]
        # A FeatureUnion of a word view (1-2 grams: terminology and short phrases)
        # and a character view (char_wb 3-5 grams). An incident is described in an
        # operator's own words, which rarely match the runbook's wording token for
        # token: "503s" vs "503", "saturation" vs "saturated", "handshake" vs
        # "handshakes". The character n-grams match inside words, so those variants
        # still align and the right runbook is retrieved instead of a near-miss. A
        # word-only model matched "503s after the deploy" to the disk-full runbook;
        # the character view fixes that misrouting.
        self._vectorizer = FeatureUnion(
            [
                ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1)),
                ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1)),
            ]
        )
        self._matrix = self._vectorizer.fit_transform(corpus)

    @staticmethod
    def _doc(rb: Runbook) -> str:
        # Match on the title and symptoms only — the recognisable *signature* of
        # the incident. Step descriptions are remediation ("rotate the logs",
        # "identify the hottest process"), and indexing them made unrelated
        # incidents collide on operational verbs (an "on-call rotation" question
        # matched the log-rotation runbook; an OOM "process" matched the hottest-
        # process step). An incident is described by what is wrong, not by the fix,
        # so matching symptom-to-symptom is both more accurate and less noisy.
        return f"{rb.title}. {rb.symptoms}"

    def match(self, incident: str) -> Match:
        q = self._vectorizer.transform([incident])
        sims = cosine_similarity(q, self._matrix).ravel()
        best = int(sims.argmax())
        return Match(self.runbooks[best], round(float(sims[best]), 4))
