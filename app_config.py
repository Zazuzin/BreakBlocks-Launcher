"""Shared product metadata and service endpoints.

Keep release-facing values in this module so the GUI, Minecraft launch records,
packaging scripts, and updater all report the same version.
"""

APP_NAME = "BreakBlocks Launcher"
APP_VERSION_NUMBER = "0.9.13"
APP_RELEASE_STAGE = "Alpha"
APP_VERSION = f"{APP_VERSION_NUMBER} {APP_RELEASE_STAGE}"
APP_USER_AGENT = f"BreakBlocks-Launcher/{APP_VERSION_NUMBER}"

GITHUB_REPOSITORY = "Zazuzin/Zazu-Launcher"
GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases"
UPDATE_MANIFEST_NAME = "breakblocks-update.json"

DEFAULT_UPDATE_CHANNEL = "stable"
UPDATE_CHANNELS = ("stable", "alpha")
