# Local testing account

For the easiest temporary testing experience, use [one-click test mode](TEST_MODE.md).
The command below remains available for a separate password-protected account.

The installation owner can create a private email/password account from the server terminal without Google OAuth or SMTP. There is no default password, administrator role, public provisioning endpoint, or access to other users' data.

This command requires an image containing the local-account setup feature. Updating GitHub source does not update an existing container; rebuilding/publishing the image requires separate approval.

For an image-only Compose installation, run from the repository root:

```powershell
docker compose --env-file .env -f deploy/compose.image.yaml exec backend python -m lifegather.setup_account
```

For the root source-build Compose installation:

```powershell
docker compose exec backend python -m lifegather.setup_account
```

For a standalone container, substitute its name (shown in Docker Desktop):

```powershell
docker exec -it lifegather-preview python -m lifegather.setup_account
```

Enter a display name, email address, and a password of 15–128 characters twice. Password input is hidden and never supplied as a command argument or environment variable. Use an interactive terminal; the command refuses redirected input or a terminal that cannot hide the password. Then open the app and use **Sign in with email**. No email is sent.

The server owner explicitly accepts the supplied email instead of proving mailbox control. The existing credential acceptance timestamp records that decision, not a successful verification email. Use an address you control, especially if recovery email is configured later. This is an ordinary private account, not a way to assume someone else's identity.

The command refuses an email already used by a local or Google account, even with different capitalization. It cannot link accounts, reset passwords, or replace existing credentials. Existing accounts continue to use their normal sign-in or recovery flow. Public signup, password linking and recovery still require their existing email verification. Without SMTP, forgotten-password recovery by email is unavailable; retain this password in a password manager.

The command uses the running container's `LIFEGATHER_DATABASE_URL`, the same PostgreSQL database as the app. It applies packaged migrations and writes the account and salted Argon2id password hash atomically. It creates no browser session and changes no existing private records. Preserve the data and database volumes; don't add `--volumes` when shutting down Compose.

For source development, run `uv run --locked python -m lifegather.setup_account` from `backend/`, using the same configuration and database as the development server.
