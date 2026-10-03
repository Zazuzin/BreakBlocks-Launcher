# Final source sweep

Reviewed: 28 September 2026

This is a historical review of the 0.9.6 Alpha source snapshot. Current
versions also include a Windows game-chat overlay and have renamed the launcher
modules and GitHub repository. See CHANGELOG.md for later changes.

## Checks completed

- All 101 automated regression checks pass.
- Every Python file compiles under Python 3.12.
- No private keys, passwords, client secrets, access tokens, build output, user
  data, logs, or Python cache files are included.
- Product wording in that snapshot used **BreakBlocks Launcher**. Later builds
  renamed the internal launcher modules and repository.
- The Microsoft OAuth client ID is a public application identifier, not a
  secret. No client secret is used by the desktop device-code flow.
- Linux source retains the tested system-Tk, permission, Microsoft sign-in,
  font, and desktop-icon fixes.
- Chat opens only the fixed `https://irc.breakblocks.com/#/connect` page in an
  embedded Chromium surface. Its isolated local browser profile persists the
  website session across launcher restarts, while authentication, channels,
  moderation, and chat behaviour remain controlled by BreakBlocks.com.
- Obsolete launcher-managed IRC passwords and preferences are removed during
  settings migration. The launcher does not read or store BreakBlocks login
  credentials itself.
- Source and packaging include GPL-3.0-only terms and the bundled third-party
  licence notices, including the Inter font licence.

## Publication blockers

The unresolved operator, contact, jurisdiction, web-chat policy, and Windows
signing items remain listed in `LEGAL-RELEASE-CHECKLIST.md`. They do not stop
private testing or code review, but they should be resolved before a stable
public release.
