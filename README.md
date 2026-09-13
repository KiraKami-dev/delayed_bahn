# DelayedBahn

**Share your DB trip. Know which change will break, and what to do about it.**

DelayedBahn is an installable web app for Deutsche Bahn travellers. Share a journey from DB Navigator and it forecasts how late each train is likely to be, the chance of making every change, and the best move if a change is at risk. Two fine-tuned time-series language models, trained on DB's own delay history and fed today's live data, answer every trip.

Built by team **error404.ai** at the European Hackathon League Zurich, September 2026.

`Llama 3.2 3B` · `OpenTSLM` · `LoRA` · `Nebius H100` · `DB API Marketplace` · `React PWA` · `Node, zero dependencies`

---

## Contents

1. [Problem](#problem)
2. [What we built](#what-we-built)
3. [Features](#features)
4. [How a shared trip flows through the system](#how-a-shared-trip-flows-through-the-system)
5. [Architecture](#architecture)
6. [Data](#data)
7. [Agentic data retrieval](#agentic-data-retrieval)
8. [Models](#models)
9. [Approach: two methods, combined](#approach-two-methods-combined)
10. [Evaluation](#evaluation)
11. [Limitations, stated plainly](#limitations-stated-plainly)
12. [Code structure](#code-structure)
13. [Quickstart](#quickstart)
14. [Team](#team)
15. [Built with](#built-with)
16. [Screenshots](#screenshots)

---

## Problem

Everyone who travels with Deutsche Bahn knows the situation: trains are late and connections break. The DB app shows the planned journey, not the chance that it actually works. A trip with a change fails at its tightest connection, and travellers find out on the platform.

We cannot fix delays for everyone. We can give each traveller a more reliable and comfortable journey: know in advance which change is at risk, how much buffer would fix it, and which alternative to take if it fails. That is where the app comes in.

Three things make this hard, and shape the design:

- **Delays are uneven.** Most trains are a few minutes late, a few are very late. A single "expected delay" hides the risk. A traveller needs a distribution and the probability of the tight change.
- **A journey is a chain.** It fails at its weakest transfer, so per-train forecasts must be chained across changes.
- **The data is scattered.** Live positions from the DB API, months of history in open datasets, station cause codes, cancellation rates. Deciding what to fetch and what to drop is a task of its own.

## What we built

- **Share a trip** from DB Navigator straight into the app. It reads trains, stations and times from the share text.
- **A forecast per train:** likely arrival delay, a 10 to 90 percent range, the chance of arriving on time, and the chance of making each change, chained over the whole journey.
- **Advice:** the plan is fine, add this much buffer, leave home by this time, or take one of these alternatives. Already missed a change? The next connections from where you stand, each scored.
- **The model's own words:** for every train, the exact inputs the model read, then the explanation it writes itself.
- **Why:** what usually goes wrong at each station, from DB's cause codes.
- **Two models that complement each other:** a trip model that reads a train's live position, and a route model that knows every recorded service at every station. The backend asks the second wherever the first has nothing to go on.
- **An agentic data retrieval loop** that searched four open-data registries, assessed 354 candidate sources, and kept the 7 that survived licence, coverage and live schema checks. Every decision is logged.

## Features

| Screen | What it does | Backend |
|---|---|---|
| **Plan** | Paste or share DB text, drop a `.txt`, or try the example trip. One card per train. | `POST /api/journeys/parse` |
| **Map** | The route on a satellite globe of Germany, legs coloured by risk, trains moving along the track, camera choreography per screen. | |
| **My journey** | Headline: the chance the plan fails. Per-train delay bars with range, a chain strip across changes, a buffer slider that re-runs the chain on the client. Each card carries the model's take: instantly the inputs it read, then its own words when written, with a live "writing, train 2 of 3" note. | `POST /api/predict`, `POST /api/explain` |
| **What next?** | Verdict and advice, leave-home-by time, alternatives compared, "I missed my connection" re-routing drawn on the map, share the result. | `POST /api/recommend`, `POST /api/reroute` |
| **Why?** | Cause families at the station (works, weather, technical, knock-on), the top DB cause codes, a 7-day sparkline. | `GET /api/causes` |
| **Evidence** | Data sourcing, model-versus-baseline chart, limitations, install button. | |
| **Install and share** | PWA with a Web Share Target, so "Share" in DB Navigator lists DelayedBahn. Stage mode for presenting from the app. | `GET /api/seed/demo` |

Everything shown is labelled by where it came from: live forecast, recorded history, class average, or illustrative example. The app never substitutes sample data for a real trip.

## How a shared trip flows through the system

```mermaid
sequenceDiagram
  autonumber
  participant DB as DB Navigator
  participant App as DelayedBahn PWA
  participant BE as Node backend :8000
  participant Trip as Trip model :8502
  participant Route as Route model :8501 / :8503
  participant API as DB Timetables API

  DB->>App: share text (Web Share Target)
  App->>BE: POST /api/journeys/parse
  BE-->>App: Journey (trains, EVA stations, times)
  App->>BE: POST /api/predict
  BE->>Trip: forecast every leg
  Trip->>API: live position, stops ahead, station lateness
  Trip-->>BE: minute distribution per leg, or "class average" when no trip matches
  BE->>Route: only the legs the trip model could not forecast
  Route-->>BE: distribution of the recorded service at that station
  BE-->>App: chained forecast: per-train delay, change risk, plan-fail probability
  App->>BE: POST /api/recommend
  BE-->>App: verdict, buffer, alternatives
  loop one train at a time
    App->>BE: POST /api/explain
    BE->>Trip: generate the rationale in the model's own words
    Trip-->>App: two-sentence summary and full text
  end
```

1. **Parse.** A grammar reads the DB share text in German or English (`RE16 (59129) … From 16:39 Nürnberg Hbf, Platform 5`) into trains, stations and times, and resolves stations to EVA numbers.
2. **Forecast.** The trip model receives every leg. For a train it finds in the live timetable it reads the delay so far, the stops ahead, how earlier trains on the line did today and how late the station is running, and answers with a probability for every minute from 0 to 999 plus the chance of cancellation.
3. **Complement.** For legs with no recorded or live trip, where the trip model would only return the average of its train class, the backend sends exactly those legs to the route model, which forecasts the recorded service at that station from 60 days of six-hourly history. The reply names both models and marks which legs came from which.
4. **Chain.** The change probability at each transfer comes from both trains' distributions and the planned transfer time. The plan-fail probability chains all changes. This is a JavaScript port of the Python `connection.py`, so the buffer slider re-runs it on the client without a round trip.
5. **Advise.** The recommendation feature turns the chain into a verdict, a leave-home-by time and scored alternatives.
6. **Explain.** After the forecast, the app asks for each train's explanation in turn. Generation takes about a minute per train on a laptop, so the card shows the instant rationale first and swaps in the model's own words when they arrive.

## Architecture

```mermaid
flowchart TB
  subgraph Data["Data layer  (Python, app/agents)"]
    R["Agentic retrieval loop<br/>search · assess · select · retrieve · validate<br/>LLM proposes, code verifies"]
    H["piebro/deutsche-bahn-data<br/>one row per train per stop, months of history"]
    L["DB Timetables + RIS::Stations<br/>plan, live changes, cancellations, cause codes"]
    C["TimeNet connectors<br/>error404/db-route-{week, quarter, season, multiscale}"]
    E["Trip examples<br/>one train, one target stop, v7 features + XGBoost prior"]
    R --> C
    H --> C
    H --> E
    L --> E
  end

  subgraph Train["Training  (Nebius H100 jobs)"]
    T1["Trip model<br/>OpenTSLM on Llama 3.2 3B, LoRA<br/>history as time-series embeddings + text"]
    T2["Route model<br/>OpenTSLM on Llama 3.2 3B, LoRA<br/>quarter profile: 60 days × 6 h"]
    E --> T1
    C --> T2
  end

  subgraph Serve["Serving"]
    S1["trip/serve.py  :8502<br/>Apple silicon, live DB calls, 60 s cache"]
    S2["db_route/serve_route.py  :8501<br/>stored held-out forecasts + station causes"]
    S3["db_route/serve_live.py on an H100<br/>reached through a bucket relay  :8503"]
    T1 --> S1
    T2 --> S2
    T2 --> S3
  end

  subgraph Backend["Node backend  :8000"]
    P["share-parser"]
    D["delay-prediction<br/>trip model first, route model for the rest,<br/>connection chain"]
    A["recommendation · reroute"]
    W["causes"]
    J["training-jobs<br/>submit and watch Nebius GPU jobs"]
  end

  subgraph App["React PWA  (Vite, MapLibre)"]
    U["Plan · Map · My journey · What next? · Why? · Evidence"]
  end

  S1 --> D
  S3 --> D
  S2 --> W
  P --> U
  D --> U
  A --> U
  W --> U
```

**Three layers, one feature name per layer.** Every feature lives at `app/<layer>/src/features/<name>/` on the frontend, the backend and the agents side, so `delay-prediction` in the app, in the backend and in the Python model server is one feature in three halves.

**Serving on one laptop.** The trip model runs on the Mac's GPU through MPS. The route model's stored forecasts and station causes are served from parquet and npz files with no torch at all. When a GPU job is up on Nebius, the route model also answers live per request: Nebius jobs have no inbound network, so requests travel as files through the project's storage bucket and the job answers the same way, about 0.6 s round trip plus 50 to 90 ms of inference.

**The backend has no npm dependencies.** Node's built-in `http`, `fetch` and `crypto` cover parsing, chaining, both model calls and the GPU job client.

## Data

### Sources

All product data comes from Deutsche Bahn's official API Marketplace and from open datasets built from the same feeds.

| Source | What we use it for | Coverage |
|---|---|---|
| [Timetables API](https://developers.deutschebahn.com/db-api-marketplace/apis/product/timetables) | Planned stops (`plan`), live delays, cancellations and platform changes (`fchg`), the route of every train | Current and upcoming trains, 60 calls per minute per key |
| [RIS::Stations](https://developers.deutschebahn.com/db-api-marketplace/apis/product/ris-stations) | Official station names and EVA numbers | Current |
| [`piebro/deutsche-bahn-data`](https://huggingface.co/datasets/piebro/deutsche-bahn-data), CC BY 4.0 | Stored Timetables responses, one row per train per stop. The models are trained on this. | Months of history, all of Germany |
| DB cause codes (IRIS) | Cause families per station for the "Why" tab and the cause-share series | From the same feeds |

- **Historic DB data** trains the models: `scripts/db_live_extract.py` merges plan and changes into one row per train per stop, `trip/build.py` turns rows into examples.
- **Live DB data** is fetched when a traveller shares a trip (`trip/live.py`) and assembled into the same row format the model was trained on.

### What the DB data solves

| Traveller question | DB data that answers it |
|---|---|
| "Which train and station is this?" | Timetables `station` lookup and RIS::Stations turn the share text into exact station IDs |
| "Is my train late right now?" | The change feed gives the current delay at every stop the train has passed |
| "Will it get worse before my stop?" | Planned route and stops ahead, plus how earlier trains on the same line did today |
| "Is this station having a bad day?" | Late share across all trains at the station in the last hours |
| "Will this train be cancelled?" | Cancellation flags in the change feed, and how often this route was cancelled before |
| "Will I make my change?" | Planned arrival and departure of both trains, combined with both delay distributions |

## Agentic data retrieval

Before training, an agent decided which open time-series sources to use and how to map their columns onto our spec. It is a search, assess, select, retrieve and validate loop in which **the LLM proposes and deterministic code disposes**: nothing the agent says is used until code has verified it.

```mermaid
flowchart LR
  S["Search<br/>agent writes registry queries,<br/>code runs them live"] --> A["Assess<br/>agent rates relevance,<br/>code applies licence, credential,<br/>coverage and cadence gates"]
  A --> P["Select<br/>agent fills a rubric,<br/>code probes the source live<br/>(DuckDB over HTTP range reads)"]
  P --> M["Retrieve<br/>agent proposes a column map,<br/>code type-checks every column<br/>against the probe"]
  M --> V["Validate<br/>accept / reject table with<br/>the failing gate per source"]
```

| Step | The agent proposes | The code verifies or refuses |
|---|---|---|
| Search | registry queries for four catalogues, from the data spec | every query runs against the live registry API |
| Assess | relevance of each candidate, with a reason | licence allow-list, credentials, coverage window, cadence, cheapest first |
| Select | rubric fields per surviving source | a live probe measures rows, columns, coverage and the station-basis change of 2 November 2025 |
| Retrieve | a column map from the source schema to the spec | every named column must exist and type-check against the probe, or the map is rejected |
| Validate | | `REJECTIONS.md` with the failing gate per source |

An unverifiable proposal is dropped, never negotiated. Every LLM call, its prompt and its answer are logged so a reader can audit each decision. The loop also runs without an LLM: the same gates and probes, no proposals.

**Run of record.** Window 2 November 2025 to 31 August 2026, four registries (a curated list, Hugging Face datasets, govdata CKAN, Zenodo): **354 candidates, 18 passed every gate, 7 probed live and used, 11 accepted on metadata only.** The rest are rejected with the gate that failed.

**Why it matters for the model.** What gets dropped is noise. Sources with the wrong cadence, an incompatible licence or a schema that does not type-check never reach the training set, so the model's inputs are only the columns the spec asked for and the probe confirmed. The connectors that build the training datasets consume these decisions, not the loop's code.

## Models

Both models share one recipe: **Llama 3.2 3B**, an open-source language model, extended with **OpenTSLM** so it can read time series next to text, started from the published `OpenTSLM/llama-3.2-3b-m4-sp` checkpoint and fine-tuned with LoRA on Nebius H100s. Both answer with `Answer: <minutes>` or `Answer: cancelled`. Instead of reading one number, we read the full softmax over the minute tokens, which gives a probability for every minute from 0 to 999 and the chance of cancellation. Training uses the exact minute plus a CRPS term, so the distribution is calibrated, not only the median.

### Trip model: one train, one target stop, today

- **Example:** a train heading to a stop. Inputs: the delays so far on this trip, this train number's usual gains along the line, the corridor's recent delays, how late the station is running, and the forecast of a statistical XGBoost model on the same features.
- **Live at request time.** The server fetches the train's current position from the Timetables API, assembles the row the model was trained on, and forecasts. One key at 60 calls per minute serves about two new legs per minute: a cold four-train journey takes about a minute, repeats within a minute are instant. When live data fails it answers with an offline estimate from recorded trips and says so.
- **Explains itself.** The same model generates its rationale freely, about 360 tokens, so the app shows the model's own words next to the forecast.

### Route model: any recorded service, any station, any date

- **Example:** a service group at a station on a travel date, with 60 days of six-hourly delay, throughput and cause-share history at that stop and across the service. Four history profiles were trained in a bake-off (a week hourly, a quarter six-hourly, a season, multiscale). The **quarter** profile won every held-out cell.
- **Covers what the trip model cannot.** 10,204 recorded service-station rows across 2,539 stations and 722 service groups, including trips days ahead for which the live timetable has nothing yet. It also carries the cause families per station behind the "Why" tab.
- **Served two ways:** from stored held-out forecasts on the laptop, or live per request on an H100 job through the bucket relay.

### Why two models

They fail in different places. The trip model is strongest for a train that is running now, because it reads its live position; for a journey next Tuesday it finds no trip and can only return the average of its train class. The route model knows every recorded service on the corridor regardless of the day, but nothing about today's position. The backend asks the trip model first and hands only the legs it could not forecast to the route model. On a three-train journey two days out, that turned two "not a forecast" averages into model forecasts while keeping the one live forecast.

## Approach: two methods, combined

The model can take the same delay history in two ways (`--prompt-mode` in `trip/train.py`):

- **Time-series embeddings:** the delay series go through OpenTSLM's time-series encoder, which turns them into embeddings the language model reads directly.
- **Pure text:** the same numbers are written into the prompt as text, together with a short sentence that describes them.
- **Combined (split):** the long history, the same-train gains and the corridor series as embeddings; the short recent trajectory as text.

Each method is an existing tool on its own. We train each separately and then the combination, so the comparison shows what each part adds. With the rationale cut down to the bare timetable, so that the series are the only source of signal, the ranking on 4,729 shared test trains at 2,000 steps is:

| Input | CRPS | Median error | Within a minute |
|---|---|---|---|
| No series | 3.68 | 4.66 min | 56% |
| Embeddings only | 2.99 | 3.73 min | 62% |
| Text only | **2.79** | **3.48 min** | **66%** |

Both routes carry the signal; text reads it a little better than the encoder at this budget. With the full written rationale all three tie, because the summary sentences already state what the series hold. The **combined split model** is the one shipped in the app; the **stacked text model at 12,000 steps** is the submission checkpoint. Full run tables: `app/agents/src/features/db_delay/trip/RUNS.md`.

## Evaluation

- **Baselines.** Every model is compared against simple and statistical baselines on the same information: persistence, route history, gradient boosting, XGBoost with the same features.
- **Split by time.** The test period is later than training, so no future information leaks. The trip model is also scored forward on September, a month it never saw in any form.
- **Metrics.** Median error is the median absolute error of the predicted median, in minutes. CRPS scores the whole distribution; lower is better. "Within a minute" is the share of trains whose predicted median is at most one minute off.

### Trip model against XGBoost on the same features

| Test set | Trains | Model | XGBoost | Within a minute, model | Within a minute, XGBoost |
|---|---:|---|---|---|---|
| June to August, held out | 28,290 | 3.23 min | 3.30 min | 66% | 59% |
| September, forward in time | 9,573 | 2.53 min | 2.60 min | 70% | 62% |

Shipped combined model, 6,000 steps. The submission text model at 12,000 steps scores median error 3.19 and CRPS 2.54 on all 93,738 test examples and 2.52 and 1.99 on 10,000 September examples, beating XGBoost by 0.08 and 0.07 minutes with confidence intervals that exclude zero.

### Route model, quarter profile, 2,000 steps

| Cell | Rows | Model | Gradient boosting | Persistence | Blend |
|---|---:|---|---|---|---|
| Unseen trains and weeks (headline) | 462 | 1.82 / 1.37 | 1.82 / 1.37 | 1.84 | 1.79 / 1.35 |
| Known trains, unseen weeks (deployment) | 600 | 1.69 / 1.32 | 1.61 / 1.25 | 1.71 | 1.61 / 1.25 |

Median error / CRPS in minutes. About 30 percent under the naive train-median baseline. Coverage of the 10 to 90 percent range is 0.70 to 0.80 against a 0.80 target, so the distributions are slightly narrow. Generated-answer accuracy on late/on-time plus cause family: 0.73 against a 0.38 majority class.

### Serving

| Path | Latency |
|---|---|
| Trip model, cached leg | milliseconds |
| Trip model, cold leg with live DB data | 15 to 40 API calls, up to a minute at 60 calls per minute |
| Route model, stored forecast | 7 ms for a whole journey |
| Route model, live on the H100 through the bucket relay | 0.6 s round trip, 50 to 90 ms inference |
| The model's own explanation | about a minute per train on a laptop |

## Limitations, stated plainly

- **The models beat a strong tabular baseline by a small, consistent margin.** Tenths of a minute, with confidence intervals that exclude zero on the trip model. They are not an order of magnitude better than XGBoost, and the Evidence screen says so.
- **A forecast for a day ahead is a forecast of the recorded service, not of that train.** The route model's reply names the record, its travel date and what then happened; the app labels it.
- **The model's own words can misstate numbers.** They are generated freely. The estimate above them reads the exact inputs, and the card says so.
- **Live data is rate-limited.** One DB key means the first check of a long journey takes about a minute. The app shows progress rather than a spinner.
- **Nothing is substituted.** When a service is down the app says which one. Only the bundled example trip ever falls back to a bundled sample, labelled as such.

## Code structure

```
app/backend/           Node API, zero dependencies
  src/features/share-parser/        DB share text → Journey (grammar, station lookup)
  src/features/delay-prediction/    trip model → route model complement → connection chain
  src/features/recommendation/      verdict, buffer, leave-home-by, reroute
  src/features/causes/              cause families per station
  src/features/journey-search/      direct train lookups on the DB API
  src/features/training-jobs/       Nebius Serverless AI jobs: submit, status, logs, cancel
app/frontend/          React 19 + Vite PWA, MapLibre globe, one folder per screen under src/features/
app/agents/            Python
  src/features/db_delay/trip/       trip model: build examples, train, serve, run_local.sh, connection.py
  src/features/db_route/            route model: connectors, train_route.py, serve_route.py, serve_live.py,
                                    relay_proxy.py, RESULTS.md, TRAINING.md
  src/features/db_route/discover/   the agentic data retrieval loop and its run of record
  connectors/error404/              TimeNet connectors for the four db-route profiles
scripts/               DB Timetables and RIS::Stations clients
team-setup/            coordination: contract, owners, decisions
```

| File | What it does |
|---|---|
| `scripts/db_live_extract.py` | Calls Timetables and RIS::Stations, merges plan and changes into one row per train per stop |
| `app/agents/src/features/db_route/discover/run.py` | Runs the retrieval loop: search, assess, probe, verify |
| `app/backend/src/features/share-parser/grammar.js` | Reads DB share text into a journey |
| `app/backend/src/features/delay-prediction/routes/delay-prediction.js` | Asks the trip model, complements with the route model, chains changes |
| `app/backend/src/features/delay-prediction/connection.js` | Change and journey probabilities, a port of `connection.py` |
| `app/backend/src/features/recommendation/routes/recommendation.js` | Verdict, alternatives, reroute |
| `app/agents/src/features/db_delay/trip/build.py` | Stop records → training examples |
| `app/agents/src/features/db_delay/trip/train.py` | Fine-tunes the trip model |
| `app/agents/src/features/db_delay/trip/serve.py` | Serves the trip model with live Timetables data and explanations |
| `app/agents/src/features/db_route/train_route.py` | Fine-tunes the route model per history profile |
| `app/agents/src/features/db_route/serve_route.py` | Serves stored route forecasts and station causes |
| `app/agents/src/features/db_route/serve_live.py` | Serves the route model live on a GPU job through the bucket relay |

## Quickstart

```bash
git clone https://github.com/KiraKami-dev/temporal_ai_error404.ai.git
cd temporal_ai_error404.ai
cp .env.example .env               # add DB_CLIENT_ID and DB_API_KEY from developers.deutschebahn.com
ln -s ../../.env app/backend/.env

python3 scripts/db_timetables.py "Hamburg Hbf"                      # live departures from DB
```

**App with the deterministic prior, no model files**

```bash
cd app/backend && npm run dev                                       # API on http://localhost:8000
npm --prefix app/frontend ci && npm --prefix app/frontend run dev   # app on http://127.0.0.1:5173
```

**App with the trained models** (Apple silicon, 16 GB or more; model files from the team's `delayedBahn-model.zip`, see `app/agents/src/features/db_delay/trip/README.md`)

```bash
D=app/agents/src/features/db_delay/trip
$D/run_local.sh setup ~/delayedBahn-env ~/delayedBahn-model/checkpoint.pt ~/delayedBahn-model/september_v7_test.parquet
cp -R ~/delayedBahn-model/xgb ~/delayedBahn-env/xgb
bash app/agents/src/features/db_route/fetch_serving_data.sh && app/agents/src/features/db_route/serve_route.sh --port 8501   # route model and causes
ENV_FILE=.env $D/run_local.sh start ~/delayedBahn-env               # trip model on :8502, app on http://localhost:8000
```

The start script detects the route server and wires it in as the complement and as the causes source. To run the route model live on a GPU job instead, see "Live serving" in `app/agents/src/features/db_route/TRAINING.md`.

**On a phone:** `adb reverse tcp:8000 tcp:8000`, open `http://localhost:8000`, install, then share from DB Navigator.

## Team

**error404.ai** — Akshat Khair (app, backend, serving), Gaurav Kulkarni (agentic data retrieval, route datasets), Jonas Stenglein (trip model), Yash (data extraction)

## Built with

- European Hackathon League Zurich
- Deutsche Bahn API Marketplace: [Timetables](https://developers.deutschebahn.com/db-api-marketplace/apis/product/timetables), [RIS::Stations](https://developers.deutschebahn.com/db-api-marketplace/apis/product/ris-stations)
- [OpenTSLM](https://arxiv.org/abs/2510.02410), Llama 3.2 3B, LoRA, XGBoost, TimeNet, DuckDB
- Nebius H100 GPUs, Node 22, React 19, Vite, MapLibre

## Screenshots

Screenshots of the app, the data extraction and the training runs go in `docs/images/` and are linked here once added.
