// Turn a friendly job description into a Nebius CreateJobRequest, with
// validation, env-driven defaults, and a rough cost estimate.
import { readFileSync } from 'node:fs';
import path from 'node:path';

// Platform catalog. Presets follow Nebius's "<n>gpu-<v>vcpu-<r>gb" naming
// (https://docs.nebius.com/compute/virtual-machines/types). Prices are
// public on-demand $/GPU-hour from https://nebius.com/prices as of 2026-09
// ("from" prices; larger vCPU presets cost more). Verify live with
// `nebius compute platform list` before betting the budget on a number.
export const PLATFORMS = {
  'gpu-l40s-a':  { gpu: 'NVIDIA L40S 48GB (AMD host)',   pricePerGpuHour: 1.55, presets: ['1gpu-8vcpu-32gb', '1gpu-16vcpu-64gb', '1gpu-24vcpu-96gb', '1gpu-32vcpu-128gb', '1gpu-40vcpu-160gb'] },
  'gpu-l40s-d':  { gpu: 'NVIDIA L40S 48GB (Intel host)', pricePerGpuHour: 1.82, presets: ['1gpu-16vcpu-96gb', '1gpu-32vcpu-192gb', '1gpu-48vcpu-288gb', '2gpu-64vcpu-384gb', '2gpu-96vcpu-576gb', '4gpu-128vcpu-768gb', '4gpu-192vcpu-1152gb'] },
  'gpu-h100-sxm': { gpu: 'NVIDIA H100 SXM 80GB',         pricePerGpuHour: 3.85, preemptiblePricePerGpuHour: 2.15, presets: ['1gpu-16vcpu-200gb', '8gpu-128vcpu-1600gb'] },
  'gpu-h200-sxm': { gpu: 'NVIDIA H200 SXM 141GB',        pricePerGpuHour: 4.50, preemptiblePricePerGpuHour: 2.45, presets: ['1gpu-16vcpu-200gb', '8gpu-128vcpu-1600gb'] },
  'gpu-b200-sxm': { gpu: 'NVIDIA B200 SXM 180GB',        pricePerGpuHour: 7.15, presets: ['1gpu-20vcpu-224gb', '8gpu-160vcpu-1792gb'] },
};

export const GIB = 1024 ** 3;
export const MIN_TIMEOUT_S = 3600;
export const MAX_TIMEOUT_S = 604800;
export const MAX_INJECTED_FILE_BYTES = 64 * 1024;
export const DEFAULTS = {
  platform: 'gpu-l40s-a',
  preset: '1gpu-8vcpu-32gb',
  image: 'pytorch/pytorch:2.7.1-cuda12.8-cudnn9-runtime',
  timeout: '2h',
  diskGiB: 250,
  shmGiB: 16,
};

export class SpecError extends Error { constructor(msg) { super(msg); this.status = 400; } }

/** "2h" | "90m" | "3600s" | 3600 -> seconds */
export function parseDurationSeconds(value) {
  if (typeof value === 'number') return Math.round(value);
  const m = /^\s*(\d+(?:\.\d+)?)\s*(s|m|h|d)?\s*$/i.exec(String(value));
  if (!m) throw new SpecError(`Bad duration "${value}" (use e.g. 3600, 90m, 2h, 1d)`);
  const mult = { s: 1, m: 60, h: 3600, d: 86400 }[(m[2] || 's').toLowerCase()];
  return Math.round(Number(m[1]) * mult);
}

export function gpusInPreset(preset) {
  const m = /^(\d+)gpu-/.exec(preset || '');
  return m ? Number(m[1]) : 0;
}

/** Rough worst-case cost if the job runs for its full timeout. */
export function estimateCost({ platform, preset, timeoutSeconds, preemptible = false }) {
  const p = PLATFORMS[platform];
  const gpus = gpusInPreset(preset);
  if (!p || !gpus) return { known: false, gpus, hours: timeoutSeconds / 3600 };
  // Preemptible: nebius.com/prices lists H100 $2.15 and H200 $2.45 per GPU-hour
  // (about 45% off). Platforms without a published preemptible price assume 50% off.
  const assumed = preemptible && !p.preemptiblePricePerGpuHour;
  const perGpu = preemptible ? (p.preemptiblePricePerGpuHour ?? p.pricePerGpuHour * 0.5) : p.pricePerGpuHour;
  const pricePerHour = perGpu * gpus;
  const hours = timeoutSeconds / 3600;
  return { known: true, gpus, gpu: p.gpu, pricePerHour: round2(pricePerHour), hours, maxCostUsd: round2(pricePerHour * hours), preemptible, preemptibleAssumed50pct: assumed };
}
const round2 = (n) => Math.round(n * 100) / 100;

function toEnvArray(env) {
  if (!env) return [];
  if (Array.isArray(env)) return env.map((e) => {
    if (typeof e === 'string') { const i = e.indexOf('='); if (i < 1) throw new SpecError(`Bad env "${e}", want KEY=VALUE`); return { name: e.slice(0, i), value: e.slice(i + 1) }; }
    if (!e?.name) throw new SpecError('env entries need a name');
    return e.secret ? { name: e.name, mysteryboxSecret: e.secret } : { name: e.name, value: String(e.value ?? '') };
  });
  return Object.entries(env).map(([name, value]) => ({ name, value: String(value) }));
}

function toVolumes(volumes) {
  return (volumes || []).map((v) => {
    if (typeof v === 'string') { // SOURCE:/container/path[:ro|rw]
      const parts = v.split(':');
      let source, containerPath, mode;
      if (v.startsWith('s3://')) { source = parts[0] + ':' + parts[1]; containerPath = parts[2]; mode = parts[3]; }
      else { [source, containerPath, mode] = parts; }
      v = { source, containerPath, mode };
    }
    if (!v.source || !v.containerPath) throw new SpecError('volume needs source and containerPath');
    if (!v.containerPath.startsWith('/')) throw new SpecError(`volume containerPath must be absolute: ${v.containerPath}`);
    const modeRaw = String(v.mode || 'rw').toUpperCase();
    const mode = modeRaw === 'RO' || modeRaw === 'READ_ONLY' ? 'READ_ONLY' : 'READ_WRITE';
    return { source: v.source, containerPath: v.containerPath, mode, ...(v.sourcePath ? { sourcePath: v.sourcePath } : {}) };
  });
}

function toInjectedFiles(files) {
  return (files || []).map((f) => {
    if (!f.containerPath?.startsWith('/')) throw new SpecError(`injected file containerPath must be absolute: ${f.containerPath}`);
    const content = f.content ?? (f.localPath ? readFileSync(f.localPath, 'utf8') : undefined);
    if (!content) throw new SpecError(`injected file ${f.containerPath} has no content`);
    const bytes = Buffer.byteLength(content, 'utf8');
    if (bytes > MAX_INJECTED_FILE_BYTES) throw new SpecError(`injected file ${f.containerPath} is ${bytes} bytes; limit is 64 KiB. Put big files in a bucket volume instead.`);
    // `content` is a protobuf `bytes` field, and protobuf's JSON mapping encodes
    // bytes as base64. Sending the raw string is rejected at the API with
    // `invalid value for bytes field content`, which is what every injected-file
    // submission hit before this. The 64 KiB limit above is measured on the
    // decoded content, since that is what the platform enforces.
    return { containerPath: f.containerPath, content: Buffer.from(content, 'utf8').toString('base64') };
  });
}

/**
 * Build a CreateJobRequest.
 * @param {object} input  { name, image, command, args, env, platform, preset, timeout, diskGiB, shmGiB,
 *                          workingDir, volumes, injectedFiles, preemptible, sshKeys, subnetId, publicIp,
 *                          restartAttempts, labels, dryRun }
 * @param {object} env    process.env-like, for NEBIUS_* defaults
 */
export function buildJobRequest(input = {}, env = process.env) {
  const projectId = input.projectId || env.NEBIUS_PROJECT_ID;
  if (!projectId) throw new SpecError('NEBIUS_PROJECT_ID is not set');
  const name = input.name;
  if (!name || !/^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/.test(name)) throw new SpecError(`Job name "${name}" must be 1-63 chars: lowercase letters, digits, hyphens`);

  const platform = input.platform || env.NEBIUS_DEFAULT_PLATFORM || DEFAULTS.platform;
  const preset = input.preset || env.NEBIUS_DEFAULT_PRESET || DEFAULTS.preset;
  if (PLATFORMS[platform] && !PLATFORMS[platform].presets.includes(preset)) {
    throw new SpecError(`Preset "${preset}" is not listed for ${platform}. Known: ${PLATFORMS[platform].presets.join(', ')}`);
  }
  const timeoutSeconds = parseDurationSeconds(input.timeout || env.NEBIUS_DEFAULT_TIMEOUT || DEFAULTS.timeout);
  if (timeoutSeconds < MIN_TIMEOUT_S || timeoutSeconds > MAX_TIMEOUT_S) throw new SpecError(`timeout must be between 1h and 168h (got ${timeoutSeconds}s)`);
  const diskGiB = Number(input.diskGiB || env.NEBIUS_DEFAULT_DISK_GIB || DEFAULTS.diskGiB);
  const shmGiB = Number(input.shmGiB || DEFAULTS.shmGiB);
  const image = input.image || env.NEBIUS_DEFAULT_IMAGE || DEFAULTS.image;
  const subnetId = input.subnetId || env.NEBIUS_SUBNET_ID || undefined;

  const spec = {
    image,
    ...(input.command ? { containerCommand: input.command } : {}),
    ...(input.args ? { args: Array.isArray(input.args) ? input.args.join(' ') : String(input.args) } : {}),
    platform, preset,
    timeout: `${timeoutSeconds}s`,
    disk: { type: 'NETWORK_SSD', sizeBytes: String(Math.round(diskGiB * GIB)) },
    shmSizeBytes: String(Math.round(shmGiB * GIB)),
    ...(subnetId ? { subnetId } : {}),
    ...(input.workingDir ? { workingDir: input.workingDir } : {}),
    ...(input.preemptible ? { preemptible: true } : {}),
    ...(input.publicIp ? { publicIp: true } : {}),
    ...(input.restartAttempts ? { restartAttempts: String(input.restartAttempts) } : {}),
  };
  const environmentVariables = toEnvArray(input.env);
  if (environmentVariables.length) spec.environmentVariables = environmentVariables;
  const volumes = toVolumes(input.volumes);
  if (volumes.length) spec.volumes = volumes;
  const injectedFiles = toInjectedFiles(input.injectedFiles);
  if (injectedFiles.length) spec.injectedFiles = injectedFiles;
  if (input.sshKeys?.length) spec.sshAuthorizedKeys = input.sshKeys;
  if (input.registry?.username) spec.registryCredentials = { username: input.registry.username, password: input.registry.password };

  const request = { metadata: { parentId: projectId, name, ...(input.labels ? { labels: input.labels } : {}) }, spec };
  if (input.dryRun) request.dryRun = true;
  const estimate = estimateCost({ platform, preset, timeoutSeconds, preemptible: !!input.preemptible });
  return { request, estimate };
}

/**
 * Convenience for "run this Python script on a GPU": injects the script (and
 * optional requirements.txt) into /workspace and wires the container command.
 * Big files (datasets, checkpoints) must come from a mounted volume.
 */
export function buildTrainingJobRequest(input = {}, env = process.env) {
  const script = input.script ?? (input.scriptPath ? readFileSync(input.scriptPath, 'utf8') : undefined);
  if (!script) throw new SpecError('training job needs script (text) or scriptPath');
  const scriptName = input.scriptName || (input.scriptPath ? path.basename(input.scriptPath) : 'train.py');
  const requirements = input.requirements ?? (input.requirementsPath ? readFileSync(input.requirementsPath, 'utf8') : undefined);
  const workdir = input.workingDir || '/workspace';

  const injectedFiles = [...(input.injectedFiles || []), { containerPath: `${workdir}/${scriptName}`, content: script }];
  if (requirements) injectedFiles.push({ containerPath: `${workdir}/requirements.txt`, content: requirements });

  const scriptArgs = Array.isArray(input.scriptArgs) ? input.scriptArgs.map(shellQuote).join(' ') : (input.scriptArgs || '');
  // The API's `args` is one string whose tokenisation rules are not documented,
  // so never rely on quoting inside it: inject a run.sh and execute that.
  const steps = ['#!/usr/bin/env bash', 'set -euo pipefail', `cd ${workdir}`, 'nvidia-smi || true'];
  if (input.setup) steps.push(input.setup);
  if (requirements) steps.push('pip install --no-cache-dir -q -r requirements.txt');

  // A multi-GPU preset does nothing on its own: `python train.py` binds one
  // device and the other three idle while you pay for them. torchrun spawns one
  // rank per GPU and sets RANK / WORLD_SIZE / LOCAL_RANK, which is what a DDP
  // training script reads. Default to it whenever the preset has more than one
  // GPU, since paying 4x for 1x throughput is never the intent; `distributed:
  // false` opts out for a script that genuinely is single-process.
  const preset = input.preset || env.NEBIUS_DEFAULT_PRESET || DEFAULTS.preset;
  const gpus = gpusInPreset(preset);
  const distributed = input.distributed ?? gpus > 1;
  if (distributed && gpus > 1) {
    steps.push(`exec torchrun --standalone --nnodes=1 --nproc_per_node=${gpus} ${scriptName} ${scriptArgs}`.trim());
  } else {
    steps.push(`exec python ${scriptName} ${scriptArgs}`.trim());
  }
  injectedFiles.push({ containerPath: `${workdir}/run.sh`, content: steps.join('\n') + '\n' });

  const volumes = [...(input.volumes || [])];
  const outputVolume = input.outputVolume ?? env.NEBIUS_OUTPUT_VOLUME;
  if (outputVolume) volumes.push({ source: outputVolume, containerPath: '/outputs', mode: 'rw' });
  const jobEnv = { ...(outputVolume ? { NEBIUS_OUTPUT_DIR: '/outputs' } : {}), ...(Array.isArray(input.env) ? Object.fromEntries(toEnvArray(input.env).map((e) => [e.name, e.value])) : (input.env || {})) };

  return buildJobRequest({
    ...input,
    command: 'bash',
    args: `${workdir}/run.sh`,
    workingDir: workdir,
    injectedFiles,
    volumes,
    env: jobEnv,
  }, env);
}

export function shellQuote(s) {
  s = String(s);
  return /^[A-Za-z0-9_\-./=:@]+$/.test(s) ? s : `'${s.replace(/'/g, `'\\''`)}'`;
}
