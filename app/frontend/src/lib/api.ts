import type { Causes, Journey, Prediction, Recommendation, Reroute } from "./contract"

// Serverless cold starts and slow mobile links need patience: 20 s per try,
// one retry on network failure, timeout or 5xx. 4xx is returned immediately.
const TIMEOUT_MS = 20000
const RETRIES = 1

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function once<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
    signal: AbortSignal.timeout(TIMEOUT_MS),
    cache: "no-store",
  })
  const type = res.headers.get("content-type") || ""
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`.trim()
    if (type.includes("json")) {
      try {
        const body = await res.json()
        if (body?.error) msg = body.error
      } catch {
        /* keep status text */
      }
    }
    throw new ApiError(res.status, msg)
  }
  if (!type.includes("json")) {
    // An expired deployment or a captive portal answers with an HTML page.
    throw new ApiError(0, `The service answered with ${type || "no content type"} instead of data (is this deployment still live?)`)
  }
  return (await res.json()) as T
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let last: unknown
  for (let attempt = 0; attempt <= RETRIES; attempt++) {
    try {
      return await once<T>(path, init)
    } catch (e) {
      last = e
      const status = (e as ApiError).status
      const retryable = status == null || status === 0 || status >= 500 || status === 429
      if (!retryable || attempt === RETRIES) break
      await new Promise((r) => setTimeout(r, 800))
    }
  }
  if (last instanceof ApiError) throw last
  const err = last as Error
  const reason = err?.name === "TimeoutError" ? "the request timed out" : err?.message || "network error"
  throw new ApiError(0, reason)
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
