BreakBlocks Launcher 0.9.21 Alpha - Linux/Steam Deck test build

NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH
MOJANG OR MICROSOFT.

Install
-------
1. Extract the complete archive.
2. Make "BreakBlocks Launcher" executable if your file manager requests it.
3. Open "BreakBlocks Launcher" and choose Execute.

This portable package includes its Python and Tk runtime. Java is selected or
downloaded separately for each Minecraft version when required.

Chat and launcher features
--------------------------
- The chat page reports when it is in the background so website notifications
  and the unread number work after switching tabs or focusing Minecraft.
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
- Added verified one-click updates for installed Ubuntu packages and portable
  Steam Deck installations.

Important release note
----------------------
Update checks activate after 0.9.21 is published as a GitHub Release with
breakblocks-update.json and the matching platform packages. The launcher
verifies the package before installation. Ubuntu asks for the normal
administrator approval; portable Steam Deck builds replace themselves and
restart. Windows packages are unsigned and may be warned about or blocked.

Data and logs
-------------
New data: ~/.local/share/breakblocks-launcher
Data from older installations moves to the BreakBlocks Launcher folder on first run.
Launcher log: ~/.local/state/breakblocks-launcher/launcher.log
Minecraft log: <data directory>/instances/<instance>/latest-launch.log

The launcher retains the three newest launch logs for each instance. If
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
The Ctrl+Shift+F9 in-game overlay is currently available in the Windows build.

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
