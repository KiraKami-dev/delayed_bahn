<!-- Explicit out-of-scope list, derived from demo-script.md. -->

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
