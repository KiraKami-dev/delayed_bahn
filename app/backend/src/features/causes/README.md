# Feature: causes

`GET /api/causes?eva=8000261` (or `?station=München Hbf`) -> cause-family shares
(works, weather, technical, knock_on, staff, external, unattributed), the top IRIS
cause codes with their German display text, a 7-day mean-delay sparkline and the
data source. Families follow `app/agents/src/features/db_route/causes.py`.
Fixture-backed (`fixtures/causes.json`, `illustrative: true`) until the db_route
pipeline output replaces the numbers. Serves the "causes of delays" visual.
