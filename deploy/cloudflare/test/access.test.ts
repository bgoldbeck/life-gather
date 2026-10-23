import { beforeEach, describe, expect, it } from "vitest";
import { accessConfig, clearAccessKeyCache, verifyAccessToken } from "../src/access";

const config = { teamDomain: "lisa.cloudflareaccess.com", audience: "aud-tag" };
const now = Date.UTC(2026, 9, 23, 12, 0, 0);
const nowS = now / 1000;

function encode(value: object | Uint8Array): string {
  const bytes =
    value instanceof Uint8Array ? value : new TextEncoder().encode(JSON.stringify(value));
  return Buffer.from(bytes).toString("base64url");
}

async function keyPair(): Promise<CryptoKeyPair> {
  return (await crypto.subtle.generateKey(
    {
      name: "RSASSA-PKCS1-v1_5",
      modulusLength: 2048,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: "SHA-256",
    },
    true,
    ["sign", "verify"],
  )) as CryptoKeyPair;
}

const pair = await keyPair();
const other = await keyPair();
const publicJwk = {
  ...((await crypto.subtle.exportKey("jwk", pair.publicKey)) as JsonWebKey),
  kid: "k1",
};

async function token(
  claims: Record<string, unknown>,
  options: { kid?: string; alg?: string; key?: CryptoKey } = {},
) {
  const header = encode({ alg: options.alg ?? "RS256", kid: options.kid ?? "k1", typ: "JWT" });
  const payload = encode({
    iss: "https://lisa.cloudflareaccess.com",
    aud: ["aud-tag"],
    exp: nowS + 600,
    nbf: nowS - 10,
    ...claims,
  });
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    options.key ?? pair.privateKey,
    new TextEncoder().encode(`${header}.${payload}`),
  );
  return `${header}.${payload}.${encode(new Uint8Array(signature))}`;
}

let fetches: string[] = [];
const fetchKeys = async (url: string) => {
  fetches.push(url);
  return { keys: [publicJwk] };
};
const verify = (value: string | null) => verifyAccessToken(value, config, { now, fetchKeys });

beforeEach(() => {
  clearAccessKeyCache();
  fetches = [];
});

describe("accessConfig", () => {
  it("needs both values", () => {
    expect(accessConfig("lisa.cloudflareaccess.com", "")).toBeNull();
    expect(accessConfig(undefined, "aud")).toBeNull();
  });
  it("normalizes the team domain", () => {
    expect(accessConfig("https://Lisa.cloudflareaccess.com/", " aud ")).toEqual({
      teamDomain: "lisa.cloudflareaccess.com",
      audience: "aud",
    });
  });
  it("refuses other hosts for the signing keys", () => {
    expect(() => accessConfig("evil.example", "aud")).toThrow();
  });
});

describe("verifyAccessToken", () => {
  it("accepts a valid token and reads keys from the team domain", async () => {
    expect(await verify(await token({}))).toBe(true);
    expect(fetches).toEqual(["https://lisa.cloudflareaccess.com/cdn-cgi/access/certs"]);
  });

  it("accepts a single string audience", async () => {
    expect(await verify(await token({ aud: "aud-tag" }))).toBe(true);
  });

  it("caches the keys", async () => {
    await verify(await token({}));
    await verify(await token({}));
    expect(fetches).toHaveLength(1);
  });

  it.each([
    ["missing", null],
    ["garbage", "a.b.c"],
    ["two parts", "a.b"],
  ])("refuses a %s token", async (_label, value) => {
    expect(await verify(value)).toBe(false);
  });

  it("refuses another application's audience", async () => {
    expect(await verify(await token({ aud: ["other"] }))).toBe(false);
  });

  it("refuses another issuer", async () => {
    expect(await verify(await token({ iss: "https://evil.cloudflareaccess.com" }))).toBe(false);
  });

  it("refuses expired and not-yet-valid tokens", async () => {
    expect(await verify(await token({ exp: nowS - 120 }))).toBe(false);
    expect(await verify(await token({ nbf: nowS + 600 }))).toBe(false);
    expect(await verify(await token({ exp: undefined }))).toBe(false);
  });

  it("refuses a token signed by another key", async () => {
    expect(await verify(await token({}, { key: other.privateKey }))).toBe(false);
  });

  it("refuses tampered claims", async () => {
    const [header, , signature] = (await token({})).split(".");
    const payload = encode({
      iss: "https://lisa.cloudflareaccess.com",
      aud: ["aud-tag"],
      exp: nowS + 99999,
      email: "someone@example.com",
    });
    expect(await verify(`${header}.${payload}.${signature}`)).toBe(false);
  });

  it("refuses other algorithms", async () => {
    expect(await verify(await token({}, { alg: "none" }))).toBe(false);
    expect(await verify(await token({}, { alg: "HS256" }))).toBe(false);
  });

  it("looks for a rotated key once a minute at most", async () => {
    await verify(await token({}));
    expect(await verify(await token({}, { kid: "unknown" }))).toBe(false);
    expect(await verify(await token({}, { kid: "unknown" }))).toBe(false);
    expect(fetches).toHaveLength(1);
    expect(
      await verifyAccessToken(await token({}, { kid: "unknown" }), config, {
        now: now + 61_000,
        fetchKeys,
      }),
    ).toBe(false);
    expect(fetches).toHaveLength(2);
  });
});
