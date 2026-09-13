# Runs on Nebius H100 jobs

Every job ran `trip/nebius/run_ablations.sh` on one H100 with the examples file named in the
`Examples` column mounted as `data/trip/examples.parquet`, and the command below inside it.
Scores are `median error / CRPS` in minutes on the job's validation and test subsets (lower is
better); the test subset is the same 5,000 examples for every 2,000- and 5,000-step run and
the full 93,738 for the long runs (`--test-limit 0`). Blends, bootstraps and the September
forward test are computed afterwards on the devbox with `combine.py`, `bootstrap.py` and
`apply_blend.py`; see DESIGN.md section 16.

| Job | Examples | Steps | Command | Validation | Test |
|---|---|---|---|---|---|
| jonas-h100-ecg-sp-start-2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --start-checkpoint OpenTSLM/llama-3.2-3b-ecg-sp` | 2.807 / 2.276 | 3.711 / 2.994 |
| jonas-h100-eval-plain-full | examples.parquet | 1 | `python trip/train.py --max-steps 1 --val-limit 3000 --test-limit 0 --generate 0 --eval-only --loss-mode plain --resume /data/runs/h100b-plain_ce/plain_ce/checkpoint.pt --splits test --eval-batch-size 32` |  | 3.477 / 2.774 |
| jonas-h100-both-fixed-caption-2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode both --series-scaling fixed --caption-share 0.3 --grad-checkpointing` | 2.767 / 2.218 | 3.647 / 2.913 |
| jonas-h100-both-plain-2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode both --grad-checkpointing` | 2.781 / 2.225 | 3.641 / 2.912 |
| jonas-h100-enc-12k | examples.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode series` |  |  |
| jonas-h100-enc-caption | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode series --caption-share 0.3` | 2.806 / 2.269 | 3.756 / 3.000 |
| jonas-h100-enc-fixed-caption | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode series --series-scaling fixed --caption-share 0.3` | 2.821 / 2.257 | 3.756 / 2.992 |
| jonas-h100-enc-fixed | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode series --series-scaling fixed` | 2.788 / 2.231 | 3.719 / 2.966 |
| jonas-h100-enc-lr5x | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode series --lr-encoder 1e-3` | 2.793 / 2.236 | 3.687 / 2.956 |
| jonas-h100-enc-stage1 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode series --lr 0 --lr-encoder 5e-4` | 2.825 / 2.288 | 3.724 / 3.031 |
| jonas-h100-enc-stage2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode both --resume /data/runs/h100-enc-stage1/custom/checkpoint.pt` |  |  |
| jonas-h100-final-both | examples.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 0 --generate 48 --loss-mode plain --prompt-mode both --grad-checkpointing --eval-batch-size 32` |  |  |
| jonas-h100-final-text | examples.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 0 --generate 48 --loss-mode plain --prompt-mode text --grad-checkpointing --eval-batch-size 32` |  |  |
| jonas-h100-final-v2-text | examples_v2.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 0 --generate 48 --loss-mode plain_crps --prompt-mode text --eval-batch-size 32` |  |  |
| jonas-h100-final-v3-both | examples_v3.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 0 --generate 48 --loss-mode plain_crps --prompt-mode both --grad-checkpointing --eval-batch-size 32` |  |  |
| jonas-h100-long-both | examples_720h.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode both --grad-checkpointing` | 2.786 / 2.231 | 3.657 / 2.924 |
| jonas-h100-long-series | examples_720h.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode series --grad-checkpointing` | 2.807 / 2.252 | 3.709 / 2.959 |
| jonas-h100-ms-both | examples_ms.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode both --grad-checkpointing` | 2.760 / 2.213 | 3.630 / 2.914 |
| jonas-h100-ms-text | examples_ms.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode text --grad-checkpointing` | 2.763 / 2.219 | 3.635 / 2.912 |
| jonas-h100-text-24k | examples.parquet | 24000 | `python trip/train.py --max-steps 24000 --val-limit 3000 --test-limit 0 --generate 48 --loss-mode plain --prompt-mode text --eval-batch-size 32` |  |  |
| jonas-h100-text-5k | examples.parquet | 5000 | `python trip/train.py --max-steps 5000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode text --grad-checkpointing` | 2.757 / 2.212 | 3.614 / 2.883 |
| jonas-h100-text-plain-repeat | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode text --grad-checkpointing` | 2.776 / 2.232 | 3.635 / 2.913 |
| jonas-h100-text-plain-2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode text --grad-checkpointing` | 2.781 / 2.233 | 3.635 / 2.907 |
| jonas-h100-text-plaincrps | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode text --grad-checkpointing` | 2.746 / 2.192 | 3.621 / 2.903 |
| jonas-h100-v2-both | examples_v2.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode both --grad-checkpointing` | 2.761 / 2.201 | 3.603 / 2.877 |
| jonas-h100-v2-text | examples_v2.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode text --grad-checkpointing` | 2.751 / 2.213 | 3.616 / 2.889 |
| jonas-h100-v3-both | examples_v3.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode both --grad-checkpointing` |  |  |
| jonas-h100-v4-text-5k | examples_v4.parquet | 5000 | `python trip/train.py --max-steps 5000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode text --grad-checkpointing` |  |  |
| jonas-h100-v4-text | examples_v4.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode text --grad-checkpointing` |  |  |
| jonas-h100-v5-both | examples_v5.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode both --grad-checkpointing` |  |  |
| jonas-h100-main-12k | examples.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 30000 --generate 48` | 2.767 / 2.232 | 3.434 / 2.754 |
| jonas-h100-main-2k | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16` | 2.818 / 2.281 | 3.711 / 2.994 |
| jonas-h100-plain-5k | examples.parquet | 5000 | `python trip/train.py --max-steps 5000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain` | 2.778 / 2.227 | 3.678 / 2.923 |
| jonas-h100-plain-lr2x | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --lr 2e-4 --lr-encoder 4e-4` | 2.784 / 2.243 | 3.717 / 2.956 |
| jonas-h100-plain-ce-2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain` | 2.788 / 2.240 | 3.702 / 2.954 |
| jonas-h100-random-encoder-2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --start-checkpoint none` | 2.825 / 2.285 | 3.727 / 3.006 |
| jonas-h100-text-only-2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --text-only --grad-checkpointing` | 2.788 / 2.247 | 3.635 / 2.938 |
