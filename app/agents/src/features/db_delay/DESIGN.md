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

## 16. Iteration on H100 (night of 12 to 13 September)

### Setup

- **Nebius serverless jobs, one H100 per run.** `trip/nebius/run_ablations.sh` reads code, requirements
  and examples from a bucket, trains and evaluates on local disk, streams progress to the job log and
  copies results to the bucket once at exit (bucket mounts may not allow overwrite or append).
  `RUNS` selects named runs (`main`, `plain_ce`, `plain_ce_lr2x`, `text_only`, `ecg_sp_start`,
  `random_encoder`) or `custom` with `CUSTOM_ARGS` for anything else.
- **Speed:** job setup takes about 4 minutes; an H100 trains at 0.31 s/step against 0.88 to 1.0 s/step
  on the devbox (RTX 6000 Ada). The text-only baseline runs at 0.73 s/step (longer prompts plus
  gradient checkpointing). A 2,000-step run with 3k validation and 5k test finishes in about 20 minutes.
- **Lessons:** the CUDA runtime image needs `build-essential` (Triton compiles kernels at runtime);
  an 8x H100 VM could not be created (not enough resources); injected job files must be base64; see
  the memory notes for the IAM steps that allow uploads.
- **Quick checks next to long runs:** `eval_checkpoint.sh` scores a saved checkpoint on the GPU beside
  training; `learning_curve.sh` scores checkpoints on 300 validation examples on the CPU.

### Results so far

Learning curve of the main run (soft targets plus CRPS), 300 validation examples:

| Model | Median error | CRPS | 10 to 90% coverage |
|---|---|---|---|
| XGBoost | 2.023 | 1.631 | 0.862 |
| Step 1,000 | 2.100 | 1.701 | 0.948 |
| Step 2,000 | 2.163 | 1.722 | 0.938 |
| Step 4,000 | 2.059 | 1.671 | 0.952 |

Test, the same 5,000 seeded examples for every model:

| Model | Steps | Median error | CRPS | 10 to 90% coverage | Brier late | Cancel log loss |
|---|---|---|---|---|---|---|
| Persistence | | 3.990 | 3.316 | 0.827 | 0.103 | 0.210 |
| Key history | | 5.873 | 4.999 | 0.628 | 0.158 | 0.189 |
| XGBoost | | 3.698 | 2.971 | 0.822 | 0.087 | 0.140 |
| Main (soft targets plus CRPS) | 5,000 | 3.722 | 2.974 | 0.913 | 0.089 | 0.179 |
| Main, the reference for the ablations | 2,000 | 3.711 | 2.994 | 0.911 | 0.088 | 0.167 |
| Text only: numbers in the prompt, no encoder | 2,000 | 3.635 | 2.938 | 0.914 | 0.086 | 0.164 |
| Plain cross-entropy | 2,000 | 3.702 | 2.954 | 0.899 | 0.089 | 0.155 |
| Plain cross-entropy | 5,000 | 3.678 | 2.923 | 0.903 | 0.087 | 0.146 |
| Plain cross-entropy, doubled learning rates | 2,000 | 3.717 | 2.956 | 0.895 | 0.089 | 0.152 |
| Text only, plain cross-entropy | 2,000 | 3.635 | 2.907 | 0.886 | 0.087 | 0.160 |
| Text plus encoder, plain cross-entropy | 2,000 | 3.641 | 2.912 | 0.892 | 0.087 | 0.158 |
| `ecg-sp` starting checkpoint | 2,000 | 3.711 | 2.994 | 0.912 | 0.088 | 0.165 |
| Random encoder | 2,000 | 3.727 | 3.006 | 0.912 | 0.089 | 0.166 |
| Blend: 0.6 main quantiles + 0.4 XGBoost | 5,000 | 3.691 | 2.951 | 0.856 | 0.087 | 0.140 |
| Blend: 0.8 plain quantiles + 0.2 XGBoost | 2,000 | 3.687 | 2.943 | 0.835 | 0.088 | 0.140 |
| Blend by lead time: plain and XGBoost | 2,000 | 3.646 | 2.924 | 0.831 | 0.086 | 0.140 |
| Blend by lead time: main and XGBoost | 5,000 | 3.671 | 2.950 | 0.856 | 0.087 | 0.140 |
| Blend by lead time: text only and XGBoost | 2,000 | 3.627 | 2.928 | 0.858 | 0.086 | 0.140 |
| Blend by lead time: plain and XGBoost | 5,000 | 3.641 | 2.907 | 0.830 | 0.086 | 0.139 |
| Blend by lead time: text plus plain and XGBoost | 2,000 | 3.618 | 2.901 | 0.826 | 0.086 | 0.140 |
| Blend by lead time: text plus encoder plus plain and XGBoost | 2,000 | 3.611 | 2.903 | 0.828 | 0.085 | 0.140 |

- **The two ingredients add up.** Text input with the plain loss is the first single model that
  beats XGBoost on the 5,000 examples with the interval clear of zero: CRPS -0.064 (-0.137 to
  -0.005), median error -0.063 (-0.144 to -0.000), after 2,000 steps. Adding the encoder on top
  of the text changes nothing (CRPS +0.005, -0.015 to +0.025, also within 15 minutes of arrival),
  while both beat the encoder-only plain run clearly (-0.042, -0.071 to -0.015): the numbers in
  the prompt carry the information. The lead-time blends of either with XGBoost are the best
  models so far (CRPS -0.070 and -0.069 against XGBoost, intervals -0.127 to -0.030 and -0.120 to
  -0.031). The recipe for the long run is therefore plain loss with the series in the prompt; the
  encoder stays in at no cost, so the model remains a time-series language model and can take
  series too long for a prompt later.

- **More steps keep helping the plain loss:** 5,000 steps improve on 2,000 (CRPS -0.031, -0.064 to
  +0.004 on the 5,000 examples), and its lead-time blend has the widest margin over XGBoost so
  far: CRPS -0.064 (-0.119 to -0.027), median error -0.058 (-0.120 to -0.015). Doubling the
  learning rates changes nothing.

- **The time-series encoder does not earn its place at 2,000 steps.** The text-only run, which
  writes the same four series into the prompt as numbers, beats the reference trained the same way
  with the encoder: CRPS -0.057 (95% interval -0.090 to -0.026), median error -0.076 (-0.121 to
  -0.033). Against XGBoost it wins on median error (-0.063, -0.138 to -0.001) but not clearly on
  CRPS (-0.034, -0.096 to +0.017); its lead-time blend with XGBoost wins on both (CRPS -0.044,
  -0.094 to -0.008; median error -0.071, -0.130 to -0.028). The starting checkpoint (`m4-sp`,
  `ecg-sp`, random encoder) makes no measurable difference, which says the same thing: the language
  model reads the numbers, the encoder path carries little. Numbers in the prompt plus the encoder,
  and text only with the plain loss, are the next runs.
- **The plain loss beats the soft targets on CRPS** at equal steps: -0.041 (-0.069 to -0.011), with
  no difference in median error.

Full test set, all 93,738 examples, plain cross-entropy at 2,000 steps against XGBoost:

| Model | Median error | CRPS | 10 to 90% coverage | Brier late | Cancel log loss |
|---|---|---|---|---|---|
| XGBoost | 3.462 | 2.759 | 0.825 | 0.087 | 0.143 |
| TSLM, plain cross-entropy | 3.477 | 2.774 | 0.905 | 0.089 | 0.158 |
| Blend, one weight | 3.461 | 2.757 | 0.839 | 0.088 | 0.142 |
| Blend by lead time | 3.427 | 2.731 | 0.835 | 0.087 | 0.142 |

- **Confirmed on the full test set** (88,479 examples that ran, paired bootstrap): the lead-time
  blend beats XGBoost, CRPS -0.028 (-0.039 to -0.019) and median error -0.035 (-0.047 to -0.024).
  The TSLM alone beats XGBoost within 15 minutes of arrival (36,556 examples: CRPS -0.055, -0.081 to
  -0.034; median error -0.081, -0.112 to -0.056; 0.991 against 1.072 minutes) and loses beyond it
  (15 to 30 minutes +0.026, 30 minutes and more +0.076 CRPS), so overall alone it is slightly worse
  (+0.015, +0.002 to +0.027). The weights fitted on validation put 0.95 on the TSLM within 15
  minutes and 0.1 to 0.3 further out. Free text is not the bottleneck either: every generated
  answer parsed.

- **Single models do not differ significantly.** Paired bootstrap on the 4,729 test examples that
  ran (95% intervals of the CRPS difference): main minus XGBoost +0.003 (-0.059 to +0.054); plain
  minus XGBoost -0.018 (-0.080 to +0.034); plain minus main -0.021 (-0.050 to +0.010); plain global
  blend minus XGBoost -0.029 (-0.084 to +0.014). The finalists need the full test set.
- **The TSLM is significantly better close to arrival, and worse 15 to 30 minutes out.** Bootstrap
  within lead-time buckets, plain cross-entropy minus XGBoost: within 15 minutes (1,927 examples)
  CRPS -0.085 (-0.211 to -0.001) and median error -0.113 (-0.263 to -0.011); 15 to 30 minutes (744)
  CRPS +0.044 (+0.014 to +0.074); 30 to 60 minutes (747) +0.048 (-0.007 to +0.102). The soft-target
  model shows the same shape with smaller margins.
- **A blend with one weight per lead-time bucket beats XGBoost overall.** Fitted on validation, the
  plain model gets weight 0.9 within 15 minutes of arrival and 0.1 to 0.3 further out. On the test
  examples it wins significantly: CRPS -0.047 (-0.101 to -0.013), median error -0.052 (-0.115 to
  -0.012). It also removes the 15 to 30 minute loss (CRPS 1.683 against XGBoost's 1.681). The same
  blend of the soft-target model is not significant (CRPS -0.021, -0.070 to +0.009). This is the
  product story: the TSLM reads the live signal in the last quarter hour, the tabular model carries
  the longer horizons.
- **Temperature calibration does not help:** the best temperature on validation is exactly 1.0. The
  high coverage is partly an artefact of whole-minute targets scored with inclusive intervals.
- **Platt scaling of P(cancelled)** helps the main model a little (0.179 to 0.170) but not the plain
  model; blending takes P(cancelled) mostly from XGBoost.
- **Free generation works:** 16 of 16 generated answers parse, with a median error of about 2 minutes.

### Second wave, 01:00 to 02:15: teach the encoder, give it more, use the data better

All plain loss, 2,000 steps on an H100, scored on the same 5,000 test examples; the partner for
each row is named. An identical repeat of the best recipe (text plus plain) scored 3.635 / 2.913
against 3.635 / 2.907, so two identical trainings differ by about 0.006 CRPS.

| Change | Partner | Median error | CRPS | Verdict |
|---|---|---|---|---|
| Encoder only, series keep their scale (no z-normalisation) | encoder only 3.702 / 2.954 | 3.719 | 2.966 | no gain |
| Encoder only, 30% series-reading questions mixed in | same | 3.756 | 3.000 | worse |
| Encoder only, both of the above | same | 3.756 | 2.992 | worse |
| Encoder only, 720 hourly points instead of 72 | same | 3.709 | 2.959 | no gain |
| Text plus encoder, 720 hourly points | text plus encoder 3.641 / 2.912 | 3.657 | 2.924 | no gain |
| Text plus encoder, scale kept plus questions | same | 3.647 | 2.913 | no gain |
| Text, multi-scale history summaries in the rationale | text 3.635 / 2.907 | 3.635 | 2.912 | better on validation (2.219 vs 2.233), no gain on test |
| Text plus encoder, multi-scale summaries | text plus encoder | 3.630 | 2.914 | no gain |
| Text, exact-minute loss plus 0.1 CRPS term | text 3.635 / 2.907 | 3.621 | 2.903 | best validation (2.192 vs 2.233); test gain inside noise |
| Text, 5,000 steps | text 2,000 steps | 3.614 | 2.883 | more training helps |
| Text, previous trains on the route (combined data) | text 3.635 / 2.907 | 3.616 | 2.889 | helps; XGBoost gains as much |
| Text plus encoder, previous trains (combined data, 720 h series) | text on the same data 3.616 / 2.889 | 3.603 | 2.877 | best 2,000-step run; beats XGBoost retrained on the same data alone (CRPS -0.060, -0.130 to -0.005); vs text -0.013 (-0.035 to +0.009) |

- **Nothing aimed at the encoder worked.** Keeping the level of the series, teaching it to read
  with exact-answer questions (OpenTSLM's curriculum idea folded into training), and ten times
  more hourly history all leave the encoder-only model where it was or make it worse, and none of
  it adds anything on top of the text channel. On short operational series the language model
  reads the numbers itself; the encoder buys context length this task does not need.
- **Richer data helps both models.** The arrival delays of the previous trains of the same type
  towards the same destination at the target stop (up to five, within six hours, arrived by the
  prediction moment; 77% of examples have at least one) improve the text model by 0.018 CRPS and
  XGBoost retrained on the same columns by 0.036 on the full test set (3.462 / 2.759 to 3.413 /
  2.723). Against that fairer XGBoost on the shared 5,000 examples the text model is ahead by
  0.048 CRPS (interval -0.121 to +0.010), its lead-time blend significantly (-0.049, -0.100 to
  -0.015), and it keeps its significant edge within 15 minutes of arrival (-0.084).
- **Multi-scale summaries as text** (90-day and 7-day route history, same-time-of-day lateness)
  improve validation but not the test examples.
- **The exact-minute loss plus a CRPS term** is the best single 2,000-step model on both splits,
  with the test gain over plain inside the noise; it rewards near misses through a proper score
  instead of blurred targets, so it is the loss of the long runs.
- **The September forward test** (10,000 examples the training never saw; XGBoost trained on
  the same May training split and scored on September, like the TSLM): XGBoost 3.244 / 2.586; the original recipe at 12,000 steps 3.257 / 2.611; text
  plus plain at 2,000 steps 3.281 / 2.626; text plus plain plus CRPS 3.266 / 2.610. Alone, every
  TSLM is behind the tabular model overall in September (plain: +0.040 CRPS, +0.013 to +0.068),
  ahead within 15 minutes of arrival (plain: -0.011, -0.021 to -0.002; plain plus CRPS: -0.016,
  -0.026 to -0.006) and clearly behind beyond 30 minutes (+0.089). The lead-time blend with
  weights fitted on May and applied blind to September beats XGBoost overall: plain 3.225 / 2.570
  (CRPS -0.016, -0.027 to -0.006), plain plus CRPS (CRPS -0.013, -0.022 to -0.005). Three
  different checkpoints give the same shape out of time.
- **Stacking and trajectory channels, submitted 02:29 to 02:33:** the XGBoost forecast as a
  sentence in the prompt (out-of-fold on the training split, `stack.py`); encoder-only runs with
  12,000 steps, a five-times higher encoder learning rate, and a frozen language model (stage 1);
  the planned trajectory of the run (running time, dwell, minutes left per stop) as encoder-only
  channels. Results follow.

### Third wave: encoder experiments, first results (02:47)

Encoder only, exact-minute plus CRPS loss, 2,000 steps, same 5,000 test examples; partner is the
encoder-only plain run at 3.702 / 2.954.

| Change | Median error | CRPS | Verdict |
|---|---|---|---|
| Encoder learning rate five times higher (1e-3) | 3.687 | 2.956 | no gain; lead blend beats XGBoost (CRPS -0.039, -0.093 to -0.007) |
| Stage 1: language model frozen, only encoder and projector trained | 3.724 | 3.031 | worse than XGBoost alone (+0.059, -0.002 to +0.113); validation 2.288 |
| Stage 2: resume that encoder, add the text channel, unfreeze the adapters (partner: text plus CRPS loss 3.621 / 2.903) | 3.608 | 2.900 | beats XGBoost (-0.072, -0.133 to -0.023); vs text -0.004 (-0.016 to +0.008): the pre-trained encoder adds nothing |
| Text plus encoder, combined data, 72-hour series, CRPS loss (partner: same with 720-hour series and plain loss, 3.603 / 2.877) | 3.606 | 2.878 | identical (+0.001, -0.031 to +0.036); beats XGBoost retrained on the same data (-0.057, -0.117 to -0.009) |
| Encoder only, 12,000 steps (partner: encoder only, plain loss, 5,000 steps, 3.678 / 2.923; text 5,000 steps 3.614 / 2.883) | 3.602 | 2.889 | best validation of the night (2.712 / 2.171); beats XGBoost at every lead time (-0.082, -0.137 to -0.041; within 15 min -0.112; beyond 30 min -0.072); level with text at 5,000 steps (+0.006, -0.044 to +0.062) |

- Training the encoder alone, with the language model fixed, is the cleanest test of whether the
  series channel carries the signal: it lands 0.08 CRPS behind the text models and behind the
  tabular baseline. Stage 2 (resume that checkpoint, unfreeze the adapters, add the text channel)
  was submitted at 02:52 and tells whether a pre-trained encoder gives the joint model a better
  start than the ECG-trained one.
- A faster encoder does not change the outcome either; the encoder's ceiling is not a learning
  rate problem.
- Giving the joint model an encoder that was trained first (stage 2) lands exactly on the text
  model: the encoder channel is read, but it carries nothing the text does not. And 72 hourly
  points through the encoder do as well as 720, so the short series is enough for the finals.
- **The encoder path does work; it learns more slowly.** Trained for 12,000 steps with the
  exact-minute plus CRPS loss, the encoder-only model (no numbers in the prompt at all) reaches
  the best validation score of the night and beats XGBoost on the shared test at every lead time,
  including beyond 30 minutes where the 2,000-step models lost. It lands where the text model was
  after 5,000 steps: the series channel carries the same information as the text, and needs
  about twice the training to extract it. That is the fair statement about OpenTSLM's encoder on
  this task, and the reason the finals keep it alongside the text.
- **And it holds out of time (04:06):** the same encoder-only 12,000-step checkpoint on the
  original September set (10,000 examples, XGBoost 3.244 / 2.586) scores 3.199 / 2.553: CRPS
  -0.033 (-0.050 to -0.017), median error -0.045 (-0.069 to -0.021), within 15 minutes -0.038
  (-0.048 to -0.030), all real. The May-fitted lead-time weights are 1.0 in every bucket, so the
  blend adds nothing. Compare the original recipe at 12,000 steps on the same set (3.257 / 2.611,
  behind XGBoost): the exact-minute plus CRPS loss is what turned the long encoder run into a
  model that beats the tabular baseline on its own, on data none of it had seen.

### Stacking: the statistical forecast as a sentence in the prompt (03:15)

Text, exact-minute plus CRPS loss, 2,000 steps, `examples_v4` (the combined data plus XGBoost's
own median, 10 to 90% range, P(late) and P(cancelled) as one rationale sentence; out-of-fold on
the training split so the model never sees a forecast fitted on its own row). Partner: XGBoost
retrained on the combined features, 3.650 / 2.935 on the same 5,000 examples.

| Model | Median error | CRPS | vs XGBoost (CRPS, 95% interval) |
|---|---|---|---|
| Text, stacked, 2k | 3.573 | 2.860 | -0.075 (-0.116 to -0.044), real |
| same, within 15 min (1,927) | | | -0.086 (-0.180 to -0.024), real |
| same, beyond 30 min (2,158) | | | -0.085 (-0.123 to -0.047), real |
| vs text plus encoder on the combined data (3.603 / 2.877) | | | -0.017 (-0.058 to +0.032) |
| Text, stacked, 5k | 3.587 | 2.858 | -0.077 (-0.131 to -0.027), real; vs the 2k run -0.003 (-0.034 to +0.029): validation improves (2.162, the best of the night), test does not |
| Text plus encoder, stacked, 2k | 3.572 | 2.864 | same as stacked text (validation 2.192 vs 2.188): the encoder adds nothing on top of the stacked text either |
| Encoder only, stacked, 2k (05:25) | 3.583 | 2.880 | -0.055 (-0.093 to -0.026), real; beyond 30 min -0.047 (-0.078 to -0.017), real; vs stacked text +0.019 (+0.010 to +0.030) with half the prompt: the series as 45 embeddings instead of about 480 number tokens |
| Split, stacked, 2k: run and previous trains as text, long history through the encoder only (05:35) | 3.594 | 2.883 | -0.052 (-0.084 to -0.028), real; vs stacked text +0.023 (+0.011 to +0.036): giving the encoder the history the text no longer has does not beat writing it out |
| Split, stacked, one value per patch (`z4`), 2k (05:40) | 3.580 | 2.877 | -0.057 (-0.098 to -0.027), real; vs stacked text +0.017 (+0.008 to +0.027): the best encoder route on the stacked data, still behind the text |

- **The first single model that beats XGBoost at every lead time.** Given the statistical
  forecast as a starting point, the language model corrects it with what it reads live; the
  correction is worth 0.075 CRPS overall and, for the first time, as much beyond 30 minutes as
  within 15. The lead-time blend fitted on validation chooses weight 1.0 for the TSLM: there is
  nothing left for a blend to add, because the stacked model already contains XGBoost.
- Validation is unchanged against the plain text run (2.188 vs 2.192), so the gain shows on the
  test months only; the 5,000-step version (running) and the 12,000-step finals on the full test
  (submitted 03:20: text, and text plus encoder, both on `examples_v4`) tell whether it holds.
- **September, out of time (03:30):** the same 2,000-step stacked model scored on 10,000
  September examples built with the combined features (`forward_v4.parquet`; XGBoost trained on
  May, scored on September, and its September forecast written into the prompts). Persistence
  3.057 / 2.493, XGBoost 2.745 / 2.175, stacked TSLM **2.689 / 2.136**: CRPS -0.039 (-0.076 to
  -0.015) and median error -0.056 (-0.107 to -0.023), both real; within 15 minutes -0.068
  (-0.148 to -0.025); the blind lead-time blend -0.040. The first TSLM that beats the tabular
  baseline alone on data none of it had seen. (This September set is the combined-feature build
  with 32,553 test examples; its numbers are not comparable with the earlier 10,000 from
  `forward.parquet`, where XGBoost scored 3.244 / 2.586.)
- **Without the forecast in the prompt it does not hold alone (04:30):** text plus encoder on the
  same combined data, 2,000 steps, on the same September examples: 2.711 / 2.148, CRPS -0.028
  (-0.072 to +0.005), no clear difference; within 15 minutes -0.071 (-0.160 to -0.023) and the
  blind lead-time blend -0.044 (-0.086 to -0.018) are real. The stacked sentence is what turns
  the model into one that beats XGBoost on its own out of time.
- **More steps do not carry out of time (05:10):** the 5,000-step stacked text model on the same
  September examples scores 2.741 / 2.161: CRPS -0.014 (-0.058 to +0.019) against XGBoost, no clear
  difference, where the 2,000-step model had -0.039 real. Within 15 minutes -0.086 (-0.175 to
  -0.038) and the blind blend -0.040 (-0.082 to -0.011) stay real.
- **Planned trajectory channels** (running time, dwell and minutes left per stop through the
  encoder, `examples_v5`): 3.604 / 2.879 against 3.606 / 2.878 without them. Nothing.

### Finals: 12,000 steps, full test set (93,738 examples)

Scored on every test example; bootstraps on the 88,479 that ran, against XGBoost on the same
features (3.462 / 2.759 on the original features).

| Model | Median error | CRPS | vs XGBoost (CRPS, 95% interval) |
|---|---|---|---|
| Text plus encoder, plain loss (04:47) | 3.397 | 2.699 | -0.060 (-0.073 to -0.048), real |
| same, within 15 min (36,556) | | | -0.091 (-0.116 to -0.069), real |
| same, beyond 30 min (39,829) | | | -0.046 (-0.063 to -0.029), real |
| its lead-time blend | 3.387 | 2.692 | -0.067 (-0.078 to -0.056), real |
| Text, plain loss, 24,000 steps (05:15) | 3.374 | 2.680 | -0.079 (-0.091 to -0.067), real; within 15 min -0.100, beyond 30 min -0.073; against text plus encoder at 12,000 steps -0.019 (-0.024 to -0.013), real |
| Text, combined data (previous trains, 720 h), exact-minute plus CRPS loss (05:10) | 3.322 | 2.644 | -0.076 (-0.088 to -0.065) against XGBoost on the combined features (3.414 / 2.720), real |
| same, within 15 min | | | -0.092 (-0.117 to -0.070), real |
| same, beyond 30 min | | | -0.073 (-0.087 to -0.059), real |
| same, against text plus encoder with the plain loss | | | -0.054 (-0.062 to -0.047), real |

- **The long run closes the gap beyond 30 minutes.** The same recipe at 2,000 steps lost to
  XGBoost beyond 30 minutes (+0.076) and overall (+0.015); at 12,000 steps it wins at every lead
  time on the full test set, alone. Validation 2.709 / 2.175.
- **Better data and the exact-minute loss add another 0.054.** The text model on the combined
  data beats XGBoost trained on the same features by 0.076 on the full test, with the lead-time
  blend choosing weight 1.0: nothing left for XGBoost to add. Validation 2.665 / 2.139.
- **September (05:30), 10,000 examples:** the combined-data text final scores 2.669 / 2.106 on the
  combined-feature September set against XGBoost's 2.745 / 2.175: CRPS -0.070 (-0.111 to -0.041),
  median error -0.076, within 15 minutes -0.096, all real, alone. Text plus encoder with the plain
  loss on the original September set: 3.214 / 2.566 against 3.244 / 2.586, -0.020 (-0.042 to
  +0.003) alone, within 15 minutes -0.040 and the blind blend -0.031 real.

### Fourth wave: what the time series and the embeddings add (05:00)

Same data (`examples.parquet`), exact-minute plus CRPS loss, 2,000 steps, the same 5,000 test
examples; only the route by which the four series reach the model changes. Every prompt keeps
the rationale sentence (current delay, trend, 30-day median), so "no series" still knows the
summary numbers.

| Series reach the model | Prompt tokens (median) | Median error | CRPS | vs text (CRPS, 95% interval) |
|---|---|---|---|---|
| Not at all | 365 | 3.677 | 2.957 | +0.054 (+0.023 to +0.085), worse |
| As numbers in the text | 844 | 3.621 | 2.903 | |
| Through the encoder only | 365 + 45 soft | 3.693 | 2.956 | +0.052 (+0.025 to +0.083), worse; vs not at all -0.002 (-0.014 to +0.011) |
| Through the encoder only, 12,000 steps (third wave) | 365 + 45 soft | 3.602 | 2.889 | no-series partner at 12,000 steps *running* |
| Through the encoder only, one value per patch (`z4`) | 365 + about 230 soft | 3.689 | 2.959 | vs the encoder with patches of four +0.003 (-0.010 to +0.016) |
| Text plus encoder | 961 + 45 soft | 3.617 | 2.898 | -0.005 (-0.023 to +0.011); vs not at all -0.059 (-0.092 to -0.028), real |
| Text plus encoder, numbers hidden in 50% of training rows | 961 + 45 soft | 3.647 | 2.925 | vs text plus encoder +0.027 (+0.003 to +0.052), worse |

- **The time series carry the win.** Without them the model is level with XGBoost (-0.014,
  -0.073 to +0.035); with them it beats it. The series are worth 0.101 CRPS beyond 30 minutes
  (-0.169 to -0.041) and 0.012 within 15 minutes, where the current delay in the rationale
  already says most.
- **At 2,000 steps the encoder reads nothing yet.** Encoder only equals no series on the test set;
  at 12,000 steps the same route reaches the text level (third wave). Whether that gain is the
  series or just longer training is what the 12,000-step no-series run decides.
- **Forcing the model to read the encoder does not help.** Hiding the numbers from the text in half
  the training rows (modality dropout) costs 0.027 against plain text plus encoder, and splitting
  the inputs so the encoder alone carries the long history costs 0.023 on the stacked data. One
  soft token per value instead of patches of four changes nothing. At 2,000 steps, on four short
  series, writing the numbers out is the better route; the encoder matches it at about half the
  prompt when it also has the stacked forecast (0.019 behind).
- **The encoder is the compact route:** the four series cost about 480 prompt tokens as numbers
  and 45 soft tokens through the encoder.

### Fifth wave: series the text did not have (05:20)

A probe of what XGBoost still gets wrong pointed at two histories no input carried
(`examples_v7`, `forward_v7`; same example ids as v4):

- **Same train, last 28 days:** the delay this train number gained or recovered between the
  current stop and the target on each previous day, arrivals strictly before `t0`.
- **Corridor:** trains that left the current stop in the last 3 hours and already reached the
  target, their gains and arrival delays, last 8 by arrival.

Coverage 98% and 82% of examples. Both lists enter the prompt as series (encoder only in `split`
mode) and as scalars for XGBoost; the rationale gets one sentence with the medians.

| Model | 5,000 shared test | Full test | September |
|---|---|---|---|
| XGBoost, combined features (v3) | 3.650 / 2.935 | 3.414 / 2.720 | 2.786 / 2.207 |
| XGBoost with the new series (v7) | 3.507 / 2.824 | 3.278 / 2.616 | 2.645 / 2.100 |
| TSLM, stacked text, v7, 2k | *running* | | |
| TSLM, stacked split, v7, 2k | *running* | | |
| TSLM, stacked text, v7, 12k (final) | | *running, about 09:00* | |

- **The best single improvement of the night, and it helps the baseline too:** -0.111 CRPS for
  XGBoost on the shared test (-0.149 to -0.077), real at every lead time. XGBoost-v7 alone now beats
  the best finished TSLM final (2.616 vs 2.644 on the full test), so the submission comparison is
  against XGBoost-v7.

### Pending at the time of writing

- Long runs on the full test set: text plus encoder with the plain loss (started 00:50); text
  with the plain loss, 24,000 steps (01:06); text on the combined data and text plus encoder on
  the combined data with 72-hour series, both with the exact-minute plus CRPS loss (02:15).
- The September forward test of the 2,000-step text models and of the long runs.
- The plain 2,000-step checkpoint on the full 93,738-example test set.
- The main configuration at 12,000 steps, on an H100 and on the devbox, followed by the September
  forward test.

### Still open

- **TimeF export, resolved:** `add_tasks` re-collected every task and record id per call, so the
  export was quadratic (16k records in 57 s). Tasks now go through TimeNet's `set_task_stream`,
  and the exporter skips TimeNet's per-task record-id scan for task types without record
  references. The full dataset (298,430 records, 582,059 tasks, 88 MB) converts in 93 s and
  writes in 287 s, and TimeNet's `verify()` passes on the result.
- **Team backend bug:** injected job files are sent as plain text instead of base64.

## 17. What the literature says about tonight's findings

Checked against primary sources on 13 September, so the write-up can present the results as
corroborated rather than surprising.

- **Numbers as text is a known strong recipe.** LLMTime (Gruver, Finzi, Qiu, Wilson, NeurIPS 2023,
  arXiv:2310.07820) forecasts by writing the series as digit strings and finds tokenisation decides
  the outcome. Llama 3 tokenises every integer 0 to 999 as one token, which is exactly our answer
  space and our input regime (delays are small integers). Zhang et al. (arXiv:2504.08818) show
  learned tokenisers or encoders can overfit the training distribution and mask the backbone's
  own ability.
- **The extra time-series module is often dispensable.** Tan et al. ("Are Language Models Actually
  Useful for Time Series Forecasting?", NeurIPS 2024 spotlight, arXiv:2406.16964) find that removing
  or replacing the LLM-side adapter does not hurt, and pretrained parts do no better than from
  scratch; our "random encoder equals pretrained encoder" and "text beats encoder" results are the
  same shape. Qiu et al. (arXiv:2602.14744, 2026) argue the opposite on much larger data, so the
  claim is contested, not settled.
- **OpenTSLM's own text-only baseline** (Langer et al., arXiv:2510.02410) loses to the encoder by
  a few F1 points on short series (HAR) and only collapses on long ones (sleep staging, ECG with
  80k tokens). Our four series are short, so the encoder's advantage is not expected here; it
  buys memory and context, which this task does not need.
- **Horizon-dependent combination is standard forecasting practice** (Wang, Hyndman, Li, Kang,
  International Journal of Forecasting 2023; Cerqueira and Torgo, arXiv:2306.14563), with the
  warning that per-horizon weights overfit small calibration sets. Our five bucket weights are
  fitted on 3,000 validation examples and confirmed on 88,479 test examples.
- **Stacking is the oldest combination recipe; an LLM as the second stage is new.** Wolpert
  (Neural Networks 1992) and Breiman ("Stacked regressions", Machine Learning 1996) fit the
  second stage on out-of-fold predictions of the first, which is why XGBoost's forecast in the
  training prompts is out-of-fold. Bates and Granger (1969) and the M4 competition (Makridakis
  et al., IJF 2018: 12 of the 17 most accurate methods were combinations) say combining beats
  either forecaster alone. The nearest LLM work is CorDP (Ashok et al., TMLR 2026,
  arXiv:2508.09904): an LLM is handed a probabilistic forecast from Chronos, Lag-Llama or ARIMA
  and corrects it, beating the base forecaster in 11 of 13 models on the Context is Key benchmark
  (Williams et al., ICML 2025, arXiv:2410.18959); the two failures are the smallest models (1B and
  1.5B), and none is fine-tuned. We found no published case of a fine-tuned 3B model trained on
  out-of-fold base forecasts, which is what the stacked TSLM is, and its blend weight of 1.0 is
  the expected outcome once the second stage already contains the first.
- **Train delay prediction.** Published real-time MAEs of 0.5 to 2.5 minutes (Kecman and Goverde
  2015 on NS; Oneto et al. 2018 on RFI; Spanninger et al. 2022 review) come from short horizons on
  more punctual networks; the RIDE benchmark (Elliker et al., arXiv:2606.05070, Belgian network,
  temporal split) reports persistence 1.61, XGBoost 1.28 and graph networks 1.23 minutes MAE
  within 40 minutes, degrading to 4 to 5 minutes beyond 45, and calls persistence hard to beat by
  a wide margin. Our 3.4 minutes over horizons up to hours on a German summer with 60% long-distance
  punctuality is in the expected band; the per-lead-bucket numbers are the comparable ones.
  Probabilistic per-stop output with CRPS is rare (Spanninger, Wiedemann, Corman 2024 is the
  nearest), which is a fair novelty claim. Deutsche Bahn's own RI-Prognose publishes no delay
  error, only 74% accuracy on cancellation and platform-change announcements.
- **Data sanity.** Official 2025 punctuality (under 6 minutes): long-distance 60.1%, regional
  88.7%; H1 2026 long-distance 58.7% with 8% partly or fully cancelled. Our 25% late stops and 5%
  cancellations across all classes are consistent with that.

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
