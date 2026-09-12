# app/frontend — error404 PWA

Installable web app: share a DB connection (DB app → Share → error404), paste or
drop it, or build one; see the route on a 3D globe, the probability the plan
fails, advice (leave-home-by, missed-connection re-route), causes of delay and
the evidence. The same app is used for presenting (stage mode).

## Run

```bash
# backend serves the API and, after a build, the app itself on :8000
cd app/backend && npm run dev

# development with hot reload (proxies /api to :8000)
cd app/frontend && npm install && npm run dev      # http://127.0.0.1:5173

# production build, served by the backend at http://localhost:8000
cd app/frontend && npm run build
```

## Links worth knowing

| URL | What it does |
|---|---|
| `/` | Plan screen |
| `/?demo=1&tab=forecast` | load the seed journey and open a tab (`plan`, `forecast`, `advice`, `causes`, `evidence`) |
| `/share?text=…` | the Web Share Target; the DB app lands here |
| `/?stage=1` | stage mode: bigger type, progress dots; → / ← walk the flow, Esc exits |
| `?motion=0` | no animations (also honours prefers-reduced-motion) |
| `?tiles=vector` | OpenFreeMap vector basemap instead of the Esri raster default |

Keys anywhere: `S` stage mode, `F` fullscreen, `M` toggle motion.

## Phone / share sheet

The app appears in Android's share sheet only when installed from HTTPS in
Chrome. Quick tunnel:

```bash
cloudflared tunnel --url http://localhost:8000
```

Open the printed `https://….trycloudflare.com` URL on the phone, menu → Install
app, then in the DB app: connection → Share → error404. iOS has no share
target; paste works there.

## Offline

Bundled fixtures in `public/seed/` (journey, prediction, recommendation,
reroute, causes) keep every screen working when the backend is down; an
"offline · seed" pill says so. The service worker caches the app shell and every
map tile it has seen, so walk the flow once on venue Wi-Fi.

Feature folders live in `src/features/`, one per feature, matching
`app/backend/src/features/` names where a feature spans both layers.
