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
| jonas-h100-ecg-sp-start-2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --start-checkpoint OpenTSLM/llama-3.2-3b-ecg-sp` |  |  |
| jonas-h100-eval-plain-full | examples.parquet | 1 | `python trip/train.py --max-steps 1 --val-limit 3000 --test-limit 0 --generate 0 --eval-only --loss-mode plain --resume /data/runs/h100b-plain_ce/plain_ce/checkpoint.pt --splits test --eval-batch-size 32` |  |  |
| jonas-h100-both-fixed-caption-2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode both --series-scaling fixed --caption-share 0.3 --grad-checkpointing` |  |  |
| jonas-h100-both-plain-2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode both --grad-checkpointing` |  |  |
| jonas-h100-both-plaincrps | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode both --grad-checkpointing` | 2.752 / 2.195 | 3.617 / 2.898 |
| jonas-h100-both-tdrop50 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode both --text-dropout 0.5 --grad-checkpointing` | 2.767 / 2.219 | 3.647 / 2.925 |
| jonas-h100-enc-12k | examples.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode series` |  |  |
| jonas-h100-enc-caption | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode series --caption-share 0.3` |  |  |
| jonas-h100-enc-fixed-caption | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode series --series-scaling fixed --caption-share 0.3` |  |  |
| jonas-h100-enc-fixed | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode series --series-scaling fixed` |  |  |
| jonas-h100-enc-lr5x | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode series --lr-encoder 1e-3` |  |  |
| jonas-h100-enc-stage1 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode series --lr 0 --lr-encoder 5e-4` |  |  |
| jonas-h100-enc-stage2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode both --resume /data/runs/h100-enc-stage1/custom/checkpoint.pt` |  |  |
| jonas-h100-final-both | examples.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 0 --generate 48 --loss-mode plain --prompt-mode both --grad-checkpointing --eval-batch-size 32` | 2.709 / 2.175 | 3.397 / 2.699 |
| jonas-h100-final-text | examples.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 0 --generate 48 --loss-mode plain --prompt-mode text --grad-checkpointing --eval-batch-size 32` |  |  |
| jonas-h100-final-v2-text | examples_v2.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 0 --generate 48 --loss-mode plain_crps --prompt-mode text --eval-batch-size 32` | 2.665 / 2.139 | 3.322 / 2.644 |
| jonas-h100-final-v3-both | examples_v3.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 0 --generate 48 --loss-mode plain_crps --prompt-mode both --grad-checkpointing --eval-batch-size 32` | 2.676 / 2.136 | 3.319 / 2.643 |
| jonas-h100-final-v4-both | examples_v4.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 0 --generate 48 --loss-mode plain_crps --prompt-mode both --grad-checkpointing --eval-batch-size 32` |  |  |
| jonas-h100-final-v4-text | examples_v4.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 0 --generate 48 --loss-mode plain_crps --prompt-mode text --eval-batch-size 32` | 2.675 / 2.136 | 3.331 / 2.647 |
| jonas-h100-final-v7-split-6k | examples_v7.parquet | 6000 | `python trip/train.py --max-steps 6000 --val-limit 3000 --test-limit 30000 --generate 48 --loss-mode plain_crps --prompt-mode split --grad-checkpointing --eval-batch-size 32` |  |  |
| jonas-h100-final-v7-text-6k | examples_v7.parquet | 6000 | `python trip/train.py --max-steps 6000 --val-limit 3000 --test-limit 30000 --generate 48 --loss-mode plain_crps --prompt-mode text --eval-batch-size 32` | 2.572 / 2.066 | 3.224 / 2.560 |
| jonas-h100-final-v7-text | examples_v7.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 0 --generate 48 --loss-mode plain_crps --prompt-mode text --eval-batch-size 32` |  |  |
| jonas-h100-long-both | examples_720h.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode both --grad-checkpointing` |  |  |
| jonas-h100-long-series | examples_720h.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode series --grad-checkpointing` |  |  |
| jonas-h100-ms-both | examples_ms.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode both --grad-checkpointing` |  |  |
| jonas-h100-ms-text | examples_ms.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode text --grad-checkpointing` |  |  |
| jonas-h100-none-12k | examples.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode none` | 2.716 / 2.171 | 3.623 / 2.894 |
| jonas-h100-none-plaincrps | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode none --grad-checkpointing` | 2.801 / 2.244 | 3.677 / 2.957 |
| jonas-h100-series-plaincrps | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode series` | 2.779 / 2.236 | 3.693 / 2.956 |
| jonas-h100-series-z4 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode series --series-scaling z4` | 2.802 / 2.247 | 3.689 / 2.959 |
| jonas-h100-text-24k | examples.parquet | 24000 | `python trip/train.py --max-steps 24000 --val-limit 3000 --test-limit 0 --generate 48 --loss-mode plain --prompt-mode text --eval-batch-size 32` | 2.709 / 2.165 | 3.374 / 2.680 |
| jonas-h100-text-5k | examples.parquet | 5000 | `python trip/train.py --max-steps 5000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode text --grad-checkpointing` |  |  |
| jonas-h100-text-plain-repeat | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode text --grad-checkpointing` |  |  |
| jonas-h100-text-plain-2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode text --grad-checkpointing` |  |  |
| jonas-h100-text-plaincrps | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode text --grad-checkpointing` |  |  |
| jonas-h100-v2-both | examples_v2.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode both --grad-checkpointing` |  |  |
| jonas-h100-v2-text | examples_v2.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --prompt-mode text --grad-checkpointing` |  |  |
| jonas-h100-v3-both | examples_v3.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode both --grad-checkpointing` |  |  |
| jonas-h100-v4-both | examples_v4.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode both --grad-checkpointing` |  |  |
| jonas-h100-v4-series | examples_v4.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode series` | 2.765 / 2.203 | 3.583 / 2.880 |
| jonas-h100-v4-split-z4 | examples_v4.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode split --series-scaling z4 --grad-checkpointing` | 2.771 / 2.200 | 3.580 / 2.877 |
| jonas-h100-v4-split | examples_v4.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode split --grad-checkpointing` | 2.777 / 2.219 | 3.594 / 2.883 |
| jonas-h100-v4-text-5k | examples_v4.parquet | 5000 | `python trip/train.py --max-steps 5000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode text --grad-checkpointing` |  |  |
| jonas-h100-v4-text | examples_v4.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode text --grad-checkpointing` |  |  |
| jonas-h100-v5-both | examples_v5.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode both --grad-checkpointing` |  |  |
| jonas-h100-v6-causes | examples_v6.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode text --grad-checkpointing` | 2.757 / 2.191 | 3.583 / 2.863 |
| jonas-h100-v7-none | examples_v7.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode none` | 2.622 / 2.108 | 3.442 / 2.769 |
| jonas-h100-v7-series | examples_v7.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode series` | 2.624 / 2.102 | 3.451 / 2.773 |
| jonas-h100-v7-split | examples_v7.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode split --grad-checkpointing` | 2.605 / 2.102 | 3.450 / 2.771 |
| jonas-h100-v7-text | examples_v7.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode text --grad-checkpointing` | 2.592 / 2.095 | 3.449 / 2.761 |
| jonas-h100-v7-zeroshot | examples_v7.parquet | 1 | `python trip/train.py --max-steps 1 --val-limit 3000 --test-limit 5000 --generate 16 --eval-only --loss-mode plain_crps --prompt-mode text --eval-batch-size 32` | 2.731 / 2.489 | 3.552 / 3.108 |
| jonas-h100-main-12k | examples.parquet | 12000 | `python trip/train.py --max-steps 12000 --val-limit 3000 --test-limit 30000 --generate 48` |  |  |
| jonas-h100-main-2k | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16` |  |  |
| jonas-h100-plain-5k | examples.parquet | 5000 | `python trip/train.py --max-steps 5000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain` |  |  |
| jonas-h100-plain-lr2x | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain --lr 2e-4 --lr-encoder 4e-4` |  |  |
| jonas-h100-plain-ce-2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain` |  |  |
| jonas-h100-random-encoder-2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --start-checkpoint none` |  |  |
| jonas-h100-text-only-2 | examples.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --text-only --grad-checkpointing` |  |  |
| jonas-h100-v7-bare-none-2 | examples_v7.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode none --rationale bare` | 3.465 / 2.728 | 4.657 / 3.678 |
| jonas-h100-v7-bare-none | examples_v7.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode none --rationale bare` |  |  |
| jonas-h100-v7-bare-series-2 | examples_v7.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode series --rationale bare` | 2.813 / 2.255 | 3.731 / 2.989 |
| jonas-h100-v7-bare-series | examples_v7.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode series --rationale bare` |  |  |
| jonas-h100-v7-bare-text-2 | examples_v7.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode text --rationale bare --grad-checkpointing` | 2.629 / 2.121 | 3.483 / 2.793 |
| jonas-h100-v7-bare-text | examples_v7.parquet | 2000 | `python trip/train.py --max-steps 2000 --val-limit 3000 --test-limit 5000 --generate 16 --loss-mode plain_crps --prompt-mode text --rationale bare --grad-checkpointing` |  |  |
