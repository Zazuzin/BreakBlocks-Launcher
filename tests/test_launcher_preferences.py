"""Exercise persisted preferences, startup checks and file maintenance."""

import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from test_minecraft_launch import ACCOUNT, installed_instance
from test_modrinth_support import FakeClient, FakeSourceClient, fabric_jar

import breakblocks_launcher as app
import instance_archives
import launcher_preferences as prefs
import minecraft_backend as backend
import modrinth_client
import startup_updates


def test_preferences_survive_settings_file_and_reject_invalid_launch_options():
    with tempfile.TemporaryDirectory() as temporary:
        file = Path(temporary) / "launcher.json"
        file.write_text(
            json.dumps(
                {
                    "settings": {
                        "chat_volume": 25,
                        "backup_count": 10,
                        "download_retries": 0,
                        "window_width": 1280,
                        "window_height": 720,
                    }
                }
            )
        )
        loaded = prefs.load(file)
        assert loaded["chat_volume"] == 25 and loaded["download_retries"] == 0
        assert loaded["backup_count"] == 10 and loaded["window_height"] == 720
        file.write_text("{broken")
        assert prefs.load(file) == prefs.DEFAULTS
    assert prefs.jvm_arguments('-Dexample="two words" -XX:+UseG1GC') == [
        "-Dexample=two words",
        "-XX:+UseG1GC",
    ]
    for value in (
        {"window_width": 1280},
        {"download_workers": 0},
        {"overlay_hotkey": "F9"},
        {"jvm_arguments": "-jar other.jar"},
    ):
        try:
            prefs.validate(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid preference accepted: {value}")


def test_chat_packet_excludes_credentials_and_changes_preview_identity():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        values = {"chat_volume": 25, "minecraft_token": "private", "java": "custom"}
        prefs.write_chat_preferences(root, values, preview=True)
        first = json.loads((root / "launcher-preferences.json").read_text())
        prefs.write_chat_preferences(root, values, preview=True)
        second = json.loads((root / "launcher-preferences.json").read_text())
        assert first["chat_volume"] == 25 and first["_preview_id"] != second["_preview_id"]
        assert "minecraft_token" not in first and "java" not in first
        assert not list(root.glob("*.tmp"))


def test_cleanup_removes_completed_install_archives_and_keeps_game_files():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        targets = {
            "minecraft-data/installers/fabric-installer.jar": b"installer",
            "java/21/runtime.zip": b"archive",
        }
        retained = {
            "instances/a/minecraft/mods/mod.jar": b"mod",
            "minecraft-data/versions/1/1.jar": b"game",
            "java/17/runtime.zip": b"uninstalled",
            "java/21/runtime/bin/java": b"runtime",
        }
        for name, data in {**targets, **retained}.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        assert prefs.clear_disposable_downloads(root) == sum(map(len, targets.values()))
        assert all(not (root / name).exists() for name in targets)
        assert all((root / name).read_bytes() == data for name, data in retained.items())


def test_cleanup_does_not_follow_a_linked_download_parent():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        archive = root / "instances/a/installers/fabric-installer.jar"
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b"keep")
        try:
            (root / "minecraft-data").symlink_to(archive.parent.parent, target_is_directory=True)
        except OSError:
            return
        assert prefs.clear_disposable_downloads(root) == 0
        assert archive.read_bytes() == b"keep"


def test_backup_retention_uses_saved_count_and_keeps_window_overrides():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "launcher.json").write_text(json.dumps({"settings": {"backup_count": 2}}))
        instance = {
            "id": "sample",
            "name": "Sample",
            "version": "1.21.1",
            "loader": "Fabric",
            "installed": True,
            "window_width": 1280,
            "window_height": 720,
        }
        folder = root / "instances/sample/minecraft/mods"
        folder.mkdir(parents=True)
        (folder / "mod.jar").write_bytes(b"fixture")
        manager = instance_archives.BackupManager(root)
        for index in range(4):
            manager.create(instance, f"Backup {index}")
        entries = manager.list("sample")
        assert len(entries) == 2
        assert entries[0]["manifest"]["reason"] == "Backup 3"
        assert entries[0]["manifest"]["instance"]["window_width"] == 1280


def test_launch_applies_window_options_and_redacts_detailed_log_tokens():
    with tempfile.TemporaryDirectory() as temporary:
        instance, record = installed_instance(Path(temporary).resolve())
        record["arguments"]["game"].extend(["--width", "640", "--height", "480"])
        (instance / "instance-launch.json").write_text(json.dumps(record))
        preferences = {
            "window_width": 1280,
            "window_height": 720,
            "jvm_arguments": "-Dcustom=true",
            "log_count": 5,
            "detailed_logging": True,
        }
        with patch.object(backend.subprocess, "Popen") as start:
            backend.launch(instance, ACCOUNT, preferences=preferences)
            command = start.call_args.args[0]
            assert command.count("--width") == command.count("--height") == 1
            assert command[command.index("--width") + 1] == "1280"
            assert command[command.index("--height") + 1] == "720"
            assert "-Dcustom=true" in command
        output = (instance / "latest-launch.log").read_text()
        assert ACCOUNT["minecraft_token"] not in output and "[redacted]" in output
        for index in range(6):
            backend.rotate_launch_logs(instance, 5).write_text(str(index))
        assert (instance / "latest-launch-4.log").is_file()
        assert not (instance / "latest-launch-5.log").exists()


def test_download_retry_discards_truncated_file_and_respects_timeout():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "launcher.json").write_text(
            json.dumps({"settings": {"download_timeout": 30, "download_retries": 1}})
        )
        short = io.BytesIO(b"partial")
        short.headers = {"Content-Length": "20"}
        complete = io.BytesIO(b"complete")
        complete.headers = {"Content-Length": "8"}
        target = root / "data.jar"
        with (
            patch.object(
                backend.urllib.request, "urlopen", side_effect=[short, complete]
            ) as open_url,
            patch.object(backend.time, "sleep"),
        ):
            backend.Installer(root).download("https://example.invalid/data", target)
        assert target.read_bytes() == b"complete"
        assert all(call.kwargs["timeout"] == 30 for call in open_url.call_args_list)
        assert not (root / "data.jar.part").exists()


def test_minecraft_download_pool_uses_saved_concurrency():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "launcher.json").write_text(json.dumps({"settings": {"download_workers": 2}}))
        installer = backend.Installer(root)
        jobs = [
            ("https://example.invalid/" + str(index), root / f"{index}.jar") for index in range(6)
        ]
        with (
            patch.object(backend.concurrent.futures, "ThreadPoolExecutor") as executor,
            patch.object(backend.concurrent.futures, "as_completed", return_value=[]),
        ):
            executor.return_value.__enter__.return_value.map.return_value = []
            installer.download_many(jobs, "Downloads", 0, 100)
        assert executor.call_args.kwargs["max_workers"] == 2


def test_read_only_external_mod_check_preserves_manifest_and_mod_files():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        folder = root / "minecraft/mods"
        folder.mkdir(parents=True)
        payload = fabric_jar("meteor-client", "Meteor Client", "0.5.8")
        file = folder / "meteor.jar"
        file.write_bytes(payload)
        source = FakeSourceClient()
        source.version = "0.5.9"
        manager = modrinth_client.ModManager(
            root, "1.21.1", "Fabric", client=FakeClient(), source_client=source
        )
        updates = manager.check_updates(read_only=True)
        assert len(updates) == 1 and updates[0]["record"]["title"] == "Meteor Client"
        assert not (root / "modrinth-mods.json").exists()
        manager.sync_local_inventory()
        saved = (root / "modrinth-mods.json").read_bytes()
        assert len(manager.check_updates(read_only=True)) == 1
        assert (root / "modrinth-mods.json").read_bytes() == saved
        assert file.read_bytes() == payload


def test_startup_mod_checks_skip_busy_instances_and_isolate_errors():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        instances = [
            {"id": name, "name": name, "version": "1.21.1", "loader": "Fabric", "installed": True}
            for name in ("busy", "broken", "good")
        ]
        for instance in instances:
            folder = root / "instances" / instance["id"] / "minecraft/mods"
            folder.mkdir(parents=True)
            (folder / "mod.jar").write_bytes(b"fixture")
        manager = Mock()
        manager.check_updates.side_effect = [
            OSError("service unavailable"),
            [{"record": {"title": "Example"}}],
        ]
        with patch.object(
            startup_updates.modrinth_client, "ModManager", return_value=manager
        ) as constructor:
            available, failures = startup_updates.check_mods(
                root, instances, lambda item: item["id"] == "busy"
            )
        assert constructor.call_count == 2
        assert available[0]["instance_id"] == "good" and failures[0][0] == "broken"
        assert all(
            call.kwargs == {"read_only": True} for call in manager.check_updates.call_args_list
        )


def test_startup_checks_run_launcher_and_mod_checks_without_selecting_chat():
    launcher = SimpleNamespace(
        closing=False,
        store=SimpleNamespace(data={"settings": {}}),
        check_for_launcher_update=Mock(),
        check_updates_on_schedule=Mock(),
        check_startup_mod_updates=Mock(),
        periodic_update_check=Mock(),
        after=Mock(),
    )
    app.Launcher.startup_checks(launcher)
    launcher.check_for_launcher_update.assert_called_once_with()
    launcher.check_startup_mod_updates.assert_called_once_with()
    launcher.check_updates_on_schedule.assert_not_called()
    launcher.store.data["settings"] = {
        "update_enabled": True,
        "update_check_startup": False,
        "mods_check_startup": False,
    }
    launcher.check_for_launcher_update.reset_mock()
    launcher.check_startup_mod_updates.reset_mock()
    app.Launcher.startup_checks(launcher)
    launcher.check_startup_mod_updates.assert_not_called()
    launcher.check_for_launcher_update.assert_not_called()
    launcher.check_updates_on_schedule.assert_not_called()


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"Passed {len(tests)} preference and startup tests")
