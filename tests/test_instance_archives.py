import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import instance_archives as archives


def fixture(directory):
    root = Path(directory)
    instance = {
        "id": "test-one",
        "name": "Test",
        "version": "26.2",
        "loader": "Fabric",
        "memory": 4096,
        "installed": True,
        "icon": "custom",
        "playtime_seconds": 120,
        "refresh_token": "must-never-export",
        "essential_mods": ["fabric-api"],
    }
    files = {
        "minecraft/mods/original.jar": b"original mod",
        "minecraft/config/settings.json": b'{"enabled": true}',
        "minecraft/natives/library.so": b"native",
        "minecraft/options.txt": b"options",
        "minecraft/saves/Test/level.dat": b"world",
        "minecraft/screenshots/one.png": b"image",
        "minecraft/resourcepacks/pack.zip": b"resource pack",
        "minecraft/config/accounts.json": b'{"token": "mod-token"}',
        "launcher-icon.png": b"icon",
        "instance-launch.json": b'{"java": "/machine-specific/java"}',
        "modrinth-mods.json": b'{"format": 2, "mods": {}}',
        "launcher.json": b'{"accounts": ["secret"]}',
        "latest-launch.log": b"private chat log",
    }
    instance_root = root / "instances" / instance["id"]
    for relative, content in files.items():
        target = instance_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return root, instance, instance_root


def assert_rejected(action):
    try:
        action()
    except (archives.ArchiveError, zipfile.BadZipFile):
        return
    raise AssertionError("An unsafe or damaged archive was accepted")


def test_restore_recovers_mods_configs_profile_and_keeps_current_world():
    with tempfile.TemporaryDirectory() as temporary:
        root, instance, folder = fixture(temporary)
        manager = archives.BackupManager(root)
        backup = manager.create(instance, "Before update")
        (folder / "minecraft/mods/original.jar").unlink()
        (folder / "minecraft/mods/new.jar").write_bytes(b"new")
        (folder / "minecraft/config/settings.json").write_bytes(b"changed config")
        (folder / "instance-launch.json").write_bytes(b"changed profile")
        (folder / "minecraft/natives/library.so").write_bytes(b"changed native")
        (folder / "minecraft/saves/Test/level.dat").write_bytes(b"world after backup")
        instance["loader"] = "Forge"
        restored = manager.restore(instance, backup)
        assert restored["loader"] == "Fabric" and restored["installed"]
        assert (folder / "minecraft/mods/original.jar").read_bytes() == b"original mod"
        assert not (folder / "minecraft/mods/new.jar").exists()
        assert (folder / "minecraft/config/settings.json").read_bytes() == b'{"enabled": true}'
        assert (folder / "minecraft/natives/library.so").read_bytes() == b"native"
        assert (folder / "minecraft/saves/Test/level.dat").read_bytes() == b"world after backup"
        assert manager.list(instance["id"])[0]["manifest"]["reason"] == "Before restore"


def test_restore_removes_files_that_were_absent_in_the_snapshot():
    with tempfile.TemporaryDirectory() as temporary:
        root, instance, folder = fixture(temporary)
        (folder / "instance-launch.json").unlink()
        instance["installed"] = False
        manager = archives.BackupManager(root)
        backup = manager.create(instance)
        (folder / "instance-launch.json").write_bytes(b"new launch profile")
        restored = manager.restore(instance, backup)
        assert not restored["installed"]
        assert not (folder / "instance-launch.json").exists()


def test_five_most_recent_backups_survive_rapid_creation():
    with tempfile.TemporaryDirectory() as temporary:
        root, instance, _folder = fixture(temporary)
        manager = archives.BackupManager(root)
        created = [manager.create(instance, f"Backup {number}") for number in range(8)]
        assert len(manager.list(instance["id"])) == 5
        assert [entry["path"] for entry in manager.list(instance["id"])] == list(
            reversed(created[-5:])
        )
        assert created[-1].exists() and not created[0].exists()


def test_export_import_preserves_setup_without_accounts_platform_paths_or_worlds():
    with tempfile.TemporaryDirectory() as temporary:
        root, instance, _folder = fixture(temporary)
        target = root / "export.zip"
        archives.export_instance(root / "instances", instance, target)
        with zipfile.ZipFile(target) as archive:
            names = archive.namelist()
            manifest = json.loads(archive.read("manifest.json"))
            assert "refresh_token" not in manifest["instance"]
            assert not any("accounts" in name or "launcher.json" in name for name in names)
            assert not any(
                "instance-launch" in name
                or "natives" in name
                or "saves" in name
                or "screenshots" in name
                or "log" in name
                for name in names
            )
        destination_root = root / "other-platform" / "instances"
        imported = archives.import_instance(destination_root, target)
        imported_folder = destination_root / imported["id"]
        assert imported["id"] != instance["id"]
        assert not imported["installed"] and imported["playtime_seconds"] == 0
        assert imported["loader"] == "Fabric" and imported["memory"] == 4096
        assert (imported_folder / "minecraft/mods/original.jar").read_bytes() == b"original mod"
        assert (imported_folder / "launcher-icon.png").is_file()


def test_personal_files_are_opt_in_and_duplicate_has_a_separate_identity():
    with tempfile.TemporaryDirectory() as temporary:
        root, instance, _folder = fixture(temporary)
        duplicate = archives.duplicate_instance(root / "instances", instance, "Test copy", True)
        folder = root / "instances" / duplicate["id"]
        assert duplicate["name"] == "Test copy" and duplicate["id"] != instance["id"]
        assert (folder / "minecraft/saves/Test/level.dat").read_bytes() == b"world"
        assert (folder / "minecraft/screenshots/one.png").is_file()
        (folder / "minecraft/mods/original.jar").write_bytes(b"copy only")
        assert (
            root / "instances/test-one/minecraft/mods/original.jar"
        ).read_bytes() == b"original mod"


def test_import_assigns_different_ids_for_repeated_imports():
    with tempfile.TemporaryDirectory() as temporary:
        root, instance, _folder = fixture(temporary)
        archive = archives.export_instance(root / "instances", instance, root / "export.zip")
        first = archives.import_instance(root / "instances", archive)
        second = archives.import_instance(root / "instances", archive)
        assert first["id"] != second["id"] != instance["id"]


def forged_archive(
    path, relative, content=b"malicious", *, extra=None, duplicate=False, corrupt=False
):
    manifest = {
        "format": 1,
        "kind": "portable-instance",
        "instance": {"name": "Bad", "version": "26.2", "loader": "Fabric"},
        "files": {
            relative: {
                "size": len(content),
                "sha256": "0" * 64 if corrupt else hashlib.sha256(content).hexdigest(),
            }
        },
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("files/" + relative, content)
        if extra:
            archive.writestr(extra, content)
        if duplicate:
            archive.writestr("manifest.json", json.dumps(manifest))


def test_import_rejects_traversal_windows_paths_credentials_and_unlisted_files():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for number, relative in enumerate(
            (
                "../outside",
                "minecraft/config/../../outside",
                "minecraft\\config\\evil",
                "C:/outside",
                "minecraft/config/CON.txt",
                "minecraft/config/accounts.json",
                "launcher.json",
            )
        ):
            archive = root / f"bad-{number}.zip"
            forged_archive(archive, relative)
            assert_rejected(lambda: archives.import_instance(root / "instances", archive))
        archive = root / "extra.zip"
        forged_archive(archive, "minecraft/mods/a.jar", extra="files/../outside")
        assert_rejected(lambda: archives.import_instance(root / "instances", archive))
        assert not (root / "outside").exists()


def test_corrupt_archive_leaves_no_partial_instance():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        archive = root / "corrupt.zip"
        forged_archive(archive, "minecraft/mods/a.jar", corrupt=True)
        assert_rejected(lambda: archives.import_instance(root / "instances", archive))
        assert not list((root / "instances").iterdir())


def test_duplicate_zip_entries_and_case_collisions_are_rejected():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        archive = root / "duplicate.zip"
        forged_archive(archive, "minecraft/mods/a.jar", duplicate=True)
        assert_rejected(lambda: archives.read_manifest(archive))
        content = b"mod"
        manifest = {
            "format": 1,
            "kind": "portable-instance",
            "instance": {"name": "Bad", "version": "26.2", "loader": "Fabric"},
            "files": {
                name: {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                for name in ("minecraft/mods/a.jar", "minecraft/mods/A.jar")
            },
        }
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("manifest.json", json.dumps(manifest))
            for name in manifest["files"]:
                output.writestr("files/" + name, content)
        assert_rejected(lambda: archives.read_manifest(archive))


def test_linked_files_and_parent_directories_are_rejected():
    if os.name == "nt":
        return  # Creating symlinks can require Windows developer mode.
    with tempfile.TemporaryDirectory() as temporary:
        root, instance, folder = fixture(temporary)
        (folder / "minecraft/config/link.json").symlink_to(root / "private.json")
        assert_rejected(
            lambda: archives.export_instance(root / "instances", instance, root / "linked.zip")
        )
        (folder / "minecraft/config/link.json").unlink()
        (folder / "minecraft").rename(root / "outside-minecraft")
        (folder / "minecraft").symlink_to(root / "outside-minecraft", target_is_directory=True)
        assert_rejected(
            lambda: archives.export_instance(root / "instances", instance, root / "linked.zip")
        )


def test_restore_rolls_back_if_replacing_a_folder_fails():
    with tempfile.TemporaryDirectory() as temporary:
        root, instance, folder = fixture(temporary)
        manager = archives.BackupManager(root)
        backup = manager.create(instance)
        (folder / "minecraft/mods/original.jar").write_bytes(b"current mod")
        (folder / "minecraft/config/settings.json").write_bytes(b"current config")
        original_replace = os.replace

        def fail_config(source, destination):
            if Path(source).parts[-3:] == ("ready", "minecraft", "config"):
                raise OSError("Simulated file lock")
            return original_replace(source, destination)

        with patch.object(archives.os, "replace", side_effect=fail_config):
            try:
                manager.restore(instance, backup)
            except OSError:
                pass
            else:
                raise AssertionError("The simulated restore failure did not run")
        assert (folder / "minecraft/mods/original.jar").read_bytes() == b"current mod"
        assert (folder / "minecraft/config/settings.json").read_bytes() == b"current config"


def test_corrupted_backup_is_verified_before_creating_or_replacing_anything():
    with tempfile.TemporaryDirectory() as temporary:
        root, instance, folder = fixture(temporary)
        manager = archives.BackupManager(root)
        backup = manager.create(instance)
        with zipfile.ZipFile(backup) as source:
            contents = {name: source.read(name) for name in source.namelist()}
        contents["files/minecraft/mods/original.jar"] = b"corrupted xx"
        with zipfile.ZipFile(backup, "w") as target:
            for name, content in contents.items():
                target.writestr(name, content)
        before = (folder / "minecraft/mods/original.jar").read_bytes()
        assert_rejected(lambda: manager.restore(instance, backup))
        assert (folder / "minecraft/mods/original.jar").read_bytes() == before
        assert len(list(manager.folder(instance["id"]).glob("*.zip"))) == 1


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"Passed {len(tests)} instance archive tests")
