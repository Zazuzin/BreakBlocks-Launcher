BreakBlocks Launcher 0.9.9 Alpha - Steam Deck x86_64

NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH
MOJANG OR MICROSOFT.

This portable package is for a Steam Deck running the standard SteamOS desktop.
It does not require pacman, apt, sudo, or disabling the read-only system partition.

INSTALL
-------
1. Switch the Steam Deck to Desktop Mode.
2. Extract the complete .tar.gz archive.
3. Open Konsole in the extracted BreakBlocks-Launcher folder.
4. Run:

     chmod +x "Install on Steam Deck.sh"
     ./"Install on Steam Deck.sh"

5. Open BreakBlocks Launcher from the application menu under Games.

ADD TO GAMING MODE
------------------
1. Open Steam in Desktop Mode.
2. Select Games, then Add a Non-Steam Game to My Library.
3. Browse to:

     /home/deck/.local/opt/breakblocks-launcher/BreakBlocks Launcher

4. Add it, then return to Gaming Mode.

PORTABLE USE
------------
You may also run "BreakBlocks Launcher" directly from the extracted folder.
Keep the entire folder together; do not move only the launcher script.

FEATURES
--------
The launcher has the same feature set as the Windows and Ubuntu 0.9.9 builds.
Its Chat page embeds the authenticated BreakBlocks website and keeps the site
cookie in a dedicated local profile so users normally remain signed in.

RUNTIME
-------
The package includes its own Python 3.12, Xft-enabled Tcl/Tk 8.6 runtime,
CustomTkinter, Pillow, PySide6/Qt WebEngine, certificates, fonts, and launcher
assets.

Bundled Ubuntu libraries are restricted to the launcher itself. SteamOS tools,
Java, Minecraft, folder opening, and the updater are started with the normal
SteamOS environment.

Java for Minecraft is selected from the system or downloaded separately by the
launcher when required.

DATA AND LOGS
-------------
Launcher data: ~/.local/share/breakblocks-launcher
Launcher log:  ~/.local/state/breakblocks-launcher/launcher.log
Minecraft log: <data directory>/instances/<instance>/latest-launch.log

The launcher retains the three newest launch logs for each instance. Microsoft
tokens are stored locally in launcher.json. Do not share that file or your data
folder.

Closing Minecraft normally with Quit Game or the title-bar X is not treated as
a crash when the launch log confirms an orderly shutdown. Launcher dialogs also
block clicks from passing through to the window underneath.

Reinstalling or updating the launcher preserves this data. No user account is
included in this archive.

LEGAL
-----
The original launcher source is GPL-3.0-only. See LICENSE, PRIVACY.md,
TERMS.md, and THIRD-PARTY-NOTICES.md. Third-party licence texts are included in
the third-party-licenses folder.

Project: https://github.com/Zazuzin/Zazu-Launcher
