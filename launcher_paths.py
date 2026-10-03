"""Locate launcher data while preserving profiles from older installations."""

from __future__ import annotations

import os
import pathlib
import shutil
import tempfile

from app_config import APP_NAME


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
        legacy = base / "Zazu Launcher"
    else:
        environment = "XDG_STATE_HOME" if state else "XDG_DATA_HOME"
        default = pathlib.Path.home() / (".local/state" if state else ".local/share")
        base = pathlib.Path(os.environ.get(environment, default))
        preferred = base / "breakblocks-launcher"
        legacy = base / "zazu-launcher"

    migrate_legacy_data(preferred, legacy)

    preferred.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(preferred, 0o700)
    except OSError:
        pass
    return preferred
