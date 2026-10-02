BreakBlocks Launcher 0.9.20 Alpha - Steam Deck x86_64

NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH
MOJANG OR MICROSOFT.

This portable package is for a Steam Deck running the standard SteamOS desktop.
It does not require pacman, apt, sudo, or disabling the read-only system partition.

RUN IN DESKTOP MODE
-------------------
1. Switch the Steam Deck to Desktop Mode.
2. Extract the complete .tar.gz archive.
3. Open the extracted BreakBlocks-Launcher folder and run "BreakBlocks Launcher".
   Choose Execute if the file manager asks. Keep the entire folder together.

ADD TO GAMING MODE
------------------
1. Open Steam in Desktop Mode.
2. Select Games, then Add a Non-Steam Game to My Library.
3. Browse to "BreakBlocks Launcher" in the extracted folder.

4. Add it, then return to Gaming Mode.

PORTABLE USE
------------
You may also run "BreakBlocks Launcher" directly from the extracted folder.
Keep the entire folder together; do not move only the launcher script.

FEATURES
--------
The chat and launcher features match the Ubuntu 0.9.20 build. The Windows
Ctrl+Shift+F9 overlay is currently Windows only.
Its Chat page embeds the authenticated BreakBlocks website and keeps the site
cookie in a dedicated local profile so users normally remain signed in. Chat
fills the complete area beside the sidebar, where right-clicking Chat provides
an Open in browser option. Secure website notifications add to the unread
number beside Chat while another launcher page is open; opening Chat clears it.
Chat also enters the background when Minecraft has focus, so incoming messages
can produce notifications while playing.
Notifications use the BBC chicken logo and a wider eight-second popup. The
unread number blends with the Chat button in its normal and highlighted states.

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
