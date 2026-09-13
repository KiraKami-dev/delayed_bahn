# Agentic retrieval, run of record (v2)

Generated 2026-09-13 08:16 UTC. Agent: gpt-4o-mini, 12 calls in total (search, assessment, schema maps, retrieval plans, reductions). Budget: {"max_months": 1, "max_rows_per_month": 400000, "max_weather_days": 7, "max_weather_stations": 3}.

## Stage 4: what the agent chose to fetch, and what code did with it

| source | plan (agent) | verifier | fetched |
|---|---|---|---|
| `known:piebro/deutsche-bahn-data` | {"months": ["2025-11"], "columns": ["station_name", "eva", "train_number", "line_number", "final_destination_station", "delay_in_min", "time", "arrival_is_canceled", "departure_is_canceled", "train_type", "train_line_rid — The dataset for November 2025 has a high row count (over 13 million), allowing us to fetch the maximum allowed rows (400,000) while ensuring we cover the necess | accepted first plan | 400000 rows x 17 cols, 17.2 MB, 3.0s |
| `known:openholidays` | {"subdivisions": ["DE-BY"], "kinds": ["public", "school"]} — The source provides holiday data relevant to the federal state of Bavaria (DE-BY) and includes both public and school holidays. This is sufficient for the annot | accepted first plan | 20 rows x 7 cols, 0.0 MB, 0.3s |
| `known:db-stations` | {"fields": ["id", "category", "federalState"]} — The source only provides station-related information, which includes the station ID, category, and federal state. Since the dataset does not contain specific fi | accepted after re-prompt: unknown field train_type; unknown field final_destination; unknown field station_name; unknown field station_id; unknown | 5388 rows x 3 cols, 0.0 MB, 0.3s |
| `known:bright-sky` | {"variables": ["temperature", "precipitation", "wind_speed", "wind_gust_speed", "visibility", "condition", "cloud_cover", "relative_humidity", "pressure_msl", "dew_point", "sunshine"], "stations": [{"name": "München Hbf" — The fetch is limited to 7 days to comply with the maximum weather days budget. Only three stations are selected to stay within the maximum rows per month limit  | accepted after re-prompt: unknown variable mean_departure_delay_service; unknown variable mean_departure_delay_station; unknown variable cancellat | 435 rows x 13 cols, 0.0 MB, 1.0s |

## Stage 5: how the agent diluted each table, and the measured effect

### `known:piebro/deutsche-bahn-data`

400,000 -> 386,698 rows, 17 -> 10 columns, 17.2 -> 6.5 MB. Roles: {"timestamp": "time", "station": "station_name", "train": "train_type", "target": "delay_in_min", "cancelled": ["arrival_is_canceled", "departure_is_canceled"]}

Agent's reasoning: The selected columns provide the necessary information for training the route-planning TSLM, while the dropped columns either carry no relevant information or are not needed for the model's inputs or outputs. The row filter ensures that only relevant train data is included.

Code normalised the proposal without changing its substance: role cancelled: 'arrival_is_canceled or departure_is_canceled' read as the columns ['arrival_is_canceled', 'departure_is_canceled']; filter: leading WHERE removed from 'WHERE train_type != 'Bus''; named in both keep and drop, dropped (the drop carries the reason): ['train_line_station_num']

| dropped column | agent's reason |
|---|---|
| `eva` | Identifier with no reuse, not needed for the model. |
| `arrival_planned_time` | Not needed as planned vs changed timestamps are not inputs. |
| `arrival_change_time` | Not needed as planned vs changed timestamps are not inputs. |
| `departure_planned_time` | Not needed as planned vs changed timestamps are not inputs. |
| `departure_change_time` | Not needed as planned vs changed timestamps are not inputs. |
| `train_line_station_num` | Not relevant for the model's inputs or target. |
| `id` | Identifier with no reuse, not needed for the model. |

| row filter | agent's reason | rows it removes alone |
|---|---|---:|
| `train_type != 'Bus'` | Buses are out of scope for the train-delay forecasting model. | 13,302 |

### `known:openholidays`

20 -> 20 rows, 7 -> 4 columns, 0.0 -> 0.0 MB. Roles: {"date_start": "start", "date_end": "end", "region": "subdivision", "kind": "kind"}

Agent's reasoning: The columns 'start', 'end', 'subdivision', and 'kind' are necessary for the model's requirements. The 'name' column is dropped because it contains free text that does not contribute to the model's inputs. The 'nationwide' column is dropped as it is a boolean that does not provide relevant information for the model's needs. The 'type' column is redundant as it duplicates the information in 'kind'.

| dropped column | agent's reason |
|---|---|
| `name` | Contains free text that is not needed for the model. |
| `nationwide` | Boolean column that does not provide relevant information for the model. |
| `type` | Duplicate information as 'kind'. |

Verifier objected to the first proposal: role date_start mapped to unknown column start of the holiday; role date_end mapped to unknown column end of the holiday; role region mapped to unknown column subdivision code; role kind mapped to unknown column public; role kind mapped to unknown column school

### `known:db-stations`

5,388 -> 5,388 rows, 3 -> 2 columns, 0.0 -> 0.0 MB. Roles: {"station_id": "id", "region": "federalState"}

Agent's reasoning: The 'id' column is essential as it serves as the station identifier, while 'federalState' is necessary for regional context. The 'category' column is dropped as it does not contribute meaningful information for the route-planning model, given its limited distinct values and lack of relevance to the required inputs or target.

| dropped column | agent's reason |
|---|---|
| `category` | This column has limited distinct values and does not provide necessary information for the model's inputs or target. |

### `known:bright-sky`

435 -> 435 rows, 13 -> 3 columns, 0.0 -> 0.0 MB. Roles: {"timestamp": "timestamp", "station": "station"}

Agent's reasoning: The columns 'timestamp' and 'station' are retained as they are required roles. Other weather variables are kept for context but may not be essential for the model's predictive capability. The drop reasons focus on the lack of distinctiveness or relevance of certain weather variables.

Code normalised the proposal without changing its substance: named in both keep and drop, dropped (the drop carries the reason): ['temperature', 'precipitation', 'wind_speed', 'wind_gust_speed', 'visibility', 'cloud_cover', 'relative_humidity', 'pressure_msl', 'dew_point', 'sunshine']

| dropped column | agent's reason |
|---|---|
| `temperature` | While it is a weather variable, it may not be essential for the model's predictive capability compared to other variables. |
| `precipitation` | This variable may not provide significant variation as it has a low number of distinct values. |
| `wind_speed` | This variable may not provide significant variation as it has a low number of distinct values. |
| `wind_gust_speed` | This variable may not provide significant variation as it has a low number of distinct values. |
| `visibility` | This variable may not provide significant variation as it has a low number of distinct values. |
| `cloud_cover` | This variable may not provide significant variation as it has a low number of distinct values. |
| `relative_humidity` | This variable may not provide significant variation as it has a low number of distinct values. |
| `pressure_msl` | This variable may not provide significant variation as it has a low number of distinct values. |
| `dew_point` | This variable may not provide significant variation as it has a low number of distinct values. |
| `sunshine` | This variable may not provide significant variation as it has a low number of distinct values. |

Verifier objected to the first proposal: role timestamp mapped to unknown column hour; role station mapped to unknown column station key


## Where the agent disagrees with the hand-built pipeline (for a human to rule on)

- It dropped `train_line_station_num` from the events table; the db_route pipeline uses it as the stop sequence for run reconstruction.
- It dropped `category` from the station hub; the pipeline emits it as the `station_category` annotation.
- It reduced the weather table to `condition` only, calling temperature and precipitation "not required". For rail delays that is the wrong call and is recorded here as such.

None of these were overruled by code: the verifier guards the required roles, not judgment. Every decision and its reason is in `reduction.json`; the reduced tables are in `reduced/`.
