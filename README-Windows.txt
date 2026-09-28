BreakBlocks Launcher 0.9.8 Alpha - Windows x64 test build

NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH
MOJANG OR MICROSOFT.

Install
-------
1. Extract the complete ZIP. Do not run the launcher inside the ZIP.
2. Open the extracted BreakBlocks-Launcher folder.
3. Double-click "BreakBlocks Launcher.exe".

Python and the GUI runtime are included. Java is selected or downloaded
separately for each Minecraft version when required.

Highlights in 0.9.8
-------------------
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

Windows security and signing
----------------------------
This local test archive is not a signed public release and Windows may warn when
it opens. The included publishing workflow will not create a public release
unless a trusted Authenticode certificate is configured and the signature is
verified. A valid signature identifies the publisher; SmartScreen reputation
can still take time to build for a new certificate.

Automatic updates
-----------------
Update checks activate after 0.9.8 is published as a GitHub Release with
breakblocks-update.json and the matching Windows package. The launcher verifies
the size and SHA-256 checksum before replacing the installation and restarting.

Data and logs
-------------
New data: %LOCALAPPDATA%\BreakBlocks Launcher
Legacy data, when already present: %LOCALAPPDATA%\Zazu Launcher
Launcher log: <active data directory>\launcher.log
Minecraft log: <active data directory>\instances\<instance>\latest-launch.log

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
the website's Log out control to end the session.

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

Project: https://github.com/Zazuzin/Zazu-Launcher
Minecraft Usage Guidelines: https://www.minecraft.net/usage-guidelines
Launcher privacy: PRIVACY.md
Launcher terms: TERMS.md
Third-party notices: THIRD-PARTY-NOTICES.md
