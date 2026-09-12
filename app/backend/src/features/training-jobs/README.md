# Feature: training-jobs

Submit, track, and cancel GPU training runs on **Nebius Serverless AI jobs**
from this backend. A job is a container on a fresh GPU VM: you give it an
image, a command, a platform/preset, and a timeout; Nebius bills the VM while
it runs and releases everything when the container exits.

- `nebius/auth.js`   – access tokens (static token, service-account JWT, or CLI)
- `nebius/client.js` – REST client for `ai/v1/jobs` (+ `iam/v1/profiles`, `vpc/v1/subnets`)
- `nebius/spec.js`   – validated `CreateJobRequest` builder, platform catalog, cost estimate
- `routes/`          – HTTP endpoints under `/api/training/*`
- `cli.js`           – terminal front-end over the same service (`npm run train -- ...`)
- `examples/`        – nvidia-smi check, a distilgpt2 fine-tune, a bring-your-own-image spec

Zero npm dependencies: Node ≥ 22 built-ins only (fetch, crypto, http).

## 0. Team access (once per teammate)

Everyone submits jobs against the same Nebius project, so they need to be a
member of it. The account owner does this in https://console.nebius.com:
**Administration → IAM → Groups → editors → Add member** (invite by email).
Each teammate then does section 1 on their own machine. Nothing secret lives
in git: `.env`, `secrets/` and `*.pem` are ignored, so every person keeps
their own login. A shared service-account key is only for a deployed server.

## 1. One-time setup (10 minutes)

### a. Nebius CLI (already installed on this Mac at `~/.nebius/bin/nebius`)

```bash
curl -sSL https://storage.eu-north1.nebius.cloud/cli/install.sh | bash   # if missing
exec -l $SHELL                                                            # picks up PATH
nebius profile create --profile default \
  --endpoint api.nebius.cloud --federation-endpoint auth.nebius.com \
  --parent-id <project_ID>          # opens the browser to log in
nebius profile list                 # sanity check
```

Project ID: **Administration → Projects** in https://console.nebius.com, or
`nebius iam v2 project list --parent-id <tenant_ID>`. It looks like `project-e00…`.

### b. Quota

**Administration → Limits → Quotas → Compute → Number of virtual machines**
must be ≥ 1, and the GPU platform you want (L40S / H100 …) must have a non-zero
quota. Request an increase in the console if not; jobs fail with
`NotEnoughResources` otherwise.

### c. Backend env

The team keeps ONE env file at the repo root: `cp .env.example .env` there, then
`ln -s ../../.env app/backend/.env`. The root example already carries the
team default (eu-north1 project + subnet, 4x L40S). Minimum content if you
write it by hand:

```bash
NEBIUS_PROJECT_ID=project-...     # Administration -> Projects
NEBIUS_SUBNET_ID=                 # leave blank; doctor prints it
```

Then:

```bash
cd app/backend && npm run train -- doctor
```

All variables the backend reads (everything except `NEBIUS_PROJECT_ID` is optional):

| Variable | Purpose |
|---|---|
| `NEBIUS_PROJECT_ID` | project that owns the jobs (`metadata.parentId`) |
| `NEBIUS_SUBNET_ID` | subnet for the job VM; required only if the project has more than one |
| `NEBIUS_ACCESS_TOKEN` | auth mode (a): static 12 h token from `nebius iam get-access-token` |
| `NEBIUS_SA_ID`, `NEBIUS_SA_KEY_ID`, `NEBIUS_SA_PRIVATE_KEY_FILE` (or `NEBIUS_SA_PRIVATE_KEY`) | auth mode (b): service account |
| `NEBIUS_CLI` | path to the CLI binary if not on PATH or in `~/.nebius/bin` |
| `NEBIUS_DEFAULT_PLATFORM` / `NEBIUS_DEFAULT_PRESET` | code defaults `gpu-l40s-a` / `1gpu-8vcpu-32gb`; the root `.env.example` sets the team default `gpu-l40s-d` / `4gpu-128vcpu-768gb` (eu-north1) |
| `NEBIUS_DEFAULT_IMAGE` | default `pytorch/pytorch:2.7.1-cuda12.8-cudnn9-runtime` |
| `NEBIUS_DEFAULT_TIMEOUT` / `NEBIUS_DEFAULT_DISK_GIB` | defaults `2h` / `250` |
| `NEBIUS_OUTPUT_VOLUME` | bucket name/ID or `s3://bucket` mounted at `/outputs` for every training job |
| `PORT` | HTTP port, default 8000 |

`doctor` authenticates, prints who you are, lists subnets, and tells you the
`NEBIUS_SUBNET_ID` to paste into `.env` if the project has one subnet.

### d. Auth: pick one

| Mode | When | Setup |
|---|---|---|
| CLI profile (default) | laptop, hackathon | nothing beyond `nebius profile create`; the backend shells out to `nebius iam get-access-token` |
| `NEBIUS_ACCESS_TOKEN` | CI, a teammate's machine, 12 h | `nebius iam get-access-token` and paste into `.env` |
| Service account | deployed backend | see below |

Service account (non-interactive, long-lived):

```bash
export SA_ID=$(nebius iam service-account create --name backend-trainer --format jsonpath='{.metadata.id}')
# give it editor rights: Administration → IAM → Groups → editors → add member $SA_ID  (or nebius iam group-membership create ...)
openssl genrsa -out app/backend/secrets/nebius-sa.pem 4096
openssl rsa -in app/backend/secrets/nebius-sa.pem -pubout -out /tmp/nebius-sa.pub.pem
nebius iam auth-public-key create --account-service-account-id $SA_ID --data "$(cat /tmp/nebius-sa.pub.pem)"
# key ID: console → IAM → Service accounts → backend-trainer → Authorized keys
```

Then in `.env`: `NEBIUS_SA_ID`, `NEBIUS_SA_KEY_ID`, `NEBIUS_SA_PRIVATE_KEY_FILE=./secrets/nebius-sa.pem`.
`secrets/` and `*.pem` are git-ignored.

## 2. Run it

### Smoke test (Nebius's own quick start: nvidia-smi on 1× L40S, ~$0.10)

```bash
cd app/backend
npm run train -- smoke
```

Submits, polls every 15 s through `PROVISIONING → STARTING → IMAGE_PULLING →
RUNNING → COMPLETED`, then prints the last 100 log lines (the `nvidia-smi`
table). Takes 3–6 minutes end to end. Exit code 0 means the whole path works.

### Train a script

```bash
npm run train -- submit \
  --name distilgpt2-run1 \
  --script src/features/training-jobs/examples/train.py \
  --requirements src/features/training-jobs/examples/requirements.txt \
  --platform gpu-l40s-a --preset 1gpu-8vcpu-32gb --timeout 1h \
  --env HF_TOKEN=hf_xxx \
  --wait \
  -- --epochs 1 --max-steps 50
```

What happens: the script and requirements are **injected** into the container
at `/workspace/` (limit 64 KiB per file), a generated `run.sh` runs
`pip install -r requirements.txt && python train.py …`, and the job is created.
Without `--wait` the command returns immediately with the job ID.

| Flag | Meaning |
|---|---|
| `--script`, `--requirements` | local files to inject |
| `--platform`, `--preset` | see `npm run train -- catalog` |
| `--timeout` | `1h`…`168h`; the job is killed and billed up to this |
| `--image` | default `pytorch/pytorch:2.7.1-cuda12.8-cudnn9-runtime` |
| `--env K=V` (repeatable) | env vars for the container |
| `--volume SRC:/path[:ro]` (repeatable) | mount a Nebius bucket/filesystem or `s3://bucket` |
| `--output BUCKET` | mount at `/outputs` and set `NEBIUS_OUTPUT_DIR` (or `NEBIUS_OUTPUT_VOLUME` in `.env`) |
| `--preemptible` | cheaper VM that can be killed; only for restartable training |
| `--dry-run` | validate with Nebius without creating anything |
| `-- …` | everything after `--` goes to the script's `sys.argv` |

### Or submit a JSON spec

```bash
npm run train -- submit-spec src/features/training-jobs/examples/finetune-distilgpt2.json --wait
npm run train -- submit-spec src/features/training-jobs/examples/custom-image.json
```

### Track / stop

```bash
npm run train -- list
npm run train -- status <job_id>          # add --raw for the full resource
npm run train -- logs <job_id> --follow   # CLI only: Nebius has no logs REST endpoint
npm run train -- wait <job_id>
npm run train -- cancel <job_id>
npm run train -- delete <job_id>          # removes it from the list; resources are already freed
```

### HTTP API (`npm run dev`, port 8000)

| Method | Path | Body / query |
|---|---|---|
| GET | `/api/training/catalog` | platforms, presets, $/GPU-h |
| GET | `/api/training/estimate?platform=&preset=&timeout=2h` | worst-case cost |
| GET | `/api/training/whoami` | auth + project + subnets |
| POST | `/api/training/jobs` | raw job `{name,image,command,args,...}` **or** training job `{name, script, requirements, scriptArgs, env, volumes, platform, preset, timeout}` |
| POST | `/api/training/jobs/dry-run` | same body; validates only |
| GET | `/api/training/jobs` | `?pageSize=&pageToken=` |
| GET | `/api/training/jobs/:id` | `?raw=1` for the full resource |
| GET | `/api/training/jobs/:id/logs` | `?tail=200` (needs the CLI on the server) |
| POST | `/api/training/jobs/:id/cancel` | |
| DELETE | `/api/training/jobs/:id` | |

```bash
curl -s localhost:8000/api/training/jobs -H 'content-type: application/json' -d '{
  "name": "api-run-1",
  "script": "import torch; print(torch.cuda.get_device_name(0))",
  "platform": "gpu-l40s-a", "preset": "1gpu-8vcpu-32gb", "timeout": "1h"
}'
```

## 3. Getting data in and models out

- **Small code/config (≤ 64 KiB each):** inject it (`--script`, `--requirements`, `injectedFiles`).
- **Datasets, checkpoints, outputs:** create an Object Storage bucket in the console
  (**Storage → Object Storage → Create bucket**) and mount it: `--volume my-bucket:/data`
  or `--output my-bucket`. The container disk is thrown away when the job ends.
- **Hugging Face Hub:** pass `--env HF_TOKEN=…` and `push_to_hub` from the script.
- **Private images:** `registry: {username, password}` in the JSON spec.

## 4. Budget: what $600 buys (on-demand, Sept 2026 list prices)

| Platform | Preset | $/h | GPU-hours for $600 |
|---|---|---|---|
| gpu-l40s-a | 1gpu-8vcpu-32gb | 1.55 | ~385 |
| gpu-l40s-d | 1gpu-16vcpu-96gb | 1.82 | ~330 |
| gpu-h100-sxm | 1gpu-16vcpu-200gb | 3.85 | ~155 |
| gpu-h200-sxm | 1gpu-16vcpu-200gb | 4.50 | ~133 |
| gpu-l40s-d | 4gpu-128vcpu-768gb (team default) | 7.28 | ~82 node-hours |
| gpu-h100-sxm | 8gpu-128vcpu-1600gb | 30.80 | ~19 |

Rules of thumb: L40S (48 GB) is fine for ≤ 7B-parameter LoRA/QLoRA and any
small model; go H100/H200 for full fine-tunes or long contexts. **Always set
`--timeout` to what the run should take plus margin**, because a hung job
bills until the timeout. `estimate` prints the worst case before submit.
Also budget for provisioning time (a few minutes per job) and any bucket storage.

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| `NEBIUS_PROJECT_ID is not set` | `cp .env.example .env` at the repo root and `ln -s ../../.env app/backend/.env` (section 1c) |
| `nebius iam get-access-token` returns nothing | `nebius profile create …`, log in in the browser |
| 403 on create | the account/service account lacks editor on the project |
| `ERROR` / `NotEnoughResources` | GPU quota is 0 or capacity is short: raise the quota or try another platform/preset. Check the **region** first: platforms are per project/region. Our tenant's `default-project-eu-west1` (the console default) only offers `gpu-h200-sxm`, and every 8-GPU H200 request there timed out. `default-project-us-central1` (`project-u00re9y9kc00bwpa7d9ftt`, team default) has B200, H200, RTX6000; `default-project-eu-north1` (`project-e00g0c62pr00fj32s0h4gj`) has H100, H200, L40S-a and L40S-d. Single-GPU jobs schedule in both within 2–3 min. **Team default is `gpu-l40s-d` / `4gpu-128vcpu-768gb` in eu-north1**, the only multi-GPU node that scheduled on 12 Sep 2026. 8× nodes (H200 in three regions; H100, B200, RTX 6000 pending for 10+ min) stall with the VM STOPPED in PROVISIONING, then error. GB300 is rejected outright: its preset needs an NVLInstanceGroup, not available via jobs. Never request the 8-GPU preset for a 0.5B/3B fine-tune |
| `FAILED` / `TimeoutExceeded` | raise `--timeout` |
| `FAILED` right after `RUNNING` | `logs <id>`; usually a pip install or script error |
| Preset rejected | run `nebius compute platform list` and use the IDs it prints; the catalog in `spec.js` is a convenience, not the source of truth |
| Logs endpoint returns 501 | install the CLI where the backend runs, or read logs in the console |
