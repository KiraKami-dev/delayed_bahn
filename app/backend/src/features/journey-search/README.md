# Feature: journey-search

`GET /api/journeys/search?from=<EVA>&to=<EVA>&departure=<ISO>&results=5` returns
`{ journeys: Journey[], source: 'db-timetables', direct: true }` — direct trains
between two stations from the official DB Timetables API. Optional `fromName`
and `toName` help when a station is missing from the local table.

- Needs `DB_CLIENT_ID` and `DB_API_KEY` (DB API Marketplace, "Timetables" API)
  in `app/backend/.env`; without them the route answers 503 and the PWA falls
  back to transport.rest.
- `plan/{eva}/{yymmdd}/{hh}` is scanned for up to 3 hours from `departure`;
  a train qualifies when the destination is on its planned onward path, and its
  arrival time is read from the destination's plan (up to 8 hours ahead, at most
  14 requests per search). Times are Berlin local in the feed and returned as
  ISO 8601 with offset.
- Only direct trains: journeys with changes come from transport.rest in the PWA.
- `routes/journey-search.js` — service + route; `journey-search.test.js` — parser,
  time conversion and search with a stubbed fetch.
