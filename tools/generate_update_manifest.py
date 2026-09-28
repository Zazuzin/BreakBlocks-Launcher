#!/usr/bin/env python3
"""Create the machine-readable manifest consumed by launcher_update.py."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

PLATFORM_ASSETS = {
    "windows-x86_64": "BreakBlocks-Launcher-{version}-Windows-x86_64.zip",
    "linux-deb-x86_64": "BreakBlocks-Launcher-{version}-Ubuntu-amd64.deb",
    "linux-portable-x86_64": "BreakBlocks-Launcher-{version}-SteamDeck-x86_64.tar.gz",
    # Compatibility key used by portable Linux builds through 0.9.4.
    "linux-x86_64": "BreakBlocks-Launcher-{version}-SteamDeck-x86_64.tar.gz",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def build_manifest(
    version: str,
    tag: str,
    repository: str,
    assets_dir: Path,
    channel: str = "alpha",
) -> dict:
    if channel not in {"stable", "alpha"}:
        raise ValueError(f"Unsupported update channel: {channel}")
    suffix = "-alpha" if channel == "alpha" else ""
    platforms = {}
    for platform_key, pattern in PLATFORM_ASSETS.items():
        filename = pattern.format(version=version, suffix=suffix)
        path = assets_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing release asset: {path}")
        if path.stat().st_size <= 0:
            raise ValueError(f"Release asset is empty: {path}")
        platforms[platform_key] = {
            "filename": filename,
            "url": (
                f"https://github.com/{repository}/releases/download/"
                f"{quote(tag, safe='')}/{quote(filename)}"
            ),
            "sha256": sha256(path),
            "size": path.stat().st_size,
        }
    return {
        "schema": 1,
        "version": version,
        "display_version": f"{version} Alpha" if channel == "alpha" else version,
        "channel": channel,
        "platforms": platforms,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--channel", choices=("stable", "alpha"), required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    manifest = build_manifest(
        arguments.version,
        arguments.tag,
        arguments.repository,
        arguments.assets_dir,
        arguments.channel,
    )
    arguments.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
