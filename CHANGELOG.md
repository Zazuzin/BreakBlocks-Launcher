# Changelog

## 0.9.23 Alpha (Windows and Linux)

- Fixed existing launch profiles retaining old absolute paths after the launcher
  data folder moves, including the Zazu Launcher to BreakBlocks Launcher migration.
  Java, library, asset and native paths are rebased to the current data folder.
- Select Java using the current Settings value at launch. Auto can download its
  required runtime if a previously selected system Java has been removed.
- Store an absolute path for system Java instead of relying on a later PATH lookup.
- Identify missing launch files before starting Minecraft. Windows process-start
  errors now show the Java and working-folder paths, with a Repair action, while
  keeping account access tokens out of error details.

## 0.9.22 Alpha (Windows and Linux)

- Added automatic recovery snapshots before mod changes and loader changes,
  with manual backups and restore under Instance Tools. The five newest backups
  are retained; restoring keeps worlds unchanged and backs up the current setup.
- Added instance duplication and ZIP export/import, with optional worlds and
  screenshots. Transfers exclude launcher sign-ins and rebuild platform-specific
  launch files in a new instance.
- Added explanations and recovery actions for common Java, mod dependency,
  memory, graphics and installation failures. Unknown errors retain their logs
  without assigning an unverified cause.
- Added Repair installation, and prevented launches during instance file changes.
- Reorganized the README with platform installation steps, SmartScreen guidance,
  credits, licensing, support, and a placeholder for the upcoming tutorial video.

## 0.9.21 Alpha (Windows and Linux)

- Updated the launcher repository and updater links after the GitHub rename.
- Renamed the remaining internal launcher modules and build entry points.
- Moved older user data into the BreakBlocks Launcher data folder on first run,
  retaining existing profiles, instances, and chat sign-in data.

## 0.9.20 Alpha (Windows and Linux test)

- Brought the shared chat notification and visibility fixes to Ubuntu and the
  portable Linux package. New messages count as unread when Minecraft has
  focus, even if the Chat tab was selected before launching.
- Synchronized Windows and Linux package versions and build checks. The
  Ctrl+Shift+F9 chat overlay remains available on Windows only.

## 0.9.15 Alpha (Windows archive test)

- Packaged the Windows GitHub Actions build as one archive containing the
  application files directly, with no second ZIP inside it.
- Kept the 0.9.14 Windows chat overlay for testing.

## 0.9.14 Alpha (Windows overlay test)

- Added a launcher-managed hotkey overlay for Minecraft sessions started on Windows.
  Ctrl+Shift+F9 moves the existing signed-in BreakBlocks chat over a windowed
  or borderless game, and Esc returns focus to Minecraft.
- The chat page and overlay use the same browser view and website session.
  Opening the overlay also clears the unread badge.
- Linux packages stay on the existing build while this Windows behavior is tested.

## 0.9.13 Alpha

- Sharpened Windows text, rounded corners, and icons on scaled displays by
  enabling native per-monitor DPI rendering before the interface starts.
- Redesigned chat notifications with the BBC chicken logo, a compact
  `name · #channel` heading, a wider message area, and an eight-second display.
- Matched the unread badge corners to the Chat button in its normal, hovered,
  and selected states on Windows, Ubuntu, and Steam Deck.

## 0.9.12 Alpha

- Expanded the embedded BreakBlocks chat across the entire launcher area to
  the right of the sidebar.
- Moved the external-browser shortcut into a right-click menu on the Chat
  sidebar button.
- Kept persistent website sign-in, secure notifications, and unread-message
  counts unchanged across Windows, Ubuntu, and Steam Deck.

## 0.9.11 Alpha

- Allowed notification permission only for the secure BreakBlocks chat origin
  and stored the choice in the dedicated web-chat profile.
- Added a launcher-styled desktop popup for new website chat notifications.
- Restored the unread-message badge beside Chat while another launcher page is
  open; opening Chat clears the count.

## 0.9.10 Alpha

- Restored the Windows BreakBlocks web chat as a native child of the launcher's
  Chat panel instead of a separate external window.
- Kept the browser process alive and automatically reattaches its native window
  if Qt recreates the handle while Chromium is loading.
- Preserved the dedicated web-chat profile, login cookies, and unchanged Linux
  embedding behavior.

## 0.9.6 Alpha

- Replaced the launcher-owned IRC client with the authenticated BreakBlocks web
  chat at `https://irc.breakblocks.com/#/connect`.
- Added a Chromium-based browser surface directly inside the Chat page on
  Windows and Linux.
- Added a dedicated persistent browser profile so BreakBlocks website cookies
  and site preferences survive launcher restarts.
- Removed the obsolete IRC nickname, server-password, automatic-connect,
  formatting, and notification settings. Existing saved IRC credentials are
  deleted from `launcher.json` during migration.
- Kept chat credentials inside the BreakBlocks website; the launcher does not
  receive or log the user's BreakBlocks password.

## 0.9.5 Alpha

- Completed the self-updater for installed Ubuntu `.deb` packages. Updates are
  downloaded and SHA-256 verified before the normal administrator approval
  prompt installs the new package and restarts the launcher.
- Kept Windows portable self-replacement and Steam Deck portable replacement,
  with rollback protection if swapping the installation fails.
- Split update-manifest targets into Windows, Ubuntu, and portable Linux so
  each installation downloads the correct package.
- Retained the earlier `linux-x86_64` manifest target so Steam Deck builds from
  0.9.4 and earlier can move onto the new updater without breaking discovery.
- Updated the release workflow to publish the Windows ZIP, Ubuntu `.deb`, Steam
  Deck archive, and their matching update manifest together.

## 0.9.4 Alpha

- Moved the Settings action buttons above the scrollable settings cards so
  **Save Settings** remains visible without scrolling.
- Added **Open Launcher Folder** beside the save button for quick access to
  launcher data, instance logs, and Minecraft crash reports.

## 0.9.3 Alpha

- Synchronized the Windows, Ubuntu, and Steam Deck feature sets from one source tree.
- Added `#BlockTown` as a second IRC channel joined automatically alongside
  `#BreakBlocks`.
- Brought the Modern IRC/IRCv3 channel list, commands, bounded scrollback,
  formatting, authentication, reconnect, and presence tracking to Linux.
- Preserved the Linux browser-opening, Microsoft authentication, portable-runtime,
  fonts, desktop icons, and crash-dialog click-through fixes.

## 0.9.2 Alpha

- Replaced the basic single-channel transport with a Modern IRC/IRCv3 client.
- Fixed the service to TLS on `irc.breakblocks.com:6697` and removed editable
  host, port, TLS, and initial-channel controls.
- Added optional IRC server-password authentication without writing credentials
  to logs.
- Added capability negotiation, `005` support, UTF-8 byte-aware message
  splitting, output flood control, keepalives, nickname fallbacks, and automatic
  reconnect with backoff.
- Added IRC command routing for every input beginning with `/`, including
  `/msg`, `/me`, `/notice`, `/part`, `/nick`, and other server commands.
- Added a three-column chat view with channels on the left, messages in the
  centre, and the live member list on the right.
- Added per-channel bounded in-memory scrollback, private-message buffers,
  IRC formatting, server timestamps, CTCP safety, and DCC blocking.
- Improved live member tracking for JOIN, PART, QUIT, KICK, NICK, MODE,
  account, away, and host updates.
- Fixed a Windows startup crash caused by unsupported Tk listbox styling
  options in the new IRC channel and member panels.
- Closing Minecraft normally with the title-bar X is no longer reported as a
  crash when the launch log confirms an orderly shutdown.
- Launcher dialogs now prevent click-through to the dashboard, so dismissing a
  crash report cannot accidentally open the Create instance window.

## 0.9.1 Alpha

### Added

- Launcher-specific Privacy Notice, Terms, third-party notices, legal release
  checklist, and proposed BreakBlocks.com policy additions.
- About-page links to the bundled legal documents, Minecraft EULA, Minecraft
  Usage Guidelines, Microsoft Privacy Statement, and BreakBlocks contact route.
- Release-time collection and validation of dependency and runtime licences.
- A one-time, versioned first-run notice covering non-affiliation, ownership,
  local token storage, and the absence of analytics.
- The GNU General Public License version 3 for the launcher's original source
  code, included in source and binary packages.
- Browser-matched IRC nickname colours, a Chat unread counter, and an optional
  bundled notification sound.
- An opt-in IRC setting to connect automatically when the launcher starts.
- Automatic Updates-tab checks for compatible Trouser Streak and Server Seeker
  GitHub releases, plus Meteor builds from Meteor's official build service.
- Minecraft crash detection with report viewing, copying, crash-folder access,
  and three retained launch logs per instance.

### Changed

- Offline profiles now require a previously verified Minecraft: Java Edition
  entitlement from a Microsoft account on the same installation.
- Existing Microsoft profiles created by 0.9.0 retain their verified status
  without losing account data.
- Replaced the animated sidebar wordmark with the approved static stacked
  BreakBlocks logo.
- Rebalanced the launcher dashboard to give Ready to Launch more space and the
  Instances list less unused space.
- Centred the sidebar version beneath the logo and added separate button cards
  for the Zazuzin and Etianl GitHub links.
- Expanded the About-page project overview and credited Zazuzin as the launcher
  creator.
- Preset the tested BreakBlocks IRC connection while keeping connection manual;
  a blank nickname now creates a temporary Guest name for that session.
- Added a live IRC member panel grouped into operators, voiced members, and
  users, with updates for joins, departures, nickname changes, and channel modes.
- Launcher data directories use owner-only permissions where supported.
- Release readmes now put the required Mojang/Microsoft disclaimer first.
- Stable is now the default update channel; Alpha remains available as an
  explicit opt-in.
- Release automation now supports both Alpha prereleases and Stable full
  releases with matching package names and update manifests.
- Sidebar community buttons now use the approved BBC charcoal background.
- Updated Pillow to 12.3.0 after the dependency audit identified advisories in
  the previous 11.3.0 build.
- Updated the development formatter to Black 26.3.1 after the dependency audit
  identified advisories in 25.1.0.
- Main pages now share one exclusive display slot, preventing Windows from
  showing child widgets from two pages during navigation.
- Restored complete outlines around the charcoal sidebar community buttons.

## 0.9.0 Alpha

### Added

- Verified launcher update discovery, download, staging, and restart support.
- Update channel and frequency controls.
- Configurable launch-window behaviour and a data-folder shortcut.
- BreakBlocks IRC chat page and a direct TLS-capable IRC transport.
- About page with project credits, legal notice, and official usage-guideline link.
- Reproducible Windows and Linux release workflow with mandatory Windows signing.

### Changed

- Renamed the former cracked-account interface to Offline Accounts.
- Migrated legacy saved offline-account labels while preserving account data.
- Centralised release metadata and network user-agent values.
- Reworked the Minecraft backend into readable, documented functions.
- Removed the unused duplicate dashboard implementation.
- Replaced the long historical package notes with contributor-facing documentation.

### Fixed

- IRC settings now normalize hostnames, host-and-port values, and common URL
  formats, with readable DNS, connection, and TLS errors.
- Removed the pale edge matte from the Mountains of Lava Inc. sidebar logo.
- Corrected the Linux bootstrap log directory.
