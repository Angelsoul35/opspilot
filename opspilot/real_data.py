"""Load and (re)fetch a real public IT-incident dataset.

The vendored corpus under ``datasets/`` is a truncated subset of
``Loukh1/IT-incidents`` on the Hugging Face Hub — real IT support tickets, each
tagged with the affected ``service`` (a routable label such as ``Kubernetes`` or
``MySQL``). opspilot routes an incident to a runbook by TF-IDF retrieval; this
module supplies the real tickets that let :mod:`opspilot.real_benchmark` measure
that routing against the ground-truth service on live inputs.

``fetch_incidents`` pulls the dataset through the public datasets-server rows API
(no auth) via :func:`urllib.request.urlopen`, which is referenced by the
module-level :data:`urlopen` name so tests can substitute a stand-in. The
retrieval/gating code never touches the network; only this fetch path does, and
it is exercised in tests through that substitutable opener.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

DATASET = "Loukh1/IT-incidents"
_ROWS_API = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=Loukh1%2FIT-incidents&config=default&split=train&offset={offset}&length={length}"
)

DEFAULT_DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "it_incidents.jsonl"

# Vendoring knobs — the corpus keeps the ticket text and the diagnosis/resolution,
# each truncated so the checked-in file stays small while remaining real text.
MAX_INPUT_CHARS = 600
MAX_RESPONSE_CHARS = 320
PAGE_SIZE = 100
RETRIES = 4


@dataclass(frozen=True)
class Incident:
    """One real IT-incident ticket: the text, its ground-truth service, the fix."""

    service: str
    text: str
    response: str = ""


def _truncate(value: str, limit: int) -> str:
    value = " ".join(str(value).split())
    return value[:limit].rstrip()


def fetch_incidents(
    limit: int | None = None,
    *,
    page_size: int = PAGE_SIZE,
    retries: int = RETRIES,
    opener: Callable[..., object] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, str]]:
    """Fetch raw rows from the Hugging Face datasets-server rows API.

    Pages through the dataset ``page_size`` rows at a time until ``limit`` rows
    are collected (or the dataset is exhausted), retrying each page up to
    ``retries`` times with exponential backoff. ``opener`` defaults to the
    module-level :data:`urlopen`; tests pass a stand-in to avoid the network.
    """
    open_url = opener or urlopen
    rows: list[dict[str, str]] = []
    offset = 0
    total: int | None = None
    while True:
        want = page_size if limit is None else min(page_size, limit - len(rows))
        if want <= 0:
            break
        url = _ROWS_API.format(offset=offset, length=want)
        payload = _get_json(url, open_url, retries, sleep)
        total = payload.get("num_rows_total", total)
        page = payload.get("rows", [])
        if not page:
            break
        for item in page:
            row = item["row"]
            rows.append(
                {
                    "service": row["service"],
                    "input": row["input"],
                    "response": row.get("response", ""),
                }
            )
        offset += len(page)
        if limit is not None and len(rows) >= limit:
            break
        if total is not None and offset >= total:
            break
    return rows


def _get_json(
    url: str,
    open_url: Callable[..., object],
    retries: int,
    sleep: Callable[[float], None],
) -> dict:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            request = Request(url, headers={"User-Agent": "opspilot-real-data"})
            with open_url(request, timeout=60) as response:  # type: ignore[call-arg]
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - retried below, re-raised if all fail
            last = exc
            if attempt < retries - 1:
                sleep(2.0**attempt)
    raise RuntimeError(f"failed to fetch {url} after {retries} attempts") from last


def vendor_dataset(
    out_path: Path | str = DEFAULT_DATASET_PATH,
    *,
    limit: int | None = None,
    max_input: int = MAX_INPUT_CHARS,
    max_response: int = MAX_RESPONSE_CHARS,
    opener: Callable[..., object] | None = None,
) -> int:
    """Fetch the dataset and write a truncated JSONL subset to ``out_path``.

    Returns the number of tickets written. The full dataset is kept (every
    service); :mod:`opspilot.real_benchmark` selects the most frequent services
    at evaluation time, so the vendored file stays faithful to the source.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw = fetch_incidents(limit=limit, opener=opener)
    written = 0
    with out_path.open("w", encoding="utf-8") as handle:
        for row in raw:
            text = _truncate(row["input"], max_input)
            if not row["service"] or not text:
                continue
            record = {
                "service": row["service"],
                "text": text,
                "response": _truncate(row["response"], max_response),
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1
    return written


def load_incidents(
    path: Path | str = DEFAULT_DATASET_PATH,
    *,
    services: Iterable[str] | None = None,
) -> list[Incident]:
    """Load the vendored tickets, optionally filtered to a set of services."""
    path = Path(path)
    keep = set(services) if services is not None else None
    incidents: list[Incident] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if keep is not None and record["service"] not in keep:
                continue
            incidents.append(
                Incident(
                    service=record["service"],
                    text=record["text"],
                    response=record.get("response", ""),
                )
            )
    return incidents


def top_services(incidents: Sequence[Incident], n: int) -> list[str]:
    """Return the ``n`` most frequent service labels, most frequent first.

    Ties break alphabetically so the selection is deterministic across runs.
    """
    counts = Counter(inc.service for inc in incidents)
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [service for service, _ in ordered[:n]]


def service_counts(incidents: Sequence[Incident]) -> dict[str, int]:
    """Count tickets per service, most frequent first."""
    counts = Counter(inc.service for inc in incidents)
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


if __name__ == "__main__":  # pragma: no cover - operator entry point for regeneration
    count = vendor_dataset()
    print(f"wrote {count} tickets to {DEFAULT_DATASET_PATH}")
