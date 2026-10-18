# One-click testing login

For the standalone Docker Desktop command using `lifegather-preview` and the
`lifegather-preview-data` volume, double-click `scripts/Start-Test-Login.cmd`,
or run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Start-Test-Login.ps1`.
The script downloads the latest image before stopping the existing app, then
recreates that container with test login enabled. It preserves the named volume
and refuses unexpected storage or custom LifeGather settings. Start Docker Desktop
first. This helper uses your connection when you run it, but builds/uploads no image.
If container startup fails after recreation, the volume is still retained; correct
the reported Docker error and rerun. It does not promise a database rollback.

For local testing, explicitly enable `LIFEGATHER_TEST_LOGIN_ENABLED=true` in the
installation's ignored `.env` file, then recreate the container using an image
that includes this feature. Docker Compose forwards the setting in both example
files. It defaults to `false`; public image downloads never enable it automatically.

With test mode enabled, open LifeGather and click **Continue as test user**.
No email, password, SMTP, or Google setup is needed. A visible banner remains
on the login screen and in the app. The same dedicated test workspace is reused
after logout, container restart, and another browser's test login.

Anyone who can reach a test-enabled installation can enter this shared workspace.
Use synthetic data only, and do not store real personal data or provider keys
there. This is not an administrator account and cannot enter other users'
workspaces. Existing Google and password accounts remain separate. Sign out
before switching to the test workspace.

Set the flag back to `false` and recreate the container to disable test login.
The endpoint becomes unavailable and existing test sessions cannot authenticate
while disabled, including through MCP. Test data is retained in the durable
volume; re-enabling test mode restores access to it. Session cookies that have
not expired or been logged out can work again when test mode is re-enabled.
Disabling this flag does not log out ordinary accounts or remove any records.

The endpoint accepts only an empty JSON POST from the configured app origin,
uses the usual opaque HttpOnly session cookie, rejects account identifiers,
and shares the bounded sign-in limiter (10 attempts per connection IP/minute).
There is no schema migration or weakened password rule.

For a standalone Docker Desktop container, set the environment variable when
creating it, while retaining its existing data mount and authentication settings.
Changing a container's environment requires recreation; restarting alone does
not apply the flag. Do not remove the data volume. Publishing an image does not
update a running container automatically.
