BreakBlocks Launcher 0.9.27 Alpha - Windows x64 test build

NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH
MOJANG OR MICROSOFT.

Install
-------
1. Extract the GitHub Actions ZIP into a new BreakBlocks-Launcher folder.
2. Open that extracted folder. Keep the executable and _internal folder together.
3. Double-click "BreakBlocks Launcher.exe".

Python and the GUI runtime are included. Java is selected or downloaded
separately for each Minecraft version when required.

Windows overlay
---------------
- Launch Minecraft from BreakBlocks, then press Ctrl+Shift+F9 while its window
  is active to bring the signed-in web chat over the game. Reply in the same
  browser session. Press Esc or Ctrl+Shift+F9 to return to Minecraft.
- The overlay follows Minecraft sessions launched by this copy of BreakBlocks.
  It is designed for windowed or borderless Minecraft; exclusive fullscreen
  can prevent desktop windows appearing over the game.
- This is a Windows test build. The overlay has not yet been verified on a
  physical Windows game session.

Earlier improvements
--------------------
- Sharpened text, icons, borders, and rounded corners on Windows displays that
  use scaling by enabling native per-monitor DPI rendering before startup.
- Updated chat notifications with the BBC chicken logo, a cleaner title, a
  wider layout, and an eight-second display time.
- Matched the unread-number background to the Chat button while idle, hovered,
  or selected so its rounded corners blend cleanly.
- Expanded the embedded chat to fill the complete area beside the sidebar.
- Added an "Open in browser" option when Chat is right-clicked in the sidebar.
- Enabled website notifications for only the secure BreakBlocks chat address,
  with the permission retained in the chat profile.
- Added a desktop notification popup and restored the unread number beside Chat
  while another launcher page is open. Opening Chat clears the number.
- Restored the BreakBlocks website inside the launcher's Chat panel instead of
  leaving it in a separate external browser window.
- Kept the browser alive and automatically reattaches its native Windows child
  window if Qt recreates the handle while Chromium is loading.
- Replaced the native IRC client with the authenticated BreakBlocks web chat.
- Embedded the website directly in the Chat page and retained its login cookie
  and site preferences in a dedicated local browser profile.
- Removed the obsolete launcher IRC password, nickname, connection, formatting,
  and notification settings.
- Added launcher-specific Privacy, Terms, third-party notices, and a release
  readiness checklist based on the launcher's actual data flows.
- Made the Mojang/Microsoft non-affiliation notice prominent in the launcher and
  release documentation.
- Offline profiles now require a Microsoft account whose Minecraft: Java
  Edition ownership has been verified on this installation.
- Added direct About-page links to the legal documents, Minecraft EULA, Usage
  Guidelines, Microsoft Privacy Statement, and BreakBlocks contact route.
- Restricted the launcher data directory to the current user where the operating
  system supports POSIX permissions.
- Added release-time collection and validation of bundled dependency licences.
- Made Stable the default update channel; Alpha remains available as an opt-in.
- Added verified one-click updates which download the correct Windows package,
  replace the portable installation after exit, and restart the launcher.

Windows security
----------------
The Windows executable is unsigned, including in GitHub Releases. Windows or
your browser may warn or block it because the publisher cannot be verified.
Download only from the official BreakBlocks Launcher GitHub release page and
check its SHA-256 checksum if you want to verify the file. Do not disable
security protections to run it.

Automatic updates
-----------------
Update checks activate after a matching version is published as a GitHub Release with
breakblocks-update.json and the matching Windows package. The launcher verifies
the size and SHA-256 checksum before replacing the installation and restarting.

Data and logs
-------------
New data: %LOCALAPPDATA%\BreakBlocks Launcher
Data from older installations moves to the BreakBlocks Launcher folder on first run.
Launcher log: <active data directory>\launcher.log
Minecraft log: <active data directory>\instances\<instance>\latest-launch.log

The launcher retains the configured number of launch logs (three by default) for each instance. If
Minecraft crashes, it offers controls to view or copy the report and open the
instance's crash-reports folder. Crash information is never uploaded automatically.

Microsoft tokens are stored in launcher.json for sign-in and token refresh. Do
not share this file or the launcher data folder. See PRIVACY.md for the complete
local-storage and network-service description.

BreakBlocks Chat
----------------
The Chat page loads https://irc.breakblocks.com/#/connect inside the launcher.
Sign in using the BreakBlocks website. Its cookie and site preferences are kept
in the local web-chat-profile directory so you normally remain signed in. Use
the website's Log out control to end the session. BreakBlocks chat notifications
are allowed only for that secure address. New notifications received while Chat
is not open add to the number beside Chat; opening Chat clears it.

Legal
-----
NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH MOJANG OR
MICROSOFT. BreakBlocks Launcher is an independent community project.

The original source code is licensed under the GNU General Public License
version 3 only. See LICENSE. BreakBlocks branding, community artwork, and
third-party marks are not covered unless their owners explicitly say otherwise.

Minecraft and related assets are © Mojang AB. “Minecraft” is a trademark of
Microsoft Corporation. Third-party names, logos, and trademarks belong to their
respective owners.

Project: https://github.com/Zazuzin/BreakBlocks-Launcher
Minecraft Usage Guidelines: https://www.minecraft.net/usage-guidelines
Launcher privacy: PRIVACY.md
Launcher terms: TERMS.md
Third-party notices: THIRD-PARTY-NOTICES.md

INSTANCE RIGHT-CLICK MENU
-------------------------
Right-click an instance for Backups / Restore, Duplicate instance, Export
instance, Import instance, and Repair installation. Import is also above
the instance list.

Backups are automatic before mod and loader changes; the configured number of snapshots (five by default)
are kept per instance. They include mods, configs, options and the launch
profile. Restoring preserves worlds and saves the current setup first.

Duplicate and Export offer an Include worlds and screenshots option. Portable
instance ZIPs exclude launcher accounts and chat sessions. Importing creates a
new instance and installs the launch files needed on that computer.

Settings and startup in 0.9.27
-----------------------------
Chat starts in the background with your saved website session. The launcher
checks for launcher and compatible installed-mod updates at startup and shows
Updates available when there is something to review. Install updates when you
choose; turn automatic checks off under Startup and updates.

Settings sections cover chat notification volume, duration and privacy,
interface/text size, backup count and space limits, Minecraft window defaults,
Java browsing/testing, storage usage/unused archive cleanup, log retention,
custom JVM options and Minecraft download controls. Windows also has overlay
enablement, hotkey and text-size settings. Save Settings to apply changes.
Edit Instance -> Window size overrides the global Minecraft window defaults.
