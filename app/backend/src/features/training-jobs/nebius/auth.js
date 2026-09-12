// Access tokens for the Nebius REST API. Three strategies, tried in order:
//   1. NEBIUS_ACCESS_TOKEN            static token (from `nebius iam get-access-token`, 12h)
//   2. NEBIUS_SA_ID + NEBIUS_SA_KEY_ID + private key   service-account JWT exchange
//   3. Nebius CLI                       `nebius iam get-access-token` on the active profile
// Docs: https://docs.nebius.com/rest-api/authentication
import { createSign } from 'node:crypto';
import { readFileSync, existsSync } from 'node:fs';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import os from 'node:os';
import path from 'node:path';

const execFileP = promisify(execFile);
export const TOKEN_EXCHANGE_URL = 'https://auth.eu.nebius.com/oauth2/token/exchange';

const b64url = (buf) => Buffer.from(buf).toString('base64url');

/** Build an RS256 JWT the way Nebius expects (kid header; iss == sub == service account ID). */
export function makeServiceAccountJwt({ saId, keyId, privateKeyPem, ttlSeconds = 300, now = Date.now() }) {
  if (!saId || !keyId || !privateKeyPem) throw new Error('makeServiceAccountJwt: saId, keyId and privateKeyPem are required');
  const iat = Math.floor(now / 1000);
  const header = b64url(JSON.stringify({ alg: 'RS256', typ: 'JWT', kid: keyId }));
  const payload = b64url(JSON.stringify({ iss: saId, sub: saId, iat, exp: iat + ttlSeconds }));
  const signer = createSign('RSA-SHA256');
  signer.update(`${header}.${payload}`);
  const signature = b64url(signer.sign(privateKeyPem));
  return `${header}.${payload}.${signature}`;
}

/** Exchange a service-account JWT for a bearer access token. */
export async function exchangeJwtForToken(jwt, { fetchImpl = fetch, url = TOKEN_EXCHANGE_URL } = {}) {
  const form = new URLSearchParams({
    grant_type: 'urn:ietf:params:oauth:grant-type:token-exchange',
    requested_token_type: 'urn:ietf:params:oauth:token-type:access_token',
    subject_token: jwt,
    subject_token_type: 'urn:ietf:params:oauth:token-type:jwt',
  });
  const res = await fetchImpl(url, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: form });
  const text = await res.text();
  if (!res.ok) throw new Error(`Nebius token exchange failed (${res.status}): ${text.slice(0, 500)}`);
  const data = JSON.parse(text);
  if (!data.access_token) throw new Error('Nebius token exchange returned no access_token');
  return { token: data.access_token, expiresInSeconds: Number(data.expires_in || 43200) };
}

/** Locate the nebius CLI: $NEBIUS_CLI, then PATH, then the default install dir. */
export function findNebiusCli(env = process.env) {
  if (env.NEBIUS_CLI) return env.NEBIUS_CLI;
  const home = path.join(os.homedir(), '.nebius', 'bin', 'nebius');
  for (const dir of (env.PATH || '').split(path.delimiter)) {
    const candidate = path.join(dir, 'nebius');
    if (dir && existsSync(candidate)) return candidate;
  }
  return existsSync(home) ? home : null;
}

export async function tokenFromCli(env = process.env) {
  const bin = findNebiusCli(env);
  if (!bin) throw new Error('Nebius CLI not found. Install: curl -sSL https://storage.eu-north1.nebius.cloud/cli/install.sh | bash');
  const { stdout } = await execFileP(bin, ['iam', 'get-access-token'], { env, timeout: 30_000 });
  const token = stdout.trim();
  if (!token) throw new Error('`nebius iam get-access-token` returned nothing. Run `nebius profile create` first.');
  return { token, expiresInSeconds: 11 * 3600 }; // CLI tokens last 12h; be conservative
}

function readPrivateKey(env) {
  if (env.NEBIUS_SA_PRIVATE_KEY) return env.NEBIUS_SA_PRIVATE_KEY.replace(/\\n/g, '\n');
  if (env.NEBIUS_SA_PRIVATE_KEY_FILE) return readFileSync(env.NEBIUS_SA_PRIVATE_KEY_FILE, 'utf8');
  throw new Error('Set NEBIUS_SA_PRIVATE_KEY_FILE (path to private.pem) or NEBIUS_SA_PRIVATE_KEY');
}

/** Describe which auth strategy the env selects, without doing any I/O. */
export function describeAuth(env = process.env) {
  if (env.NEBIUS_ACCESS_TOKEN) return 'static token (NEBIUS_ACCESS_TOKEN)';
  if (env.NEBIUS_SA_ID) return `service account ${env.NEBIUS_SA_ID}`;
  return 'nebius CLI profile';
}

/**
 * Returns a function () => Promise<string> that yields a valid bearer token,
 * caching it until shortly before expiry.
 */
export function createTokenProvider(env = process.env, { fetchImpl = fetch, skewSeconds = 120 } = {}) {
  let cached = null; // { token, expiresAt }
  return async function getToken() {
    if (cached && Date.now() < cached.expiresAt) return cached.token;
    let result;
    if (env.NEBIUS_ACCESS_TOKEN) {
      result = { token: env.NEBIUS_ACCESS_TOKEN.trim(), expiresInSeconds: 3600 };
    } else if (env.NEBIUS_SA_ID) {
      if (!env.NEBIUS_SA_KEY_ID) throw new Error('NEBIUS_SA_KEY_ID is required with NEBIUS_SA_ID');
      const jwt = makeServiceAccountJwt({ saId: env.NEBIUS_SA_ID, keyId: env.NEBIUS_SA_KEY_ID, privateKeyPem: readPrivateKey(env) });
      result = await exchangeJwtForToken(jwt, { fetchImpl });
    } else {
      result = await tokenFromCli(env);
    }
    cached = { token: result.token, expiresAt: Date.now() + Math.max(60, result.expiresInSeconds - skewSeconds) * 1000 };
    return cached.token;
  };
}
