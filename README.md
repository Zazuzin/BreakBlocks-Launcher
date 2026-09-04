# Zazu Launcher

Zazu Launcher is an independent, cross-platform launcher for Minecraft: Java Edition. It provides a modern desktop interface for creating isolated Minecraft instances, selecting mod loaders, and managing Microsoft or local offline profiles.

> **Development status:** Zazu Launcher is currently an alpha project. Microsoft account authentication uses the launcher's own Microsoft Entra application registration. Approval of that application for Minecraft Services is currently pending.

## Current features

- Native desktop interface for Windows and Linux
- Complete Minecraft version catalogue
- Separate game directory for every instance
- Vanilla, Fabric, Quilt, Forge, and NeoForge profiles
- Automatic Java runtime selection and installation
- Shared Minecraft asset and library cache
- Installation progress with stages and percentages
- Microsoft OAuth device-code sign-in
- Minecraft ownership and profile checks
- Microsoft skin heads in the account selector
- Multiple accounts with a clearly selected launch account
- Local offline profiles with Minecraft-compatible offline UUIDs
- Per-instance Minecraft launch logs

## Microsoft authentication

Zazu Launcher uses Microsoft OAuth 2.0 device authorization as a public desktop client. Users authenticate on Microsoft's website; the launcher never receives or stores Microsoft passwords.

The authentication sequence is:

1. Microsoft OAuth device authorization
2. Xbox Live user authentication
3. XSTS authorization for Minecraft Services
4. Minecraft access-token exchange
5. Java Edition ownership and profile lookup

The public Microsoft Entra Application (Client) ID used by the launcher is:

`f621b9a7-a133-49c0-b04b-66de82aacb62`

OAuth and Minecraft session tokens are stored only in the current user's local launcher data. They must never be committed to this repository or included in bug reports.

## Running from source

Python 3.12 or newer is recommended.

```bash
python -m venv .venv
```

Activate the environment, then install the dependencies:

```bash
python -m pip install -r requirements.txt
python zazu_launcher.py
```

Linux users may also need to install their distribution's Tk package, commonly named `python3-tk`.

## Launcher data

- Windows: `%LOCALAPPDATA%\Zazu Launcher`
- Linux: `~/.local/share/zazu-launcher`

Minecraft instances, settings, account sessions, downloaded Java runtimes, and logs are kept outside the source directory.

## Project structure

- `zazu_launcher.py` — desktop interface and account management
- `minecraft_backend.py` — instance installation and Minecraft launching
- `zazu_launcher_boot.pyw` — Windows packaged-runtime bootstrap
- `Zazu Launcher` — Linux packaged-build start script
- `Zazu Launcher.bat` — Windows packaged-build start script
- `fonts/` — Linux packaged-build font configuration

## Disclaimer

Zazu Launcher is an independent project and is not affiliated with, endorsed by, or sponsored by Microsoft, Mojang Studios, or Minecraft. Minecraft is a trademark of Microsoft Corporation.
