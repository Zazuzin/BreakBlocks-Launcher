# BreakBlocks Launcher

**NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH MOJANG
OR MICROSOFT.**

BreakBlocks Launcher is an independent desktop launcher for managing Minecraft
instances, accounts, mods, and BreakBlocks community links. The interface is
written in Python with Tk and CustomTkinter and is packaged for Windows and
Linux/Steam Deck.

The current development version is **0.9.9 Alpha**.

## Current features

- Fabric, Forge, NeoForge, and Vanilla instance profiles
- Microsoft authentication and ownership-gated Offline profiles
- Per-instance names, icons, memory, loaders, and tracked playtime
- Crash detection with an integrated report viewer and three retained launch logs
- Modrinth browse, installed-mod inventory, and automatic compatible update
  checks from Modrinth and linked official mod sources
- Optional Fabric Essentials installation for Meteor Client, Trouser Streak,
  Zazu's Server Seeker, and Fabric API
- Verified one-click launcher updates through GitHub Releases for Windows,
  Ubuntu, and portable Linux/Steam Deck, with Stable selected by default and
  Alpha available as an opt-in channel
- Configurable Java, memory, launch behaviour, and update preferences
- The authenticated BreakBlocks web chat embedded directly in the Chat page,
  with a persistent local browser profile so website sign-in and preferences
  survive launcher restarts

## Run from source

Python 3.10 or newer with Tk support is required.

```bash
python -m pip install -r requirements.txt
python zazu_launcher_boot.pyw
```

## Project structure

| Path | Responsibility |
| --- | --- |
| `zazu_launcher.py` | Application state and desktop interface |
| `minecraft_backend.py` | Version installation, Java selection, and launch commands |
| `modrinth_client.py` | Mod inventory, search, installation, and updates |
| `mod_sources.py` | Trusted non-Modrinth source adapters |
| `launcher_update.py` | Release discovery, integrity checks, staging, and restart |
| `chat_browser.py` | Persistent embedded browser for BreakBlocks web chat |
| `app_config.py` | Product version and release endpoints |
| `tests/` | Dependency-light regression tests |

Older internal `zazu_*` names remain in place where changing them could break
existing data or shortcuts. They are implementation details; the public product
name is BreakBlocks Launcher.

## Tests and formatting

```bash
python -m black --check --line-length 100 *.py tests tools
python -m ruff check *.py tests tools
PYTHONPATH=. sh -c 'for test_file in tests/test_*.py; do python "$test_file" || exit; done'
```

Release builds and Windows signing are documented in [PUBLISHING.md](PUBLISHING.md).
Release changes are tracked in [CHANGELOG.md](CHANGELOG.md).
Release legal checks are tracked in
[LEGAL-RELEASE-CHECKLIST.md](LEGAL-RELEASE-CHECKLIST.md).

## Licence

The original source code for BreakBlocks Launcher is licensed under the
[GNU General Public License v3.0 only](LICENSE). BreakBlocks branding,
community artwork, and third-party names and marks are not covered by that
licence unless their owners explicitly say otherwise.

## Legal

BreakBlocks Launcher is an independent community project. It is not affiliated
with, endorsed by, sponsored by, or approved by Microsoft Corporation or Mojang
AB.

Minecraft and related assets are © Mojang AB. “Minecraft” is a trademark of
Microsoft Corporation. Microsoft, Mojang, Minecraft, and all other third-party
names, logos, and trademarks belong to their respective owners.

See the [Launcher Privacy Notice](PRIVACY.md), [Launcher Terms](TERMS.md),
[Third-Party Notices](THIRD-PARTY-NOTICES.md), official
[Minecraft Usage Guidelines](https://www.minecraft.net/usage-guidelines), and
[Minecraft EULA](https://www.minecraft.net/eula).
