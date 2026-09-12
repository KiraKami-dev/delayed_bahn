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

## Nebius region gotcha (12 Sep 2026, evening)

- The console's default project is **eu-west1**, which only offers `gpu-h200-sxm`.
  Three jobs there requested the full `8gpu-128vcpu-1600gb` node and all
  failed with `NotEnoughResources` (VM schedule timeout). Credits were never
  the problem; capacity was.
- **Team default: us-central1** (`project-u00re9y9kc00bwpa7d9ftt`, subnet
  `vpcsubnet-u00dkfnwx2mpagdhtw`): B200 180 GB (`gpu-b200-sxm`,
  `1gpu-20vcpu-224gb`, ~$7.15/h, ~84 h on $600), H200, RTX6000.
  `app/backend/.env.example` points there; the CLI profile on Akshat's
  machine was switched too.
- **Fallback: eu-north1** (`project-e00g0c62pr00fj32s0h4gj`, subnet
  `vpcsubnet-e00hf5r45dv0k0aa0b`): H100, H200, L40S-a, L40S-d. A 1× L40S
  smoke job scheduled there on the first try.
- **8× H200 does not schedule anywhere tonight.** Quota is fine (32 H200
  per region). eu-west1: 3 jobs errored. eu-north1: VM allocated but never
  started in 24 min, cancelled. us-central1: same, still stuck after 10+
  min at 19:35 UTC. Single-GPU jobs start in 2–3 min. Request **one GPU**;
  the 8-GPU node is ~$36/h anyway (~16 h on $600).
- Verified tonight: 1× L40S in eu-north1 and 1× B200 in us-central1 both
  ran nvidia-smi end to end with `npm run train -- smoke`.
