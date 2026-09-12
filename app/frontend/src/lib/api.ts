import type { Causes, Journey, Prediction, Recommendation, Reroute } from "./contract"

const TIMEOUT_MS = 8000

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
    signal: AbortSignal.timeout(TIMEOUT_MS),
  })
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.error) msg = body.error
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, msg)
  }
  return (await res.json()) as T
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const post = (body: unknown) => ({ method: "POST", body: JSON.stringify(body) })

export const api = {
  health: () => request<{ ok: boolean }>("/api/health"),
  seedDemo: () => request<Journey>("/api/seed/demo"),
  parseJourney: (text: string) => request<Journey>("/api/journeys/parse", post({ text })),
  predict: (journey: Journey) => request<Prediction>("/api/predict", post(journey)),
  recommend: (journey: Journey, prediction: Prediction, doorToStationMin?: number, acceptableRisk?: number) =>
    request<Recommendation>("/api/recommend", post({ journey, prediction, doorToStationMin, acceptableRisk })),
  reroute: (journey: Journey, missedLegIndex: number) =>
    request<Reroute>("/api/reroute", post({ journey, missedLegIndex })),
  causes: (evaNumber: string, name?: string) =>
    request<Causes>(`/api/causes?eva=${encodeURIComponent(evaNumber)}${name ? `&station=${encodeURIComponent(name)}` : ""}`),
}

export async function loadFixture<T>(name: string): Promise<T> {
  const res = await fetch(`/seed/${name}.json`, { signal: AbortSignal.timeout(TIMEOUT_MS) })
  if (!res.ok) throw new Error(`fixture ${name} missing`)
  return (await res.json()) as T
}
