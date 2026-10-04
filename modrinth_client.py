#!/usr/bin/env python3
"""Modrinth browsing and per-instance mod management for BreakBlocks Launcher."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import mod_sources
from app_config import APP_USER_AGENT

API_BASE = "https://api.modrinth.com/v2"
USER_AGENT = APP_USER_AGENT
SUPPORTED_LOADERS = {
    "Fabric": "fabric",
    "Forge": "forge",
    "NeoForge": "neoforge",
    "Quilt": "quilt",
}
SERVER_ONLY_ENVIRONMENTS = {"server_only", "dedicated_server_only"}
CLIENT_ENVIRONMENTS = (
    "client_and_server",
    "client_only",
    "client_only_server_optional",
    "singleplayer_only",
    "client_or_server",
    "client_or_server_prefers_both",
    "unknown",
)


class ModrinthError(RuntimeError):
    pass


def safe_filename(value: str) -> str:
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
        raise ModrinthError("Modrinth returned an unsafe or unsupported mod filename")
    return name


def file_hash(path: pathlib.Path, algorithm: str = "sha512") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class ModrinthClient:
    def __init__(self, opener=None):
        self.opener = opener or urllib.request.urlopen

    def request_json(self, route: str, params=None):
        url = API_BASE + route
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with self.opener(request, timeout=25) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                response_detail = error.read(2048).decode("utf-8", errors="replace").strip()
            except Exception:
                response_detail = ""
            suffix = f": {response_detail}" if response_detail else ""
            raise ModrinthError(f"Modrinth returned HTTP {error.code}{suffix}") from error
        except urllib.error.URLError as error:
            raise ModrinthError(f"Could not connect to Modrinth: {error.reason}") from error
        except Exception as error:
            raise ModrinthError(f"Modrinth request failed: {error}") from error

    def search(
        self, query: str, game_version: str, loader: str, *, offset=0, limit=30, index="relevance"
    ):
        loader_name = SUPPORTED_LOADERS.get(loader)
        if not loader_name:
            raise ModrinthError("This instance does not use a supported mod loader")
        facets = [
            ["project_type:mod"],
            [f"versions:{game_version}"],
            [f"categories:{loader_name}"],
            [f"environment:{environment}" for environment in CLIENT_ENVIRONMENTS],
        ]
        data = self.request_json(
            "/search",
            {
                "query": query.strip(),
                "facets": json.dumps(facets, separators=(",", ":")),
                "index": index,
                "offset": max(0, int(offset)),
                "limit": min(100, max(1, int(limit))),
            },
        )
        data["hits"] = [
            hit
            for hit in data.get("hits", [])
            if not hit.get("environment")
            or not set(hit.get("environment", [])).issubset(SERVER_ONLY_ENVIRONMENTS)
        ]
        return data

    def project(self, project_id: str):
        return self.request_json("/project/" + urllib.parse.quote(str(project_id), safe=""))

    def version(self, version_id: str):
        return self.request_json("/version/" + urllib.parse.quote(str(version_id), safe=""))

    def version_from_hash(self, digest: str, algorithm="sha512"):
        return self.request_json(
            "/version_file/" + urllib.parse.quote(str(digest), safe=""),
            {"algorithm": algorithm},
        )

    def project_versions(self, project_id: str, game_version: str, loader: str):
        loader_name = SUPPORTED_LOADERS.get(loader)
        if not loader_name:
            return []
        return self.request_json(
            "/project/" + urllib.parse.quote(str(project_id), safe="") + "/version",
            {
                "loaders": json.dumps([loader_name], separators=(",", ":")),
                "game_versions": json.dumps([game_version], separators=(",", ":")),
                "include_changelog": "false",
            },
        )

    def compatible(self, version: dict, game_version: str, loader: str) -> bool:
        loader_name = SUPPORTED_LOADERS.get(loader)
        return (
            loader_name in version.get("loaders", [])
            and game_version in version.get("game_versions", [])
            and version.get("environment") not in SERVER_ONLY_ENVIRONMENTS
            and version.get("status", "listed") in {"listed", "unknown"}
        )

    def latest_version(self, project_id: str, game_version: str, loader: str):
        versions = [
            version
            for version in self.project_versions(project_id, game_version, loader)
            if self.compatible(version, game_version, loader)
        ]
        for channel in ("release", "beta", "alpha"):
            match = next(
                (version for version in versions if version.get("version_type") == channel), None
            )
            if match:
                return match
        return versions[0] if versions else None

    def open_download(self, url: str):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "cdn.modrinth.com":
            raise ModrinthError("Mod download was not hosted on Modrinth's approved CDN")
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            return self.opener(request, timeout=60)
        except Exception as error:
            raise ModrinthError(f"Mod download failed: {error}") from error


class ModManager:
    MANIFEST_VERSION = 2

    def __init__(
        self,
        instance_root,
        game_version: str,
        loader: str,
        *,
        client=None,
        source_client=None,
        progress=None,
    ):
        self.instance_root = pathlib.Path(instance_root).resolve()
        self.game_version = str(game_version)
        self.loader = str(loader)
        if self.loader not in SUPPORTED_LOADERS:
            raise ModrinthError(
                "Choose a Fabric, Forge, NeoForge or Quilt instance to install mods"
            )
        self.client = client or ModrinthClient()
        self.source_client = source_client or mod_sources.SourceClient()
        self.progress = progress or (lambda _percent, _message: None)
        self.minecraft_dir = self.instance_root / "minecraft"
        self.mods_dir = self.minecraft_dir / "mods"
        self.manifest_path = self.instance_root / "modrinth-mods.json"
        self.mods_dir.mkdir(parents=True, exist_ok=True)

    def load_manifest(self):
        if not self.manifest_path.exists():
            return {"format": self.MANIFEST_VERSION, "mods": {}}
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if data.get("format") not in {1, self.MANIFEST_VERSION} or not isinstance(
                data.get("mods"), dict
            ):
                raise ValueError("unsupported manifest")
            if data.get("format") == 1:
                data["format"] = self.MANIFEST_VERSION
                for project_id, record in data["mods"].items():
                    record.setdefault("provider", "modrinth")
                    record.setdefault("project_id", project_id)
                    record.setdefault("managed", True)
            return data
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise ModrinthError(
                f"The instance's Modrinth manifest could not be read: {error}"
            ) from error

    def save_manifest(self, manifest):
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.manifest_path)

    def installed(self):
        manifest = self.sync_local_inventory()
        records = []
        for record_id, record in manifest["mods"].items():
            item = copy.deepcopy(record)
            item["record_id"] = record_id
            records.append(item)
        return sorted(records, key=lambda record: str(record.get("title", "")).casefold())

    def unmanaged_files(self):
        return sorted(
            self.record_path(record)
            for record in self.installed()
            if record.get("provider") == "local" and self.record_path(record).is_file()
        )

    def _local_record_id(self, metadata, filename, manifest):
        mod_id = re.sub(r"[^a-z0-9_.-]+", "-", str(metadata.get("id", "unknown")).casefold())
        source_key = mod_sources.KNOWN_MOD_IDS.get(mod_id)
        base = f"external:{source_key}" if source_key else f"local:{mod_id}"
        candidate = base
        suffix = 2
        while (
            candidate in manifest["mods"]
            and manifest["mods"][candidate].get("filename") != filename
        ):
            candidate = f"{base}:{suffix}"
            suffix += 1
        return candidate, source_key

    @staticmethod
    def _link_known_external_source(record):
        """Attach the official update source to an existing known mod record."""
        source_key = mod_sources.KNOWN_MOD_IDS.get(str(record.get("mod_id", "")).strip().casefold())
        if not source_key:
            return False
        source = mod_sources.ESSENTIAL_SOURCES[source_key]
        expected = {
            "provider": source["provider"],
            "source_key": source_key,
            "repo": source.get("repo"),
            "title": source["title"],
        }
        changed = any(record.get(key) != value for key, value in expected.items())
        if changed:
            record.update(expected)
        return changed

    def sync_local_inventory(self, persist=True):
        manifest = self.load_manifest()
        records = manifest["mods"]
        changed = False
        files = sorted(self.mods_dir.glob("*.jar")) + sorted(self.mods_dir.glob("*.jar.disabled"))
        present = {}
        for path in files:
            filename = path.name[:-9] if path.name.endswith(".disabled") else path.name
            try:
                safe_filename(filename)
            except ModrinthError:
                continue
            present[filename] = (path, not path.name.endswith(".disabled"))

        by_filename = {
            record.get("filename"): key for key, record in records.items() if record.get("filename")
        }
        for filename, (path, enabled) in present.items():
            file_stat = path.stat()
            record_id = by_filename.get(filename)
            if record_id:
                record = records[record_id]
                if self._link_known_external_source(record):
                    changed = True
                if bool(record.get("enabled", True)) != enabled:
                    record["enabled"] = enabled
                    changed = True
                if not record.get("managed", True):
                    file_changed = (
                        record.get("file_size") != file_stat.st_size
                        or record.get("file_mtime_ns") != file_stat.st_mtime_ns
                    )
                    if file_changed:
                        current_hash = file_hash(path, "sha512")
                        try:
                            metadata = mod_sources.read_fabric_metadata(path)
                        except mod_sources.SourceError:
                            metadata = {
                                "id": pathlib.Path(filename).stem,
                                "name": pathlib.Path(filename).stem,
                                "version": "Unknown",
                            }
                        source_key = mod_sources.KNOWN_MOD_IDS.get(
                            str(metadata.get("id", "")).casefold()
                        )
                        github_repo = mod_sources.github_repo_from_metadata(metadata)
                        provider = "local"
                        title = (
                            metadata.get("name")
                            or metadata.get("id")
                            or pathlib.Path(filename).stem
                        )
                        if source_key:
                            source = mod_sources.ESSENTIAL_SOURCES[source_key]
                            provider = source["provider"]
                            title = source["title"]
                            github_repo = source.get("repo", github_repo)
                        elif github_repo:
                            provider = "github"
                        record.update(
                            {
                                "provider": provider,
                                "source_key": source_key,
                                "repo": github_repo,
                                "mod_id": metadata.get("id"),
                                "title": title,
                                "version_id": str(metadata.get("version", "Unknown")),
                                "version_number": str(metadata.get("version", "Unknown")),
                                "sha512": current_hash,
                                "file_size": file_stat.st_size,
                                "file_mtime_ns": file_stat.st_mtime_ns,
                                "installed_at": int(file_stat.st_mtime),
                            }
                        )
                        changed = True
                continue
            try:
                metadata = mod_sources.read_fabric_metadata(path)
                sha512 = file_hash(path, "sha512")
            except (OSError, mod_sources.SourceError):
                metadata = {
                    "id": pathlib.Path(filename).stem,
                    "name": pathlib.Path(filename).stem,
                    "version": "Unknown",
                }
                sha512 = file_hash(path, "sha512")
            record_id, source_key = self._local_record_id(metadata, filename, manifest)
            github_repo = mod_sources.github_repo_from_metadata(metadata)
            if source_key:
                source = mod_sources.ESSENTIAL_SOURCES[source_key]
                provider = source["provider"]
                title = source["title"]
                github_repo = source.get("repo", github_repo)
            else:
                provider = "github" if github_repo else "local"
                title = metadata.get("name") or metadata.get("id") or pathlib.Path(filename).stem
            records[record_id] = {
                "provider": provider,
                "source_key": source_key,
                "repo": github_repo,
                "project_id": None,
                "mod_id": metadata.get("id"),
                "title": title,
                "version_id": str(metadata.get("version", "Unknown")),
                "version_number": str(metadata.get("version", "Unknown")),
                "filename": filename,
                "sha512": sha512,
                "file_size": file_stat.st_size,
                "file_mtime_ns": file_stat.st_mtime_ns,
                "game_version": self.game_version,
                "loader": self.loader,
                "enabled": enabled,
                "manual": True,
                "managed": False,
                "required_by": [],
                "installed_at": int(file_stat.st_mtime),
            }
            by_filename[filename] = record_id
            changed = True

        for record_id, record in list(records.items()):
            if record.get("managed", True):
                continue
            if record.get("filename") not in present:
                del records[record_id]
                changed = True
        if changed and persist:
            self.save_manifest(manifest)
        return manifest

    def record_path(self, record):
        filename = safe_filename(record.get("filename", ""))
        path = self.mods_dir / filename
        return path if record.get("enabled", True) else path.with_name(filename + ".disabled")

    @staticmethod
    def primary_file(version):
        files = [
            item
            for item in version.get("files", [])
            if item.get("file_type") not in {"sources-jar", "dev-jar", "javadoc-jar", "signature"}
        ]
        item = next(
            (candidate for candidate in files if candidate.get("primary")),
            files[0] if files else None,
        )
        if not item:
            raise ModrinthError(
                "The selected Modrinth version does not contain a downloadable mod file"
            )
        safe_filename(item.get("filename", ""))
        if not item.get("hashes", {}).get("sha512") and not item.get("hashes", {}).get("sha1"):
            raise ModrinthError("The selected Modrinth file does not provide a verification hash")
        return item

    def _project_details(self, project_id, fallback=None):
        fallback = fallback or {}
        if fallback.get("title") and fallback.get("slug"):
            return fallback
        project = self.client.project(project_id)
        return {
            "project_id": project.get("id", project_id),
            "title": project.get("title", fallback.get("title", project_id)),
            "slug": project.get("slug", fallback.get("slug", project_id)),
            "icon_url": project.get("icon_url", fallback.get("icon_url")),
        }

    def _dependency_version(self, dependency):
        version = None
        if dependency.get("version_id"):
            version = self.client.version(dependency["version_id"])
            if not self.client.compatible(version, self.game_version, self.loader):
                version = None
        project_id = dependency.get("project_id") or (version or {}).get("project_id")
        if version is None and project_id:
            version = self.client.latest_version(project_id, self.game_version, self.loader)
        if version is None:
            name = dependency.get("file_name") or project_id or "unknown dependency"
            raise ModrinthError(f"Required dependency {name} has no compatible Modrinth version")
        return version

    def resolve_plan(self, project_id, project_hint=None):
        root_version = self.client.latest_version(project_id, self.game_version, self.loader)
        if not root_version:
            raise ModrinthError("No compatible Modrinth version exists for this instance")
        plan = []
        nodes = {}
        parents = {}
        visiting = set()

        def visit(version, hint, required_by=None):
            current_id = str(version.get("project_id") or hint.get("project_id") or "")
            if not current_id:
                raise ModrinthError("Modrinth returned a version without a project ID")
            if required_by:
                parents.setdefault(current_id, set()).add(str(required_by))
            if current_id in nodes:
                return
            if current_id in visiting:
                raise ModrinthError("Modrinth returned a circular required-dependency chain")
            if not self.client.compatible(version, self.game_version, self.loader):
                raise ModrinthError("A required mod version is incompatible with this instance")
            visiting.add(current_id)
            details = self._project_details(current_id, hint)
            for dependency in version.get("dependencies", []):
                if dependency.get("dependency_type") != "required":
                    continue
                dependency_version = self._dependency_version(dependency)
                dependency_id = str(
                    dependency_version.get("project_id") or dependency.get("project_id") or ""
                )
                visit(dependency_version, {"project_id": dependency_id}, current_id)
            visiting.remove(current_id)
            node = {
                "project_id": current_id,
                "title": details.get("title", current_id),
                "slug": details.get("slug", current_id),
                "icon_url": details.get("icon_url"),
                "version": version,
                "file": self.primary_file(version),
            }
            nodes[current_id] = node
            plan.append(node)

        hint = dict(project_hint or {}, project_id=str(project_id))
        visit(root_version, hint)
        return plan, parents

    def _owned_filename(self, manifest, filename, project_id):
        return next(
            (
                other_id
                for other_id, record in manifest["mods"].items()
                if record.get("filename") == filename and other_id != project_id
            ),
            None,
        )

    def _download(self, item, destination, completed, total, title):
        filename = safe_filename(item["filename"])
        temporary = destination / (filename + ".part")
        destination_file = destination / filename
        sha512 = hashlib.sha512()
        # Modrinth may expose SHA-1 only for older files; SHA-512 is preferred below.
        sha1 = hashlib.sha1(usedforsecurity=False)
        written = 0
        try:
            with self.client.open_download(item["url"]) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 256):
                    output.write(chunk)
                    sha512.update(chunk)
                    sha1.update(chunk)
                    written += len(chunk)
                    percent = int(((completed + written) / max(1, total)) * 100)
                    self.progress(min(99, percent), f"Downloading {title}…")
            expected512 = item.get("hashes", {}).get("sha512")
            expected1 = item.get("hashes", {}).get("sha1")
            if expected512 and sha512.hexdigest().lower() != expected512.lower():
                raise ModrinthError(f"Hash verification failed for {filename}")
            if not expected512 and expected1 and sha1.hexdigest().lower() != expected1.lower():
                raise ModrinthError(f"Hash verification failed for {filename}")
            os.replace(temporary, destination_file)
            return destination_file
        finally:
            temporary.unlink(missing_ok=True)

    def install_project(self, project_id, project_hint=None, *, manual=True, required_by=None):
        project_id = str(project_id)
        self.progress(0, "Resolving Modrinth dependencies…")
        plan, parents = self.resolve_plan(project_id, project_hint)
        manifest = self.load_manifest()
        records = copy.deepcopy(manifest["mods"])

        for record in records.values():
            record["required_by"] = [
                value for value in record.get("required_by", []) if value != project_id
            ]

        files_to_download = []
        seen_names = {}
        for node in plan:
            node_id = node["project_id"]
            item = node["file"]
            filename = safe_filename(item["filename"])
            collision = seen_names.get(filename)
            if collision and collision != node_id:
                raise ModrinthError(f"Two required projects use the same filename: {filename}")
            seen_names[filename] = node_id
            owner = self._owned_filename(manifest, filename, node_id)
            destination = self.mods_dir / filename
            existing = manifest["mods"].get(node_id, {})
            existing_path = self.record_path(existing) if existing else destination
            if owner:
                raise ModrinthError(f"{filename} is already managed by another Modrinth project")
            disabled_destination = destination.with_name(filename + ".disabled")
            if destination.exists() and disabled_destination.exists():
                raise ModrinthError(f"Both enabled and disabled copies of {filename} exist")
            if (destination.exists() or disabled_destination.exists()) and existing.get(
                "filename"
            ) != filename:
                raise ModrinthError(
                    f"{filename} already exists as an unmanaged mod and will not be overwritten"
                )
            expected = item.get("hashes", {}).get("sha512")
            valid_existing = (
                existing_path.is_file()
                and existing.get("version_id") == node["version"].get("id")
                and expected
                and file_hash(existing_path, "sha512").lower() == expected.lower()
            )
            if not valid_existing:
                files_to_download.append(node)

        total = sum(max(1, int(node["file"].get("size", 0))) for node in files_to_download)
        completed = 0
        staging = self.instance_root / ".modrinth-staging" / uuid.uuid4().hex
        staging.mkdir(parents=True, exist_ok=False)
        try:
            for node in files_to_download:
                self._download(node["file"], staging, completed, total, node["title"])
                completed += max(1, int(node["file"].get("size", 0)))

            old_filenames = {}
            for node in plan:
                node_id = node["project_id"]
                version = node["version"]
                item = node["file"]
                filename = safe_filename(item["filename"])
                previous = records.get(node_id, {})
                old_filenames[node_id] = previous.get("filename")
                staged = staging / filename
                enabled = bool(previous.get("enabled", True))
                if staged.exists():
                    destination = self.mods_dir / filename
                    destination = (
                        destination if enabled else destination.with_name(filename + ".disabled")
                    )
                    os.replace(staged, destination)
                inherited_manual = bool(previous.get("manual"))
                is_root = node_id == project_id
                node_required_by = set(parents.get(node_id, set()))
                if is_root and required_by:
                    node_required_by.update(str(value) for value in required_by)
                records[node_id] = {
                    "provider": "modrinth",
                    "managed": True,
                    "project_id": node_id,
                    "title": node["title"],
                    "slug": node["slug"],
                    "icon_url": node.get("icon_url"),
                    "version_id": version.get("id"),
                    "version_number": version.get("version_number", version.get("name", "Unknown")),
                    "version_type": version.get("version_type", "release"),
                    "filename": filename,
                    "sha512": item.get("hashes", {}).get("sha512", ""),
                    "game_version": self.game_version,
                    "loader": self.loader,
                    "enabled": enabled,
                    "manual": inherited_manual or (is_root and bool(manual)),
                    "required_by": sorted(node_required_by),
                    "installed_at": int(time.time()),
                }

            manifest["mods"] = records
            self._prune_orphans(manifest)
            self.save_manifest(manifest)

            referenced = {record.get("filename") for record in manifest["mods"].values()}
            for old_name in old_filenames.values():
                if old_name and old_name not in referenced:
                    try:
                        (self.mods_dir / safe_filename(old_name)).unlink(missing_ok=True)
                        (self.mods_dir / (safe_filename(old_name) + ".disabled")).unlink(
                            missing_ok=True
                        )
                    except ModrinthError:
                        pass
            self.progress(100, "Mod installation complete")
            return manifest["mods"].get(project_id)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def _normalized_version(value):
        return str(value or "").strip().casefold().removeprefix("v")

    def _install_external_descriptor(self, record_id, descriptor):
        manifest = self.sync_local_inventory()
        records = copy.deepcopy(manifest["mods"])
        previous = records.get(record_id, {})
        filename = safe_filename(descriptor.get("filename", ""))
        owner = self._owned_filename(manifest, filename, record_id)
        if owner:
            raise ModrinthError(f"{filename} is already managed by another installed mod")
        destination = self.mods_dir / filename
        disabled_destination = destination.with_name(filename + ".disabled")
        if (destination.exists() or disabled_destination.exists()) and previous.get(
            "filename"
        ) != filename:
            raise ModrinthError(f"{filename} already exists and will not be overwritten")

        staging = self.instance_root / ".mod-source-staging" / uuid.uuid4().hex
        staging.mkdir(parents=True, exist_ok=False)
        try:
            try:
                staged, metadata, sha512 = self.source_client.download(
                    descriptor, staging, self.progress
                )
            except mod_sources.SourceError as error:
                raise ModrinthError(str(error)) from error
            enabled = bool(previous.get("enabled", True))
            target = destination if enabled else disabled_destination
            os.replace(staged, target)
            old_filename = previous.get("filename")
            source_key = descriptor.get("source_key")
            records[record_id] = {
                "provider": descriptor.get("provider", "github"),
                "source_key": source_key,
                "repo": descriptor.get("repo"),
                "managed": True,
                "project_id": None,
                "mod_id": metadata.get("id"),
                "title": descriptor.get("title") or metadata.get("name") or metadata.get("id"),
                "version_id": str(
                    descriptor.get("version_id") or metadata.get("version", "Unknown")
                ),
                "source_version_id": str(descriptor.get("version_id") or ""),
                "version_number": str(
                    metadata.get("version") or descriptor.get("version_number") or "Unknown"
                ),
                "filename": filename,
                "sha512": sha512,
                "game_version": self.game_version,
                "loader": self.loader,
                "enabled": enabled,
                "manual": True,
                "required_by": list(previous.get("required_by", [])),
                "installed_at": int(time.time()),
            }
            manifest["mods"] = records
            self.save_manifest(manifest)
            if old_filename and old_filename != filename:
                try:
                    (self.mods_dir / safe_filename(old_filename)).unlink(missing_ok=True)
                    (self.mods_dir / (safe_filename(old_filename) + ".disabled")).unlink(
                        missing_ok=True
                    )
                except ModrinthError:
                    pass
            self.progress(100, f"Installed {records[record_id]['title']}")
            result = copy.deepcopy(records[record_id])
            result["record_id"] = record_id
            return result
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def install_external(self, source_key):
        try:
            descriptor = self.source_client.essential_latest(source_key, self.game_version)
        except mod_sources.SourceError as error:
            raise ModrinthError(str(error)) from error
        if not descriptor:
            title = mod_sources.ESSENTIAL_SOURCES.get(source_key, {}).get("title", source_key)
            raise ModrinthError(f"No {title} build is available for Minecraft {self.game_version}")
        return self._install_external_descriptor(f"external:{source_key}", descriptor)

    def install_essentials(self, selected):
        results = []
        for source_key in selected:
            title = {
                "fabric-api": "Fabric API",
                **{key: value["title"] for key, value in mod_sources.ESSENTIAL_SOURCES.items()},
            }.get(source_key, source_key)
            try:
                self.progress(0, f"Installing {title}…")
                if source_key == "fabric-api":
                    record = self.install_project(
                        "P7dR8mSH",
                        {"project_id": "P7dR8mSH", "title": "Fabric API", "slug": "fabric-api"},
                    )
                else:
                    record = self.install_external(source_key)
                results.append(
                    {
                        "source_key": source_key,
                        "title": title,
                        "status": "installed",
                        "record": record,
                    }
                )
            except Exception as error:
                results.append(
                    {
                        "source_key": source_key,
                        "title": title,
                        "status": "skipped",
                        "error": str(error),
                    }
                )
        return results

    def _promote_local_modrinth_record(self, manifest, record_id, record):
        digest = record.get("sha512")
        if not digest:
            return record_id, record, False
        try:
            version = self.client.version_from_hash(digest, "sha512")
            project_id = str(version.get("project_id") or "")
            if not project_id:
                return record_id, record, False
            details = self._project_details(project_id, {})
        except Exception:
            return record_id, record, False
        target_id = (
            project_id
            if project_id not in manifest["mods"] or project_id == record_id
            else record_id
        )
        record.update(
            {
                "provider": "modrinth",
                "managed": True,
                "project_id": project_id,
                "title": details.get("title", record.get("title", project_id)),
                "slug": details.get("slug", project_id),
                "icon_url": details.get("icon_url"),
                "version_id": version.get("id"),
                "version_number": version.get(
                    "version_number", version.get("name", record.get("version_number", "Unknown"))
                ),
            }
        )
        if target_id != record_id:
            del manifest["mods"][record_id]
            manifest["mods"][target_id] = record
        return target_id, record, True

    def _latest_external_for_record(self, record):
        try:
            if record.get("source_key"):
                return self.source_client.essential_latest(record["source_key"], self.game_version)
            if record.get("repo"):
                return self.source_client.generic_github_latest(
                    record["repo"], self.game_version, record
                )
        except mod_sources.SourceError:
            return None
        return None

    def update_record(self, record):
        record_id = str(record.get("record_id") or record.get("project_id") or "")
        manifest = self.sync_local_inventory()
        current = manifest["mods"].get(record_id, record)
        provider = current.get("provider", "modrinth")
        if provider == "modrinth" and current.get("project_id"):
            return self.install_project(
                current["project_id"],
                current,
                manual=bool(current.get("manual", True)),
                required_by=current.get("required_by", []),
            )
        descriptor = self._latest_external_for_record(current)
        if not descriptor:
            raise ModrinthError(
                f"No compatible update source is available for {current.get('title', 'this mod')}"
            )
        return self._install_external_descriptor(record_id, descriptor)

    def _delete_record_file(self, manifest, project_id):
        record = manifest["mods"].get(project_id)
        if not record:
            return
        filename = record.get("filename")
        shared = any(
            other_id != project_id and other.get("filename") == filename
            for other_id, other in manifest["mods"].items()
        )
        if filename and not shared:
            try:
                (self.mods_dir / safe_filename(filename)).unlink(missing_ok=True)
                (self.mods_dir / (safe_filename(filename) + ".disabled")).unlink(missing_ok=True)
            except ModrinthError:
                pass
        del manifest["mods"][project_id]
        for other in manifest["mods"].values():
            other["required_by"] = [
                value for value in other.get("required_by", []) if value != project_id
            ]

    def _prune_orphans(self, manifest):
        changed = True
        while changed:
            changed = False
            for project_id, record in list(manifest["mods"].items()):
                if not record.get("manual") and not record.get("required_by"):
                    self._delete_record_file(manifest, project_id)
                    changed = True

    def remove_project(self, project_id):
        project_id = str(project_id)
        manifest = self.load_manifest()
        record = manifest["mods"].get(project_id)
        if not record:
            raise ModrinthError("This mod is not managed by BreakBlocks Launcher")
        if record.get("required_by"):
            if record.get("manual"):
                record["manual"] = False
                self.save_manifest(manifest)
                return {"kept": True, "title": record.get("title", project_id)}
            names = ", ".join(record["required_by"])
            raise ModrinthError(f"This required dependency is still used by: {names}")
        title = record.get("title", project_id)
        self._delete_record_file(manifest, project_id)
        self._prune_orphans(manifest)
        self.save_manifest(manifest)
        return {"kept": False, "title": title}

    def set_enabled(self, project_id, enabled):
        project_id = str(project_id)
        manifest = self.load_manifest()
        record = manifest["mods"].get(project_id)
        if not record:
            raise ModrinthError("This mod is not managed by BreakBlocks Launcher")
        currently_enabled = bool(record.get("enabled", True))
        enabled = bool(enabled)
        if currently_enabled == enabled:
            return record
        filename = safe_filename(record.get("filename", ""))
        enabled_path = self.mods_dir / filename
        disabled_path = self.mods_dir / (filename + ".disabled")
        source = enabled_path if currently_enabled else disabled_path
        destination = enabled_path if enabled else disabled_path
        if not source.is_file():
            raise ModrinthError(f"Managed mod file is missing: {source.name}")
        if destination.exists():
            raise ModrinthError(
                f"Cannot change mod state because {destination.name} already exists"
            )
        os.replace(source, destination)
        record["enabled"] = enabled
        self.save_manifest(manifest)
        return record

    def check_updates(self, read_only=False):
        updates = []
        manifest = self.sync_local_inventory(persist=not read_only)
        changed = False
        records = list(manifest["mods"].items())
        total = max(1, len(records))
        for index, (record_id, record) in enumerate(records):
            self.progress(int((index / total) * 100), f"Checking {record.get('title', 'mod')}…")
            if not record.get("managed", True) and not record.get("source_key"):
                record_id, record, promoted = self._promote_local_modrinth_record(
                    manifest, record_id, record
                )
                changed = changed or promoted
            provider = record.get("provider", "modrinth")
            latest = None
            if provider == "modrinth" and record.get("project_id"):
                latest = self.client.latest_version(
                    record["project_id"], self.game_version, self.loader
                )
                has_update = bool(latest and latest.get("id") != record.get("version_id"))
            else:
                latest = self._latest_external_for_record(record)
                current_source = record.get("source_version_id")
                if current_source:
                    has_update = bool(
                        latest and str(latest.get("version_id")) != str(current_source)
                    )
                else:
                    has_update = bool(
                        latest
                        and self._normalized_version(latest.get("version_number"))
                        != self._normalized_version(record.get("version_number"))
                    )
            if has_update:
                item_record = copy.deepcopy(record)
                item_record["record_id"] = record_id
                updates.append({"record": item_record, "version": latest, "provider": provider})
        if changed and not read_only:
            self.save_manifest(manifest)
        self.progress(100, "Update check complete")
        return updates
