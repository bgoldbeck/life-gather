import { describe, expect, it } from "vitest";
import settings from "../container-settings.json";
import {
  ConfigError,
  containerEnv,
  forwardRequest,
  instanceName,
  isInternalPath,
  tickRequest,
} from "../src/edge";

const complete = {
  PUBLIC_URL: "https://lifegather-test.example.workers.dev",
  DATABASE_URL: "postgresql://user:pw@db.example/lifegather?sslmode=require",
  VAULT_KEYS: "2026-10:a2V5",
  JOB_TICK_TOKEN: "t".repeat(64),
  R2_BUCKET: "lifegather-test-files",
  R2_ENDPOINT_URL: "https://account.r2.cloudflarestorage.com",
  R2_ACCESS_KEY_ID: "id",
  R2_SECRET_ACCESS_KEY: "secret",
};

describe("containerEnv", () => {
  it("maps settings and fixes the hosted modes", () => {
    const env = containerEnv({ ...complete, GOOGLE_CLIENT_ID: " client ", SMTP_HOST: "" });
    expect(env.LIFEGATHER_BACKGROUND_MODE).toBe("external");
    expect(env.LIFEGATHER_STORAGE_BACKEND).toBe("s3");
    expect(env.LIFEGATHER_S3_BUCKET).toBe("lifegather-test-files");
    expect(env.LIFEGATHER_GOOGLE_CLIENT_ID).toBe("client");
    expect(env).not.toHaveProperty("LIFEGATHER_SMTP_HOST");
    expect(env).not.toHaveProperty("LIFEGATHER_TRUSTED_PROXIES");
  });

  it("names every missing required setting without values", () => {
    try {
      containerEnv({ PUBLIC_URL: complete.PUBLIC_URL, VAULT_KEYS: " " });
      expect.unreachable();
    } catch (error) {
      expect(error).toBeInstanceOf(ConfigError);
      const missing = (error as ConfigError).missing;
      expect(missing).toContain("VAULT_KEYS");
      expect(missing).toContain("DATABASE_URL");
      expect(missing).not.toContain("PUBLIC_URL");
      expect((error as Error).message).not.toContain("https://");
    }
  });

  it("never lets a Worker setting override a fixed one", () => {
    const fixed = Object.keys(settings.fixed);
    const mapped = [...Object.keys(settings.required), ...Object.keys(settings.optional)];
    expect(mapped.filter((name) => fixed.includes(name))).toEqual([]);
  });
});

describe("isInternalPath", () => {
  it.each(["/internal", "/internal/jobs/tick", "/INTERNAL/jobs/tick"])("blocks %s", (path) => {
    expect(isInternalPath(path)).toBe(true);
  });
  it.each(["/", "/api/assets", "/internalize", "/auth/google/callback"])("allows %s", (path) => {
    expect(isInternalPath(path)).toBe(false);
  });
});

describe("forwardRequest", () => {
  it("replaces forwarded headers with Cloudflare's view of the visitor", async () => {
    const original = new Request("https://site.example/api/chat", {
      method: "POST",
      body: "hello",
      headers: {
        "cf-connecting-ip": "203.0.113.7",
        "x-forwarded-for": "10.0.0.1, 198.51.100.2",
        forwarded: "for=10.0.0.1",
        "x-forwarded-host": "evil.example",
        "cf-access-jwt-assertion": "token",
        cookie: "session=abc",
      },
    });
    const forwarded = forwardRequest(original);
    expect(forwarded.headers.get("x-forwarded-for")).toBe("203.0.113.7");
    expect(forwarded.headers.get("x-forwarded-proto")).toBe("https");
    expect(forwarded.headers.has("forwarded")).toBe(false);
    expect(forwarded.headers.has("x-forwarded-host")).toBe(false);
    expect(forwarded.headers.has("cf-access-jwt-assertion")).toBe(false);
    expect(forwarded.headers.get("cookie")).toBe("session=abc");
    expect(forwarded.method).toBe("POST");
    expect(await forwarded.text()).toBe("hello");
  });

  it("sends no client address when Cloudflare gave none", () => {
    const forwarded = forwardRequest(
      new Request("https://site.example/", { headers: { "x-forwarded-for": "1.2.3.4" } }),
    );
    expect(forwarded.headers.has("x-forwarded-for")).toBe(false);
  });
});

describe("tickRequest", () => {
  it("calls the bounded tick with the bearer token", () => {
    const request = tickRequest(complete);
    expect(request.method).toBe("POST");
    expect(new URL(request.url).pathname).toBe("/internal/jobs/tick");
    expect(new URL(request.url).searchParams.get("seconds")).toBe("50");
    expect(request.headers.get("authorization")).toBe(`Bearer ${complete.JOB_TICK_TOKEN}`);
  });

  it("refuses without a token", () => {
    expect(() => tickRequest({})).toThrow(ConfigError);
  });
});

describe("instanceName", () => {
  it("uses one instance by default", () => {
    expect(instanceName({}, () => 0.99)).toBe("app-0");
  });
  it("spreads over the pool and clamps bad sizes", () => {
    expect(instanceName({ POOL_SIZE: "3" }, () => 0.99)).toBe("app-2");
    expect(instanceName({ POOL_SIZE: "0" }, () => 0.5)).toBe("app-0");
    expect(instanceName({ POOL_SIZE: "nope" }, () => 0.5)).toBe("app-0");
    expect(instanceName({ POOL_SIZE: "500" }, () => 0.99)).toBe("app-9");
  });
});
