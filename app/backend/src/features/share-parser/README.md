# Feature: share-parser

`POST /api/journeys/parse` `{ text }` -> `Journey` (contract). Turns the text the
DB Navigator app hands to the share sheet into legs with stations, ISO times
(Europe/Berlin offset) and transfer minutes. Serves demo shot 0:20 "journey
extracted".

- `grammar.js` -- line tokenizer + state machine (real sample in the header comment).
- `stations.js` + `fixtures/stations.json` -- name -> EVA/lat/lon; DB Timetables `station/` lookup when `DB_CLIENT_ID`/`DB_API_KEY` exist. Stations missing from the table get lat/lon by EVA from RIS::Stations (needs the DB app subscribed to it), else from OpenStreetMap (`uic_ref`), so the map can draw every leg.
- `vbid.js` -- best-effort bahn.de link resolver behind `BAHN_VBID_RESOLVER=1` (else 422).
- `fixtures/share-texts/` -- real sample, German variant, two legs, two connections, URL-only.
- 400 when no complete connection is found; extra fields on legs: `trainNumber`, `fromPlatform`, `toPlatform`.
