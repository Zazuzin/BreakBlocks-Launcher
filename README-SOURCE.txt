BreakBlocks Launcher 0.9.11 Alpha - synchronized source package

NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH
MOJANG OR MICROSOFT.

Requirements
------------
- Python 3.10 or newer
- Tk support for Python

Install and run
---------------
  python -m pip install -r requirements.txt
  python zazu_launcher_boot.pyw

Development checks
------------------
  python -m pip install -r requirements-dev.txt
  python -m black --check --line-length 100 *.py tests tools
  python -m ruff check *.py tests tools

Then run every tests/test_*.py file with the source directory on PYTHONPATH.
The suite is intentionally dependency-light and does not require a Minecraft
or Microsoft account.

Main modules
------------
- app_config.py: product version and release endpoints
- zazu_launcher.py: state, accounts, settings, and desktop interface
- minecraft_backend.py: instance installation and Minecraft launching
- modrinth_client.py: Modrinth browsing, inventory, and updates
- mod_sources.py: trusted external mod sources
- launcher_update.py: verified launcher updates
- chat_browser.py: persistent embedded BreakBlocks web chat
- PRIVACY.md and TERMS.md: launcher-specific public policies
- LICENSE: GNU General Public License version 3
- THIRD-PARTY-NOTICES.md: bundled dependency attribution index
- LEGAL-RELEASE-CHECKLIST.md: completed work and release blockers

The old zazu_* module names remain internal for compatibility with existing
installations. Public UI and package names use BreakBlocks Launcher.

Release process
---------------
PUBLISHING.md documents the GitHub Actions release, code-signing requirements,
update manifest, and Alpha/Stable tag formats. Public Windows releases
intentionally fail if trusted Authenticode credentials are not configured.

Crash handling
--------------
Each instance retains its three newest launch logs. A new Minecraft crash report
or a non-zero exit without an orderly shutdown marker opens a local crash dialog
with controls to view or copy the report and open the crash-reports folder.
Reports are not uploaded.

Chat status
-----------
The Chat page embeds https://irc.breakblocks.com/#/connect. BreakBlocks.com
handles authentication and chat behaviour. A dedicated local browser profile
retains the website cookie and preferences across launcher restarts.

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
