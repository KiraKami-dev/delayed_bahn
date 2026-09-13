# Traveler frontend verification

- Ownership for the traveler frontend, frontend manifest/lockfile and smoke checks was explicitly delegated to this session by the user. Do not infer ownership of backend or generated shared types.
- Build and typecheck: `npm --prefix app/frontend run build`.
- Run the frontend on a separate port when the coordination dashboard already uses 5173: `npm --prefix app/frontend run dev -- --port 5174`. The existing Vite proxy targets the product backend at 8000, configurable with `API_PORT`.
- Browser smoke checks: with the frontend running, `PLAYWRIGHT_CHANNEL=chrome npm --prefix app/frontend run test:smoke` uses an installed Google Chrome. Alternatively install the Playwright Chromium browser and omit `PLAYWRIGHT_CHANNEL`. `FRONTEND_URL` overrides the default `http://127.0.0.1:5174`.
- Browser smoke checks intercept API requests with isolated fixtures. They cover error recovery, explicit demo data, stale requests, keyboard station selection, German daylight-saving time, responsive layouts, map controls and WebGL fallback. The time-conversion check imports a Vite source module, so this suite targets the dev server.
- Only an explicitly chosen example journey may use bundled prediction/recommendation fixtures. A real traveler's failed request must never be replaced with an unrelated example. Keep mock/prior results and unverified alternative timing scenarios visibly labelled.
- The optional 3D map is lazy-loaded and must never prevent using trip forms or reading results. The local SVG landscape requires no generation service, API keys or network request to an image provider.
- MapLibre 6 requires its worker to be bundled explicitly with Vite's `?worker&url` import and passed to `setWorkerUrl`; the default relative worker path fails from Vite's optimized dependency directory.
- For production offline verification, finish the build first, load the app from the backend, and wait for an activated service-worker controller before disabling the browser context's network and reloading. Do not rebuild while the browser is installing that service worker.
