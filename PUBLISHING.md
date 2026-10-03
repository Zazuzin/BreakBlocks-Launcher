# Publishing BreakBlocks Launcher

## Private test packages

Before preparing a release, the **Build private test packages** workflow
can be started manually from GitHub Actions. It runs the formatting and test
suite and creates an unsigned Windows ZIP, Ubuntu `.deb`, and portable Steam
Deck archive as private workflow artifacts retained for 14 days. These files
are for testing only: the Windows executable is unsigned, may trigger Windows
security warnings, and is never published as a GitHub Release by this workflow.

The release process below does not require a signing certificate. Review and
publish the resulting draft release separately.

Releases are built by `.github/workflows/release.yml`. Use `v<version>-alpha`
for an Alpha prerelease and `v<version>` for a Stable full release. The workflow
tests both platforms, creates PyInstaller one-folder packages, verifies that
the Windows executable is unsigned, builds the Ubuntu package, generates the
matching update manifest, and attaches all files to a draft GitHub Release.

## One-time repository setup

Protect release tags and restrict who can publish GitHub Releases. There are no
Windows certificate secrets to configure. Windows packages have no verified
publisher identity and may be warned about or blocked by Windows or browsers.

## Legal release gate

Before creating a public tag, complete every unresolved item in
`LEGAL-RELEASE-CHECKLIST.md`. In particular, confirm the legal operator,
monitored email address, and governing jurisdiction.
The embedded web chat is restricted to the fixed BreakBlocks URL and keeps its
website session in an isolated local profile, but a stable public release still
requires the site's operator, cookie/session retention, moderation, and age
policies to be published. The tested URL and storage behaviour are recorded in
the launcher and privacy notice.

The release jobs collect licence files from the exact Python dependencies and
runtime used for each platform. A missing or mismatched dependency licence is a
release failure, not a warning.

The release workflow verifies that the Windows executable is unsigned and
creates a draft with that fact in its notes. The draft must be inspected and
published manually. Do not tell users to turn off browser or Windows security
features to run the launcher.

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
6. Inspect the draft assets, source archive, update manifest, checksums, and
   release notes. Publish the draft only after the release checklist is done.

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
