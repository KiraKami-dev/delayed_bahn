# Handoff: starting the rail delay pipeline again

For an agent picking this up cold. What the pipeline does is in `README.md`. This
file is the part that is not obvious from the code: what to keep, what to change,
how much data to pull, and the traps that cost real time.

## Keep these

- **Query the parquet in place.** DuckDB with `httpfs` reads the monthly files over
  HTTPS and fetches only the columns and byte ranges it needs. Three months costs
  about 20 seconds and no local copy of a 68 GB repository. Never download the whole
  thing.
- **Compute the labels, do not generate them.** Three sentence templates written once;
  every number and direction word derived from the horizon. Labels stay objective, cost
  nothing, and cannot be accused of grading their own homework.
- **Derive the rationale's direction word from the answer.** The first version said
  "rising" ahead of an answer that fell, which teaches incoherent reasoning. Deriving it
  makes contradiction impossible, and `test_forecast_rationale_agrees_with_its_answer`
  keeps it that way.
- **Split on two axes.** Hold whole stations out, and start the test period a full
  context window after training ends. Report every cell.
- **The TimeF bridge.** OpenTSLM does not depend on TimeNet; its requirements name
  neither. `timef_bridge.py` is the missing path and is deliberately domain-free, so it
  is reusable well beyond rail. This is the most valuable file here.
- **LoRA.** With the language model frozen, only the encoder and projector train, and the
  model never learns to emit the answer format. It produces fluent unparseable text and
  loss still falls, so the failure is silent. Pass `--lora`.
- **Offline synthetic tests.** Seven checks, no network, under a second.

## Change these, in this order

1. **Split the series by train category, not by station alone.** Measured on August 2026,
   out of sample: station and hour explains 3.1% of delay variance, adding train type
   reaches 17.9%. An ICE averages 16.4 minutes late where an RB averages 4.2 at the same
   station, so one number per station-hour blends unlike regimes.
2. **Do not split by line number.** It looks like the dominant factor at 64.9% in sample
   and collapses to 4.2% out of sample. A line label averages over every service on that
   route all day in both directions. The column is also null for all long-distance trains.
3. **Drop the peak-hour task.** Its answer lives in a horizon the model never sees and the
   rationale offers no route to it. Only a third of answers parse and accuracy is zero.
   Replace it with a four-way period question or cut it.
4. **Rebalance the comparison task.** The majority class beats the model in every cell.
5. **Add a gradient-boosted baseline.** We only compare against a context mean. Anyone who
   knows forecasting will ask, and a tree may well win. Show it either way.
6. **Start from a published OpenTSLM checkpoint.** Fifty-one exist and are ungated, but
   they wrap gated base models, so someone must accept the Gemma or Llama licence first.
   Training the encoder from random weights on a few thousand examples is the most likely
   reason we only match the baseline.
7. **Make the evaluation cells comparable, or stop comparing across them.** Baseline error
   ranges from 0.98 to 7.84 minutes between cells, so only within-cell ratios mean anything.
8. **Name a target user before any of the above.** The rubric leads with it and the pitch
   has no spine without it.

## Minimal scope: how much data to pull

The dataset spans July 2024 to August 2026, but **it is not one dataset**. The scrape
covered about 107 stations until September 2025 and roughly 5,200 from November 2025
onward. October 2025 is the transition.

| Month | Distinct stations |
|---|---|
| 2025-09 | 107 |
| 2025-11 | 5,293 |
| 2026-06 | 5,297 |
| 2026-08 | 5,203 |

So the usable window is **November 2025 to August 2026, ten months**, not twenty-six.
Reaching further back does not add history, it swaps in a different dataset.

- **To prove the pipeline runs:** one month, 40 stations. About 960 windows, 20 seconds.
- **Minimum for an honest time split:** three consecutive months. A context week plus an
  embargo week eats most of a single month, leaving too few test windows.
- **To get more training data, add stations, not months.** Query cost barely moves with
  station count, and months bring coverage drift and daylight-saving folds.

| Scope | Windows | Tasks |
|---|---|---|
| 40 stations, 1 month | 960 | 2,880 |
| 40 stations, 3 months | 2,446 | 7,338 |
| 200 stations, 1 month | ~4,800 | ~14,400 |

Years are actively harmful here. Nothing about this problem needs annual seasonality
within a hackathon, and crossing the coverage break would poison the split.

## Traps that cost time

- **Naive variance decomposition inflates with group count.** Grouping by anything
  fine-grained gives an impressive in-sample number that vanishes out of sample. Fit the
  group means on one half of the period and score them on the other. I got this wrong
  three times before trusting it.
- **Timestamps are German local time, not UTC**, and TimeNet rejects naive datetimes.
  Attach `Europe/Berlin`. A single summer month has no transition; anything spanning
  29 March 2026 needs an explicit fold policy.
- **`extract()` rebuilds `top_stations` on every call.** Pin the ranking once before
  looping over months or each month gets a different station set.
- **Both Gemma and Llama are gated.** A token can read their metadata and still be refused
  the weights, so an access check that only hits the API will pass and the download will
  fail.
- **Nebius jobs inject only a script and a requirements file, capped at 64 KiB each.** The
  container has to clone OpenTSLM and fetch the prepared data itself.
- **The training entry point validates stage names against a fixed list**, so new data
  arrives as a new stage in a fork, not as a flag.

## Running it

```bash
python test_db_delay.py                       # offline, no network
python prepare.py data                        # ~20 s for three months
PYTHONPATH=. python train_minimal.py \
  --data data/splits.pkl --out out/run --llm-id Qwen/Qwen2.5-0.5B --lora --max-steps 4000
python rescore.py out/run                     # per-task scores from saved predictions
```

Needs `timenet[build]`, `timenet-connectors`, `opentslm` and `duckdb` on Python 3.12.
A run of 4,000 steps takes about eleven minutes on one RTX 6000 Ada.

## Where the last run got to

Qwen2.5-0.5B with LoRA, final loss 0.047. On the hardest cell, where neither the station
nor the period was seen: the six-hour forecast is roughly level with predicting the
window's own mean, the binary comparison sits below the majority class, and the peak-hour
task fails. The pipeline is finished and measured. The model is not yet worth showing.
