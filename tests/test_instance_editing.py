import inspect
import json
import os
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

import breakblocks_launcher
import minecraft_backend


def test_playtime_formatter_is_compact_and_stable():
    assert breakblocks_launcher.format_playtime(0) == "0m"
    assert breakblocks_launcher.format_playtime(12) == "<1m"
    assert breakblocks_launcher.format_playtime(60) == "1m"
    assert breakblocks_launcher.format_playtime(3660) == "1h 1m"
    assert breakblocks_launcher.format_playtime(90000) == "1d 1h"
    assert breakblocks_launcher.format_playtime("invalid") == "0m"


def test_store_migrates_playtime_without_losing_existing_instance_data():
    with tempfile.TemporaryDirectory() as temporary:
        old_xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = temporary
        try:
            root = Path(temporary) / "breakblocks-launcher"
            root.mkdir(parents=True)
            (root / "launcher.json").write_text(
                json.dumps(
                    {
                        "accounts": [],
                        "instances": [
                            {
                                "id": "one",
                                "name": "One",
                                "playtime_seconds": "125.9",
                                "custom": "kept",
                            },
                            {"id": "two", "name": "Two", "playtime_seconds": -50},
                        ],
                        "settings": {},
                    }
                )
            )
            store = breakblocks_launcher.Store()
            assert store.data["instances"][0]["playtime_seconds"] == 125
            assert store.data["instances"][0]["custom"] == "kept"
            assert store.data["instances"][1]["playtime_seconds"] == 0
        finally:
            if old_xdg is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = old_xdg


def test_recorded_playtime_accumulates_and_persists():
    store = SimpleNamespace(
        data={"instances": [{"id": "example", "playtime_seconds": 120}]},
        save_calls=0,
    )

    def save():
        store.save_calls += 1

    store.save = save
    launcher = SimpleNamespace(store=store, store_lock=threading.RLock())
    breakblocks_launcher.Launcher.record_instance_playtime(launcher, "example", 61.2, 123456)
    assert store.data["instances"][0]["playtime_seconds"] == 181
    assert store.data["instances"][0]["last_played_at"] == 123456
    assert store.save_calls == 1


def test_background_playtime_merge_preserves_changes_from_a_reopened_launcher():
    with tempfile.TemporaryDirectory() as temporary:
        data_file = Path(temporary) / "launcher.json"
        latest = {
            "accounts": [{"id": "new-account"}],
            "instances": [
                {"id": "example", "name": "Renamed elsewhere", "playtime_seconds": 300},
                {"id": "new-instance", "name": "Created elsewhere"},
            ],
            "settings": {"memory": 8192},
        }
        data_file.write_text(json.dumps(latest))
        store = SimpleNamespace(
            file=data_file,
            data={
                "accounts": [],
                "instances": [{"id": "example", "name": "Stale", "playtime_seconds": 10}],
                "settings": {},
            },
        )
        store.save = lambda: data_file.write_text(json.dumps(store.data))
        launcher = SimpleNamespace(store=store, store_lock=threading.RLock())
        breakblocks_launcher.Launcher.record_instance_playtime(launcher, "example", 60, 999)
        saved = json.loads(data_file.read_text())
        assert saved["accounts"] == [{"id": "new-account"}]
        assert saved["settings"]["memory"] == 8192
        assert saved["instances"][0]["name"] == "Renamed elsewhere"
        assert saved["instances"][0]["playtime_seconds"] == 360
        assert saved["instances"][1]["id"] == "new-instance"


def test_regular_store_save_does_not_overwrite_newer_background_playtime():
    with tempfile.TemporaryDirectory() as temporary:
        old_xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = temporary
        try:
            store = breakblocks_launcher.Store()
            store.data["instances"] = [
                {"id": "example", "name": "Original", "playtime_seconds": 60}
            ]
            store.save()
            persisted = json.loads(store.file.read_text())
            persisted["instances"][0]["playtime_seconds"] = 600
            persisted["instances"][0]["last_played_at"] = 1234
            store.file.write_text(json.dumps(persisted))
            store.data["instances"][0]["name"] = "Renamed"
            store.save()
            saved = json.loads(store.file.read_text())["instances"][0]
            assert saved["name"] == "Renamed"
            assert saved["playtime_seconds"] == 600
            assert saved["last_played_at"] == 1234
        finally:
            if old_xdg is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = old_xdg


def test_ready_card_and_edit_dialog_expose_requested_instance_controls():
    launch_card = inspect.getsource(breakblocks_launcher.LauncherDashboardCanvas._draw_launch_card)
    editor = inspect.getsource(breakblocks_launcher.Launcher.edit_instance)
    assert '"PLAYTIME"' in launch_card and "format_playtime" in launch_card
    assert '"RAM"' in launch_card and 'f"{memory} MiB"' in launch_card
    assert '"Edit Instance"' in launch_card and "launcher.edit_instance" in launch_card
    assert 'self.dialog_field(body, "INSTANCE NAME"' in editor
    assert 'text="RAM ALLOCATION"' in editor
    assert '["Vanilla", "Fabric", "Forge", "NeoForge", "Quilt"]' in editor
    assert 'text="Change Icon…"' in editor
    assert 'instance["name"] = new_name' in editor
    assert 'instance["memory"] = new_memory' in editor
    assert 'instance["loader"] = new_loader' in editor


def test_loader_change_reinstalls_with_rollback_and_keeps_instance_folder():
    editor = inspect.getsource(breakblocks_launcher.Launcher.edit_instance)
    installer = inspect.getsource(breakblocks_launcher.Launcher.start_install)
    assert 'rollback={"loader": old_loader, "installed": old_installed}' in editor
    assert "minecraft_backend.Installer" in installer
    assert ".install(self.store.instances / ident, version, loader)" in installer
    assert "item.update(rollback_data)" in installer
    assert "shutil.rmtree" not in editor
    assert "shutil.rmtree" not in installer


def test_launch_watcher_tracks_the_real_process_lifetime():
    launch = inspect.getsource(breakblocks_launcher.Launcher.launch)
    assert "process = minecraft_backend.launch" in launch
    assert "process.wait()" in launch
    assert "record_instance_playtime" in launch
    assert "newest_crash_report" in launch
    assert "daemon=False" in launch


def test_launch_log_rotation_keeps_exactly_three_logs():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "latest-launch.log").write_text("newest")
        (root / "latest-launch-1.log").write_text("previous")
        (root / "latest-launch-2.log").write_text("oldest")

        current = minecraft_backend.rotate_launch_logs(root)
        current.write_text("current")

        assert current.name == "latest-launch.log"
        assert current.read_text() == "current"
        assert (root / "latest-launch-1.log").read_text() == "newest"
        assert (root / "latest-launch-2.log").read_text() == "previous"
        assert sorted(path.name for path in root.glob("latest-launch*.log")) == [
            "latest-launch-1.log",
            "latest-launch-2.log",
            "latest-launch.log",
        ]


def test_crash_report_detection_ignores_reports_from_older_sessions():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        reports = root / "minecraft" / "crash-reports"
        reports.mkdir(parents=True)
        old = reports / "crash-old.txt"
        old.write_text("old")
        os.utime(old, (100, 100))
        assert minecraft_backend.newest_crash_report(root, launched_at=200) is None

        current = reports / "crash-current.txt"
        current.write_text("current")
        os.utime(current, (205, 205))
        assert minecraft_backend.newest_crash_report(root, launched_at=200) == current


def test_clean_shutdown_detection_distinguishes_orderly_close_from_crash():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        log = root / "latest-launch.log"
        log.write_text("[Render thread/INFO]: Stopping!\n", encoding="utf-8")
        assert minecraft_backend.launch_log_indicates_clean_shutdown(root)

        log.write_text(
            "[Render thread/INFO]: Stopping!\n---- Minecraft Crash Report ----\n",
            encoding="utf-8",
        )
        assert not minecraft_backend.launch_log_indicates_clean_shutdown(root)

        log.write_text("Process ended without a shutdown marker\n", encoding="utf-8")
        assert not minecraft_backend.launch_log_indicates_clean_shutdown(root)


def test_nonzero_exit_opens_crash_dialog_while_normal_exit_does_not():
    status_messages = []
    crash_calls = []
    launcher = SimpleNamespace(
        running_instances={"example": 1},
        overlay_game_pids={},
        launching_instances={"example"},
        store=SimpleNamespace(
            instances=Path("unused"),
            data={
                "settings": {"keep_launcher_open": True},
                "instances": [{"id": "example", "name": "Example"}],
            },
        ),
        refresh_instances=lambda: None,
        status=SimpleNamespace(set=status_messages.append),
        show_minecraft_crash=lambda *values: crash_calls.append(values),
    )

    breakblocks_launcher.Launcher.finish_instance_session(launcher, "example", 60, 0, None)
    assert crash_calls == []
    assert status_messages[-1].startswith("Minecraft closed")

    launcher.running_instances["example"] = 1
    launcher.launching_instances.add("example")
    breakblocks_launcher.Launcher.finish_instance_session(launcher, "example", 60, 1, None)
    assert crash_calls == [("example", 1, None)]
    assert status_messages[-1] == "Minecraft crashed — exit code 1"


def test_nonzero_exit_after_orderly_window_close_does_not_open_crash_dialog():
    status_messages = []
    crash_calls = []
    launcher = SimpleNamespace(
        running_instances={"example": 1},
        overlay_game_pids={},
        launching_instances={"example"},
        store=SimpleNamespace(
            instances=Path("unused"),
            data={
                "settings": {"keep_launcher_open": True},
                "instances": [{"id": "example", "name": "Example"}],
            },
        ),
        refresh_instances=lambda: None,
        status=SimpleNamespace(set=status_messages.append),
        show_minecraft_crash=lambda *values: crash_calls.append(values),
    )
    original = minecraft_backend.launch_log_indicates_clean_shutdown
    minecraft_backend.launch_log_indicates_clean_shutdown = lambda _path: True
    try:
        breakblocks_launcher.Launcher.finish_instance_session(launcher, "example", 60, 1, None)
    finally:
        minecraft_backend.launch_log_indicates_clean_shutdown = original
    assert crash_calls == []
    assert status_messages[-1].startswith("Minecraft closed")


def test_modal_dialog_guard_blocks_dashboard_click_through():
    canvas = SimpleNamespace(
        launcher=SimpleNamespace(modal_action_blocked=lambda: True),
        _scroll_drag=None,
        _hit_at=lambda _x, _y: {"callback": lambda: (_ for _ in ()).throw(AssertionError())},
    )
    event = SimpleNamespace(x=10, y=10)
    assert breakblocks_launcher.LauncherDashboardCanvas._on_button_release(canvas, event) == "break"


def test_crash_dialog_exposes_report_actions_and_bounded_reader():
    crash_dialog = inspect.getsource(breakblocks_launcher.Launcher.show_minecraft_crash)
    assert 'text="View report"' in crash_dialog
    assert 'text="Open crash folder"' in crash_dialog
    assert 'text="Copy report"' in crash_dialog
    with tempfile.TemporaryDirectory() as temporary:
        report = Path(temporary) / "crash.txt"
        report.write_text("abcdefghij")
        assert breakblocks_launcher.read_report_text(report, limit=5).startswith("abcde")
        assert "Report shortened" in breakblocks_launcher.read_report_text(report, limit=5)


def test_linux_minecraft_window_class_matches_the_observed_game_window():
    assert minecraft_backend.linux_minecraft_window_class("26.2") == "Minecraft* 26.2"


def test_linux_minecraft_desktop_registration_uses_the_matching_window_class():
    old_os = minecraft_backend.SYSTEM_OS
    old_xdg = os.environ.get("XDG_DATA_HOME")
    with tempfile.TemporaryDirectory() as temporary:
        minecraft_backend.SYSTEM_OS = "linux"
        os.environ["XDG_DATA_HOME"] = temporary
        try:
            desktop_file = minecraft_backend.register_linux_minecraft_desktop("26.2")
        finally:
            minecraft_backend.SYSTEM_OS = old_os
            if old_xdg is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = old_xdg
        assert desktop_file is not None
        content = desktop_file.read_text(encoding="utf-8")
        assert "StartupWMClass=Minecraft* 26.2" in content
        assert "NoDisplay=true" in content


def test_linux_launch_sets_the_java_window_class_before_starting_minecraft():
    source = inspect.getsource(minecraft_backend.launch)
    assert 'process_environment["AWT_WM_CLASS"] = window_class' in source
    assert "register_linux_minecraft_desktop" in source
    assert "env=process_environment" in source


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"Passed {len(tests)} instance editing tests")
