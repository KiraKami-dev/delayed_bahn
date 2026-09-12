# analysis

One-off measurements behind the choices in `../DESIGN.md`. Not part of the pipeline.

Run from a directory holding `data/raw/data-2026-08.parquet` (the August 2026 monthly
file from `piebro/deutsche-bahn-data`). Needs `duckdb`; the model scripts also need
`transformers`, `torch` and `opentslm`.

| Script | Measures | DESIGN.md |
|---|---|---|
| `grouping_skill.py` | Station size distribution, `line_number` coverage, out-of-sample skill of station, line and train-number groupings, skill of live delay at earlier stops | §3, §7, §8 |
| `trip_signal.py` | Stops per run, and how much line x station history adds on top of live delay | §3 |
| `longdistance_ids.py` | Raw scrape layout (`ppth`), ride id and train number stability, long-distance route keys | §7 |
| `route_pattern.py` | Delay distribution, full stop pattern versus origin x destination, fallback key | §5, §7 |
| `tok_ints.py` | Whether integer minutes are single Llama 3.2 tokens | §5 |
| `num_tokens.py` | Number token ids, `cancelled` tokenization, numeric proximity of pretrained embeddings | §5, §6 |
| `load_3b.py` | Loading `OpenTSLM/llama-3.2-3b-m4-sp` on `unsloth/Llama-3.2-3B` | §11 |

Brier skill throughout: fit group means on days 1 to 15, score days 17 to 31, fall back
to the global late rate for groups with fewer than 10 fitting observations.
