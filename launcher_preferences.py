"""Validated desktop preferences and maintenance of disposable downloads."""

from __future__ import annotations

import json
import pathlib
import re
import shlex
import shutil
import subprocess
import uuid

DEFAULTS = {
    "chat_popups": True,
    "chat_sound": True,
    "chat_volume": 70,
    "chat_duration": 8,
    "chat_hide_previews": False,
    "overlay_enabled": True,
    "overlay_hotkey": "Ctrl+Shift+F9",
    "overlay_text_scale": 100,
    "ui_scale": 100,
    "text_scale": 100,
    "automatic_backups": True,
    "backup_count": 5,
    "backup_max_mb": 2048,
    "window_width": 0,
    "window_height": 0,
    "update_check_startup": True,
    "mods_check_startup": True,
    "log_count": 3,
    "detailed_logging": False,
    "jvm_arguments": "",
    "download_workers": 10,
    "download_timeout": 60,
    "download_retries": 1,
}
RANGES = {
    "chat_volume": (0, 100),
    "chat_duration": (3, 30),
    "overlay_text_scale": (80, 200),
    "ui_scale": (90, 150),
    "text_scale": (90, 125),
    "backup_count": (1, 20),
    "backup_max_mb": (256, 102400),
    "window_width": (320, 7680),
    "window_height": (240, 4320),
    "log_count": (1, 10),
    "download_workers": (1, 16),
    "download_timeout": (15, 180),
    "download_retries": (0, 3),
}
CHAT_KEYS = tuple(key for key in DEFAULTS if key.startswith(("chat_", "overlay_")))


def parse_hotkey(value):
    parts = str(value).replace(" ", "").split("+")
    aliases = {"ctrl": ("Ctrl", 2), "shift": ("Shift", 4), "alt": ("Alt", 1)}
    modifiers = []
    mask = 0
    for part in parts[:-1]:
        name, flag = aliases.get(part.lower(), (None, 0))
        if name is None or name in modifiers:
            raise ValueError("Use Ctrl, Shift or Alt once, followed by F1–F12 or a letter.")
        modifiers.append(name)
        mask |= flag
    key = parts[-1].upper()
    if not modifiers:
        raise ValueError("The overlay shortcut needs Ctrl, Shift or Alt.")
    if re.fullmatch(r"F(?:[1-9]|1[0-2])", key):
        virtual_key = 0x6F + int(key[1:])
    elif re.fullmatch(r"[A-Z0-9]", key):
        virtual_key = ord(key)
    else:
        raise ValueError("Use an overlay shortcut such as Ctrl+Shift+F9.")
    return "+".join([*modifiers, key]), mask, virtual_key


def jvm_arguments(value):
    try:
        arguments = shlex.split(str(value))
    except ValueError as error:
        raise ValueError("Check the quotes in your custom Java arguments.") from error
    if any(arg in {"-jar", "-cp", "-classpath"} or arg.startswith("@") for arg in arguments):
        raise ValueError(
            "Custom Java options cannot replace Minecraft's classpath or main program."
        )
    if any("\0" in arg or "\n" in arg for arg in arguments):
        raise ValueError("Custom Java arguments must be on one line.")
    return arguments


def validate(values):
    result = {}
    for key, default in DEFAULTS.items():
        value = values.get(key, default)
        if isinstance(default, bool):
            if not isinstance(value, bool):
                raise ValueError(f"Invalid value for {key.replace('_', ' ')}.")
        elif key in RANGES:
            try:
                value = int(str(value).rstrip("%") or "0")
            except (ValueError, TypeError) as error:
                raise ValueError(f"Enter a number for {key.replace('_', ' ')}.") from error
            low, high = RANGES[key]
            if not (key.startswith("window_") and value == 0) and not low <= value <= high:
                raise ValueError(
                    f"{key.replace('_', ' ').capitalize()} must be between {low} and {high}."
                )
        elif key == "overlay_hotkey":
            value = parse_hotkey(value)[0]
        elif key == "jvm_arguments":
            value = str(value).strip()
            jvm_arguments(value)
        result[key] = value
    if bool(result["window_width"]) != bool(result["window_height"]):
        raise ValueError("Enter both Minecraft window dimensions, or leave both blank.")
    return result


def normalized(values=None):
    values = values or {}
    safe = dict(DEFAULTS)
    for key in DEFAULTS:
        if key not in values:
            continue
        try:
            candidate = dict(safe, **{key: values[key]})
            if key.startswith("window_"):
                candidate.update(
                    window_width=values.get("window_width", 0),
                    window_height=values.get("window_height", 0),
                )
            safe = validate(candidate)
        except (ValueError, TypeError):
            pass
    return safe


def load(path):
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        return normalized(data.get("settings", data))
    except (OSError, ValueError, TypeError, AttributeError):
        return dict(DEFAULTS)


def write_chat_preferences(folder, settings, preview=False):
    folder = pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / "launcher-preferences.json"
    temporary = destination.with_suffix(".tmp")
    settings = normalized(settings)
    packet = {key: settings[key] for key in CHAT_KEYS}
    packet["_preview_id"] = uuid.uuid4().hex if preview else 0
    temporary.write_text(json.dumps(packet), encoding="utf-8")
    temporary.replace(destination)


def test_java(value):
    path = shutil.which("java") if str(value).strip().lower() == "auto" else str(value).strip()
    if not path or not pathlib.Path(path).is_file():
        raise ValueError(
            "Choose an installed Java executable. Auto downloads Java when Minecraft needs it."
        )
    result = subprocess.run(
        [str(pathlib.Path(path).resolve()), "-version"], capture_output=True, text=True, timeout=15
    )
    if result.returncode:
        raise ValueError("Java could not start: " + (result.stderr or result.stdout)[:600])
    return str(pathlib.Path(path).resolve()), (result.stderr or result.stdout).strip()[:600]


def directory_bytes(folder):
    folder = pathlib.Path(folder)
    if not folder.is_dir() or folder.is_symlink():
        return 0
    resolved = folder.resolve()
    total = 0
    for path in folder.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(resolved):
                total += path.stat().st_size
        except OSError:
            continue
    return total


def storage_usage(root):
    root = pathlib.Path(root)
    return {
        name: directory_bytes(root / name)
        for name in ("instances", "minecraft-data", "java", "backups", "web-chat-profile")
    }


def disposable_downloads(root):
    root = pathlib.Path(root).resolve()

    def safe(path):
        return path.resolve().is_relative_to(root) and not any(
            parent.is_symlink()
            for parent in (path, *path.parents)
            if parent != root and parent.is_relative_to(root)
        )

    candidates = []
    installers = root / "minecraft-data" / "installers"
    if installers.is_dir() and safe(installers):
        candidates.extend(installers.glob("*-installer.jar"))
    java = root / "java"
    if java.is_dir() and safe(java):
        for folder in java.iterdir():
            if folder.is_dir() and safe(folder):
                installed = any(
                    path.is_file() and safe(path)
                    for pattern in ("*/bin/java", "*/bin/java.exe")
                    for path in folder.glob(pattern)
                )
                if installed:
                    candidates.extend(
                        path for path in folder.iterdir() if path.name.endswith((".zip", ".tar.gz"))
                    )
    return [path for path in candidates if path.is_file() and safe(path)]


def clear_disposable_downloads(root):
    released = 0
    for path in disposable_downloads(root):
        size = path.stat().st_size
        path.unlink()
        released += size
    return released


def format_bytes(value):
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
