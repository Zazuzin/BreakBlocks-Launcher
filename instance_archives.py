"""Instance recovery snapshots and portable transfers, independent of the GUI."""

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

FORMAT_VERSION = 1
BACKUP_LIMIT = 5
MAX_ARCHIVE_BYTES = 50 * 1024**3
MAX_ARCHIVE_FILES = 200000
RECOVERY_PATHS = (
    "minecraft/mods",
    "minecraft/config",
    "minecraft/defaultconfigs",
    "minecraft/natives",
    "minecraft/options.txt",
    "minecraft/optionsof.txt",
    "minecraft/optionsshaders.txt",
    "instance-launch.json",
    "modrinth-mods.json",
    "launcher-icon.png",
)
PORTABLE_PATHS = tuple(
    path for path in RECOVERY_PATHS if path not in {"instance-launch.json", "minecraft/natives"}
) + (
    "minecraft/resourcepacks",
    "minecraft/shaderpacks",
    "minecraft/servers.dat",
)
PERSONAL_PATHS = ("minecraft/saves", "minecraft/screenshots")
LOADERS = {"Vanilla", "Fabric", "Forge", "NeoForge", "Quilt"}
METADATA_KEYS = ("name", "version", "loader", "memory", "icon", "essential_mods")


class ArchiveError(ValueError):
    pass


def instance_directory(instances, ident):
    root = Path(instances).resolve()
    if not isinstance(ident, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", ident):
        raise ArchiveError("This instance has an invalid folder name.")
    path = root / ident
    if path.is_symlink() or path.resolve().parent != root:
        raise ArchiveError("Instance folders must stay inside the launcher instances folder.")
    return path


def instance_metadata(instance):
    metadata = {key: instance[key] for key in METADATA_KEYS if key in instance}
    name = metadata.get("name", "Imported instance")
    version = metadata.get("version", "")
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise ArchiveError("The instance name must contain between 1 and 80 characters.")
    if not isinstance(version, str) or not re.fullmatch(r"[a-zA-Z0-9_.+-]{1,80}", version):
        raise ArchiveError("The archive contains an invalid Minecraft version.")
    if metadata.get("loader") not in LOADERS:
        raise ArchiveError("The archive contains an unsupported mod loader.")
    try:
        metadata["memory"] = max(1024, min(32768, int(metadata.get("memory", 4096))))
    except (ValueError, TypeError, OverflowError) as error:
        raise ArchiveError("The archive contains an invalid RAM setting.") from error
    if not isinstance(metadata.get("icon", "grass_block"), str):
        raise ArchiveError("The archive contains an invalid icon.")
    essentials = metadata.get("essential_mods", [])
    if not isinstance(essentials, list) or any(not isinstance(item, str) for item in essentials):
        raise ArchiveError("The archive contains invalid mod preferences.")
    return metadata


def _credential_file(relative):
    """Exclude known account/token stores from transfers, including mod account lists."""
    name = PurePosixPath(relative).name.lower()
    return bool(
        re.fullmatch(r"(?:accounts?|credentials?|tokens?|sessions?)(?:[._-].*)?", name)
        or name in {"launcher.json", "launcher_accounts.json", "launcher_profiles.json"}
    )


def _files(root, paths, portable=False):
    found = []
    for relative in paths:
        base = root / relative
        if base.is_symlink() or not base.resolve().is_relative_to(root):
            raise ArchiveError(f"Cannot archive a linked file or folder: {relative}")
        if not base.exists():
            continue
        candidates = sorted(base.rglob("*")) if base.is_dir() else [base]
        for path in candidates:
            if path.is_symlink():
                raise ArchiveError(f"Cannot archive a linked file or folder: {path.name}")
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if portable and (_credential_file(rel) or path.suffix.lower() in {".tmp", ".lock"}):
                continue
            found.append((rel, path))
    if len(found) > MAX_ARCHIVE_FILES:
        raise ArchiveError("This instance contains too many files for a single archive.")
    if sum(path.stat().st_size for _, path in found) > MAX_ARCHIVE_BYTES:
        raise ArchiveError("This instance is larger than the 50 GiB archive limit.")
    return found


def _write_archive(root, instance, destination, kind, reason, include_personal, progress):
    paths = RECOVERY_PATHS if kind == "recovery" else PORTABLE_PATHS
    if include_personal:
        paths += PERSONAL_PATHS
    files = _files(root, paths, portable=kind == "portable-instance")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    manifest = {
        "format": FORMAT_VERSION,
        "kind": kind,
        "created_at": int(time.time()),
        "reason": str(reason)[:160],
        "instance": instance_metadata(instance),
        "include_personal": bool(include_personal),
        "files": {},
    }
    if kind == "recovery":
        manifest["instance_id"] = instance["id"]
        manifest["installed"] = bool(instance.get("installed"))
    progress = progress or (lambda _percent, _message: None)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
            for index, (relative, path) in enumerate(files):
                progress(int(index / max(1, len(files)) * 95), f"Saving {path.name}…")
                digest = hashlib.sha256()
                size = 0
                with (
                    path.open("rb") as source,
                    archive.open("files/" + relative, "w", force_zip64=True) as target,
                ):
                    while chunk := source.read(1024 * 1024):
                        target.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                manifest["files"][relative] = {"size": size, "sha256": digest.hexdigest()}
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        read_manifest(temporary, kind)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        progress(100, "Archive saved")
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def _safe_relative(value):
    if not isinstance(value, str) or "\\" in value or ":" in value or "\x00" in value:
        raise ArchiveError("The archive contains an unsafe file path.")
    path = PurePosixPath(value)
    if path.is_absolute() or not value or str(path) != value:
        raise ArchiveError("The archive contains an unsafe file path.")
    reserved = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.I)
    if any(
        part in {".", ".."}
        or part.endswith((".", " "))
        or reserved.match(part)
        or any(ord(char) < 32 or char in '<>"|?*' for char in part)
        for part in path.parts
    ):
        raise ArchiveError("The archive contains an unsafe file path.")
    return value


def read_manifest(archive_path, expected_kind=None):
    try:
        with zipfile.ZipFile(archive_path) as archive:
            info = archive.getinfo("manifest.json")
            if info.file_size > 16 * 1024 * 1024:
                raise ArchiveError("The archive manifest is too large.")
            manifest = json.loads(archive.read(info))
            if not isinstance(manifest, dict) or manifest.get("format") != FORMAT_VERSION:
                raise ArchiveError("This is not a supported BreakBlocks instance archive.")
            kind = manifest.get("kind")
            if kind not in {"recovery", "portable-instance"} or (
                expected_kind and kind != expected_kind
            ):
                raise ArchiveError("This archive is not the required type of instance backup.")
            manifest["instance"] = instance_metadata(manifest.get("instance", {}))
            files = manifest.get("files")
            if not isinstance(files, dict) or len(files) > MAX_ARCHIVE_FILES:
                raise ArchiveError("The archive file list is invalid.")
            allowed = RECOVERY_PATHS if kind == "recovery" else PORTABLE_PATHS
            if manifest.get("include_personal") is True and kind == "portable-instance":
                allowed += PERSONAL_PATHS
            total = 0
            expected_names = {"manifest.json"}
            folded = set()
            for relative, item in files.items():
                _safe_relative(relative)
                if not any(relative == p or relative.startswith(p + "/") for p in allowed):
                    raise ArchiveError("The archive contains files outside the instance folders.")
                if kind == "portable-instance" and _credential_file(relative):
                    raise ArchiveError(
                        "Portable archives must not contain account credential files."
                    )
                if relative.casefold() in folded:
                    raise ArchiveError("The archive contains conflicting file names.")
                folded.add(relative.casefold())
                if (
                    not isinstance(item, dict)
                    or type(item.get("size")) is not int
                    or item["size"] < 0
                ):
                    raise ArchiveError("The archive contains invalid file sizes.")
                if not re.fullmatch(r"[a-f0-9]{64}", str(item.get("sha256", ""))):
                    raise ArchiveError("The archive contains an invalid file checksum.")
                entry = archive.getinfo("files/" + relative)
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode) or entry.is_dir() or entry.file_size != item["size"]:
                    raise ArchiveError("The archive contains an invalid or linked file.")
                expected_names.add(entry.filename)
                total += item["size"]
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != expected_names:
                raise ArchiveError("The archive contains unexpected or duplicate entries.")
            if total > MAX_ARCHIVE_BYTES:
                raise ArchiveError("The expanded archive exceeds the 50 GiB limit.")
            return manifest
    except (
        OSError,
        KeyError,
        TypeError,
        AttributeError,
        json.JSONDecodeError,
        zipfile.BadZipFile,
    ) as error:
        raise ArchiveError("The instance archive is damaged or incomplete.") from error


def _extract(archive_path, directory, expected_kind, progress=None):
    manifest = read_manifest(archive_path, expected_kind)
    progress = progress or (lambda _percent, _message: None)
    with zipfile.ZipFile(archive_path) as archive:
        for index, (relative, item) in enumerate(manifest["files"].items()):
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            size = 0
            progress(int(index / max(1, len(manifest["files"])) * 90), f"Reading {target.name}…")
            with archive.open("files/" + relative) as source, target.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > item["size"]:
                        raise ArchiveError("An archive file is larger than its declared size.")
                    digest.update(chunk)
                    output.write(chunk)
            if size != item["size"] or digest.hexdigest() != item["sha256"]:
                raise ArchiveError(
                    f"The checksum for {target.name} did not match. Nothing was restored."
                )
    return manifest


class BackupManager:
    def __init__(self, launcher_root):
        self.root = Path(launcher_root).resolve()
        self.instances = self.root / "instances"
        self.backups = self.root / "backups"

    def folder(self, ident):
        instance_directory(self.instances, ident)
        if self.backups.is_symlink():
            raise ArchiveError("The backups folder must not be a linked folder.")
        return instance_directory(self.backups, ident)

    def create(self, instance, reason="Manual backup", progress=None):
        root = instance_directory(self.instances, instance["id"])
        if not root.is_dir():
            raise ArchiveError("The instance folder could not be found.")
        folder = self.folder(instance["id"])
        folder.mkdir(parents=True, exist_ok=True)
        os.chmod(folder, 0o700)
        name = (
            time.strftime("%Y%m%d-%H%M%S")
            + f"-{time.time_ns():020d}-"
            + uuid.uuid4().hex[:8]
            + ".zip"
        )
        destination = _write_archive(
            root, instance, folder / name, "recovery", reason, False, progress
        )
        for entry in self.list(instance["id"])[BACKUP_LIMIT:]:
            entry["path"].unlink(missing_ok=True)
        return destination

    def list(self, ident):
        entries = []
        for path in sorted(self.folder(ident).glob("*.zip"), reverse=True):
            if path.is_symlink():
                continue
            try:
                manifest = read_manifest(path, "recovery")
                if manifest.get("instance_id") == ident:
                    entries.append(
                        {"path": path, "manifest": manifest, "size": path.stat().st_size}
                    )
            except (OSError, ArchiveError):
                continue
        return entries

    def restore(self, instance, archive_path, progress=None):
        root = instance_directory(self.instances, instance["id"])
        selected = Path(archive_path)
        if (
            selected.is_symlink()
            or selected.resolve().parent != self.folder(instance["id"]).resolve()
        ):
            raise ArchiveError("Choose a backup from this instance's backup list.")
        with tempfile.TemporaryDirectory(prefix=".restore-", dir=self.root) as temporary:
            stage = Path(temporary) / "ready"
            stage.mkdir()
            manifest = _extract(selected, stage, "recovery", progress)
            if manifest.get("instance_id") != instance["id"]:
                raise ArchiveError("This backup belongs to a different instance.")
            # Validate before changing anything, and keep the current setup as another backup.
            self.create(instance, "Before restore")
            previous = Path(temporary) / "previous"
            previous.mkdir()
            changed = []
            try:
                for relative in RECOVERY_PATHS:
                    current = root / relative
                    restored = stage / relative
                    saved = previous / relative
                    # Linked targets must never redirect a restore outside this instance.
                    if current.is_symlink() or any(
                        parent.is_symlink() for parent in current.parents if parent != root.parent
                    ):
                        raise ArchiveError("A linked folder prevents a safe restore.")
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    current.parent.mkdir(parents=True, exist_ok=True)
                    had_previous = current.exists()
                    if had_previous:
                        os.replace(current, saved)
                    changed.append((current, saved, had_previous))
                    if restored.exists():
                        os.replace(restored, current)
            except Exception:
                for current, saved, had_previous in reversed(changed):
                    if current.is_dir():
                        shutil.rmtree(current)
                    else:
                        current.unlink(missing_ok=True)
                    if had_previous:
                        os.replace(saved, current)
                raise
        metadata = manifest["instance"]
        metadata["installed"] = bool(manifest.get("installed"))
        return metadata


def export_instance(instances, instance, destination, include_personal=False, progress=None):
    root = instance_directory(instances, instance["id"])
    if not root.is_dir():
        raise ArchiveError("The instance folder could not be found.")
    destination = Path(destination).resolve()
    if destination.is_relative_to(root):
        raise ArchiveError("Save the archive outside this instance's folder.")
    return _write_archive(
        root, instance, destination, "portable-instance", "Export", include_personal, progress
    )


def import_instance(instances, archive_path, name=None, progress=None):
    root = Path(instances).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".import-", dir=root) as temporary:
        stage = Path(temporary) / "ready"
        stage.mkdir()
        manifest = _extract(archive_path, stage, "portable-instance", progress)
        instance = manifest["instance"]
        if name is not None:
            instance["name"] = name.strip()
        instance_metadata(instance)
        ident = "instance-" + uuid.uuid4().hex[:12]
        instance.update(id=ident, installed=False, playtime_seconds=0)
        (stage / "minecraft").mkdir(exist_ok=True)
        destination = instance_directory(root, ident)
        os.replace(stage, destination)
        os.chmod(destination, 0o700)
        return instance


def duplicate_instance(instances, instance, name, include_personal=False, progress=None):
    """Use the portable path so a copy never inherits stale platform launch paths."""
    root = Path(instances).resolve()
    with tempfile.TemporaryDirectory(prefix=".duplicate-", dir=root) as temporary:
        archive = Path(temporary) / "instance.zip"
        export_instance(root, instance, archive, include_personal, progress)
        return import_instance(root, archive, name, progress)
