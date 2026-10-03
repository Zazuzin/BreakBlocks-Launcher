"""Locate launcher data while preserving profiles from older installations."""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import tempfile

from app_config import APP_NAME

# Historical folder names are needed to find data from older installations.
LEGACY_DATA_FOLDERS = {"nt": "Zazu Launcher", "posix": "zazu-launcher"}


def migrate_account_skin(root: pathlib.Path, account: dict) -> bool:
    """Reconnect a profile to its moved local skin cache without touching sign-in data."""
    saved = str(account.get("skin") or "")
    parts = saved.replace("\\", "/").rsplit("/", 2)
    saved_in_cache = len(parts) >= 2 and parts[-2].casefold() == "skins"
    if saved and not saved_in_cache and pathlib.Path(saved).is_file():
        return False  # Preserve an explicitly selected image outside the skin cache.
    filenames = []
    if saved_in_cache and re.fullmatch(r"[A-Za-z0-9_-]{1,80}\.png", parts[-1], re.I):
        filenames.append(parts[-1])
    ident = str(account.get("id") or "")
    if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", ident):
        filenames.append(ident + ".png")
    folder = (root / "skins").resolve()
    for filename in dict.fromkeys(filenames):
        candidate = folder / filename
        if candidate.is_file() and candidate.resolve().parent == folder:
            current = str(candidate)
            if current != saved:
                account["skin"] = current
                return True
            return False
    return False


def migrate_legacy_data(preferred: pathlib.Path, legacy: pathlib.Path) -> None:
    """Move older profiles into the new location without replacing newer data."""
    if not legacy.is_dir():
        return
    if not preferred.exists():
        try:
            legacy.rename(preferred)
            return
        except OSError:
            # Open files can prevent a folder rename on Windows. Keep the
            # original intact until a complete copy is ready for use.
            preferred.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix=".breakblocks-migration-", dir=preferred.parent
            ) as temporary:
                staged = pathlib.Path(temporary) / "launcher"
                shutil.copytree(legacy, staged, symlinks=True)
                staged.rename(preferred)
            return
    if not preferred.is_dir() or (preferred / "launcher.json").exists():
        return

    # The bootstrap can create the new log directory before Store starts.
    # Move each missing entry; launcher.json goes last, marking migration done.
    def move_missing_entries(source: pathlib.Path, destination: pathlib.Path) -> None:
        for item in sorted(source.iterdir(), key=lambda path: path.name == "launcher.json"):
            target = destination / item.name
            if target.is_dir() and not target.is_symlink() and item.is_dir():
                move_missing_entries(item, target)
            elif not target.exists() and not target.is_symlink():
                try:
                    item.rename(target)
                except OSError:
                    if item.is_dir() and not item.is_symlink():
                        shutil.copytree(item, target, symlinks=True)
                    else:
                        shutil.copy2(item, target, follow_symlinks=False)

    move_missing_entries(legacy, preferred)


def launcher_data_root(*, state: bool = False) -> pathlib.Path:
    """Use the BreakBlocks folder and move older user data into it when needed."""
    if os.name == "nt":
        base = pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home() / "AppData/Local"))
        preferred = base / APP_NAME
        legacy = base / LEGACY_DATA_FOLDERS["nt"]
    else:
        environment = "XDG_STATE_HOME" if state else "XDG_DATA_HOME"
        default = pathlib.Path.home() / (".local/state" if state else ".local/share")
        base = pathlib.Path(os.environ.get(environment, default))
        preferred = base / "breakblocks-launcher"
        legacy = base / LEGACY_DATA_FOLDERS["posix"]

    migrate_legacy_data(preferred, legacy)

    preferred.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(preferred, 0o700)
    except OSError:
        pass
    return preferred
