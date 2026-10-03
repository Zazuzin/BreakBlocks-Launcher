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


def test_java_setup_time_is_excluded_from_minecraft_playtime():
    clock = [0.0]
    recorded = []
    instance = {"id": "example", "installed": True, "memory": 4096}
    account = {"id": "player", "name": "Player", "type": "Microsoft"}
    launcher = SimpleNamespace(
        selected_instance_id="example",
        store=SimpleNamespace(
            instances=Path("instances"),
            data={
                "instances": [instance],
                "accounts": [account],
                "settings": {"active_account": "player", "java": "auto"},
            },
        ),
        active_installs=set(),
        running_instances=set(),
        launching_instances=set(),
        closing=False,
        status=SimpleNamespace(set=lambda _value: None),
        show_notice=lambda *_args, **_kwargs: None,
        refresh_instances=lambda: None,
        post_ui=lambda callback: callback(),
        ensure_microsoft_session=lambda _account: None,
        mark_instance_running=lambda *_args: None,
        record_instance_playtime=lambda ident, elapsed, launched_at: recorded.append(
            (ident, elapsed, launched_at)
        ),
        finish_instance_session=lambda *_args: None,
    )

    def wait():
        clock[0] += 20.0
        return 0

    def start_game(*_args, **options):
        assert options["java_override"] == "auto"
        clock[0] += 100.0  # Runtime selection/download takes longer than the session.
        return SimpleNamespace(pid=123, wait=wait)

    class Thread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    with (
        patch.object(app.minecraft_backend, "launch", start_game),
        patch.object(app.minecraft_backend, "newest_crash_report", return_value=None),
        patch.object(app.time, "monotonic", lambda: clock[0]),
        patch.object(app.time, "time", lambda: 1000.0 + clock[0]),
        patch.object(app.threading, "Thread", Thread),
    ):
        app.Launcher.launch(launcher)
    assert recorded == [("example", 20.0, 1100.0)]


class ContextMenu:
    def __init__(self, *_args, **_options):
        self.entries = []
        self.destroyed = False
        self.released = False

    def add_command(self, **options):
        self.entries.append(options)

    def tk_popup(self, x, y):
        self.position = (x, y)

    def grab_release(self):
        self.released = True

    def destroy(self):
        self.destroyed = True


def context_menu_fixture():
    instances = [{"id": "first", "name": "First"}, {"id": "second", "name": "Second"}]
    actions = []
    launcher = SimpleNamespace(
        store=SimpleNamespace(data={"instances": instances}),
        selected_instance_id="first",
        instance_context_menu=ContextMenu(),
        ui_font="Arial",
        running_instances={},
        launching_instances=set(),
        active_installs=set(),
        instance_tasks=set(),
        refresh_instances=lambda: None,
        instance_backups=lambda instance: actions.append(("backups", instance["id"])),
        instance_transfer_dialog=lambda instance, mode: actions.append((mode, instance["id"])),
        import_instance_archive=lambda: actions.append(("import", None)),
        repair_instance=lambda instance: actions.append(("repair", instance["id"])),
    )
    launcher.select_instance = MethodType(app.Launcher.select_instance, launcher)
    launcher.instance_is_busy = MethodType(app.Launcher.instance_is_busy, launcher)
    return launcher, actions


def test_instance_context_menu_selects_clicked_instance_and_retains_its_tool_target():
    launcher, actions = context_menu_fixture()
    previous = launcher.instance_context_menu
    with patch.object(app.tk, "Menu", ContextMenu):
        app.Launcher.show_instance_context_menu(launcher, "second", 230, 440)
    menu = launcher.instance_context_menu
    assert launcher.selected_instance_id == "second"
    assert previous.destroyed and menu.released
    assert menu.position == (230, 440)
    assert [entry["label"] for entry in menu.entries] == [
        "Backups / Restore",
        "Duplicate instance",
        "Export instance",
        "Import instance",
        "Repair installation",
    ]
    launcher.selected_instance_id = "first"
    for entry in menu.entries:
        assert entry["state"] == "normal"
        entry["command"]()
    assert actions == [
        ("backups", "second"),
        ("duplicate", "second"),
        ("export", "second"),
        ("import", None),
        ("repair", "second"),
    ]
    with patch.object(app.tk, "Menu", ContextMenu):
        app.Launcher.show_instance_context_menu(launcher, "removed", 0, 0)
    assert launcher.instance_context_menu is menu
    assert not menu.destroyed


def test_instance_context_menu_disables_file_tools_while_instance_is_busy():
    for activity in ("running", "launching", "installing", "mods", "transfer"):
        launcher, _actions = context_menu_fixture()
        if activity == "running":
            launcher.running_instances["second"] = object()
        elif activity == "launching":
            launcher.launching_instances.add("second")
        else:
            key = "modrinth:second" if activity == "mods" else "second"
            launcher.active_installs.add(key)
            if activity == "transfer":
                launcher.instance_tasks.add(key)
        with patch.object(app.tk, "Menu", ContextMenu):
            app.Launcher.show_instance_context_menu(launcher, "second", 1, 2)
        entries = launcher.instance_context_menu.entries
        assert all(entries[index]["state"] == "disabled" for index in (0, 1, 2, 4))
        assert entries[3]["state"] == ("disabled" if activity == "transfer" else "normal")


def test_dashboard_right_click_only_targets_instance_rows_and_respects_modals():
    opened = []
    launcher = SimpleNamespace(
        show_instance_context_menu=lambda *args: opened.append(args),
        modal_action_blocked=lambda: False,
    )
    canvas = object.__new__(app.LauncherDashboardCanvas)
    canvas.launcher = launcher
    canvas._hit_regions = [
        {"bounds": (10, 20, 100, 60), "instance_id": "scrolled-instance"},
        {"bounds": (110, 20, 150, 60)},
    ]
    event = SimpleNamespace(x=50, y=40, x_root=250, y_root=340)
    assert canvas._on_instance_context_menu(event) == "break"
    assert opened == [("scrolled-instance", 250, 340)]
    event.x = 125  # A regular dashboard button does not open instance tools.
    assert canvas._on_instance_context_menu(event) is None
    event.x = 105  # Neither does the gap or scrollbar beside a row.
    assert canvas._on_instance_context_menu(event) is None
    event.x = 50
    launcher.modal_action_blocked = lambda: True
    assert canvas._on_instance_context_menu(event) == "break"
    assert len(opened) == 1


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"Passed {len(tests)} instance recovery flow tests")
