# Dataset variant search (v3)

Profile quarter, proxy = gradient boosting on per-channel summaries + annotations, selection on validation CRPS only, noise floor 0.02. Agent: gpt-4o-mini, 5 calls.

| round | channels kept | hypothesis (agent) | val CRPS | gain | verdict |
|---|---|---|---|---|---|
| 0 | 10 | incumbent: every channel | 1.388 |  | accepted |
| 1 | 4 | This variant focuses on the most relevant channels directly related to service delays and weather, which should provide a clearer signal for | 1.3918 | -0.0038 | rejected |
| 2 | 4 | By retaining channels that directly influence delays and throughput while removing less relevant ones, this variant should enhance the model | 1.5256 | -0.1376 | rejected |
| 3 | 4 | This variant retains key channels that are closely tied to service delays and technical factors, which may provide a more focused and effect | 1.403 | -0.015 | rejected |
| 4 | 4 | This variant combines critical delay-related channels with knock-on effects, which may capture the cascading impacts of delays more effectiv | 1.4047 | -0.0167 | rejected |
| 5 | 5 | This variant includes essential delay-related channels while also incorporating throughput and weather factors, which are crucial for unders | 1.3874 | 0.0006 | rejected |

Winner keeps 10 of 10 channels; dropped: []

| cell | n | median error | CRPS | coverage 10-90 |
|---|---:|---|---|---|
| val | 427 | 1.783 | 1.388 | 0.68 |
| test_seen_entity | 1134 | 1.677 | 1.312 | 0.68 |
| test | 462 | 1.787 | 1.365 | 0.65 |
| test_seen_time | 3015 | 1.532 | 1.185 | 0.72 |
