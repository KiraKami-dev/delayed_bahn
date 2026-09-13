# Every run in minutes

Generated with `trip/plain_metrics.py` (summary figures of the predicted median) on the seeded
5,000 test examples every run scored. Run names are the tags in `RUNS.md`; `v7-*` runs use the
same-train and corridor series, `v4-*` the stacked XGBoost forecast, `none-*` no series at all.

All runs on the same 4,729 test trains (the seeded 5,000 that every run scored, cancelled removed), sorted by average miss

| Run | Average miss (min) | Within 1 min | Within 2 min | Within 5 min | Bias (min) | In 10-90% range |
|---|---|---|---|---|---|---|
| v7-text | 3.45 | 65% | 75% | 86% | -1.86 | 89% |
| v7-split | 3.45 | 65% | 75% | 86% | -1.89 | 88% |
| XGBoost, plus new series | 3.51 | 58% | 72% | 85% | -2.00 | 82% |
| v7-zeroshot (no fine-tuning) | 3.55 | 64% | 73% | 86% | -1.58 | 91% |
| final-v4-text | 3.54 | 64% | 73% | 86% | -1.88 | 89% |
| final-v2-text | 3.56 | 64% | 74% | 86% | -2.12 | 89% |
| text-24k | 3.56 | 63% | 73% | 86% | -1.75 | 90% |
| final-both | 3.56 | 64% | 74% | 86% | -1.82 | 90% |
| v4-text | 3.57 | 64% | 74% | 86% | -1.95 | 89% |
| v4-split-z4 | 3.58 | 64% | 74% | 86% | -1.96 | 88% |
| v4-series | 3.58 | 64% | 74% | 86% | -1.96 | 88% |
| v4-text-5k | 3.59 | 63% | 73% | 85% | -1.45 | 89% |
| v4-split | 3.59 | 64% | 74% | 86% | -1.99 | 89% |
| enc-12k | 3.60 | 64% | 74% | 86% | -2.06 | 89% |
| v2_both | 3.60 | 63% | 73% | 86% | -2.11 | 89% |
| v3-both | 3.61 | 64% | 74% | 86% | -2.11 | 89% |
| enc-stage2 | 3.61 | 64% | 74% | 86% | -2.11 | 89% |
| text-5k | 3.61 | 63% | 73% | 86% | -1.64 | 90% |
| v2_text | 3.62 | 64% | 74% | 86% | -2.20 | 89% |
| both-plaincrps | 3.62 | 64% | 74% | 86% | -2.13 | 88% |
| text-plaincrps | 3.62 | 63% | 74% | 86% | -2.11 | 89% |
| none-12k | 3.62 | 64% | 74% | 86% | -2.12 | 89% |
| main_12k | 3.63 | 64% | 75% | 87% | -2.00 | 92% |
| text_plain | 3.64 | 63% | 74% | 86% | -2.14 | 89% |
| both_plain | 3.64 | 64% | 74% | 86% | -2.22 | 89% |
| both-tdrop50 | 3.65 | 63% | 73% | 86% | -2.18 | 89% |
| XGBoost, combined features | 3.65 | 56% | 70% | 85% | -2.07 | 82% |
| none-plaincrps | 3.68 | 63% | 73% | 86% | -2.08 | 89% |
| enc-lr5x | 3.69 | 63% | 73% | 85% | -2.09 | 89% |
| series-z4 | 3.69 | 63% | 73% | 85% | -2.13 | 89% |
| series-plaincrps | 3.69 | 63% | 73% | 86% | -2.10 | 89% |
| XGBoost | 3.70 | 55% | 69% | 85% | -2.00 | 82% |
| plain_full | 3.70 | 62% | 73% | 85% | -2.18 | 90% |
| enc-stage1 | 3.72 | 62% | 73% | 85% | -2.18 | 87% |
| Persistence | 3.99 | 61% | 71% | 85% | -2.49 | 83% |
