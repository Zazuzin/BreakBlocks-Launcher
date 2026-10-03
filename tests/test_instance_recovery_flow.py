import tempfile
import threading
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import patch

import breakblocks_launcher as app
import instance_archives


class ImmediateThread:
    def __init__(self, target, **_options):
        self.target = target

    def start(self):
        self.target()


class Widget:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value

    def grid(self):
        pass


def launcher_fixture(directory):
    root = Path(directory)
    instance = {
        "id": "test",
        "name": "Test",
        "version": "26.2",
        "loader": "Forge",
        "installed": False,
        "memory": 4096,
        "icon": "grass_block",
    }
    folder = root / "instances" / "test"
    (folder / "minecraft/mods").mkdir(parents=True)
    (folder / "minecraft/mods/original.jar").write_bytes(b"original")
    (folder / "instance-launch.json").write_bytes(b"original launch profile")
    notices = []
    saves = []
    launcher = SimpleNamespace(
        store=SimpleNamespace(
            root=root,
            instances=root / "instances",
            data={"instances": [instance], "settings": {"java": "auto"}},
            save=lambda: saves.append(True),
        ),
        store_lock=threading.RLock(),
        selected_instance_id="test",
        active_installs=set(),
        running_instances={},
        launching_instances=set(),
        show_install_progress=lambda ident: launcher.active_installs.add(ident),
        finish_install_progress=lambda ident: launcher.active_installs.discard(ident),
        refresh_instances=lambda: None,
        post_ui=lambda callback: callback(),
        show_notice=lambda *args, **kwargs: notices.append((args, kwargs)),
        status=Widget(),
        launch_dashboard=SimpleNamespace(set_progress=lambda **_options: None),
    )
    launcher.instance_is_busy = MethodType(app.Launcher.instance_is_busy, launcher)
    launcher.idle_instance = MethodType(app.Launcher.idle_instance, launcher)
    return launcher, instance, folder, notices


def test_loader_change_takes_original_loader_snapshot_before_installer_mutates_files():
    with tempfile.TemporaryDirectory() as temporary:
        launcher, instance, folder, _notices = launcher_fixture(temporary)

        class Installer:
            def __init__(self, *_args):
                pass

            def install(self, *_args):
                backup = instance_archives.BackupManager(launcher.store.root).list("test")[0]
                assert backup["manifest"]["instance"]["loader"] == "Fabric"
                assert backup["manifest"]["installed"]
                (folder / "instance-launch.json").write_bytes(b"new launch profile")

        with (
            patch.object(app.threading, "Thread", ImmediateThread),
            patch.object(app.minecraft_backend, "Installer", Installer),
        ):
            app.Launcher.start_install(
                launcher,
                "test",
                "26.2",
                "Forge",
                rollback={"loader": "Fabric", "installed": True},
                backup_reason="Before loader change",
            )
        assert instance["installed"] and instance["loader"] == "Forge"
        assert (folder / "instance-launch.json").read_bytes() == b"new launch profile"
        assert not launcher.active_installs


def test_failed_loader_install_restores_files_and_original_loader_metadata():
    with tempfile.TemporaryDirectory() as temporary:
        launcher, instance, folder, notices = launcher_fixture(temporary)

        class BrokenInstaller:
            def __init__(self, *_args):
                pass

            def install(self, *_args):
                (folder / "minecraft/mods/original.jar").write_bytes(b"partial update")
                (folder / "instance-launch.json").write_bytes(b"partial profile")
                raise OSError("Download interrupted")

        with (
            patch.object(app.threading, "Thread", ImmediateThread),
            patch.object(app.minecraft_backend, "Installer", BrokenInstaller),
        ):
            app.Launcher.start_install(
                launcher,
                "test",
                "26.2",
                "Forge",
                rollback={"loader": "Fabric", "installed": True},
                backup_reason="Before loader change",
            )
        assert instance["loader"] == "Fabric" and instance["installed"]
        assert (folder / "minecraft/mods/original.jar").read_bytes() == b"original"
        assert (folder / "instance-launch.json").read_bytes() == b"original launch profile"
        assert "were restored" in notices[-1][0][1]
        assert not launcher.active_installs


def test_failed_backup_prevents_loader_mutation():
    with tempfile.TemporaryDirectory() as temporary:
        launcher, instance, folder, notices = launcher_fixture(temporary)
        with (
            patch.object(app.threading, "Thread", ImmediateThread),
            patch.object(
                instance_archives.BackupManager, "create", side_effect=OSError("Disk full")
            ),
            patch.object(app.minecraft_backend, "Installer") as installer,
        ):
            app.Launcher.start_install(
                launcher,
                "test",
                "26.2",
                "Forge",
                rollback={"loader": "Fabric", "installed": True},
                backup_reason="Before loader change",
            )
        installer.assert_not_called()
        assert instance["loader"] == "Fabric" and instance["installed"]
        assert (folder / "instance-launch.json").read_bytes() == b"original launch profile"
        assert "Disk full" in notices[-1][0][1]


def test_mod_mutation_waits_for_a_successful_backup():
    with tempfile.TemporaryDirectory() as temporary:
        launcher, instance, folder, _notices = launcher_fixture(temporary)
        instance["loader"] = "Fabric"
        launcher.mod_context = {"instance": instance, "busy": False}
        launcher.mod_context_alive = lambda: True
        launcher.mod_progress_area = Widget()
        launcher.mod_progress = Widget()
        launcher.mod_progress_percent = SimpleNamespace(configure=lambda **_options: None)
        launcher.mod_progress_text = Widget()
        launcher.mod_status = Widget()
        launcher.update_mod_progress = lambda *_args: None
        failures = []
        launcher.fail_modrinth_operation = lambda *_args: failures.append(True)
        launcher.finish_modrinth_operation = lambda _ident, result, complete: complete(result)
        operations = []
        with (
            patch.object(app.threading, "Thread", ImmediateThread),
            patch.object(
                instance_archives.BackupManager, "create", side_effect=OSError("Disk full")
            ),
            patch.object(app, "log_launcher_error"),
        ):
            app.Launcher.run_modrinth_operation(
                launcher,
                "Updating mod…",
                lambda: operations.append("updated"),
                lambda _result: None,
                backup_reason="Before updating mod",
            )
        assert not operations and failures
        assert (folder / "minecraft/mods/original.jar").read_bytes() == b"original"


def test_game_launch_is_blocked_during_mod_operations():
    with tempfile.TemporaryDirectory() as temporary:
        launcher, instance, _folder, notices = launcher_fixture(temporary)
        instance["installed"] = True
        launcher.store.data["accounts"] = [{"id": "account", "name": "Player", "type": "Microsoft"}]
        launcher.store.data["settings"]["active_account"] = "account"
        launcher.active_installs.add("modrinth:test")
        with patch.object(app.threading, "Thread") as thread:
            app.Launcher.launch(launcher)
        thread.assert_not_called()
        assert notices[-1][0][0] == "Instance task in progress"


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"Passed {len(tests)} instance recovery flow tests")
