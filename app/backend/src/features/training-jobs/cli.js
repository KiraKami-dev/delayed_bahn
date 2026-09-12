#!/usr/bin/env node
// Terminal front-end for the training-jobs feature. Same code path as the
// HTTP routes, so anything that works here works via the API.
//   npm run train -- doctor
//   npm run train -- smoke
//   npm run train -- submit --name my-run --script examples/train.py --requirements examples/requirements.txt --wait
//   npm run train -- submit-spec examples/nvidia-smi.json
//   npm run train -- list | status <id> | wait <id> | logs <id> [--follow] | cancel <id> | delete <id>
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { loadDotenv } from '../../server.js';
import { createTrainingService } from './routes/training-jobs.js';
import { findNebiusCli } from './nebius/auth.js';
import { isTerminal } from './nebius/client.js';

const here = path.dirname(fileURLToPath(import.meta.url));

function parseArgs(argv) {
  const out = { _: [], env: [], volume: [], inject: [], scriptArgs: [] };
  let i = 0;
  while (i < argv.length) {
    const a = argv[i];
    if (a === '--') { out.scriptArgs = argv.slice(i + 1); break; }
    if (a.startsWith('--')) {
      const key = a.slice(2);
      const next = argv[i + 1];
      const isFlag = next === undefined || next.startsWith('--');
      const val = isFlag ? true : next;
      if (key === 'env' || key === 'volume' || key === 'inject') out[key].push(val); else out[key] = val;
      i += isFlag ? 1 : 2;
    } else { out._.push(a); i++; }
  }
  return out;
}

const log = (...a) => console.error(...a);
const print = (o) => console.log(typeof o === 'string' ? o : JSON.stringify(o, null, 2));

async function main() {
  loadDotenv();
  const args = parseArgs(process.argv.slice(2));
  const [cmd, target] = args._;
  const svc = createTrainingService({ env: process.env });

  switch (cmd) {
    case 'doctor': {
      log(`Node ${process.version}`);
      log(`Nebius CLI: ${findNebiusCli() || 'not found (needed only for logs / interactive login)'}`);
      log(`NEBIUS_PROJECT_ID: ${process.env.NEBIUS_PROJECT_ID || 'MISSING'}`);
      const who = await svc.whoami();
      print(who);
      if (!process.env.NEBIUS_SUBNET_ID) {
        const subs = Array.isArray(who.subnets) ? who.subnets : [];
        if (subs.length === 1) log(`\nOne subnet found. Add to app/backend/.env:\n  NEBIUS_SUBNET_ID=${subs[0].id}`);
        else if (subs.length > 1) log(`\n${subs.length} subnets found; set NEBIUS_SUBNET_ID to one of them in app/backend/.env.`);
      }
      log('\nOK: authenticated and project reachable.');
      return;
    }
    case 'catalog': return print(svc.catalog());
    case 'estimate': return print(svc.estimate({ platform: args.platform, preset: args.preset, timeout: args.timeout, preemptible: !!args.preemptible }));
    case 'smoke': {
      // Same workload as Nebius's own quick start: nvidia-smi on one L40S.
      const name = args.name || `smoke-nvidia-smi-${Date.now().toString(36)}`;
      const body = { name, image: 'nvidia/cuda:13.1.1-runtime-ubuntu24.04', command: 'bash', args: '-c nvidia-smi', timeout: '1h', platform: args.platform, preset: args.preset };
      return submitAndMaybeWait(svc, body, { ...args, wait: true });
    }
    case 'submit': {
      if (!args.script) fail('submit needs --script <file.py> (see README)');
      const body = {
        name: args.name || `train-${path.basename(args.script, '.py')}-${Date.now().toString(36)}`,
        scriptPath: args.script, requirementsPath: args.requirements,
        // --inject local.py[:/container/path] , repeatable. A script that imports
        // sibling modules needs them alongside it; without this the only routes
        // are a bucket round-trip or pasting everything into one file.
        injectedFiles: (args.inject || []).map((spec) => {
          const sep = spec.lastIndexOf(':');
          const local = sep > 1 ? spec.slice(0, sep) : spec;
          const dest = sep > 1 ? spec.slice(sep + 1) : `/workspace/${path.basename(local)}`;
          return { containerPath: dest, content: readFileSync(local, 'utf8') };
        }),
        scriptArgs: args.scriptArgs, env: args.env, volumes: args.volume,
        platform: args.platform, preset: args.preset, image: args.image, timeout: args.timeout,
        diskGiB: args['disk-gib'], preemptible: !!args.preemptible, outputVolume: args.output, setup: args.setup,
      };
      return submitAndMaybeWait(svc, body, args);
    }
    case 'submit-spec': {
      if (!target) fail('submit-spec needs a JSON file (see examples/)');
      const body = JSON.parse(readFileSync(path.resolve(target), 'utf8'));
      if (body.scriptPath) body.scriptPath = path.resolve(path.dirname(target), body.scriptPath);
      if (body.requirementsPath) body.requirementsPath = path.resolve(path.dirname(target), body.requirementsPath);
      return submitAndMaybeWait(svc, body, args);
    }
    case 'list': return print(await svc.list({ pageSize: args.limit || 50 }));
    case 'status': case 'get': return print(await svc.get(need(target), { raw: !!args.raw }));
    case 'wait': return print(await waitVerbose(svc, need(target)));
    case 'cancel': return print(await svc.cancel(need(target)));
    case 'delete': return print(await svc.remove(need(target)));
    case 'logs': return streamLogs(need(target), args);
    default:
      log(readFileSync(fileURLToPath(import.meta.url), 'utf8').split('\n').slice(1, 8).map((l) => l.replace(/^\/\/ ?/, '')).join('\n'));
      process.exit(cmd ? 2 : 0);
  }
}

async function submitAndMaybeWait(svc, body, args) {
  const { request, estimate } = svc.build(body);
  log(`Job "${request.metadata.name}" on ${request.spec.platform}/${request.spec.preset}, timeout ${request.spec.timeout}` + (estimate.known ? ` -> worst case ~$${estimate.maxCostUsd} at $${estimate.pricePerHour}/h` : ''));
  if (args['dry-run']) return print(await svc.dryRun(body));
  const res = await svc.submit(body);
  log(`Submitted. jobId=${res.jobId}`);
  log(`  status: npm run train -- status ${res.jobId}`);
  log(`  logs:   npm run train -- logs ${res.jobId} --follow`);
  if (!args.wait) return print(res);
  const final = await waitVerbose(svc, res.jobId);
  print(final);
  if (findNebiusCli()) { log('\n--- last 100 log lines ---'); await streamLogs(res.jobId, { tail: 100 }); }
  process.exitCode = final.state === 'COMPLETED' ? 0 : 1;
}

async function waitVerbose(svc, id) {
  log(`Waiting for ${id} (Ctrl+C stops waiting, not the job)...`);
  return svc.wait(id, { intervalMs: 15_000, onUpdate: (job) => log(`  ${new Date().toISOString()}  ${job.status?.state}${job.status?.stateDetails?.message ? ' - ' + job.status.stateDetails.message : ''}`) });
}

function streamLogs(id, args) {
  const bin = findNebiusCli();
  if (!bin) fail('Logs need the Nebius CLI. Install: curl -sSL https://storage.eu-north1.nebius.cloud/cli/install.sh | bash');
  const cliArgs = ['ai', 'job', 'logs', id, '--tail', String(args.tail || 200)];
  if (args.follow) cliArgs.push('--follow');
  if (args.since) cliArgs.push('--since', String(args.since));
  return new Promise((resolve) => spawn(bin, cliArgs, { stdio: 'inherit' }).on('exit', (code) => { process.exitCode = code ?? 0; resolve(); }));
}

const need = (v) => v || fail('missing job id');
function fail(msg) { log(`error: ${msg}`); process.exit(2); }

main().catch((e) => { log(`error: ${e.message}`); if (e.body) log(JSON.stringify(e.body, null, 2)); process.exit(1); });
