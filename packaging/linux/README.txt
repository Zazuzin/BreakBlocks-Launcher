BreakBlocks Launcher 0.9.29 Alpha - Ubuntu amd64 package

NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH
MOJANG OR MICROSOFT.

Install with:
  sudo apt install ./BreakBlocks-Launcher-0.9.29-Ubuntu-amd64.deb

Future updates can be installed from the launcher's update prompt. The package
is downloaded and verified first, then Ubuntu asks for administrator approval.

Open BreakBlocks Launcher from the application menu, or run:
  breakblocks-launcher

The package uses the system Python 3.12 and Tk libraries and bundles its Python
application dependencies, including the Qt WebEngine chat surface. Java for
Minecraft is selected or downloaded separately when required. Launcher logs
are stored in:
  ~/.local/state/breakblocks-launcher/launcher.log

BreakBlocks website notifications are enabled only for the secure chat address.
New notifications add to the unread number beside Chat while another launcher
page is open; opening Chat clears it. Notifications use the BBC chicken logo,
a compact title, and an eight-second display time.
The chat also enters the background when Minecraft has focus, so new messages
can produce notifications while playing. The Ctrl+Shift+F9 overlay is currently
available in the Windows build.

See PRIVACY.md, TERMS.md, THIRD-PARTY-NOTICES.md, and LICENSE for the launcher
policies and licences.

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

Settings and startup in 0.9.29
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
