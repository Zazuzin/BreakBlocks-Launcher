"""Release discovery, verified downloads, and portable self-update staging."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import time
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app_config import (
    APP_USER_AGENT,
    DEFAULT_UPDATE_CHANNEL,
    GITHUB_RELEASES_API,
    UPDATE_MANIFEST_NAME,
)
from process_environment import system_process_environment

ProgressCallback = Callable[[int, str], None]
VERSION_PATTERN = re.compile(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
INSTALL_SOURCE = "source"
INSTALL_WINDOWS_PORTABLE = "windows-portable"
INSTALL_LINUX_DEB = "linux-deb"
INSTALL_LINUX_PORTABLE = "linux-portable"


class UpdateError(RuntimeError):
    """Raised when release metadata or a downloaded update is invalid."""


@dataclass(frozen=True)
class UpdateAsset:
    url: str
    sha256: str
    size: int
    filename: str


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    display_version: str
    channel: str
    notes: str
    release_url: str
    asset: UpdateAsset


def version_tuple(value: str) -> tuple[int, int, int]:
    """Return the numeric three-part version embedded in a display or tag value."""
    match = VERSION_PATTERN.search(value)
    if match is None:
        raise ValueError(f"Invalid launcher version: {value!r}")
    return tuple(int(part) for part in match.groups())


def current_platform_key() -> str:
    """Return the release-manifest key for this operating system and CPU."""
    machine = platform.machine().lower()
    architecture = "x86_64" if machine in {"amd64", "x86_64"} else machine
    if os.name == "nt":
        return f"windows-{architecture}"
    if sys.platform.startswith("linux"):
        return f"linux-{architecture}"
    return f"{sys.platform}-{architecture}"


def detect_install_type(app_directory: pathlib.Path) -> str:
    """Identify how this launcher copy must be updated."""
    app_directory = app_directory.resolve()
    if app_directory.name != "app":
        return INSTALL_SOURCE

    install_root = app_directory.parent
    if os.name == "nt" and (install_root / "BreakBlocks Launcher.exe").is_file():
        return INSTALL_WINDOWS_PORTABLE
    if sys.platform.startswith("linux"):
        if (install_root / ".deb-package").is_file():
            return INSTALL_LINUX_DEB
        if (install_root / "BreakBlocks Launcher").is_file():
            return INSTALL_LINUX_PORTABLE
    return INSTALL_SOURCE


def platform_key_for_install_type(install_type: str) -> str:
    """Return the update-manifest key for a detected installation type."""
    machine = platform.machine().lower()
    architecture = "x86_64" if machine in {"amd64", "x86_64"} else machine
    prefixes = {
        INSTALL_WINDOWS_PORTABLE: "windows",
        INSTALL_LINUX_DEB: "linux-deb",
        INSTALL_LINUX_PORTABLE: "linux-portable",
    }
    prefix = prefixes.get(install_type)
    if install_type == INSTALL_SOURCE:
        if os.name == "nt":
            prefix = "windows"
        elif sys.platform.startswith("linux"):
            prefix = "linux-deb"
    if prefix is None:
        return current_platform_key()
    return f"{prefix}-{architecture}"


def detect_install_root(app_directory: pathlib.Path) -> pathlib.Path | None:
    """Locate a packaged launcher root; source checkouts are intentionally ignored."""
    if getattr(sys, "frozen", False):
        root = pathlib.Path(sys.executable).resolve().parent
    elif app_directory.name == "app":
        root = app_directory.resolve().parent
    else:
        return None

    launcher_name = "BreakBlocks Launcher.exe" if os.name == "nt" else "BreakBlocks Launcher"
    return root if (root / launcher_name).is_file() else None


class UpdateClient:
    """Read the signed-release feed and stage verified portable packages."""

    def __init__(
        self,
        current_version: str,
        releases_url: str = GITHUB_RELEASES_API,
        opener: Callable[..., Any] | None = None,
        platform_key: str | None = None,
    ) -> None:
        self.current_version = current_version
        self.releases_url = releases_url
        self._open = opener or urllib.request.urlopen
        self.platform_key = platform_key or current_platform_key()

    def check(self, channel: str = DEFAULT_UPDATE_CHANNEL) -> UpdateInfo | None:
        """Return the newest compatible update, or ``None`` when current."""
        if channel not in {"stable", "alpha"}:
            raise ValueError(f"Unsupported update channel: {channel}")
        releases = self._get_json(self.releases_url)
        if not isinstance(releases, list):
            raise UpdateError("The release service returned an invalid response")

        candidates: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
        for release in releases:
            if not isinstance(release, dict) or release.get("draft"):
                continue
            if channel == "stable" and release.get("prerelease"):
                continue
            try:
                release_version = version_tuple(str(release.get("tag_name", "")))
            except ValueError:
                continue
            if release_version > version_tuple(self.current_version):
                candidates.append((release_version, release))

        for _release_version, release in sorted(candidates, reverse=True, key=lambda item: item[0]):
            manifest_asset = next(
                (
                    asset
                    for asset in release.get("assets", [])
                    if asset.get("name") == UPDATE_MANIFEST_NAME
                ),
                None,
            )
            if manifest_asset is None:
                continue
            manifest = self._get_json(manifest_asset.get("browser_download_url", ""))
            return self._parse_manifest(manifest, release, channel)
        return None

    def download(
        self,
        update: UpdateInfo,
        destination: pathlib.Path,
        progress: ProgressCallback | None = None,
    ) -> pathlib.Path:
        """Download an update package and verify its size and SHA-256 digest."""
        callback = progress or (lambda _percent, _message: None)
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / update.asset.filename
        temporary = target.with_suffix(f"{target.suffix}.part")
        request = self._request(update.asset.url)
        digest = hashlib.sha256()
        received = 0
        try:
            with self._open(request, timeout=90) as source, temporary.open("wb") as output:
                content_length = int(source.headers.get("Content-Length", 0) or 0)
                expected = update.asset.size or content_length
                while block := source.read(256 * 1024):
                    output.write(block)
                    digest.update(block)
                    received += len(block)
                    if expected:
                        callback(min(99, int(received * 100 / expected)), "Downloading update")
            if update.asset.size and received != update.asset.size:
                raise UpdateError(
                    f"Update download size mismatch: expected {update.asset.size}, received {received}"
                )
            if digest.hexdigest() != update.asset.sha256:
                raise UpdateError("Update download failed its SHA-256 verification")
            temporary.replace(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        callback(100, "Update downloaded")
        return target

    def stage(self, archive: pathlib.Path, staging_directory: pathlib.Path) -> pathlib.Path:
        """Safely extract a verified package and return its launcher root."""
        if staging_directory.exists():
            shutil.rmtree(staging_directory)
        staging_directory.mkdir(parents=True)
        if archive.suffix.lower() == ".zip":
            self._extract_zip(archive, staging_directory)
        elif archive.name.endswith((".tar.gz", ".tgz")):
            self._extract_tar(archive, staging_directory)
        else:
            raise UpdateError(f"Unsupported update package: {archive.name}")

        entries = [path for path in staging_directory.iterdir() if path.name != "__MACOSX"]
        payload = entries[0] if len(entries) == 1 and entries[0].is_dir() else staging_directory
        launcher_name = "BreakBlocks Launcher.exe" if os.name == "nt" else "BreakBlocks Launcher"
        if not (payload / launcher_name).is_file():
            raise UpdateError("The update package does not contain the launcher executable")
        return payload

    def _parse_manifest(
        self,
        manifest: Any,
        release: dict[str, Any],
        selected_channel: str,
    ) -> UpdateInfo:
        if not isinstance(manifest, dict) or manifest.get("schema") != 1:
            raise UpdateError("The update manifest uses an unsupported schema")
        version = str(manifest.get("version", ""))
        try:
            manifest_version = version_tuple(version)
            release_version = version_tuple(str(release.get("tag_name", "")))
            if manifest_version != release_version:
                raise UpdateError("The update manifest version does not match its release tag")
            if manifest_version <= version_tuple(self.current_version):
                raise UpdateError("The release manifest does not contain a newer version")
        except ValueError as error:
            raise UpdateError(str(error)) from error

        channel = str(manifest.get("channel", "")).lower()
        if channel not in {"stable", "alpha"}:
            raise UpdateError("The update manifest contains an invalid channel")
        if selected_channel == "stable" and channel != "stable":
            raise UpdateError("An alpha release was returned for the stable channel")

        platforms = manifest.get("platforms", {})
        platform_data = platforms.get(self.platform_key) if isinstance(platforms, dict) else None
        if (
            platform_data is None
            and isinstance(platforms, dict)
            and self.platform_key.startswith("linux-")
        ):
            # Accept the original portable Linux key during the transition to
            # separate Ubuntu and Steam Deck packages.
            platform_data = platforms.get(current_platform_key())
        if not isinstance(platform_data, dict):
            raise UpdateError(f"No update is available for {self.platform_key}")
        url = str(platform_data.get("url", ""))
        digest = str(platform_data.get("sha256", "")).lower()
        filename = str(platform_data.get("filename") or pathlib.PurePosixPath(url).name)
        if not url.startswith("https://"):
            raise UpdateError("Update package URLs must use HTTPS")
        if not SHA256_PATTERN.fullmatch(digest):
            raise UpdateError("The update manifest contains an invalid SHA-256 digest")
        if pathlib.PurePath(filename).name != filename:
            raise UpdateError("The update manifest contains an invalid filename")
        try:
            size = int(platform_data.get("size", 0))
        except (TypeError, ValueError) as error:
            raise UpdateError("The update manifest contains an invalid package size") from error
        if size <= 0:
            raise UpdateError("The update manifest contains an invalid package size")

        matching_asset = next(
            (
                release_asset
                for release_asset in release.get("assets", [])
                if release_asset.get("name") == filename
            ),
            None,
        )
        if matching_asset is None or matching_asset.get("browser_download_url") != url:
            raise UpdateError("The update package is not attached to the selected release")

        return UpdateInfo(
            version=version,
            display_version=str(manifest.get("display_version") or version),
            channel=channel,
            notes=str(manifest.get("notes") or release.get("body") or ""),
            release_url=str(release.get("html_url") or ""),
            asset=UpdateAsset(url=url, sha256=digest, size=size, filename=filename),
        )

    def _get_json(self, url: str) -> Any:
        if not url.startswith("https://"):
            raise UpdateError("Release metadata URLs must use HTTPS")
        request = self._request(url)
        try:
            with self._open(request, timeout=30) as response:
                return json.load(response)
        except UpdateError:
            raise
        except Exception as error:
            raise UpdateError(f"Could not contact the update service: {error}") from error

    @staticmethod
    def _request(url: str) -> urllib.request.Request:
        return urllib.request.Request(
            url,
            headers={
                "User-Agent": APP_USER_AGENT,
                "Accept": "application/vnd.github+json, application/json",
            },
        )

    @staticmethod
    def _extract_zip(archive: pathlib.Path, destination: pathlib.Path) -> None:
        root = destination.resolve()
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                target = (root / member.filename).resolve()
                if target != root and root not in target.parents:
                    raise UpdateError(f"Unsafe path in update package: {member.filename}")
            # Every member path has been resolved and confined to root above.
            source.extractall(root)  # nosec B202

    @staticmethod
    def _extract_tar(archive: pathlib.Path, destination: pathlib.Path) -> None:
        root = destination.resolve()
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                target = (root / member.name).resolve()
                if target != root and root not in target.parents:
                    raise UpdateError(f"Unsafe path in update package: {member.name}")
                if member.issym() or member.islnk():
                    link_target = (target.parent / member.linkname).resolve()
                    if link_target != root and root not in link_target.parents:
                        raise UpdateError(f"Unsafe link in update package: {member.name}")
            # Every member path and link target has been confined to root above.
            source.extractall(root)  # nosec B202


def start_self_update(staged_root: pathlib.Path, install_root: pathlib.Path) -> None:
    """Start an external helper that replaces the package after this process exits."""
    staged_root = staged_root.resolve()
    install_root = install_root.resolve()
    if staged_root == install_root or install_root in staged_root.parents:
        raise UpdateError("The staged update must be outside the current installation")
    if not os.access(install_root.parent, os.W_OK):
        raise UpdateError("The launcher folder is not writable by the current user")

    if os.name == "nt":
        _start_windows_update(staged_root, install_root)
    elif sys.platform.startswith("linux"):
        _start_linux_update(staged_root, install_root)
    else:
        raise UpdateError("Automatic installation is not supported on this platform")


def debian_install_command(archive: pathlib.Path) -> list[str]:
    """Build the non-shell command used to install a verified Ubuntu package."""
    archive = archive.resolve()
    if not sys.platform.startswith("linux"):
        raise UpdateError("Ubuntu package installation is available only on Linux")
    if not archive.is_file() or archive.suffix.lower() != ".deb":
        raise UpdateError("The downloaded Ubuntu update is not a valid .deb package")
    pkexec = shutil.which("pkexec")
    apt_get = shutil.which("apt-get")
    if not pkexec or not apt_get:
        raise UpdateError(
            "The system update tools are unavailable. Open the downloaded .deb file "
            "with your package installer instead."
        )
    return [pkexec, apt_get, "install", "--yes", str(archive)]


def install_debian_update(archive: pathlib.Path) -> None:
    """Ask the desktop for administrator approval and install a verified .deb."""
    result = subprocess.run(
        debian_install_command(archive),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=10 * 60,
        check=False,
        env=system_process_environment(),
    )
    if result.returncode:
        detail = (result.stdout or "").strip()
        if result.returncode in {126, 127}:
            detail = "Administrator approval was cancelled or unavailable."
        elif detail:
            detail = detail[-1600:]
        else:
            detail = f"The package installer exited with code {result.returncode}."
        raise UpdateError(detail)


def restart_debian_launcher() -> None:
    """Start the newly installed Ubuntu launcher as the current desktop user."""
    executable = pathlib.Path("/usr/bin/breakblocks-launcher")
    if not executable.is_file():
        raise UpdateError("The updated launcher command could not be found")
    subprocess.Popen(
        [str(executable)],
        start_new_session=True,
        close_fds=True,
        env=system_process_environment(),
    )


def _start_windows_update(staged_root: pathlib.Path, install_root: pathlib.Path) -> None:
    script = pathlib.Path(tempfile.gettempdir()) / f"breakblocks-update-{os.getpid()}.ps1"
    script.write_text(
        textwrap.dedent("""
            param(
                [int]$LauncherProcessId,
                [string]$StagedRoot,
                [string]$InstallRoot
            )
            $ErrorActionPreference = "Stop"
            Wait-Process -Id $LauncherProcessId -ErrorAction SilentlyContinue
            $backup = "$InstallRoot.previous"
            if (Test-Path -LiteralPath $backup) {
                Remove-Item -LiteralPath $backup -Recurse -Force
            }
            try {
                Move-Item -LiteralPath $InstallRoot -Destination $backup
                Move-Item -LiteralPath $StagedRoot -Destination $InstallRoot
                Start-Process -FilePath (Join-Path $InstallRoot "BreakBlocks Launcher.exe")
                Remove-Item -LiteralPath $backup -Recurse -Force
            } catch {
                if ((Test-Path -LiteralPath $backup) -and -not (Test-Path -LiteralPath $InstallRoot)) {
                    Move-Item -LiteralPath $backup -Destination $InstallRoot
                }
                throw
            }
            Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
            """).lstrip(),
        encoding="utf-8",
    )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-LauncherProcessId",
            str(os.getpid()),
            "-StagedRoot",
            str(staged_root),
            "-InstallRoot",
            str(install_root),
        ],
        creationflags=creation_flags,
        close_fds=True,
        env=system_process_environment(),
    )


def _start_linux_update(staged_root: pathlib.Path, install_root: pathlib.Path) -> None:
    script = pathlib.Path(tempfile.gettempdir()) / f"breakblocks-update-{os.getpid()}.sh"
    script.write_text(
        textwrap.dedent("""
            #!/usr/bin/env sh
            set -eu
            launcher_pid="$1"
            staged_root="$2"
            install_root="$3"
            while kill -0 "$launcher_pid" 2>/dev/null; do sleep 1; done
            backup="${install_root}.previous"
            rm -rf -- "$backup"
            if mv -- "$install_root" "$backup" && mv -- "$staged_root" "$install_root"; then
                chmod +x "$install_root/BreakBlocks Launcher"
                "$install_root/BreakBlocks Launcher" >/dev/null 2>&1 &
                rm -rf -- "$backup"
            else
                if [ -d "$backup" ] && [ ! -e "$install_root" ]; then
                    mv -- "$backup" "$install_root"
                fi
                exit 1
            fi
            rm -f -- "$0"
            """).lstrip(),
        encoding="utf-8",
    )
    script.chmod(0o700)
    subprocess.Popen(
        [str(script), str(os.getpid()), str(staged_root), str(install_root)],
        start_new_session=True,
        close_fds=True,
        env=system_process_environment(),
    )


def should_check(last_checked_at: float, frequency: str, now: float | None = None) -> bool:
    """Return whether the configured update interval has elapsed."""
    intervals = {"startup": 0, "daily": 24 * 60 * 60, "weekly": 7 * 24 * 60 * 60}
    if frequency == "never":
        return False
    if frequency not in intervals:
        raise ValueError(f"Unsupported update frequency: {frequency}")
    current_time = time.time() if now is None else now
    return current_time - max(0, last_checked_at) >= intervals[frequency]
