// Second lock behind Cloudflare Access: the Worker serves only requests that
// carry a valid Access token for this application, even if the Access policy
// is later removed or the hostname changes.

export type AccessConfig = { teamDomain: string; audience: string };

type Jwk = JsonWebKey & { kid?: string };
type FetchKeys = (url: string) => Promise<{ keys: Jwk[] }>;

const KEY_CACHE_MS = 60 * 60 * 1000;
const KEY_REFRESH_MS = 60 * 1000;
const CLOCK_SKEW_S = 60;

let cached: { url: string; at: number; keys: Jwk[] } | null = null;

export function accessConfig(teamDomain?: string, audience?: string): AccessConfig | null {
  const team = teamDomain?.trim().replace(/^https:\/\//, "").replace(/\/+$/, "");
  const aud = audience?.trim();
  if (!team || !aud) return null;
  if (!/^[a-z0-9-]+\.cloudflareaccess\.com$/i.test(team)) {
    throw new Error("ACCESS_TEAM_DOMAIN must look like <team>.cloudflareaccess.com");
  }
  return { teamDomain: team.toLowerCase(), audience: aud };
}

function decodeSegment(segment: string): Uint8Array {
  const base64 = segment.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

function decodeJson(segment: string): Record<string, unknown> {
  const value: unknown = JSON.parse(new TextDecoder().decode(decodeSegment(segment)));
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("not an object");
  }
  return value as Record<string, unknown>;
}

async function defaultFetchKeys(url: string): Promise<{ keys: Jwk[] }> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Access keys answered ${response.status}`);
  return (await response.json()) as { keys: Jwk[] };
}

async function signingKeys(url: string, now: number, fetchKeys: FetchKeys, refresh: boolean) {
  // A forced refresh still waits a minute, so unknown key IDs cannot make
  // every request fetch the keys again.
  const maxAge = refresh ? KEY_REFRESH_MS : KEY_CACHE_MS;
  if (cached && cached.url === url && now - cached.at < maxAge) {
    return cached.keys;
  }
  const { keys } = await fetchKeys(url);
  cached = { url, at: now, keys: Array.isArray(keys) ? keys : [] };
  return cached.keys;
}

/** True only for an unexpired RS256 Access token issued for this application. */
export async function verifyAccessToken(
  token: string | null,
  config: AccessConfig,
  options: { now?: number; fetchKeys?: FetchKeys } = {},
): Promise<boolean> {
  if (!token) return false;
  const parts = token.split(".");
  if (parts.length !== 3) return false;
  const [rawHeader, rawPayload, rawSignature] = parts as [string, string, string];
  let header: Record<string, unknown>;
  let payload: Record<string, unknown>;
  let signature: Uint8Array;
  try {
    header = decodeJson(rawHeader);
    payload = decodeJson(rawPayload);
    signature = decodeSegment(rawSignature);
  } catch {
    return false;
  }
  if (header.alg !== "RS256" || typeof header.kid !== "string") return false;

  const nowMs = options.now ?? Date.now();
  const nowS = Math.floor(nowMs / 1000);
  const issuer = `https://${config.teamDomain}`;
  const audiences = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
  if (payload.iss !== issuer) return false;
  if (!audiences.includes(config.audience)) return false;
  if (typeof payload.exp !== "number" || payload.exp + CLOCK_SKEW_S < nowS) return false;
  if (typeof payload.nbf === "number" && payload.nbf - CLOCK_SKEW_S > nowS) return false;

  const url = `${issuer}/cdn-cgi/access/certs`;
  const fetchKeys = options.fetchKeys ?? defaultFetchKeys;
  let keys = await signingKeys(url, nowMs, fetchKeys, false);
  let jwk = keys.find((key) => key.kid === header.kid);
  if (!jwk) {
    // Access rotates keys; look again once before refusing.
    keys = await signingKeys(url, nowMs, fetchKeys, true);
    jwk = keys.find((key) => key.kid === header.kid);
  }
  if (!jwk) return false;
  try {
    const key = await crypto.subtle.importKey(
      "jwk",
      { kty: jwk.kty, n: jwk.n, e: jwk.e },
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false,
      ["verify"],
    );
    return await crypto.subtle.verify(
      "RSASSA-PKCS1-v1_5",
      key,
      signature,
      new TextEncoder().encode(`${rawHeader}.${rawPayload}`),
    );
  } catch {
    return false;
  }
}

export function clearAccessKeyCache(): void {
  cached = null;
}
