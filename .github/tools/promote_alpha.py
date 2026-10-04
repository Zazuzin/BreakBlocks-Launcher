"""Promote a successful test build to a reviewed Alpha update release."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path


def gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True, encoding="utf-8")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate() -> dict:
    request = json.loads(Path(".github/alpha-update-test.json").read_text())
    if request["phase"] not in {"prepare", "publish", "verify"}:
        raise ValueError("Invalid release phase")
    if not re.fullmatch(r"\d+\.\d+\.\d+", request["version"]):
        raise ValueError("Invalid version")
    if request["tag"] != f"v{request['version']}-alpha":
        raise ValueError("Only Alpha releases are supported")
    if not re.fullmatch(r"[0-9a-f]{40}", request["source"]):
        raise ValueError("The source must be an exact commit")
    if type(request["run"]) is not int or request["run"] <= 0:
        raise ValueError("Invalid build run")
    repository = os.environ["GH_REPO"]
    run = json.loads(gh("api", f"repos/{repository}/actions/runs/{request['run']}"))
    if (
        run["status"] != "completed"
        or run["conclusion"] != "success"
        or run["head_sha"] != request["source"]
        or run["path"] != ".github/workflows/test-build.yml"
        or run["event"] != "push"
        or run["head_branch"] != "main"
    ):
        raise ValueError("The requested source does not have a successful main build")
    if request["phase"] in {"publish", "verify"}:
        if type(request.get("release_id")) is not int or request["release_id"] <= 0:
            raise ValueError("Missing reviewed draft release ID")
        for key in ("manifest_sha256", "checksums_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", request.get(key, "")):
                raise ValueError(f"Missing reviewed {key}")
    return request


def prepare(request: dict, assets: Path) -> None:
    source = Path("release-source").resolve()
    version = request["version"]
    metadata = subprocess.check_output(
        [sys.executable, "-c", "from app_config import APP_VERSION; print(APP_VERSION)"],
        cwd=source,
        text=True,
    ).strip()
    if metadata != f"{version} Alpha":
        raise ValueError("Source version does not match the Alpha request")
    documents = {"LICENSE", "PRIVACY.md", "TERMS.md", "THIRD-PARTY-NOTICES.md"}
    windows = assets / "BreakBlocks-Launcher"
    if not all((windows / name).is_file() for name in documents):
        raise ValueError("Windows licence or policy documents are missing")
    if not (windows / "third-party-licenses").is_dir():
        raise ValueError("Windows dependency licences are missing")
    if not (windows / "_internal/assets/audio/notification.wav").is_file():
        raise ValueError("The Windows notification sound is missing")
    shutil.make_archive(
        str(assets / f"BreakBlocks-Launcher-{version}-Windows-x86_64"),
        "zip",
        root_dir=assets,
        base_dir=windows.name,
    )
    shutil.rmtree(windows)
    portable = assets / f"BreakBlocks-Launcher-{version}-SteamDeck-x86_64.tar.gz"
    with tarfile.open(portable, "r:gz") as archive:
        members = {member.name: member for member in archive.getmembers()}
        root = "BreakBlocks-Launcher/"
        required = documents | {"BreakBlocks Launcher", "_internal/assets/audio/notification.wav"}
        if not all(root + name in members for name in required):
            raise ValueError("Portable Linux package is missing required files")
        if not members[root + "BreakBlocks Launcher"].mode & 0o111:
            raise ValueError("The portable Linux launcher is not executable")
        if not any(name.startswith(root + "third-party-licenses/") for name in members):
            raise ValueError("Linux dependency licences are missing")
    source_zip = assets / f"BreakBlocks-Launcher-{version}-source.zip"
    subprocess.run(
        [
            "git",
            "archive",
            "--format=zip",
            "--prefix=BreakBlocks-Launcher-Source/",
            f"--output={source_zip.resolve()}",
            "HEAD",
        ],
        cwd=source,
        check=True,
    )
    with zipfile.ZipFile(source_zip) as archive:
        required = documents | {
            "launcher_preferences.py",
            "settings_panel.py",
            "startup_updates.py",
        }
        if not all(
            "BreakBlocks-Launcher-Source/" + name in archive.namelist() for name in required
        ):
            raise ValueError("Source archive is missing required files")
    subprocess.run(
        [
            sys.executable,
            str(source / "tools/generate_update_manifest.py"),
            "--version",
            version,
            "--tag",
            request["tag"],
            "--channel",
            "alpha",
            "--repository",
            os.environ["GH_REPO"],
            "--assets-dir",
            str(assets),
            "--output",
            str(assets / "breakblocks-update.json"),
        ],
        check=True,
    )
    checksum_file = assets / "SHA256SUMS.txt"
    checksum_file.write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in sorted(assets.iterdir())),
        encoding="utf-8",
    )
    notes = Path("alpha-release-notes.md")
    changes = (source / "CHANGELOG.md").read_text(encoding="utf-8").split("## ")[1]
    notes.write_text(
        "Alpha release for launcher update testing.\n\n"
        + changes.split("\n", 1)[1].strip()
        + "\n\nTo test updating, use a launcher older than 0.9.27 and select the Alpha update channel. "
        "This release is not offered on the Stable channel.\n\n"
        "The Windows executable is unsigned, so Windows SmartScreen or your browser may warn. "
        "Download only from this official repository and verify SHA256SUMS.txt. "
        "Do not disable security protections.\n\n"
        "NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH "
        "MOJANG OR MICROSOFT. See the bundled licence, privacy notice, terms and third-party notices.\n",
        encoding="utf-8",
    )
    print(
        gh(
            "release",
            "create",
            request["tag"],
            *map(str, sorted(assets.iterdir())),
            "--target",
            request["source"],
            "--draft",
            "--prerelease",
            "--title",
            f"BreakBlocks Launcher {version} Alpha",
            "--notes-file",
            str(notes),
        )
    )
    print("REVIEWED_MANIFEST " + (assets / "breakblocks-update.json").read_text())
    print("REVIEWED_CHECKSUMS " + checksum_file.read_text())
    print("MANIFEST_SHA256=" + digest(assets / "breakblocks-update.json"))
    print("CHECKSUMS_SHA256=" + digest(checksum_file))


def publish(request: dict, assets: Path) -> None:
    repository = os.environ["GH_REPO"]
    tag = request["tag"]
    release_endpoint = f"repos/{repository}/releases/{request['release_id']}"
    release = json.loads(gh("api", release_endpoint))
    if not release["draft"] or not release["prerelease"]:
        raise ValueError("Expected an unpublished Alpha draft")
    if release["target_commitish"] != request["source"] or release["tag_name"] != tag:
        raise ValueError("Release source changed after review")
    for asset in release["assets"]:
        if Path(asset["name"]).name != asset["name"]:
            raise ValueError("Invalid release filename")
        with (assets / asset["name"]).open("wb") as output:
            subprocess.run(
                [
                    "gh",
                    "api",
                    f"repos/{repository}/releases/assets/{asset['id']}",
                    "-H",
                    "Accept: application/octet-stream",
                ],
                stdout=output,
                check=True,
            )
    if digest(assets / "breakblocks-update.json") != request["manifest_sha256"]:
        raise ValueError("The update manifest changed after review")
    checksum_file = assets / "SHA256SUMS.txt"
    if digest(checksum_file) != request["checksums_sha256"]:
        raise ValueError("The checksum list changed after review")
    listed = set()
    for line in checksum_file.read_text().splitlines():
        expected, name = line.split("  ", 1)
        if Path(name).name != name or name in listed:
            raise ValueError("Invalid checksum filename")
        listed.add(name)
        if digest(assets / name) != expected:
            raise ValueError(f"Release asset checksum mismatch: {name}")
    if {path.name for path in assets.iterdir()} != listed | {checksum_file.name}:
        raise ValueError("Unexpected release assets")
    manifest = json.loads((assets / "breakblocks-update.json").read_text())
    if manifest["version"] != request["version"] or manifest["channel"] != "alpha":
        raise ValueError("Incorrect manifest metadata")
    attached = {asset["name"]: asset for asset in release["assets"]}
    release_base = f"https://github.com/{repository}/releases/download"
    draft_ref = release["html_url"].rsplit("/", 1)[-1]
    for entry in manifest["platforms"].values():
        path = assets / entry["filename"]
        asset = attached[path.name]
        if (
            digest(path) != entry["sha256"]
            or path.stat().st_size != entry["size"]
            or asset["size"] != entry["size"]
            or entry["url"] != f"{release_base}/{tag}/{path.name}"
            or asset["browser_download_url"]
            not in {entry["url"], f"{release_base}/{draft_ref}/{path.name}"}
        ):
            raise ValueError("Manifest and release assets disagree")
    sys.path.insert(0, str(Path.cwd()))
    from launcher_update import UpdateClient

    # GitHub uses an untagged placeholder URL until a new draft is published.
    published_metadata = release | {
        "assets": [
            asset | {"browser_download_url": f"{release_base}/{tag}/{asset['name']}"}
            for asset in release["assets"]
        ]
    }
    for platform_key in manifest["platforms"]:
        update = UpdateClient("0.9.26", platform_key=platform_key)._parse_manifest(
            manifest, published_metadata, "alpha"
        )
        if update.version != request["version"]:
            raise ValueError("The launcher cannot parse this platform's update")
    published = json.loads(gh("api", "--method", "PATCH", release_endpoint, "-F", "draft=false"))
    if published["draft"] or published["tag_name"] != tag:
        raise ValueError("GitHub did not publish the requested release")
    print("Published " + published["html_url"])
    verify(request)


def verify(request: dict) -> None:
    repository = os.environ["GH_REPO"]
    release = json.loads(gh("api", f"repos/{repository}/releases/{request['release_id']}"))
    if (
        release["draft"]
        or not release["prerelease"]
        or release["tag_name"] != request["tag"]
        or release["target_commitish"] != request["source"]
    ):
        raise ValueError("The requested Alpha release is not published")
    attached = {asset["name"]: asset for asset in release["assets"]}
    for name, key in (
        ("breakblocks-update.json", "manifest_sha256"),
        ("SHA256SUMS.txt", "checksums_sha256"),
    ):
        if attached[name]["digest"] != "sha256:" + request[key]:
            raise ValueError("The published metadata changed after review")
    sys.path.insert(0, str(Path.cwd()))
    from launcher_update import UpdateClient

    releases_url = f"https://api.github.com/repos/{repository}/releases"

    def open_release(http_request, **kwargs):
        # Authenticate only the CI metadata request to avoid a shared runner's
        # anonymous API quota. Package and manifest downloads remain public.
        if http_request.full_url == releases_url:
            http_request.add_header("Authorization", "Bearer " + os.environ["GH_TOKEN"])
        return urllib.request.urlopen(http_request, **kwargs)

    def client(version: str, platform_key: str = "windows-x86_64"):
        return UpdateClient(version, opener=open_release, platform_key=platform_key)

    for attempt in range(6):
        update = client("0.9.26").check("alpha")
        if update is not None and update.version == request["version"]:
            break
        if attempt == 5:
            raise ValueError("Published Alpha update is not visible to an older launcher")
        time.sleep(5)
    for platform_key in ("linux-deb-x86_64", "linux-portable-x86_64", "linux-x86_64"):
        update = client("0.9.26", platform_key).check("alpha")
        if update is None or update.version != request["version"]:
            raise ValueError(f"No published update for {platform_key}")
    if client("0.9.26").check("stable") is not None:
        raise ValueError("The Alpha release must not be offered on the Stable channel")
    if client(request["version"]).check("alpha"):
        raise ValueError("The current launcher must not be offered the same version")
    print("Live updater checks passed for Windows, Ubuntu and portable Linux")
    print("Older Alpha detects update; Stable and current versions do not")


if __name__ == "__main__":
    request = validate()
    if sys.argv[1] == "validate":
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            for key in ("phase", "version", "tag", "source", "run"):
                output.write(f"{key}={request[key]}\n")
    elif sys.argv[1] == "release":
        assets = Path("release-assets")
        assets.mkdir(exist_ok=True)
        if request["phase"] == "verify":
            verify(request)
        else:
            (prepare if request["phase"] == "prepare" else publish)(request, assets)
    else:
        raise ValueError("Unknown operation")
