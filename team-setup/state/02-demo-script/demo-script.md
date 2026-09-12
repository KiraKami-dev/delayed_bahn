<!-- The 90-second demo, shot by shot. FROZEN once written. -->

# Demo script — DRAFT, freezes when the storyline route is picked

**Status:** draft. Shots are settled; the route, station names and numbers
are placeholders until the "pick the storyline route" task is done. After
that this file is frozen (AGENTS.md rule 5).

**Format:** live pitch. **Storyline route:** `<ROUTE — our biggest trouble with DB>`.

| Time | Shot | On screen |
|---|---|---|
| 0:00–0:10 | The pain | Presenter: "I was too frustrated to come to Zurich." Photo/screenshot of the real DB journey on `<ROUTE>` with its connections. Half an hour of buffer was not enough. |
| 0:10–0:20 | Share from DB | Phone (mirrored): open the DB app, press **Share** on the connection, pick our PWA from the share sheet. |
| 0:20–0:30 | Journey extracted | Our app shows the parsed journey: each train as a card (train, from → to, planned times, transfer time). No typing. |
| 0:30–0:45 | Per-train delay | Each card gets a predicted delay from the fine-tuned model, with the chain shown: train 1 late → transfer shrinks → train 3 missed. Headline: **"Probability your plan fails: NN%"**. |
| 0:45–0:60 | Recommendation | Below the number, plain-language advice: "take the earlier IC, 25 min more buffer, you arrive relaxed" or "this connection is good". Tap → alternative connection with comfortable transfer. |
| 0:60–0:75 | Proof | Side by side: our model vs the given baseline (raw data into GPT / Claude Opus) on the Oct→Aug held-out data for `<ROUTE>`. One chart, one number. |
| 0:75–0:90 | Close | Weather-forecast line: "not 'it will rain' — 'take an umbrella'." Installed-PWA icon on the home screen. What's next: causes (level 3). |

## Minimum build list (derived from the shots)

- Shot 0:10 — PWA registered as a share target (web share target manifest); installable.
- Shot 0:20 — share-text parser: DB share text → structured journey (handles more than one connection in the text).
- Shot 0:30 — backend inference endpoint: journey → per-train delay estimate → chained failure probability; fine-tuned 0.5B / 3B model trained on `<ROUTE>` Oct→Aug data.
- Shot 0:45 — recommendation algorithm on top of the delay output; alternative-connection lookup via the timetable API.
- Shot 0:60 — evaluation script: our model vs the raw-data-into-GPT/Opus baseline, one chart.
- All shots — seed journey for `<ROUTE>` that works offline if the API is down (failure recovery).
