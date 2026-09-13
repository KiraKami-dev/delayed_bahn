# Scoring helpers behind RESULTS.md

Run from a directory that holds `runs/<tag>/<profile>/` (metrics.json, scalar_<cell>.npz pulled from the bucket) and `registry_allde/` (the all-Germany TimeNet registry).

- `pull_runs.py <tag>...` — download a run's metrics and scored quantiles from the bucket (S3 keys from `app/backend/.env`).
- `baselines_local.py <profile> <tag>` — gradient boosting, persistence and route-history baselines on exactly the rows the run scored, plus a blend weight fitted on validation; writes `baselines_local.json` and `blend_<cell>.npz` beside the run.
- `make_blend_tag.py <tag> <profile>` — publish the blended quantiles as `runs/<tag>-blend/<profile>/` so `serve_route.py` can serve them unchanged.
- `results_table.py [cells...]` — the markdown table across every scored run.
