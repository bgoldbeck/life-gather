// Request rules for the test-site Worker. Kept free of Cloudflare runtime
// imports so the unit tests run in plain Node.
import settings from "../container-settings.json";

export const APP_PORT = 8787;
export const TICK_SECONDS = 50;
export const TICK_INSTANCE = "app-0";

export type Config = Record<string, string | undefined>;

export class ConfigError extends Error {
  constructor(readonly missing: string[]) {
    super(`Missing test-site settings: ${missing.join(", ")}`);
  }
}

/** Environment for the LifeGather container, built from Worker settings. */
export function containerEnv(config: Config): Record<string, string> {
  const result: Record<string, string> = { ...settings.fixed };
  const missing: string[] = [];
  for (const [target, source] of Object.entries(settings.required)) {
    const value = config[source]?.trim();
    if (value) result[target] = value;
    else missing.push(source);
  }
  if (missing.length) throw new ConfigError(missing);
  for (const [target, source] of Object.entries(settings.optional)) {
    const value = config[source]?.trim();
    if (value) result[target] = value;
  }
  return result;
}

/** Paths only the Worker itself may call, never a visitor. */
export function isInternalPath(pathname: string): boolean {
  const path = pathname.toLowerCase();
  return path === "/internal" || path.startsWith("/internal/");
}

const DROPPED_HEADERS = [
  "forwarded",
  "x-forwarded-for",
  "x-forwarded-proto",
  "x-forwarded-host",
  "x-real-ip",
  "cf-access-jwt-assertion",
];

/** Copy a visitor's request with forwarded headers set only from Cloudflare's view. */
export function forwardRequest(request: Request): Request {
  const headers = new Headers(request.headers);
  for (const name of DROPPED_HEADERS) headers.delete(name);
  const client = request.headers.get("cf-connecting-ip");
  if (client) headers.set("x-forwarded-for", client);
  headers.set("x-forwarded-proto", "https");
  return new Request(request, { headers });
}

/** The scheduler's call to run due scans for a bounded time. */
export function tickRequest(config: Config): Request {
  const token = config.JOB_TICK_TOKEN?.trim();
  if (!token) throw new ConfigError(["JOB_TICK_TOKEN"]);
  return new Request(`http://localhost/internal/jobs/tick?seconds=${TICK_SECONDS}`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}` },
  });
}

/** Name of the container instance that serves a request. */
export function instanceName(config: Config, random: () => number = Math.random): string {
  const size = Math.min(Math.max(Number.parseInt(config.POOL_SIZE ?? "1", 10) || 1, 1), 10);
  return `app-${Math.floor(random() * size) % size}`;
}

export function plainResponse(status: number, message: string): Response {
  return new Response(`${message}\n`, {
    status,
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}
