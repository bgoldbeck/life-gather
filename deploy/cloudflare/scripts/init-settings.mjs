// Creates test-site.env from the example with a new vault key, tick token and
// proxy secret.
// Refuses to replace an existing file, so saved secrets are never lost.
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const here = (name) => fileURLToPath(new URL(`../${name}`, import.meta.url));
const target = here("test-site.env");
if (existsSync(target)) {
  console.error("test-site.env already exists; edit it instead.");
  process.exit(1);
}
const month = new Date().toISOString().slice(0, 7);
const text = readFileSync(here("test-site.env.example"), "utf8")
  .replace(/^VAULT_KEYS=$/m, `VAULT_KEYS=test-${month}:${randomBytes(32).toString("base64")}`)
  .replace(/^JOB_TICK_TOKEN=$/m, `JOB_TICK_TOKEN=${randomBytes(32).toString("hex")}`)
  .replace(/^PROXY_SECRET=$/m, `PROXY_SECRET=${randomBytes(32).toString("hex")}`);
writeFileSync(target, text, { mode: 0o600, flag: "wx" });
console.log("Created test-site.env with a new vault key, tick token and proxy secret.");
console.log("Keep a copy of VAULT_KEYS in your password manager.");
