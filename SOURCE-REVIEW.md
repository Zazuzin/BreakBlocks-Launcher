# BreakBlocks Launcher source review

Version: **0.9.29 Alpha**

Windows, Ubuntu and Steam Deck share one source tree. Both source archives
contain the complete code, assets, tests, licence files and packaging scripts.
Start with `BUILD-WINDOWS.md` or `BUILD-LINUX.md` for the platform being reviewed.

| File | Responsibility |
| --- | --- |
| `breakblocks_launcher_boot.pyw` | Startup, runtime setup and startup error logging |
| `breakblocks_launcher.py` | Desktop interface, accounts, settings and instance actions |
| `minecraft_backend.py` | Microsoft sign-in, Java selection, installation and Minecraft launch |
| `instance_archives.py` | Backups, restore, duplicate and ZIP import/export |
| `launch_diagnostics.py` | Explanations and recovery actions for launch failures |
| `launcher_paths.py` | Data-folder migration and account-picture cache paths |
| `modrinth_client.py`, `mod_sources.py` | Mod browsing, installation and updates |
| `launcher_update.py`, `app_config.py` | Product metadata and verified launcher updates |
| `chat_browser.py` | Embedded BreakBlocks chat and local browser profile |
| `windows_chat_overlay.py` | Windows game-chat overlay |
| `display_environment.py`, `process_environment.py` | Desktop scaling, fonts and system programs |
| `packaging/`, `BreakBlocksLauncher.spec` | Windows, Ubuntu and portable Linux builds |
| `tests/` | Regression checks |

The only historical product-name values are in `LEGACY_DATA_FOLDERS` in
`launcher_paths.py`. They locate data written by older versions and are not
used for interface labels, package names or update endpoints.

The archives contain no installed games, account files, cookies, launch logs,
virtual environments or build output. The Microsoft application ID in the
source is a public device-code client identifier; the desktop flow does not
use a client secret.

`PRIVACY.md`, `TERMS.md`, `THIRD-PARTY-NOTICES.md` and `LICENSE` accompany the
source. The remaining operator and website-policy questions are recorded in
`LEGAL-RELEASE-CHECKLIST.md` and `WEBSITE-LEGAL-CHANGES.md` for Sheepy's review.

The 0.9.29 settings and startup flow live in `launcher_preferences.py`,
`settings_panel.py` and `startup_updates.py`. `tests/test_launcher_preferences.py`
covers persistence, cleanup boundaries, retention, launch options and read-only
update checks. Chat starts without switching away from the Launcher page.
