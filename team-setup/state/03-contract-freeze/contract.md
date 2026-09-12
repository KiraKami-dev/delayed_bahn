<!-- Shared types + API surface. FROZEN at this gate. -->

# Contract — DRAFT, NOT FROZEN

Derived from the demo-script build list. The contract-freeze lead freezes
it once the demo script is frozen (route picked). Until then teammates can
code against it but must expect field names to move.

## Shared types

```ts
type Station = { evaNumber: string; name: string };

type Leg = {
  trainId: string;            // e.g. "ICE 75"
  from: Station;
  to: Station;
  plannedDeparture: string;   // ISO 8601, local time with offset
  plannedArrival: string;
  transferMinutes?: number;   // planned transfer to the next leg
};

type Journey = { id: string; legs: Leg[]; source: "db-share" | "manual" | "seed" };

type Explained<T> = {
  value: T;
  reasoning: string;          // one paragraph, human-readable
  sources: string[];          // data windows, feeds, model id
  confidence: "low" | "medium" | "high";   // advisory, not calibrated
};

type LegDelay = {
  trainId: string;
  expectedDelayMinutes: Explained<number>;
  missProbability: Explained<number>;      // 0..1, chance this transfer breaks
};

type Prediction = {
  journeyId: string;
  legs: LegDelay[];
  planFailProbability: Explained<number>;  // 0..1, chained across legs
  modelId: string;                          // fine-tuned model version
};

type Recommendation = {
  verdict: "good" | "add-buffer" | "take-alternative";
  advice: Explained<string>;               // "take an umbrella" language
  bufferMinutes?: number;
  alternative?: Journey;                   // comfortable connection, if any
};
```

## API surface (backend, Node, `/api`)

| Method | Path | Body → Response | Feature |
|---|---|---|---|
| GET | `/api/health` | → `{ ok: true }` | backend |
| POST | `/api/journeys/parse` | `{ text: string }` → `Journey` (400 if no connection found) | share-parser |
| POST | `/api/predict` | `Journey` → `Prediction` | delay-prediction |
| POST | `/api/recommend` | `{ journey: Journey; prediction: Prediction }` → `Recommendation` | recommendation |
| GET | `/api/seed/demo` | → `Journey` for the storyline route (offline fallback) | pwa-shell |

## Mocks until real

- `/api/predict` returns fixed per-leg delays for the seed journey until the fine-tuned model is served.
- `/api/recommend` returns a canned "take-alternative" for the seed journey until the algorithm exists.

Freezing this contract requires stopping the team and getting sign-off.
