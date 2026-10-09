# Vendored dataset: real IT-incident tickets

`it_incidents.jsonl` is a truncated copy of the public **[`Loukh1/IT-incidents`]**
dataset on the Hugging Face Hub — 3252 real IT support tickets, each tagged with
the affected service. It backs the retrieval benchmark in
`opspilot/real_benchmark.py` (routing an incident to its service) and the
tests in `tests/test_real_benchmark.py`.

[`Loukh1/IT-incidents`]: https://huggingface.co/datasets/Loukh1/IT-incidents

## Schema

One JSON object per line:

| Field      | Type   | Meaning                                                             |
| ---------- | ------ | ------------------------------------------------------------------- |
| `service`  | string | The affected service/component — the routable ground-truth label (e.g. `Kubernetes`, `MySQL`, `Traefik`). |
| `text`     | string | The incident ticket text (the source `input` field), truncated.     |
| `response` | string | The diagnosis + resolution (the source `response` field), truncated. |

The source also carries a constant `instruction` field ("Diagnose and resolve the
IT issue based on the provided ticket description and logs."); it is identical for
every row and is dropped on vendoring.

## How labels are chosen for the benchmark

The vendored file keeps **every** service (26 in total). The benchmark selects the
most frequent `N` services at evaluation time (`N_SERVICES = 12` by default) via
`opspilot.real_data.top_services`, so the checked-in data stays faithful to the
source and the class set is a parameter, not baked into the file. Ties in
frequency break alphabetically, so the selection is deterministic. The 12 most
frequent services cover 2214 of the 3252 tickets.

## Provenance and size

- **Source:** `Loukh1/IT-incidents`, `default` config, `train` split, fetched
  through the public datasets-server rows API (no authentication).
- **Transform:** each `input` is truncated to 600 characters and each `response`
  to 320, with whitespace collapsed, to keep the file small (~2.1 MB) while
  remaining real text. No row content is otherwise altered.
- **License:** the dataset is published on the Hugging Face Hub; consult the
  source dataset card for its exact license and terms before redistribution. This
  subset is vendored for reproducible evaluation only.

## How to regenerate

From the repository root, with the package installed:

```bash
python -m opspilot.real_data        # rewrites datasets/it_incidents.jsonl from the Hub
```

This calls `opspilot.real_data.vendor_dataset`, which fetches every row through
`urllib` (with retries and backoff), truncates the text, and writes this file. The
fetch path is behind a substitutable `urlopen`, so the tests exercise it with a
stand-in and never touch the network.
