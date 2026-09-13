# Agentic data retrieval for the db-route datasets

A search, assess, select, retrieve and validate loop for open time-series sources, with an
LLM agent proposing and deterministic code disposing. It produced the source decisions behind
the `error404/db-route-*` TimeNet connectors; the run of record is committed under `results/`.

## What the agent decides and what the code verifies

| step | the agent (gpt-4o-mini, JSON mode, `llm.py`) proposes | the code verifies or refuses |
|---|---|---|
| search | registry queries for the four catalogues, from the data spec | every query is run against the live registry API (`scout.py`) |
| assess | relevance of each candidate to the spec, with a reason | licence allow-list, credentials, coverage window and cadence gates (`gates.py`), cheapest first |
| select | rubric fields per surviving source (`rubric.py`) | a live probe: DuckDB over HTTP range reads measures rows, columns, coverage and the 2025-11-02 station-basis step (`probe.py`) |
| retrieve | a column map from the source schema to the spec's fields | `verify_schema()`: every named column must exist and type-check against the probe, or the map is rejected |
| validate | | the accept/reject table is written as `REJECTIONS.md` with the failing gate per source |

An unverifiable proposal is dropped, never negotiated. Every LLM call, its prompt and its
answer are logged to `results/agent_log.json` so a reader can audit each decision.

## Run it

```bash
cd app/agents/src/features/db_route
OPENAI_API_KEY=...  python -m discover.run --out results     # with the agent
python -m discover.run --out results                         # without: the same gates and probes, no proposals
```

Standard library only, plus `duckdb` for the live probes. Without `OPENAI_API_KEY` the loop
still runs and records that no agent was present.

## Run of record (`results/`)

Window 2025-11-02 to 2026-08-31, four registries (a known list, HuggingFace datasets, govdata
CKAN, Zenodo): 354 candidates, 18 passed every gate, 7 of those probed live and used, 11
accepted on metadata only and left as candidates. The rest are rejected with the gate that
failed in `REJECTIONS.md`. `assessment.json` carries every entry with its gate result, probe
measurements, rubric, agent verdict and verified schema map; `candidates.jsonl` is the raw
scout output.

The code is self-contained: nothing here imports from the rest of `db_route`. The connectors
consume its decisions, not its code.
