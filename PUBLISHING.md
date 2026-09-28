# Publishing BreakBlocks Launcher

## Private test packages

Before creating a public release, the **Build private test packages** workflow
can be started manually from GitHub Actions. It runs the formatting and test
suite and creates an unsigned Windows ZIP, Ubuntu `.deb`, and portable Steam
Deck archive as private workflow artifacts retained for 14 days. These files
are for testing only: the Windows executable is deliberately marked
`UNSIGNED`, may trigger Windows security warnings, and is never published as a
GitHub Release.

The public release process below remains fail-closed and still requires the
trusted Windows signing certificate.

Releases are built by `.github/workflows/release.yml`. Use `v<version>-alpha`
for an Alpha prerelease and `v<version>` for a Stable full release. The workflow
tests both platforms, creates PyInstaller one-folder packages, signs and
verifies the Windows executable, builds the Ubuntu package, generates the
matching update manifest, and publishes all files to one GitHub Release.

## One-time repository setup

1. Obtain a publicly trusted Windows code-signing certificate for the legal
   publisher. Do not use a self-signed certificate for public releases.
2. Export the certificate and private key as a password-protected PFX file.
3. Add `WINDOWS_SIGNING_CERT_BASE64` as a GitHub Actions secret containing the
   base64-encoded PFX bytes.
4. Add `WINDOWS_SIGNING_CERT_PASSWORD` as a GitHub Actions secret.
5. Protect the release environment and restrict who can create release tags.

## Legal release gate

Before creating a public tag, complete every unresolved item in
`LEGAL-RELEASE-CHECKLIST.md`. In particular, confirm the legal operator,
monitored email address, governing jurisdiction, and code-signing publisher.
The embedded web chat is restricted to the fixed BreakBlocks URL and keeps its
website session in an isolated local profile, but a stable public release still
requires the site's operator, cookie/session retention, moderation, and age
policies to be published. The tested URL and storage behaviour are recorded in
the launcher and privacy notice.

The release jobs collect licence files from the exact Python dependencies and
runtime used for each platform. A missing or mismatched dependency licence is a
release failure, not a warning.

The release workflow fails closed when signing credentials are absent or when
Windows reports an invalid Authenticode signature. Signing establishes the
publisher identity; Microsoft Defender SmartScreen reputation is managed by
Microsoft and may still take time to build for a new certificate.

## Publish a release

1. Update `APP_VERSION_NUMBER` in `app_config.py` and the version in
   `pyproject.toml`. Set `APP_RELEASE_STAGE` to `Alpha` or `Stable`.
2. Update the release notes and run every test locally.
3. Confirm that `LICENSE`, `PRIVACY.md`, `TERMS.md`,
   `THIRD-PARTY-NOTICES.md`, and the public website policies describe the same
   release.
4. Commit the exact source to publish.
5. Create and push `v<version>-alpha` for an Alpha prerelease, or `v<version>`
   for a Stable full release.

The generated `breakblocks-update.json` contains separate entries for the
Windows ZIP, Ubuntu `.deb`, and portable Linux/Steam Deck archive, including
their HTTPS URLs, sizes, and SHA-256 digests. The launcher does not install a
package unless its attached release asset, byte size, and digest all match.
Windows and portable Linux replace their installation after the launcher exits
and then restart. Ubuntu uses the normal administrator approval prompt to
install the verified `.deb`, then restarts. Stable is the launcher default and
ignores GitHub prereleases; users who select Alpha receive both Stable and Alpha
updates. The legacy `linux-x86_64` key remains mapped to the Steam Deck archive
so portable installations on 0.9.4 or earlier can upgrade into this layout.
