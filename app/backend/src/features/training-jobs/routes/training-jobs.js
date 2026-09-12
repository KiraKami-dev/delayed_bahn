// HTTP surface for submitting and tracking Nebius training jobs.
// Mounted by src/server.js. All handlers return JSON.
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createTokenProvider, describeAuth, findNebiusCli } from '../nebius/auth.js';
import { NebiusJobsClient, summarizeJob, NebiusApiError } from '../nebius/client.js';
import { buildJobRequest, buildTrainingJobRequest, PLATFORMS, DEFAULTS, estimateCost, parseDurationSeconds } from '../nebius/spec.js';

const execFileP = promisify(execFile);

export function createTrainingService({ env = process.env, client, fetchImpl = fetch } = {}) {
  let _client = client;
  const getClient = () => {
    if (_client) return _client;
    if (!env.NEBIUS_PROJECT_ID) { const e = new Error('NEBIUS_PROJECT_ID is not set; create app/backend/.env with NEBIUS_PROJECT_ID=... (see the training-jobs README)'); e.status = 503; throw e; }
    _client = new NebiusJobsClient({ projectId: env.NEBIUS_PROJECT_ID, getToken: createTokenProvider(env, { fetchImpl }), fetchImpl });
    return _client;
  };

  return {
    catalog() {
      return {
        defaults: { platform: env.NEBIUS_DEFAULT_PLATFORM || DEFAULTS.platform, preset: env.NEBIUS_DEFAULT_PRESET || DEFAULTS.preset, image: env.NEBIUS_DEFAULT_IMAGE || DEFAULTS.image, timeout: env.NEBIUS_DEFAULT_TIMEOUT || DEFAULTS.timeout },
        platforms: Object.entries(PLATFORMS).map(([id, p]) => ({ id, ...p })),
        note: 'Prices are public on-demand $/GPU-hour as of 2026-09; verify with `nebius compute platform list`.',
      };
    },
    estimate({ platform, preset, timeout, preemptible }) {
      return estimateCost({ platform: platform || DEFAULTS.platform, preset: preset || DEFAULTS.preset, timeoutSeconds: parseDurationSeconds(timeout || DEFAULTS.timeout), preemptible: !!preemptible });
    },
    async whoami() {
      const c = getClient();
      const [profile, subnets] = await Promise.all([c.whoami(), c.listSubnets().catch((e) => ({ error: e.message }))]);
      return { auth: describeAuth(env), projectId: c.projectId, subnetId: env.NEBIUS_SUBNET_ID || null, profile, subnets: subnets.items?.map((s) => ({ id: s.metadata?.id, name: s.metadata?.name, networkId: s.spec?.networkId })) ?? subnets, cli: findNebiusCli(env) };
    },
    /** body: either a raw job ({name,image,command,args,...}) or a training job ({name, script|scriptPath, requirements, scriptArgs, ...}) */
    build(body) {
      const isTraining = body.script || body.scriptPath;
      return isTraining ? buildTrainingJobRequest(body, env) : buildJobRequest(body, env);
    },
    async submit(body) {
      const { request, estimate } = this.build(body);
      const { jobId, operationId } = await getClient().createJob(request);
      return { jobId, operationId, name: request.metadata.name, estimate, request: redact(request) };
    },
    async dryRun(body) {
      const { request, estimate } = this.build({ ...body, dryRun: true });
      const op = await getClient().createJob(request);
      return { valid: true, estimate, operation: op.operation, request: redact(request) };
    },
    async list(query = {}) {
      const res = await getClient().listJobs({ pageSize: query.pageSize, pageToken: query.pageToken });
      return { jobs: (res.items || []).map(summarizeJob), nextPageToken: res.nextPageToken || null };
    },
    async get(id, { raw } = {}) {
      const job = await getClient().getJob(id);
      return raw ? job : summarizeJob(job);
    },
    async wait(id, opts) { return summarizeJob(await getClient().waitForJob(id, opts)); },
    cancel(id) { return getClient().cancelJob(id); },
    remove(id) { return getClient().deleteJob(id); },
    /** Logs are CLI/console only per Nebius docs; shell out to the CLI if present. */
    async logs(id, { tail = 200, follow = false, since } = {}) {
      const bin = findNebiusCli(env);
      if (!bin) { const e = new Error('Job logs need the Nebius CLI (not found). Install it or view logs in the console: Serverless AI -> Jobs.'); e.status = 501; throw e; }
      const args = ['ai', 'job', 'logs', id, '--tail', String(tail), '--timestamps'];
      if (since) args.push('--since', since);
      if (follow) args.push('--follow');
      const { stdout, stderr } = await execFileP(bin, args, { env, maxBuffer: 16 * 1024 * 1024, timeout: follow ? 0 : 60_000 });
      return { id, logs: stdout, stderr: stderr || undefined };
    },
  };
}

function redact(request) {
  // Don't echo secrets or whole scripts back to API callers.
  const spec = { ...request.spec };
  if (spec.injectedFiles) spec.injectedFiles = spec.injectedFiles.map((f) => ({ containerPath: f.containerPath, bytes: Buffer.byteLength(f.content, 'utf8') }));
  if (spec.registryCredentials) spec.registryCredentials = { username: spec.registryCredentials.username, password: '***' };
  return { ...request, spec };
}

export function registerRoutes(router, ctx = {}) {
  const svc = ctx.service || createTrainingService(ctx);
  const wrap = (fn) => async (req) => { try { return await fn(req); } catch (e) { if (e instanceof NebiusApiError) e.status = e.status === 401 || e.status === 403 ? e.status : e.status >= 400 && e.status < 500 ? 400 : 502; throw e; } };

  router.get('/api/training/catalog', wrap(() => svc.catalog()));
  router.get('/api/training/estimate', wrap(({ query }) => svc.estimate(Object.fromEntries(query))));
  router.get('/api/training/whoami', wrap(() => svc.whoami()));
  router.get('/api/training/jobs', wrap(({ query }) => svc.list(Object.fromEntries(query))));
  router.post('/api/training/jobs', wrap(({ body }) => svc.submit(body)));
  router.post('/api/training/jobs/dry-run', wrap(({ body }) => svc.dryRun(body)));
  router.get('/api/training/jobs/:id', wrap(({ params, query }) => svc.get(params.id, { raw: query.get('raw') === '1' })));
  router.get('/api/training/jobs/:id/logs', wrap(({ params, query }) => svc.logs(params.id, { tail: Number(query.get('tail') || 200), since: query.get('since') || undefined })));
  router.post('/api/training/jobs/:id/cancel', wrap(({ params }) => svc.cancel(params.id)));
  router.delete('/api/training/jobs/:id', wrap(({ params }) => svc.remove(params.id)));
  return svc;
}
