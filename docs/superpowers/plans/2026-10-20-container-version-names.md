# Container version visibility

User addition during asset-types release: display the actually running version in
Docker's container Name column. Keep the same v0.59.0 release deliberately bundled.

- The existing local preview was inspected at v0.58.0 / revision 2229dc1 and renamed
  to lifegather-preview-v0.58.0 without restart or data change.
- Test and update Start-Test-Login.ps1 to recognize legacy/versioned preview names,
  reject multiple previews, preserve existing storage/configuration protections,
  pull before stopping, validate the pulled image's OCI version and immutable ID,
  then launch that exact image as lifegather-preview-v<version>.
- Do not execute the recreate launcher or redeploy a running instance. Verify with
  offline fixtures for legacy/new names, invalid metadata, multiple matches and
  failed downloads. Compose project/volume names stay stable.
- Commit the tested launcher separately, then include it in the authorized source
  PR and local image publication; no additional automatic deployment is implied.

Offline verification passed all eight launcher cases and the three existing release
script suites. The actual renamed preview remained healthy on its original image.
