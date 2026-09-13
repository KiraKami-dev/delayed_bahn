// Offline smoke tests: spec building, JWT signing, client request shape,
// polling, and HTTP routing. No network, no Nebius account needed.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { generateKeyPairSync, createVerify } from 'node:crypto';
import { buildJobRequest, buildTrainingJobRequest, estimateCost, parseDurationSeconds, SpecError, shellQuote } from './nebius/spec.js';
import { makeServiceAccountJwt, exchangeJwtForToken, createTokenProvider } from './nebius/auth.js';
import { NebiusJobsClient, summarizeJob, isTerminal } from './nebius/client.js';
import { createTrainingService, registerRoutes } from './routes/training-jobs.js';
import { Router } from '../../server.js';

const ENV = { NEBIUS_PROJECT_ID: 'project-e00test', NEBIUS_SUBNET_ID: 'vpcsubnet-e00test' };

test('parseDurationSeconds accepts h/m/s/d and numbers', () => {
  assert.equal(parseDurationSeconds('2h'), 7200);
  assert.equal(parseDurationSeconds('90m'), 5400);
  assert.equal(parseDurationSeconds('3600s'), 3600);
  assert.equal(parseDurationSeconds(3600), 3600);
  assert.equal(parseDurationSeconds('1d'), 86400);
  assert.throws(() => parseDurationSeconds('soon'), SpecError);
});

test('buildJobRequest matches the Nebius quick-start shape', () => {
  const { request, estimate } = buildJobRequest({ name: 'my-job', image: 'nvidia/cuda:13.1.1-runtime-ubuntu24.04', command: 'bash', args: '-c nvidia-smi', platform: 'gpu-l40s-a', preset: '1gpu-8vcpu-32gb', timeout: '1h' }, ENV);
  assert.deepEqual(request.metadata, { parentId: 'project-e00test', name: 'my-job' });
  assert.equal(request.spec.image, 'nvidia/cuda:13.1.1-runtime-ubuntu24.04');
  assert.equal(request.spec.containerCommand, 'bash');
  assert.equal(request.spec.args, '-c nvidia-smi');
  assert.equal(request.spec.timeout, '3600s');
  assert.equal(request.spec.subnetId, 'vpcsubnet-e00test');
  assert.deepEqual(request.spec.disk, { type: 'NETWORK_SSD', sizeBytes: String(250 * 1024 ** 3) });
  assert.equal(estimate.maxCostUsd, 1.55);
});

test('buildJobRequest validates name, preset, timeout, injected file size, volumes', () => {
  assert.throws(() => buildJobRequest({ name: 'Bad_Name' }, ENV), /lowercase/);
  assert.throws(() => buildJobRequest({ name: 'ok', platform: 'gpu-h100-sxm', preset: '1gpu-8vcpu-32gb' }, ENV), /not listed/);
  assert.throws(() => buildJobRequest({ name: 'ok', timeout: '10m' }, ENV), /between 1h and 168h/);
  assert.throws(() => buildJobRequest({ name: 'ok', injectedFiles: [{ containerPath: '/x', content: 'a'.repeat(64 * 1024 + 1) }] }, ENV), /64 KiB/);
  assert.throws(() => buildJobRequest({ name: 'ok', volumes: ['bucket:relative/path'] }, ENV), /absolute/);
  assert.throws(() => buildJobRequest({ name: 'ok' }, {}), /NEBIUS_PROJECT_ID/);
});

test('buildJobRequest maps env, volumes (string + object, s3), preemptible', () => {
  const { request } = buildJobRequest({ name: 'v', env: { A: '1' }, volumes: ['mybucket:/data:ro', 's3://ext-bucket:/ext', { source: 'fs-1', containerPath: '/fs', sourcePath: 'sub' }], preemptible: true }, ENV);
  assert.deepEqual(request.spec.environmentVariables, [{ name: 'A', value: '1' }]);
  assert.deepEqual(request.spec.volumes, [
    { source: 'mybucket', containerPath: '/data', mode: 'READ_ONLY' },
    { source: 's3://ext-bucket', containerPath: '/ext', mode: 'READ_WRITE' },
    { source: 'fs-1', containerPath: '/fs', mode: 'READ_WRITE', sourcePath: 'sub' },
  ]);
  assert.equal(request.spec.preemptible, true);
});

test('buildTrainingJobRequest injects script, requirements and run.sh; args avoid shell quoting', () => {
  const { request } = buildTrainingJobRequest({ name: 'tr', script: 'print("hi")\n', requirements: 'torch\n', scriptArgs: ['--epochs', '2', 'it s'], outputVolume: 'out-bucket' }, ENV);
  const files = Object.fromEntries(request.spec.injectedFiles.map((f) => [f.containerPath, Buffer.from(f.content, 'base64').toString('utf8')]));
  assert.equal(files['/workspace/train.py'], 'print("hi")\n');
  assert.equal(files['/workspace/requirements.txt'], 'torch\n');
  assert.match(files['/workspace/run.sh'], /pip install --no-cache-dir -q -r requirements\.txt/);
  assert.match(files['/workspace/run.sh'], /exec python train\.py --epochs 2 'it s'/);
  assert.equal(request.spec.containerCommand, 'bash');
  assert.equal(request.spec.args, '/workspace/run.sh');
  assert.deepEqual(request.spec.volumes, [{ source: 'out-bucket', containerPath: '/outputs', mode: 'READ_WRITE' }]);
  assert.deepEqual(request.spec.environmentVariables, [{ name: 'NEBIUS_OUTPUT_DIR', value: '/outputs' }]);
  assert.equal(shellQuote("a'b"), `'a'\\''b'`);
});

test('estimateCost scales with GPUs and hours', () => {
  const e = estimateCost({ platform: 'gpu-h100-sxm', preset: '8gpu-128vcpu-1600gb', timeoutSeconds: 7200 });
  assert.equal(e.gpus, 8); assert.equal(e.pricePerHour, 30.8); assert.equal(e.maxCostUsd, 61.6);
  assert.equal(estimateCost({ platform: 'unknown', preset: '1gpu-x', timeoutSeconds: 3600 }).known, false);
  // Published preemptible price for H100; platforms without one fall back to 50% off.
  const pre = estimateCost({ platform: 'gpu-h100-sxm', preset: '1gpu-16vcpu-200gb', timeoutSeconds: 7200, preemptible: true });
  assert.equal(pre.pricePerHour, 2.15); assert.equal(pre.maxCostUsd, 4.3); assert.equal(pre.preemptibleAssumed50pct, false);
  const assumed = estimateCost({ platform: 'gpu-l40s-a', preset: '1gpu-8vcpu-32gb', timeoutSeconds: 3600, preemptible: true });
  assert.equal(assumed.pricePerHour, 0.78); assert.equal(assumed.preemptibleAssumed50pct, true);
});

test('service-account JWT is RS256 with kid/iss/sub/exp and verifies', () => {
  const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
  const pem = privateKey.export({ type: 'pkcs8', format: 'pem' });
  const jwt = makeServiceAccountJwt({ saId: 'serviceaccount-e00abc', keyId: 'publickey-e00xyz', privateKeyPem: pem, now: 1_700_000_000_000 });
  const [h, p, s] = jwt.split('.');
  assert.deepEqual(JSON.parse(Buffer.from(h, 'base64url')), { alg: 'RS256', typ: 'JWT', kid: 'publickey-e00xyz' });
  const payload = JSON.parse(Buffer.from(p, 'base64url'));
  assert.equal(payload.iss, 'serviceaccount-e00abc'); assert.equal(payload.sub, 'serviceaccount-e00abc');
  assert.equal(payload.exp - payload.iat, 300);
  const v = createVerify('RSA-SHA256'); v.update(`${h}.${p}`);
  assert.equal(v.verify(publicKey, Buffer.from(s, 'base64url')), true);
});

test('token exchange posts the RFC 8693 form and caches via provider', async () => {
  let calls = 0;
  const fetchImpl = async (url, init) => {
    calls++;
    assert.equal(String(url), 'https://auth.eu.nebius.com/oauth2/token/exchange');
    const form = new URLSearchParams(init.body);
    assert.equal(form.get('grant_type'), 'urn:ietf:params:oauth:grant-type:token-exchange');
    assert.equal(form.get('subject_token_type'), 'urn:ietf:params:oauth:token-type:jwt');
    return new Response(JSON.stringify({ access_token: 'tok', token_type: 'Bearer', expires_in: 43200 }), { status: 200 });
  };
  assert.deepEqual(await exchangeJwtForToken('x.y.z', { fetchImpl }), { token: 'tok', expiresInSeconds: 43200 });
  const { privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
  const provider = createTokenProvider({ NEBIUS_SA_ID: 'sa', NEBIUS_SA_KEY_ID: 'k', NEBIUS_SA_PRIVATE_KEY: privateKey.export({ type: 'pkcs8', format: 'pem' }) }, { fetchImpl });
  assert.equal(await provider(), 'tok'); assert.equal(await provider(), 'tok');
  assert.equal(calls, 2, 'one exchange call, second provider() call served from cache');
  const staticProvider = createTokenProvider({ NEBIUS_ACCESS_TOKEN: ' static ' });
  assert.equal(await staticProvider(), 'static');
});

function fakeFetch(handlers) {
  const seen = [];
  const fetchImpl = async (url, init = {}) => {
    const u = new URL(url); seen.push({ method: init.method, path: u.pathname, query: Object.fromEntries(u.searchParams), headers: init.headers, body: init.body ? JSON.parse(init.body) : undefined });
    const h = handlers.shift();
    if (!h) throw new Error(`unexpected fetch ${init.method} ${u.pathname}`);
    return new Response(JSON.stringify(h.body), { status: h.status ?? 200 });
  };
  return { fetchImpl, seen };
}

test('client sends bearer auth and the documented endpoints', async () => {
  const { fetchImpl, seen } = fakeFetch([
    { body: { id: 'op-1', resourceId: 'job-1' } },
    { body: { metadata: { id: 'job-1', name: 'n' }, status: { state: 'RUNNING' } } },
    { body: { items: [], nextPageToken: '' } },
    { body: { id: 'op-2' } },
    { body: { id: 'op-3' } },
    { body: { message: 'nope' }, status: 403 },
  ]);
  const c = new NebiusJobsClient({ projectId: 'project-x', getToken: async () => 'T', fetchImpl });
  const created = await c.createJob({ metadata: {}, spec: {} });
  assert.deepEqual(created.jobId, 'job-1');
  assert.equal((await c.getJob('job-1')).status.state, 'RUNNING');
  await c.listJobs({ pageSize: 10 }); await c.cancelJob('job-1'); await c.deleteJob('job-1');
  await assert.rejects(() => c.getJob('job-1'), (e) => e.status === 403 && /nope/.test(e.message));
  assert.deepEqual(seen.map((s) => [s.method, s.path]), [['POST', '/ai/v1/jobs'], ['GET', '/ai/v1/jobs/job-1'], ['GET', '/ai/v1/jobs'], ['POST', '/ai/v1/jobs/cancel'], ['DELETE', '/ai/v1/jobs/job-1'], ['GET', '/ai/v1/jobs/job-1']]);
  assert.equal(seen[0].headers.Authorization, 'Bearer T');
  assert.deepEqual(seen[2].query, { parentId: 'project-x', pageSize: '10' });
  assert.deepEqual(seen[3].body, { id: 'job-1' });
});

test('waitForJob polls until a terminal state', async () => {
  const states = ['PROVISIONING', 'RUNNING', 'RUNNING', 'COMPLETED'];
  const { fetchImpl } = fakeFetch(states.map((s) => ({ body: { metadata: { id: 'j' }, status: { state: s } } })));
  const c = new NebiusJobsClient({ projectId: 'p', getToken: async () => 'T', fetchImpl });
  const updates = [];
  const job = await c.waitForJob('j', { intervalMs: 1, sleep: async () => {}, onUpdate: (j) => updates.push(j.status.state) });
  assert.equal(job.status.state, 'COMPLETED');
  assert.deepEqual(updates, ['PROVISIONING', 'RUNNING', 'COMPLETED']);
  assert.equal(isTerminal('FAILED'), true); assert.equal(isTerminal('IMAGE_PULLING'), false);
  assert.equal(summarizeJob(job).state, 'COMPLETED');
});

test('routes map to the service and redact injected files', async () => {
  const { fetchImpl } = fakeFetch([{ body: { id: 'op', resourceId: 'job-9' } }]);
  const client = new NebiusJobsClient({ projectId: 'p', getToken: async () => 'T', fetchImpl });
  const router = new Router();
  registerRoutes(router, { service: createTrainingService({ env: ENV, client }) });
  const m = router.match('POST', '/api/training/jobs');
  const res = await m.handler({ params: {}, query: new URLSearchParams(), body: { name: 'r', script: 'print(1)' } });
  assert.equal(res.jobId, 'job-9');
  assert.ok(res.request.spec.injectedFiles.every((f) => f.bytes > 0 && f.content === undefined));
  assert.ok(router.match('GET', '/api/training/jobs/abc/logs'));
  assert.equal(router.match('GET', '/api/training/jobs/abc/logs').params.id, 'abc');
  assert.equal(router.match('GET', '/api/training/catalog').params.id, undefined);
});

test('a multi-GPU preset launches under torchrun, not plain python', () => {
  // The whole point of paying for four GPUs: without this the other three idle.
  const { request } = buildTrainingJobRequest(
    { name: 'ddp', script: 'print(1)\n', platform: 'gpu-l40s-d', preset: '4gpu-128vcpu-768gb' },
    ENV,
  );
  const files = Object.fromEntries(request.spec.injectedFiles.map((f) => [f.containerPath, Buffer.from(f.content, 'base64').toString('utf8')]));
  assert.match(files['/workspace/run.sh'], /exec torchrun --standalone --nnodes=1 --nproc_per_node=4 train\.py/);
});

test('a single-GPU preset still runs plain python', () => {
  const { request } = buildTrainingJobRequest(
    { name: 'single', script: 'print(1)\n', platform: 'gpu-l40s-a', preset: '1gpu-8vcpu-32gb' },
    ENV,
  );
  const files = Object.fromEntries(request.spec.injectedFiles.map((f) => [f.containerPath, Buffer.from(f.content, 'base64').toString('utf8')]));
  assert.match(files['/workspace/run.sh'], /exec python train\.py/);
  assert.doesNotMatch(files['/workspace/run.sh'], /torchrun/);
});

test('distributed:false opts a multi-GPU job out of torchrun', () => {
  const { request } = buildTrainingJobRequest(
    { name: 'optout', script: 'print(1)\n', platform: 'gpu-l40s-d', preset: '4gpu-128vcpu-768gb', distributed: false },
    ENV,
  );
  const files = Object.fromEntries(request.spec.injectedFiles.map((f) => [f.containerPath, Buffer.from(f.content, 'base64').toString('utf8')]));
  assert.doesNotMatch(files['/workspace/run.sh'], /torchrun/);
});

test('injected file content is base64, as the protobuf bytes field requires', () => {
  // Sending the raw string is rejected live with
  // `invalid value for bytes field content`, which silently broke every
  // injected-file submission. The 64 KiB cap is still measured on the decoded
  // content, since that is what the platform enforces.
  const { request } = buildTrainingJobRequest({ name: 'b64', script: 'print("hi")\n' }, ENV);
  const file = request.spec.injectedFiles.find((f) => f.containerPath === '/workspace/train.py');
  assert.equal(Buffer.from(file.content, 'base64').toString('utf8'), 'print("hi")\n');
  assert.notEqual(file.content, 'print("hi")\n');
});

test('the 64 KiB limit applies to decoded bytes, not the base64 expansion', () => {
  // base64 inflates by 4/3, so a 60 KiB file must still pass.
  const sixtyKiB = 'x'.repeat(60 * 1024);
  assert.doesNotThrow(() => buildTrainingJobRequest({ name: 'big', script: sixtyKiB }, ENV));
  assert.throws(() => buildTrainingJobRequest({ name: 'toobig', script: 'x'.repeat(65 * 1024) }, ENV), /64 KiB/);
});
