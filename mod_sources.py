#!/usr/bin/env python3
"""Trusted non-Modrinth sources and local Fabric JAR inspection."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from app_config import APP_USER_AGENT

USER_AGENT = APP_USER_AGENT
GITHUB_API = "https://api.github.com"
METEOR_BASE = "https://meteorclient.com"
APPROVED_DOWNLOAD_HOSTS = {
    "meteorclient.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}

SERVER_SEEKER_SOURCE = {
    "title": "Zazu's Server Seeker",
    "provider": "github",
    "repo": "Zazuzin/Zazus-Server-Seeker",
    "mod_ids": {"zazus-server-tool", "zazus-server-seeker", "zazus-server-scanner"},
    "asset_contains": "zazus-server-seeker",
}

ESSENTIAL_SOURCES = {
    "meteor-client": {
        "title": "Meteor Client",
        "provider": "meteor",
        "repo": "MeteorDevelopment/meteor-client",
        "mod_ids": {"meteor-client"},
    },
    "trouser-streak": {
        "title": "Trouser Streak",
        "provider": "github",
        "repo": "etianl/Trouser-Streak",
        "mod_ids": {"streak-addon"},
        "asset_contains": "trouser-streak",
    },
    "zazus-server-seeker": SERVER_SEEKER_SOURCE,
    # Compatibility for manifests created before the product-name correction.
    "zazus-server-scanner": SERVER_SEEKER_SOURCE,
}

ESSENTIAL_SOURCE_ALIASES = {"zazus-server-scanner": "zazus-server-seeker"}
KNOWN_MOD_IDS = {
    mod_id: source_key
    for source_key, source in ESSENTIAL_SOURCES.items()
    if source_key not in ESSENTIAL_SOURCE_ALIASES
    for mod_id in source["mod_ids"]
}


class SourceError(RuntimeError):
    pass


def safe_jar_filename(value: str) -> str:
    name = str(value or "")
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or "\0" in name
        or len(name) > 240
        or not name.lower().endswith(".jar")
    ):
        raise SourceError("The download returned an unsafe or unsupported JAR filename")
    return name


def read_fabric_metadata(path) -> dict:
    path = pathlib.Path(path)
    try:
        with zipfile.ZipFile(path) as archive:
            raw = archive.read("fabric.mod.json")
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict) or not data.get("id"):
            raise ValueError("missing mod id")
        return data
    except (OSError, KeyError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        raise SourceError(f"{path.name} is not a readable Fabric mod JAR: {error}") from error


def github_repo_from_metadata(metadata: dict) -> str | None:
    contact = metadata.get("contact") if isinstance(metadata.get("contact"), dict) else {}
    for key in ("sources", "repo", "issues", "homepage"):
        value = str(contact.get(key, ""))
        match = re.match(r"https://github\.com/([^/]+)/([^/#?]+)", value, re.IGNORECASE)
        if match:
            return f"{match.group(1)}/{match.group(2).removesuffix('.git')}"
    return None


def _numeric_version(value: str):
    match = re.match(r"^\s*(\d+(?:\.\d+)*)", str(value))
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


def _compare_versions(left, right):
    size = max(len(left), len(right))
    return (left + (0,) * (size - len(left))) > (right + (0,) * (size - len(right)))


def _matches_requirement(game_version: str, requirement: str) -> bool:
    requirement = str(requirement or "*").strip()
    if not requirement or requirement == "*":
        return True
    current = _numeric_version(game_version)
    for alternative in requirement.split("||"):
        clauses = re.findall(r"(>=|<=|>|<|=|~|\^)?\s*(\d+(?:\.\d+)*(?:\.[xX*])?)", alternative)
        if not clauses:
            if requirement == game_version:
                return True
            continue
        matches = True
        for operator, wanted_text in clauses:
            if wanted_text.endswith((".*", ".x", ".X")):
                prefix = wanted_text[:-2]
                matches = matches and (
                    game_version == prefix or game_version.startswith(prefix + ".")
                )
                continue
            wanted = _numeric_version(wanted_text)
            if operator == ">=":
                matches = matches and (current == wanted or _compare_versions(current, wanted))
            elif operator == ">":
                matches = matches and _compare_versions(current, wanted)
            elif operator == "<=":
                matches = matches and not _compare_versions(current, wanted)
            elif operator == "<":
                matches = matches and current != wanted and not _compare_versions(current, wanted)
            elif operator in {"~", "^"}:
                prefix_size = 2 if len(wanted) > 1 else 1
                matches = matches and current[:prefix_size] == wanted[:prefix_size]
            else:
                matches = matches and current == wanted
        if matches:
            return True
    return False


def metadata_supports_game(metadata: dict, game_version: str) -> bool:
    depends = metadata.get("depends") if isinstance(metadata.get("depends"), dict) else {}
    requirement = depends.get("minecraft", "*")
    if isinstance(requirement, list):
        return any(_matches_requirement(game_version, item) for item in requirement)
    return _matches_requirement(game_version, requirement)


def _game_version_in_filename(filename: str, game_version: str) -> bool:
    # A release asset commonly ends in ``-26.2.jar``.  The dot before ``jar``
    # is a file-extension separator, not another part of the game version.
    # Only reject a following dot when it is followed by another digit, which
    # prevents 26.2 from accidentally matching 26.2.1 without rejecting
    # 26.2.jar.
    pattern = rf"(?<![0-9.]){re.escape(str(game_version))}(?![0-9]|\.[0-9])"
    return bool(re.search(pattern, filename, re.IGNORECASE))


class SourceClient:
    def __init__(self, opener=None):
        self.opener = opener or urllib.request.urlopen

    def request_json(self, url: str):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json, application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with self.opener(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise SourceError(f"Update source returned HTTP {error.code}") from error
        except urllib.error.URLError as error:
            raise SourceError(f"Could not connect to update source: {error.reason}") from error
        except Exception as error:
            raise SourceError(f"Could not read update source: {error}") from error

    def meteor_latest(self, game_version: str):
        stats = self.request_json(METEOR_BASE + "/api/stats")
        if not isinstance(stats, dict):
            raise SourceError("Meteor returned an invalid build catalogue")
        build = (stats.get("builds") or {}).get(str(game_version))
        if build is None:
            return None
        version_number = f"{game_version}-{build}"
        return {
            "provider": "meteor",
            "source_key": "meteor-client",
            "repo": ESSENTIAL_SOURCES["meteor-client"]["repo"],
            "title": "Meteor Client",
            "version_id": version_number,
            "version_number": version_number,
            "filename": f"meteor-client-{version_number}.jar",
            "url": METEOR_BASE
            + "/api/download?"
            + urllib.parse.urlencode({"version": game_version}),
            "size": 0,
            "game_version": str(game_version),
            "expected_mod_ids": sorted(ESSENTIAL_SOURCES["meteor-client"]["mod_ids"]),
        }

    def github_releases(self, repo: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(repo)):
            raise SourceError("The mod contains an invalid GitHub repository address")
        releases = self.request_json(
            f"{GITHUB_API}/repos/{repo}/releases?" + urllib.parse.urlencode({"per_page": 30})
        )
        if not isinstance(releases, list):
            raise SourceError(f"GitHub returned an invalid release catalogue for {repo}")
        return releases

    def github_latest(
        self,
        repo: str,
        game_version: str,
        *,
        title=None,
        source_key=None,
        mod_ids=(),
        asset_contains=None,
    ):
        releases = self.github_releases(repo)
        for allow_prerelease in (False, True):
            for release in releases:
                if release.get("draft") or bool(release.get("prerelease")) != allow_prerelease:
                    continue
                candidates = []
                for asset in release.get("assets", []):
                    name = str(asset.get("name", ""))
                    if not name.lower().endswith(".jar") or not _game_version_in_filename(
                        name, game_version
                    ):
                        continue
                    if asset_contains and asset_contains.casefold() not in name.casefold():
                        continue
                    if asset.get("browser_download_url"):
                        candidates.append(asset)
                if not candidates:
                    continue
                asset = candidates[0]
                return {
                    "provider": "github",
                    "source_key": source_key,
                    "repo": repo,
                    "title": title or repo.rsplit("/", 1)[-1],
                    "version_id": str(release.get("id") or release.get("tag_name")),
                    "version_number": str(
                        release.get("tag_name") or release.get("name") or "Latest"
                    ),
                    "filename": safe_jar_filename(asset.get("name", "")),
                    "url": asset["browser_download_url"],
                    "size": max(0, int(asset.get("size", 0))),
                    "game_version": str(game_version),
                    "expected_mod_ids": sorted(set(mod_ids)),
                }
        return None

    def essential_latest(self, source_key: str, game_version: str):
        source = ESSENTIAL_SOURCES.get(source_key)
        if not source:
            raise SourceError(f"Unknown Essentials source: {source_key}")
        if source["provider"] == "meteor":
            return self.meteor_latest(game_version)
        return self.github_latest(
            source["repo"],
            game_version,
            title=source["title"],
            source_key=source_key,
            mod_ids=source["mod_ids"],
            asset_contains=source.get("asset_contains"),
        )

    def generic_github_latest(self, repo: str, game_version: str, record: dict):
        return self.github_latest(
            repo,
            game_version,
            title=record.get("title"),
            mod_ids={record.get("mod_id")} if record.get("mod_id") else set(),
        )

    def open_download(self, url: str):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in APPROVED_DOWNLOAD_HOSTS:
            raise SourceError("The mod download was not hosted by an approved source")
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            response = self.opener(request, timeout=90)
            final_host = (
                urllib.parse.urlsplit(response.geturl()).hostname
                if hasattr(response, "geturl")
                else parsed.hostname
            )
            if final_host not in APPROVED_DOWNLOAD_HOSTS:
                response.close()
                raise SourceError("The mod download redirected to an unapproved host")
            return response
        except SourceError:
            raise
        except Exception as error:
            raise SourceError(f"Mod download failed: {error}") from error

    def download(self, descriptor: dict, destination, progress=None):
        destination = pathlib.Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        filename = safe_jar_filename(descriptor.get("filename", ""))
        temporary = destination / (filename + ".part")
        target = destination / filename
        digest = hashlib.sha512()
        written = 0
        expected_size = max(0, int(descriptor.get("size", 0)))
        try:
            with self.open_download(descriptor["url"]) as response, temporary.open("wb") as output:
                while chunk := response.read(256 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
                    if progress:
                        percent = (
                            int((written / max(1, expected_size)) * 100) if expected_size else 50
                        )
                        progress(
                            min(99, percent), f"Downloading {descriptor.get('title', filename)}…"
                        )
            metadata = read_fabric_metadata(temporary)
            expected_ids = set(descriptor.get("expected_mod_ids") or ())
            if expected_ids and metadata.get("id") not in expected_ids:
                raise SourceError(
                    f"Downloaded {descriptor.get('title', filename)} reported unexpected mod ID {metadata.get('id')}"
                )
            if not metadata_supports_game(metadata, descriptor.get("game_version", "")):
                raise SourceError(
                    f"Downloaded {descriptor.get('title', filename)} is not compatible with Minecraft {descriptor.get('game_version')}"
                )
            os.replace(temporary, target)
            return target, metadata, digest.hexdigest()
        finally:
            temporary.unlink(missing_ok=True)
