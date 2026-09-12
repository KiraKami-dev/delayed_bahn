# Partner Notes

SDK, sandbox, dataset, and credits notes from partner companies on site.

## DB / timetable API (12 Sep 2026)

- API connection confirmed working. Stick with it.
- Rate limit: **60 requests per minute** per client. Access is a client ID
  and a client secret; registering several is an open idea (`ideas.md`).
- Timetable data is the primary input. The **RIS disruption feed** was
  mentioned as an additional source.
- Data format changed in October 2025, so the usable window is October
  2025 → August 2026 (~8 months, roughly 10–20 GB).

## Baseline given by the track

- Paste the raw data, not fine-tuned, into GPT / Claude Opus. Beat that
  with a fine-tuned 0.5B or 3B model.

## GPU / training

- Training on Nebius Serverless AI jobs via `app/backend/src/features/training-jobs/`
  (see its README for presets and budget). A run currently takes ~6 min;
  at ~2 h per run there is time for two runs. Real GPU speed still to check.
