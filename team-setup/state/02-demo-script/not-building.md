<!-- Explicit out-of-scope list, derived from demo-script.md. -->

# Not building (for this demo)

- Native Android / iOS apps — PWA only.
- One delay for the whole journey — always per train, chained.
- On-device / in-browser inference — backend only.
- Our own journey planner or ticket exchange — we build on top of the DB app's share flow.
- Advanced journey-planner filters remain out of scope. Akshat explicitly requested two-station lookup for departures from now, with globe exploration and route zoom.
- Previous/next-train delay as model input (series of delays) — imagined for later, add only if the core is done.
- Causal prediction / disaster probability remains evaluation. The homepage may link to clearly labelled station-level possible-cause evidence; never claim it explains a specific train without supporting data.
- Push notifications — only if the PWA check says they work for free; not a demo shot.
- Full network coverage — the model is trained on the one storyline route.
- Training data before October 2025 — old format, excluded.
- Anything not on the shot list in demo-script.md.

# Not building

DRAFT. No active event is configured and `demo-script.md` is still empty, so
nothing here is frozen scope. This is the cut list for the candidate
Deutsche Bahn direction logged in `../ideas.md`. Rewrite it against the real
demo script once a challenge is picked.

| Cut | Why |
|---|---|
| DB live Timetables API (DBOpenData) | Needs a developer-portal key; registration lag does not fit the build window. Static monthly parquet instead. |
| Weather, traffic or event-calendar joins | Extra sourcing and alignment work that no rubric line rewards. |
| Network graph effects (delay propagation between stations) | Interesting and large; a separate project, not a 24-hour deliverable. |
| Per-train-run sequences across stops | Too few, too irregular to need a temporal model; a text baseline would match it. |
| Any fourth question type | Three cover numeric, binary and multi-class scoring already. |
| Pretraining a time-series encoder from scratch | Only the connector projection is trained; the base model stays frozen. |
| Raw hourly partition (`raw_data/`, the bulk of the 67.6 GB) | The processed monthly files carry every column the slice needs. |
| Serving, auth, persistence, multi-user state in the demo | Single-operator demo run from one machine. |

The two lists above were written before and after the challenge pick; where they disagree (e.g. the live Timetables API), the decisions log wins until the team reconciles this file.
