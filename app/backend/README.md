# app/backend

How to run just this folder standalone, once a stack is chosen:

```bash
cd app/backend
npm install && npm run dev     # or: pip install -e . / mvn spring-boot:run,
                                # whichever this event's stack picks
```

Feature folders live in `src/features/`, one per feature, matching
`app/frontend/src/features/` names 1:1 where a feature spans both. Copy
`src/features/_TEMPLATE/` to start a new one.

Owner: see `../../team-setup/state/owners.md` (decided fresh per event,
not fixed here).
