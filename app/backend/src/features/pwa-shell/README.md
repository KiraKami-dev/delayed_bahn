# Feature: pwa-shell

Serves the built PWA (`app/frontend/dist`, or `STATIC_DIR`) from the same
origin as `/api` -- the manifest, service worker and web share target need
that -- and `GET /api/seed/demo`, the storyline journey every screen falls
back to when the network is down (contract: `GET /api/seed/demo`).

- `static.js` -- file serving with an SPA fallback so `/share?text=...` loads the app shell.
- `fixtures/seed-journey.json` -- RB 16 Nürnberg Hbf -> München Hbf, S 8 -> München Flughafen Terminal.
  Stations carry optional `lat`/`lon` (additive to the contract's `Station`).
- `routes/` -- this feature's routes.
