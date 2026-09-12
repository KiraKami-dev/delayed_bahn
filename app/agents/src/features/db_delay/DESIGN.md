# Design: trip delay prediction with a time-series language model

Decisions taken on 2026-09-12 (Temporal AI hackathon, Aionic Labs / ETH Agentic
Systems Lab / Nebius) before the rebuild. Each choice lists its reason and the
measurement behind it. Numbers come from the scripts in `analysis/`, run on the
August 2026 monthly file unless stated otherwise.

This replaces the station-hour tasks of the first prototype (see `HANDOFF.md` in
this directory). What carries over is listed at the end.

## 1. Challenge fit

The brief: use TimeNet to prepare open time-series data, train or fine-tune a TSLM
that connects temporal signals with language, compare it to a baseline on held-out
data without leakage across time, subjects or devices, and demonstrate it.

- **Submission:** working demo, code and training config, checkpoint or adapter,
  dataset documentation, short evaluation with baseline comparison.
- **Judged on:** a useful problem, thoughtful data preparation, adequate TSLM
  training, rigorous evaluation, a clear demonstration.
- **Bonus points:** reusable TimeNet connectors, agentic dataset pipelines.
- **Connector gap:** the TimeNet catalog holds five datasets, all health or generic
  (`chengsenwang/tsqa`, `physionet/ecg-qa-cot`, `physionet/sleep-edfx`,
  `timenet/hello-world`, `timenet/test-mean`). A Deutsche Bahn connector would be
  its first transport dataset.

## 2. Target user and product

**Decision:** the primary user is a traveller. They share a trip from the DB app
and get how late the train will most likely arrive, how certain that is, and a
short explanation. The share flow itself is demo-only and not built here.

- **The output a traveller sees:** "about +8 min, likely 3 to 20 min, 72% chance
  of making your change", plus one or two sentences of reasoning.
- **Operations view:** a station view that sums these trip predictions is an
  optional demo screen, not a separate model.

**Why:** the traveller question is concrete, easy to demo live, and matches what
travellers already look for on bahnvorhersage.de or Zugfinder.

## 3. Prediction unit

**Decision:** one example is one train run, one target stop and one prediction
moment `t0`. The lead time (stops and minutes between `t0` and the target stop)
varies, from one stop ahead up to before departure.

**Why:** the train's own delay so far dominates everything else. Static groupings
explain little.

| What the predictor knows (late >= 6 min, Brier skill) | 1 stop ahead | 3 stops ahead | 8 stops ahead |
|---|---|---|---|
| Delay of this run at an earlier stop | 0.784 | 0.605 | 0.379 |
| Same, plus line x station history | 0.804 | 0.646 | 0.450 |
| Best static grouping without live delay | 0.110 | 0.110 | 0.110 |

**Consequences:**

- **History matters most at longer lead times** (+0.07 at 8 stops), so results are
  always reported per lead-time bucket.
- **A run is short:** stops per run p10 / median / p90 are 2 / 8 / 15 for
  long-distance, 5 / 15 / 29 for S-Bahn and 1 / 7 / 17 for regional trains. A run
  alone is too short for a patch encoder, hence several series per example (§4).

## 4. Model inputs

**Decision:** each example carries several time series plus text.

**Time series:**

1. **This run today:** the train's delay at each stop it has already passed.
2. **Key history:** delay at the target stop over the last 30 days, for the most
   specific key with enough observations (§7).
3. **Target station:** hourly share of stops at least 6 min late, last 72 h.
4. **Network:** hourly late share for the train's class (long-distance, regional,
   S-Bahn), network-wide, last 72 h.

**Text:** train category and number, planned arrival time at the target, lead time,
and the planned route. The prompt may note when today's stop pattern differs from
the usual one.

**Leakage rule:** only data timestamped before `t0`. Key history uses earlier days
only. Normal profiles and fallback statistics are fit on the training period only.

## 5. Target and output format

**Decision:** the model answers the exact delay in whole minutes, or `cancelled`.

- **Label:** `Answer: <minutes>` with minutes clipped to 0..999 (early arrivals
  become 0), or `Answer: cancelled` in lowercase.
- **Tokens:** with the Llama 3.2 tokenizer every integer 0..999 is one standard
  vocabulary token (128,256-token vocab, nothing added). `Answer: 8` tokenizes as
  `Answer`, `:`, `Ġ`, `8`, and `Answer: cancelled` as `Answer`, `:`, `Ġcancelled`.
  Capitalised `Cancelled` splits into two tokens, so labels stay lowercase. Number
  token ids are not contiguous (`8` is 23, `10` is 605), so the code keeps a
  minute-to-id lookup table.
- **Two-step answer (hurdle model):** at the position after `Answer:` the model
  chooses between `Ġ` (a delay follows) and `Ġcancelled`, which gives P(cancelled).
  At the next position it chooses among the tokens `0`..`999`, which gives the
  delay distribution given the train runs. Then P(delay = k) = P(runs) x P(k | runs).
  Both steps are renormalised over the allowed tokens; probability mass that falls
  on other tokens is reported as a sanity metric.
- **Readouts from one forward pass:** median (headline), 10th to 90th percentile
  (certainty), P(delay < 6 min), and the connection probability (§10).

**Why not buckets:** a minute value is what the traveller wants, and the full
distribution already gives any range. Buckets would add arbitrary boundaries.

**Why not a free-text number alone:** the first prototype's generated numeric
forecast lost to a plain context mean in three of four cells, and a single number
hides the heavy tail:

| Non-cancelled stops | p50 | p75 | p90 | p95 | p99 | > 60 min | cancelled | early |
|---|---|---|---|---|---|---|---|---|
| Long-distance | 5 | 17 | 37 | 54 | 101 | 3.8% | 7.0% | 1.2% |
| Other trains | 1 | 3 | 8 | 13 | 30 | 0.15% | 4.1% | 0.5% |

The longest delay observed in August was 1,415 minutes, hence the clip at 999.

## 6. Loss

**Problem:** plain cross-entropy treats `9` as exactly as wrong as `500` when the
truth is `8`. The pretrained output embeddings already place nearby numbers
closer (cosine similarity 8 vs 9: 0.659, 8 vs 10: 0.443, 8 vs 80: 0.307,
8 vs 500: 0.135), but the loss does not reward that.

**Decision:** keep standard cross-entropy on the rationale and the first answer
step, and change only the number position:

1. **Soft targets:** q(k) proportional to exp(-|k - y| / b) with b = 1 + 0.1 y, so
   the width grows with the delay. Loss: -sum over k of q(k) log p(k), over the
   1,000 number tokens.
2. **CRPS term:** with F the predicted cumulative distribution over 0..999, add
   sum over k of (F(k) - 1[k >= y])^2. It penalises probability in proportion to
   its distance from the truth, and it is also the evaluation metric.

Total at the number position: soft cross-entropy + lambda x CRPS. Cancelled
examples skip the number position.

**Ablation:** the same model trained with plain one-hot cross-entropy.

## 7. Aggregation keys

**Decision:** key history uses a fallback chain. Take the most specific key with at
least 10 observations in the fitting period:
full stop pattern x station, then origin x destination x station, then train type
x station.

- **Line numbers are unusable for long-distance trains:** `line_number` is null for
  100% of ICE, IC and EC stops (0% for S-Bahn and RE).
- **The planned route exists in the raw scrape:** it stores the full Timetables API
  responses, where `ppth` lists every stop (for example
  `<dp fb="ICE 771" ppth="Neumünster|Hamburg Hbf|…|Stuttgart Hbf"/>`). The
  processed monthly files drop it.
- **Training builds the stop pattern from the processed data:** the ordered
  stations of a ride on that day, including cancelled stops, so the key does not
  leak which stops were cancelled. The live demo reads `ppth` from the API.
- **`train_line_ride_id` is a recurring service id:** it appears on 17.7 days per
  month on average and never spans more than one train number. Train numbers are
  less clean: 43% run to more than one destination.
- **Patterns vary within a service:** 27% of ride ids run more than one stop
  pattern in a month (1.54 on average), so the pattern is worth keying on when data
  allows.

Out-of-sample Brier skill for late >= 6 min (fit on days 1 to 15, score on days 17
to 31; coverage is the share of test stops whose key had at least 10 fitting
observations):

| Key (x station) | Long-distance | Coverage | Other trains | Coverage |
|---|---|---|---|---|
| train type | 0.071 | 0.99 | 0.096 | 0.99 |
| origin x destination | 0.162 | 0.77 | 0.119 | 0.85 |
| full stop pattern | 0.112 | 0.49 | 0.113 | 0.81 |
| ride id | 0.125 | 0.69 | 0.068 | 0.68 |
| **fallback: pattern, then origin x destination, then type** | **0.175** | 1.00 | **0.129** | 1.00 |

All trains, simpler keys, same method: station 0.079, station x hour 0.076, train
type 0.050, station x type 0.106, station x type x hour 0.097, line 0.080, line x
station 0.110, line x station x hour 0.098, train number 0.087, train number x
station 0.085. **Station versus line is a tie**, and it is second-order next to
live delay. No existing service we found aggregates by line; bahnvorhersage.de
predicts per stop of a run, Zugfinder keeps statistics per train number.

## 8. Data

- **Source:** Hugging Face `piebro/deutsche-bahn-data`, CC BY 4.0.
- **Months:** November 2025 to August 2026, ten processed monthly files of about
  600 MB each. Coverage jumps from about 107 to about 5,200 stations in October
  2025, so earlier months are a different dataset.
- **Stations:** all of them, buses excluded. Most stations are small (5,201 in
  August; 4,730 with at least 24 stops a day, 1,037 with at least 100, 200 with at
  least 300) and the top 300 carry only 32% of stops, so restricting to big
  stations would miss most real trips. Small stations simply contribute a weak
  station series.
- **Compute:** hourly aggregation over all stations takes 0.1 s per month in DuckDB,
  so scale is not a constraint.
- **Examples:** sample about 200k to 300k from all stops, stratified by train class,
  lead-time bucket and outcome, rather than using every stop.
- **Time zone:** timestamps are German local time. Localise to Europe/Berlin and
  store UTC. The window contains only the 29 March 2026 spring-forward gap and no
  repeated hour; confirm the data has no rows in the missing hour.
- **Live data:** the raw partition is updated several times a day and already holds
  today's hours, which serves the forward test (§9). The DB Timetables API (free
  plan, `scripts/db_timetables.py`) provides current delays and `ppth` for the demo.
- **TimeNet:** examples are built as a TimeF dataset through a TimeNet connector;
  `timef_bridge.py` feeds them to OpenTSLM.

## 9. Split and evaluation

**Backtest split:**

| Part | Period |
|---|---|
| Train | November 2025 to April 2026 |
| Validation | May 2026 |
| Gap | at least the longest context window |
| Test | June to August 2026 |

- **Why a time split:** testing on the latest period is standard for forecasting;
  a random split leaks the future. Nearby stations share network-wide disruptions,
  so holding out stations alone would not be enough. A held-out-station cell is
  still reported.
- **Demo model:** after choosing settings on the backtest, retrain on everything up
  to the last available days.
- **Forward test:** predictions made on the evening before the pitch, for the next
  morning's trains, scored once the data arrives. Nobody can call that test set
  leaked.
- **Training window:** bahnvorhersage.de retrains daily on a rolling six weeks.
  Compare six weeks against ten months on the XGBoost baseline before committing.

**Metrics,** all per lead-time bucket and per train class:

- error of the median (MAE)
- CRPS of the distribution
- coverage of the 10 to 90% range (should be close to 80%)
- Brier score and calibration for P(late >= 6)
- log loss for P(cancelled)

**Baselines:**

1. **Persistence:** the current delay carries to the target stop.
2. **Key history:** median delay for the fallback key.
3. **XGBoost** on engineered features. This is the model bahnvorhersage.de reports
   using, so it is the bar to meet.
4. **Text-only LLM:** the same base model fine-tuned with the series written as
   numbers in the prompt. This isolates what the time-series encoder adds.

**TSLM ablations:** plain cross-entropy versus soft targets plus CRPS; the
`m4-sp` checkpoint versus `ecg-sp` versus a randomly initialised encoder.

## 10. Transfer times and connections

**Decision:** transfer times are applied after the model, not inside it.

- **Formula:** P(connection) = P(planned buffer + departure delay - arrival delay
  >= minimum transfer time), from the arriving train's distribution and the
  departing train's distribution.
- **Why outside:** transfer times are static, the historical data does not record
  which connections travellers made, and the model stays reusable.
  bahnvorhersage.de combines them the same way.
- **Source:** RIS::Stations `connecting-times` on the DB API Marketplace, per
  station or station pair, CC BY 4.0. The free test plan allows 10k requests a
  month but DB must approve the application. Fallback: a fixed default per
  station size.
- **Caveats:** treating the two trains as independent is optimistic, because one
  disruption often hits both. DB sometimes holds connecting trains, which is not
  modelled.

## 11. Model and compute

- **Base model:** `unsloth/Llama-3.2-3B`. Meta rejected our gated access request.
  The mirror's two safetensors shards have the same SHA-256 as
  `meta-llama/Llama-3.2-3B`
  (`584d8d3e…e002`, `4719a045…cefb`), so the weights are identical. The Llama 3.2
  Community License still applies, including its attribution requirements when a
  checkpoint or adapter is shared.
- **Starting checkpoint:** `OpenTSLM/llama-3.2-3b-m4-sp` (soft prompt, MIT, trained
  on general forecasting series). `OpenTSLM/llama-3.2-3b-ecg-sp`, the last
  curriculum stage, is the comparison.
- **Loading:** `OpenTSLM.load_pretrained` hard-codes the meta-llama id, so build
  `OpenTSLMSP(llm_id="unsloth/Llama-3.2-3B")` and call `load_from_file` on the
  downloaded `model_checkpoint.pt`. Verified: loads from epoch 43, 6.5 GB GPU
  memory, 2,507,520 trainable encoder and projector parameters before LoRA.
- **Tokenizer check:** the mirror sets pad token `<|finetune_right_pad_id|>` (128004)
  with left padding; EOS is `<|end_of_text|>` (128001). Check that the loss on the
  first training batch is sensible.
- **LoRA:** enabled. Without it the model never learns the answer format.
- **Compute:** the team devbox (one RTX 6000 Ada, 48 GB) runs the TSLM; Nebius
  serverless jobs run the text-only baseline and ablations in parallel.

## 12. Not building

| Cut | Why |
|---|---|
| The DB app share flow | Demo-only mock; the product question is the prediction. |
| Transfer times inside the model | Static data; applied afterwards (§10). |
| Delay buckets as training labels | Exact minutes plus the distribution cover every range. |
| Aggregating by line number | Null for all long-distance trains; no better than station. |
| Months before November 2025 | Different station coverage. |
| Buses | Different mode; not a train trip. |
| Weather and event joins | Extra sourcing no rubric line rewards. |
| Modelling held connections | No data on DB's holding decisions. |

## 13. Open items

- **RIS::Stations approval** for transfer times; apply early.
- **DST check** for the 29 March 2026 gap.
- **Pad token and left padding** of the mirror tokenizer, on the first batch.
- **Stop pattern versus `ppth`:** confirm the processed-data pattern matches the API
  route for the live demo.
- **Soft-target width and CRPS weight** (b and lambda), tuned on validation.
- **Risk:** XGBoost may match or beat the TSLM on raw error. The honest framing is
  comparable accuracy, a clear win over the text-only LLM, calibrated uncertainty
  and a readable explanation.
- **Time:** submission is 2026-09-13 10:00 UTC. Build the examples and the
  non-LLM baselines first; they are the fallback submission.

## 14. Carried over from the first prototype

- Query the parquet with DuckDB; download only the months needed.
- Compute labels and template the rationale from the data; derive the rationale's
  closing clause from the answer so it can never contradict it.
- `timef_bridge.py` as the domain-free path from TimeF to OpenTSLM.
- LoRA on; offline synthetic smoke tests.
- Pin station or key rankings once before looping over months.

## 15. Implementation (2026-09-12)

Code lives in `trip/` (see `trip/README.md`). What was built, what the data turned out
to be, and where the implementation departs from the sections above.

### Data facts found while building

- **Schema:** all ten monthly files share one schema; no per-month handling is needed.
- **`delay_in_min` is the departure delay** (the arrival delay only at a run's last stop).
  One ICE arrived 41 minutes late and left 46 late; the column says 46. The target is
  therefore computed from `arrival_planned_time` and `arrival_change_time`.
- **Run id:** `id` without its trailing `-<stop number>` identifies one run on one day
  (1.29M runs in August, no duplicate stops). Stop numbers start at 1 and have small
  gaps (0.38 missing numbers per run on average).
- **Cancelled stops** still carry a delay value, so cancellation comes from the flags.

### Example set

- **Scale:** 142,183,754 stops loaded; 298,430 examples; the build takes about 70 s.

| Split | Period of the prediction moment | Examples |
|---|---|---|
| Train | 15 Nov 2025 to 30 Apr 2026 | 174,070 |
| Validation | 2 May to 31 May 2026 | 30,622 |
| Test | 2 Jun to 31 Aug 2026 | 93,738 |

- **Train starts on 15 November** so the 30-day history has data; the day before
  validation and the day before test are dropped.
- **Sampling** is hash-seeded and reproducible: 48% of long-distance runs, 1.9% of
  regional and 2.3% of S-Bahn runs, one target stop per run. 23% of examples are
  before departure, placed 0 to 120 minutes before the first planned departure.
- **Pattern key includes the train type**, so an RE and an S-Bahn on the same stations
  keep separate history (slightly more specific than the key measured in §7).
- **History level used:** stop pattern for 77% of long-distance and 96% of regional and
  S-Bahn examples; no key with 10 observations for 0.1 to 0.3%.
- **Station and network series** use only hours strictly before the hour of the
  prediction moment.
- **Lead time** is measured to the planned arrival; 4.4% of examples are already past
  it because the train is late.

### Prompt and answer

- **The rationale is written from the inputs alone and never states the minutes.**
  This replaces the prototype rule of deriving the closing clause from the answer
  (§14): if the text named a number before `Answer:`, the distribution read afterwards
  would collapse onto it. Because the rationale is a function of the inputs,
  evaluation teacher-forces it and reads P(cancelled) and the minute distribution in
  one forward pass; a free-generation check on a small test sample confirms the model
  also writes it.
- **Minute smoothing applies only at the answer token.** Numbers inside the rationale
  (times, delays so far) keep plain cross-entropy, since they are facts copied from the
  input.
- **Four series per example:** departure delay at each stop so far (a single zero
  before departure), 30-day daily median at the target stop, 72 hourly late shares at
  the target station, 72 hourly late shares for the train class nationwide. Each is
  z-normalised with its mean and spread stated in the text.

### Model and training

- **Padding bug fixed:** OpenTSLM's batching keeps the first N tokens of each text
  segment, which is only correct with right padding. The mirror tokenizer pads on the
  left, which would have trained on truncated prompts without any error. The wrapper
  forces right padding and sets pad to EOS, as in the original checkpoints.
- **Memory:** OpenTSLM computes full 128k-vocabulary logits at every position and uses
  eager attention. The wrapper runs the backbone, applies the output layer only at
  answer positions, and switches to SDPA: peak memory fell from 48.3 to 40.9 GB and a
  step from 0.92 to 0.79 s at batch 8. Batch 16 does not fit in 48 GB.
- **Settings:** LoRA r 16, alpha 32 on all attention and MLP projections (24.3M
  parameters), plus the encoder and projector; learning rate 1e-4 for LoRA and 2e-4 for
  the encoder, 3% warmup, cosine decay to a tenth; 12,000 steps at batch 8 (about 96k
  examples, a little over half an epoch). Soft-target width b = 1 + 0.1 y, CRPS weight
  0.1.
- **Readout sanity (smoke run):** 97 to 99% of the probability after `Answer:` falls on
  the space or `cancelled` tokens, and over 99.99% after the space falls on number tokens.
- **Evaluation subsets:** 3,000 validation and 30,000 test examples, seeded, identical for
  every TSLM run; `report.py` scores all models on the shared example ids.

### Baseline results (test, 93,738 examples)

| Model | Median error (min) | CRPS | 10 to 90% coverage | Brier late | Cancel log loss |
|---|---|---|---|---|---|
| Persistence (current delay, residual spread per lead bucket) | 3.746 | 3.105 | 0.839 | 0.104 | 0.216 |
| Key history (quantiles of the 30-day series) | 5.545 | 4.703 | 0.633 | 0.157 | 0.195 |
| XGBoost (19 quantiles, late and cancel classifiers) | 3.462 | 2.759 | 0.825 | 0.087 | 0.143 |

XGBoost with 5,000 instead of 1,500 trees scores the same (3.462 / 2.759), so it is
converged. TSLM results go here once the overnight runs finish.

### Built after the first runs were queued

- **Robustness check:** the first overnight launch crashed within a minute, because 61
  target stations and 136 via lists have no name in the scrape. `check_samples.py` now
  renders all 298,430 examples and checks the answer tokens on 30,000 before any
  unattended run: 0 failures; prompts are 370 text tokens at the median and 493 at most,
  plus 72 series tokens.
- **Connection probability** (`connection.py`, §10): the arriving and departing delay
  distributions are convolved and compared with the planned buffer minus the minimum
  transfer time, then multiplied by the chance both trains run. Changes are chained as
  independent. A Monte Carlo test checks the convolution.
- **TimeNet connector** (`timenet_connector/`, `timef_export.py`): `error404/db-trip-delay`
  downloads the monthly files idempotently, builds the examples and converts them to TimeF.
  - One record per example; the run's delays sit on an ordinal axis.
  - The daily history and both hourly series share one timeline, starting at local midnight
    30 days before the prediction moment.
  - Annotations, plus a minute task carrying the input-only rationale and a cancellation task.
  - TimeNet's integrity check passes on the written version.
  - Two TimeF rules shaped it: one `spec_type` may not have two contracts, so each series
    has its own type; an annotation needs a value, so missing fields are skipped.
- **September forward test** (§9, `run_forward_eval.sh`): the upstream monthly release
  script (MIT, piebro/deutsche-bahn-data) turns the raw September API responses into the
  same schema, and the builder takes prediction moments from 1 September.
  - The raw scrape stores fetch times in UTC and timetable times in German local time; the
    last change feed was fetched at 19:50 local on 12 September.
  - Upstream fills a missing change time with the planned time, so a stop after the last
    snapshot would look punctual. `--label-cutoff` keeps only targets planned before 18:00
    local on 12 September.
  - The period is newer than every published monthly file and than the training data. It is
    an out-of-time test, not predictions made before the trains ran.

### Still open

- **Live inference** from the DB Timetables API for the demo; `predict.py` replays recorded
  trips and changes.
- **Frontier LLM baseline** (the team's chosen baseline): needs an API key, and none is
  configured on the build machines.
- **Text-only LLM baseline and the random-encoder and `ecg-sp` ablations** (§9); only the
  plain cross-entropy ablation runs.

## Sources

- Challenge deck: Aionic Labs, "Temporal AI Challenge" (hackathon handout).
- Dataset: https://huggingface.co/datasets/piebro/deutsche-bahn-data and
  https://github.com/piebro/deutsche-bahn-data
- TimeNet catalog: https://docs.timenet.ai/catalog/datasets.html
- OpenTSLM checkpoints: https://huggingface.co/OpenTSLM
- bahnvorhersage.de method: https://bahnvorhersage.de/blog/time-histograms/ and
  https://gitlab.com/bahnvorhersage/bahnvorhersage
- Zugfinder: https://www.zugfinder.net/de/start
- RIS::Stations: https://developers.deutschebahn.com/db-api-marketplace/apis/product/ris-stations
- Llama mirror: https://huggingface.co/unsloth/Llama-3.2-3B
