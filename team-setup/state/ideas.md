# Ideas

Pre-decision brainstorm log. See AGENTS.md rule 6 / spec 4.1c.

Format:
`- [T+HH:MM] <idea> — <raised by> — status: <raised|exploring|adopted|discarded>`

Offsets below are measured from `build_starts` (2026-09-12T12:30:00Z).
They were first written as T+00:00, the fallback `now_t_plus()` returns while
`build_starts` is unset, and corrected once the event record landed on main.

- [i-366d40b9-80e9-4882-94e2-e51869297761] [T+01:52] Temporal AI Challenge over Deutsche Bahn delay data (HF piebro/deutsche-bahn-data, 26 monthly parquet files, 7.7 GB processed, CC BY 4.0) as the sourced dataset — Jonas — status: exploring
- [i-de7d0ab1-970b-42cf-96a3-bb66a5c4283f] [T+01:52] Define the series as per-station hourly aggregates over months, not per-train-run delay across stops; short irregular per-run sequences would let a text baseline beat the connector — Jonas — status: exploring
- [i-01c5f393-786e-42b8-89a5-d3369e4f6833] [T+01:52] Slice: ~80 busy stations, 6 months, hourly, 3 channels (mean delay minutes, cancellation rate, trains per hour), 168-hour context window — Jonas — status: raised
- [i-216bc263-468e-4416-8b56-bb465b487e44] [T+01:52] Generate QA pairs deterministically: templates plus an answer function computed over the future window, so labels stay objective without a hand-written ground truth — Jonas — status: raised
- [i-b7dd5738-2b84-497d-9d53-4fada61c6aa2] [T+01:52] Three question types: mean delay next 6h (MAE), next day worse than trailing 4-week average (accuracy), peak hour of next day (24-way) — Jonas — status: raised
- [i-ff10632b-02fa-43d6-b0af-06ad2385683b] [T+01:52] Headline baseline is the same base model given identical numbers serialized as text with no connector; it is what proves the connector earns its place — Jonas — status: raised
- [i-8b10081a-9d90-490a-b3c6-f230e514c98a] [T+01:52] Leakage design: 2x2 grid of stations seen/held out crossed with train/future months, one-week embargo between splits, report all four cells — Jonas — status: raised
- [i-a73b8c67-ddac-4111-a672-5be21b1aa07b] [T+01:52] Hour-8 checkpoint ships a baselines-only submission as the floor before any connector training starts — Jonas — status: raised
- [i-bb0ad83a-d294-48e4-807d-85f4d6d41d3c] [T+01:52] Fallback if GPU compute is not settled: ECG-QA on PTB-XL, which has an off-the-shelf QA layer — Jonas — status: raised
- [i-4ae23ac3-6816-40f1-abcd-547a6dfbc0ca] [T+01:52] Open blocker: no GPU compute confirmed for the fine-tune step; this is the go/no-go for the whole challenge pick — Jonas — status: discarded
- [i-ee265cac-92ef-4477-80c1-a5da36c1dccf] [T+01:57] Compute is solved: the deck promises a $1000 Nebius voucher per team plus training-compute access, so the fine-tune step is funded and the earlier blocker is closed — Jonas — status: raised
- [i-1cbca778-e978-4124-bb72-5ad438de1424] [T+01:57] Use TimeNet's BaseHuggingFaceConnector (set HF_REPO, implement convert) but override download to fetch selected monthly parquet files; the inherited download streams one dict per row and 226M rows is not viable — Jonas — status: raised
- [i-8cfae972-497d-4698-a8aa-58ea00ef6887] [T+01:57] Emit the three questions as TimeNet task objects: ScalarPredictionTask for mean delay, ClassificationTask for the comparison and the peak hour, each carrying rationale as the chain of thought — Jonas — status: raised
- [i-5f9a81ac-61c2-4002-8353-5e4037c04e69] [T+01:57] The text baseline is free: OpenTSLM QADataset._format_sample_str serialises the same series into the prompt, so the with-connector versus numbers-as-text comparison needs no extra code — Jonas — status: raised
- [i-121a4a44-d7c6-465b-9b99-e9a7caee2225] [T+01:57] TimeNet ships an add-dataset-connector agent skill at .agents/skills/; point a coding agent at it rather than reverse-engineering the connector contract — Jonas — status: raised
- [i-e021ee1f-aada-4010-9fa0-259eca7456d6] [T+01:57] Gap in the current plan: slide 13 puts 'identify a target user and problem' first and 'a useful problem' heads the rubric, but the DB direction has no named user yet — Jonas — status: raised
- [i-e77e2fbe-3736-4a91-9799-56998a529e45] [T+01:57] Bonus-point lane worth taking since the team is already agent-heavy: an agentic pipeline that searches, assesses and validates candidate datasets — Jonas — status: raised
