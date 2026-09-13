# error404 TimeNet connectors

Four dataset ids, one connector body, one experiment.

| dataset id | profile | bucket × span | series / record |
| --- | --- | --- | --- |
| `error404/db-route-week` | S | 1 h × 7 d | 7 |
| `error404/db-route-quarter` | M | 6 h × 60 d | 10 |
| `error404/db-route-season` | L | 1 d × 120 d | 10 |
| `error404/db-route-multiscale` | XM | 1 h × 7 d + 6 h × 60 d + 1 d × 120 d | 19, three time axes |

A record is **one Deutsche Bahn service group at one station on one travel date**. The four
datasets share entities, anchors, labels and split — only the history preceding each anchor
differs — and every record carries `artifact_bundle_sha` so a consumer can check that rather than
trust it. Held-out cells are entity- *and* date-disjoint (`split_cell` ∈ `train`, `val`,
`test_seen_entity`, `test_seen_time`, `test`).

## Build

TimeNet discovers connectors at `timenet_connectors.datasets.<org>.<name>` and nowhere else, so
link this folder into the installed package once, then build:

```bash
python app/agents/connectors/link.py
timenet-build build error404/db-route-week --out /tmp/registry --no-isolation
python -c "from timenet.client import TimeNet; TimeNet('/tmp/registry').load('error404/db-route-week').describe()"
```

`download()` needs the fact cache at `$DB_ROUTE_CACHE` (default `~/.cache/db_route`): the monthly
archive files, the day-sharded cause/notice extraction and the three hourly fact tables. It builds
whatever is missing, which is the only stage that touches the network, and it is idempotent.
`python src/features/db_route/facts.py all --regions munich` does the same from the command line.

Knobs (environment variables, read at build time):

| variable | default | meaning |
| --- | --- | --- |
| `DB_ROUTE_CACHE` | `~/.cache/db_route` | where the fact cache lives |
| `DB_ROUTE_ENTITIES` | `500` | how many `(service group, station)` entities to curate |
| `DB_ROUTE_MONTHS` | every local month | `YYYY-MM,YYYY-MM` inclusive archive range |

## What TimeNet's three slots hold

| slot | contents |
| --- | --- |
| **signals** | one `TimeSeries` per (layer, signal); four delay channels share the `delay` spec and differ by `signal`; archival raw minutes, no normalisation |
| **metadata** | span-less annotations: `entity_id`, `service_group`, `station`, `train_type`, `anchor_iso`, `weekday`, `split`, `split_cell`, `recency_weight`, `imputed_fraction`, `attributed_share`, `artifact_bundle_sha`, plus one `caption:<layer>/<signal>` per series |
| **annotations** | `planned_disruption`: the dated IRIS notices (Bauarbeiten, Störung, …) overlapping the context, as `TimeInterval` spans with the operator's own validity window |
| **tasks** | `ScalarPredictionTask` departure delay (minutes) · `ClassificationTask` late ≥ 5 min · `ClassificationTask` dominant cause family · `AnswerTask` traveller action, chained from the cause task |

## Tests

Offline, synthetic, no fact cache:

```bash
python -m pytest app/agents/connectors/error404/db_route_week/tests
```

They check that the four cards bind the four profiles, that a build is byte-identical to itself,
and that the annotation model is used the way the cards claim.

## Layout

```
connectors/
  link.py                       # symlink this org folder into timenet_connectors/datasets/
  error404/
    db_route/pipeline.py        # the shared download/convert body
    db_route_week/              # __init__.py, connector.py, dataset.yaml, requirements.txt, tests/
    db_route_quarter/
    db_route_season/
    db_route_multiscale/
```

The domain code the pipeline calls (`facts`, `causes`, `entities`, `anchors`, `labels`,
`resample`, `build`, `connector`) is `src/features/db_route/`.
