// Thin REST client for Nebius Serverless AI jobs (ai/v1) plus the two IAM/VPC
// lookups needed for setup. Endpoints verified against https://api.nebius.cloud/openapi.json.
export const API_BASE_URL = 'https://api.nebius.cloud';

export const JOB_STATES = ['STATE_UNSPECIFIED', 'PROVISIONING', 'STARTING', 'IMAGE_PULLING', 'RUNNING', 'CANCELLING', 'DELETING', 'COMPLETED', 'FAILED', 'CANCELLED', 'ERROR'];
export const TERMINAL_STATES = new Set(['COMPLETED', 'FAILED', 'CANCELLED', 'ERROR']);
export const isTerminal = (state) => TERMINAL_STATES.has(state);

export class NebiusApiError extends Error {
  constructor(status, message, body, { method, path } = {}) {
    super(`Nebius API ${method} ${path} -> ${status}: ${message}`);
    this.status = status; this.body = body; this.method = method; this.path = path;
  }
}

export class NebiusJobsClient {
  /**
   * @param {object} opts
   * @param {string} opts.projectId   NEBIUS_PROJECT_ID (metadata.parentId for every job)
   * @param {() => Promise<string>} opts.getToken  bearer token provider (see auth.js)
   */
  constructor({ projectId, getToken, baseUrl = API_BASE_URL, fetchImpl = fetch } = {}) {
    if (!projectId) throw new Error('NebiusJobsClient: projectId is required (NEBIUS_PROJECT_ID)');
    if (typeof getToken !== 'function') throw new Error('NebiusJobsClient: getToken() is required');
    this.projectId = projectId; this.getToken = getToken; this.baseUrl = baseUrl.replace(/\/$/, ''); this.fetch = fetchImpl;
  }

  async request(method, path, { query, body } = {}) {
    const url = new URL(this.baseUrl + path);
    for (const [k, v] of Object.entries(query || {})) if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
    const headers = { Authorization: `Bearer ${await this.getToken()}`, Accept: 'application/json' };
    let payload;
    if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
    const res = await this.fetch(url, { method, headers, body: payload });
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
    if (!res.ok) {
      const msg = data?.message || data?.error || data?.raw || res.statusText;
      throw new NebiusApiError(res.status, msg, data, { method, path });
    }
    return data;
  }

  // ---- jobs -------------------------------------------------------------
  /** POST /ai/v1/jobs -> Operation. Returns { jobId, operation }. */
  async createJob(createRequest) {
    const op = await this.request('POST', '/ai/v1/jobs', { body: createRequest });
    return { jobId: op.resourceId, operationId: op.id, operation: op };
  }
  getJob(id, { view } = {}) { return this.request('GET', `/ai/v1/jobs/${encodeURIComponent(id)}`, { query: { view } }); }
  getJobByName(name) { return this.request('GET', '/ai/v1/jobs/get-by-name', { query: { parentId: this.projectId, name } }); }
  listJobs({ pageSize = 50, pageToken } = {}) { return this.request('GET', '/ai/v1/jobs', { query: { parentId: this.projectId, pageSize, pageToken } }); }
  cancelJob(id) { return this.request('POST', '/ai/v1/jobs/cancel', { body: { id } }); }
  restartJob(id) { return this.request('POST', '/ai/v1/jobs/restart', { body: { id } }); }
  deleteJob(id) { return this.request('DELETE', `/ai/v1/jobs/${encodeURIComponent(id)}`); }

  /** Poll until the job reaches a terminal state. Resolves with the final Job. */
  async waitForJob(id, { intervalMs = 15_000, timeoutMs = 0, onUpdate, signal, sleep = defaultSleep } = {}) {
    const started = Date.now();
    let lastState;
    for (;;) {
      const job = await this.getJob(id);
      const state = job?.status?.state;
      if (state !== lastState) { lastState = state; onUpdate?.(job); }
      if (isTerminal(state)) return job;
      if (timeoutMs && Date.now() - started > timeoutMs) throw new Error(`waitForJob: ${id} still ${state} after ${timeoutMs}ms`);
      if (signal?.aborted) throw new Error('waitForJob: aborted');
      await sleep(intervalMs);
    }
  }

  // ---- setup helpers ----------------------------------------------------
  whoami() { return this.request('GET', '/iam/v1/profiles'); }
  listSubnets() { return this.request('GET', '/vpc/v1/subnets', { query: { parentId: this.projectId } }); }
}

const defaultSleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Compact, UI-friendly view of a Job resource. */
export function summarizeJob(job) {
  if (!job) return null;
  const { metadata = {}, spec = {}, status = {} } = job;
  return {
    id: metadata.id, name: metadata.name, createdAt: metadata.createdAt,
    state: status.state, stateDetails: status.stateDetails, startedAt: status.startedAt, finishedAt: status.finishedAt,
    image: spec.image, platform: spec.platform, preset: spec.preset, timeout: spec.timeout, preemptible: !!spec.preemptible,
    publicEndpoints: status.publicEndpoints, privateEndpoints: status.privateEndpoints,
  };
}
