# Source review notes

Reviewed: 4 October 2026. Source version: **0.9.30 Alpha**.

## Source contents

- Product labels, package names and repository links use BreakBlocks Launcher.
- Historical data-directory names are confined to the compatibility table in
  `launcher_paths.py`. Existing accounts, instances, chat sessions and cached
  profile pictures continue to migrate from older installations.
- Source archives contain tracked project files only. They exclude account data,
  browser profiles, installed games, logs, Python caches, virtual environments,
  Git history and build output.
- The public Microsoft application identifier remains in the source because it
  is required by the desktop device-code sign-in flow. No client secret is used.
- GPL terms, project credits and dependency/font notices are retained.

## Build and test paths

- The Windows build script checks formatting, runs the Windows regression suite,
  collects dependency licences and packages the launcher. The test and release
  workflows call this same script.
- The Linux build runs all test files. The X11 focus check additionally runs
  under Xvfb in the test workflow.
- Ubuntu uses system Python and Tk with bundled application dependencies. The
  portable Linux / Steam Deck build uses PyInstaller and includes the fonts.
- The source-review entry points are listed in `SOURCE-REVIEW.md`.

## Remaining release decisions

Operator/contact details and website-policy confirmations are recorded in
`LEGAL-RELEASE-CHECKLIST.md` and `WEBSITE-LEGAL-CHANGES.md`. These source archives
are for review and do not create or publish a stable release.
