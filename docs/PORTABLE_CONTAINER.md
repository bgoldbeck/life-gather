# Portable container

One image runs self-hosted (Docker Compose on any Linux server, the default) and
on hosted container platforms. Nothing here changes the default Compose setup:
every option below is off or keeps today's behaviour unless you set it.

## S3-compatible file storage in the image

The published image now includes the `s3` extra (boto3), so
`LIFEGATHER_STORAGE_BACKEND=s3` works without rebuilding. See
[file storage](FILE_STORAGE.md) for the bucket settings.

## Vault keys from the environment

The vault key encrypts stored AI keys and Gmail tokens. Besides
`LIFEGATHER_VAULT_KEY_FILE`, keys can come from an environment variable, which is
how container platforms pass secrets:

```
LIFEGATHER_VAULT_KEYS=2026-10:BASE64KEY
```

Each entry is `id:base64key`: an ID of 1–32 letters, digits, `.`, `_` or `-`, and
a standard base64 32-byte key (`openssl rand -base64 32`). To move an existing
key file into the environment, use `base64 -w0 vault.key` as the key.

**Rotation.** List the new key first and the old key after it:

```
LIFEGATHER_VAULT_KEYS=2026-11:NEWKEY,2026-10:OLDKEY
```

On the next start (or `python -m lifegather.migrate`), every stored credential
is re-encrypted under the first key in one transaction and the database records
the new key. Then remove the old entry. With both `LIFEGATHER_VAULT_KEYS` and
`LIFEGATHER_VAULT_KEY_FILE` set, the file counts as previous key `file`, which
moves a file-based installation to an environment key. An instance still running
with the old key refuses to save credentials after the rotation (it answers 503)
until it restarts with the new list. Back up the new key before removing the old.

Recovery bundles keep carrying the key the database uses as `vault.key`.

## Startup tasks and the migrate job

At startup the app imports a legacy SQLite file once, upgrades the database
schema, moves inline originals to file storage and finishes any vault rotation.
These tasks hold a PostgreSQL advisory lock, so several instances starting at
once take turns and the later ones find the work done.

Deployments that prefer a separate step can run the same tasks once and exit:

```
docker compose run --rm backend python -m lifegather.migrate
```

and start the app with `LIFEGATHER_MIGRATE_ON_START=false`. The app then refuses
to start while the schema is behind, instead of upgrading it. Self-hosting needs
neither: the default is `true`.

## Health checks

- `GET /health` is liveness: the process answers. Docker's health check uses it.
- `GET /health/ready` is readiness: 200 `{"status":"ready"}` once startup has
  finished and the database answers at this release's schema, otherwise 503
  `{"status":"not_ready"}`. Use it for load balancers and rolling deploys.

Neither reports account, key or provider details.

## Behind a reverse proxy

By default the app ignores `X-Forwarded-For` and `X-Forwarded-Proto`, so login
rate limits see the proxy's address. To use the real client address, list the
proxies that connect to the app:

```
LIFEGATHER_TRUSTED_PROXIES=172.18.0.0/16
```

Entries are IP addresses or CIDR networks, comma-separated; `*` is not accepted.
Only requests whose direct peer is listed may set those headers. Secure cookies
still follow `LIFEGATHER_PUBLIC_URL`, which must be the public HTTPS origin.

When the proxy's own address can't be listed (for example a Cloudflare Worker
in front of a Cloudflare Container), set a shared secret instead:

```
LIFEGATHER_PROXY_SECRET=<32+ random visible characters>
```

The proxy must send it as `X-LifeGather-Proxy-Secret`, replace any copy from
the visitor, and set `X-Forwarded-For` to exactly one client address. Requests
with a missing or wrong secret, or a list of addresses, keep the connection's
own address and scheme. The secret header is removed before the app sees the
request, and the secret never goes into recovery bundles. Both settings are
empty by default, so a plain self-hosted install is unchanged.

## Background scans on sleeping containers

Platforms that stop idle containers also stop the in-process scan loop. Set
`LIFEGATHER_BACKGROUND_MODE=external` and tick from a scheduler; see
[background scans from an outside scheduler](EXTERNAL_BACKGROUND.md).

## Logs, alerts and the Operations page

Logs are JSON lines on standard error with no private content. Set
`LIFEGATHER_OPERATOR_EMAILS` to your sign-in email to get the Operations page,
and `LIFEGATHER_ALERT_WEBHOOK_URL` (or SMTP) for error alerts; see
[operations](OPERATIONS.md).
