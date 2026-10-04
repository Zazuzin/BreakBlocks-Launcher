"""Packaged update routing, replacement, restart and rollback regressions."""

import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import breakblocks_launcher
import launcher_update


def test_frozen_install_detection_uses_the_executable_location():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for platform_name, os_name, executable, expected in (
            ("win32", "nt", "BreakBlocks Launcher.exe", launcher_update.INSTALL_WINDOWS_PORTABLE),
            ("linux", "posix", "BreakBlocks Launcher", launcher_update.INSTALL_LINUX_PORTABLE),
        ):
            install = root / platform_name
            app = install / "_internal"
            app.mkdir(parents=True)
            binary = install / executable
            binary.write_text("launcher", encoding="utf-8")
            with (
                mock.patch.object(launcher_update, "os", SimpleNamespace(name=os_name)),
                mock.patch.object(sys, "platform", platform_name),
                mock.patch.object(sys, "frozen", True, create=True),
                mock.patch.object(sys, "executable", str(binary)),
            ):
                assert launcher_update.detect_install_type(app) == expected
                assert launcher_update.detect_install_root(app) == install.resolve()
                assert launcher_update.detect_install_type(root / "unrelated") == expected


def test_unfrozen_source_is_not_replaced_even_beside_an_executable():
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary)
        for name in ("BreakBlocks Launcher", "BreakBlocks Launcher.exe"):
            (source / name).write_text("launcher", encoding="utf-8")
        with mock.patch.object(sys, "frozen", False, create=True):
            assert launcher_update.detect_install_type(source) == launcher_update.INSTALL_SOURCE
            assert launcher_update.detect_install_root(source) is None


def test_legacy_windows_layout_remains_updatable():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        app = root / "app"
        app.mkdir()
        (root / "BreakBlocks Launcher.exe").write_text("launcher", encoding="utf-8")
        with (
            mock.patch.object(launcher_update, "os", SimpleNamespace(name="nt")),
            mock.patch.object(sys, "frozen", False, create=True),
        ):
            assert (
                launcher_update.detect_install_type(app) == launcher_update.INSTALL_WINDOWS_PORTABLE
            )
            assert launcher_update.detect_install_root(app) == root.resolve()


class Widget:
    def __init__(self, *_args, **kwargs):
        self.options = kwargs
        self.alive = True

    def configure(self, **kwargs):
        self.options.update(kwargs)

    def pack(self, **_kwargs):
        pass

    def grid(self, **_kwargs):
        pass

    def grid_columnconfigure(self, *_args, **_kwargs):
        pass

    def insert(self, *_args):
        pass

    def protocol(self, *_args):
        pass

    def winfo_exists(self):
        return self.alive

    def destroy(self):
        self.alive = False


def test_packaged_update_button_downloads_without_opening_a_browser():
    buttons = []

    def button(*args, **kwargs):
        result = Widget(*args, **kwargs)
        buttons.append(result)
        return result

    for install_type, text in (
        (launcher_update.INSTALL_WINDOWS_PORTABLE, "Download and restart"),
        (launcher_update.INSTALL_LINUX_PORTABLE, "Download and restart"),
        (launcher_update.INSTALL_LINUX_DEB, "Download and install"),
    ):
        buttons.clear()
        launcher = SimpleNamespace(
            update_install_type=install_type,
            update_install_running=False,
            font_heading="font",
            font_small="font",
            font_body="font",
            font_button="font",
            make_dialog=lambda *_args: (Widget(), Widget()),
            download_launcher_update=mock.Mock(),
            open_external_url=mock.Mock(),
        )
        update = SimpleNamespace(display_version="0.9.29 Alpha", notes="Changes")
        with mock.patch.multiple(
            breakblocks_launcher.ctk,
            CTkLabel=Widget,
            CTkTextbox=Widget,
            CTkFrame=Widget,
            CTkButton=button,
        ):
            breakblocks_launcher.Launcher.show_launcher_update(launcher, update)
            install_button = next(item for item in buttons if item.options["text"] == text)
            install_button.options["command"]()
        launcher.download_launcher_update.assert_called_once()
        launcher.open_external_url.assert_not_called()


def test_gui_download_verifies_stages_and_starts_the_restart_helper():
    class Response(io.BytesIO):
        headers = {}

    class ImmediateThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        install = root / "installed launcher"
        app = install / "_internal"
        app.mkdir(parents=True)
        executable = "BreakBlocks Launcher.exe" if os.name == "nt" else "BreakBlocks Launcher"
        (install / executable).write_bytes(b"old launcher")
        data = root / "user data"
        data.mkdir()
        account_file = data / "launcher.json"
        account_file.write_bytes(b"preserved accounts and instances")
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("BreakBlocks-Launcher/" + executable, b"new launcher")
            archive.writestr("BreakBlocks-Launcher/_internal/new-file", b"new runtime")
        package = payload.getvalue()
        update = launcher_update.UpdateInfo(
            version="0.9.29",
            display_version="0.9.29 Alpha",
            channel="alpha",
            notes="Changes",
            release_url="https://github.com/Zazuzin/BreakBlocks-Launcher/releases/tag/v0.9.29-alpha",
            asset=launcher_update.UpdateAsset(
                url="https://downloads.example.test/update.zip",
                filename="update.zip",
                size=len(package),
                sha256=hashlib.sha256(package).hexdigest(),
            ),
        )
        launcher = SimpleNamespace(
            store=SimpleNamespace(root=data),
            status=mock.Mock(),
            update_install_type=(
                launcher_update.INSTALL_WINDOWS_PORTABLE
                if os.name == "nt"
                else launcher_update.INSTALL_LINUX_PORTABLE
            ),
            update_install_running=False,
            running_instances={},
            launching_instances=set(),
            active_installs=set(),
            instance_tasks=set(),
            update_client=launcher_update.UpdateClient(
                "0.9.28", opener=lambda *_a, **_k: Response(package)
            ),
            post_ui=lambda callback: callback(),
            after=mock.Mock(),
            close_launcher=mock.Mock(),
            show_notice=mock.Mock(),
            open_external_url=mock.Mock(),
        )
        launcher.finish_update_download = (
            lambda *args: breakblocks_launcher.Launcher.finish_update_download(launcher, *args)
        )
        launcher.fail_update_download = (
            lambda *args: breakblocks_launcher.Launcher.fail_update_download(launcher, *args)
        )
        with (
            mock.patch.object(sys, "frozen", True, create=True),
            mock.patch.object(sys, "executable", str(install / executable)),
            mock.patch.object(breakblocks_launcher, "APP_DIR", app),
            mock.patch.object(breakblocks_launcher.threading, "Thread", ImmediateThread),
            mock.patch.object(launcher_update, "start_self_update") as start_update,
        ):
            breakblocks_launcher.Launcher.download_launcher_update(
                launcher, update, Widget(), Widget()
            )
        start_update.assert_called_once()
        staged, detected_root = start_update.call_args.args
        assert detected_root == install.resolve()
        assert staged.parent.parent == install.parent
        assert (staged / executable).read_bytes() == b"new launcher"
        assert (data / "updates/0.9.29/update.zip").read_bytes() == package
        assert account_file.read_bytes() == b"preserved accounts and instances"
        assert not launcher.update_install_running
        launcher.after.assert_called_once_with(100, launcher.close_launcher)
        launcher.show_notice.assert_not_called()
        launcher.open_external_url.assert_not_called()


def test_failed_extraction_cleans_only_its_staging_directory():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        install = root / "launcher"
        install.mkdir()
        (install / "original").write_text("keep", encoding="utf-8")
        unsafe = root / "unsafe.zip"
        with zipfile.ZipFile(unsafe, "w") as archive:
            archive.writestr("../escape", "unsafe")
        try:
            launcher_update.UpdateClient("0.9.28").stage_for_install(unsafe, install)
        except launcher_update.UpdateError:
            pass
        else:
            raise AssertionError("Unsafe archive accepted")
        assert (install / "original").read_text() == "keep"
        assert not list(root.glob(".breakblocks-update-*"))
        launcher_update.discard_staged_update(install)
        assert install.is_dir()


def _native_helper_test(fail_replacement=False):
    with tempfile.TemporaryDirectory(prefix="bbl update '") as temporary:
        root = Path(temporary)
        install, staged = root / "installed launcher", root / "staged launcher"
        install.mkdir()
        staged.mkdir()
        windows = os.name == "nt"
        executable = "BreakBlocks Launcher.exe" if windows else "BreakBlocks Launcher"
        for directory, version in ((install, "old"), (staged, "new")):
            if windows:
                content = version
            else:
                content = f'#!/bin/sh\nprintf "{version}" > "$0.started"\n'
            (directory / executable).write_text(content, encoding="utf-8")
            (directory / executable).chmod(0o700)
        (install / "old-only").write_text("old", encoding="utf-8")
        (staged / "new-only").write_text("new", encoding="utf-8")
        with (
            mock.patch.object(launcher_update.tempfile, "gettempdir", return_value=str(root)),
            mock.patch.object(launcher_update.subprocess, "Popen") as spawn,
        ):
            launcher_update.start_self_update(staged, install)
        assert spawn.call_args.kwargs["cwd"] == str(root)
        command = spawn.call_args.args[0]
        environment = os.environ.copy()
        if windows:
            script = Path(command[command.index("-File") + 1])
            environment.update(
                BBL_TEST_HELPER_SCRIPT=str(script),
                BBL_TEST_INSTALL=str(install),
                BBL_TEST_STAGED=str(staged),
                BBL_TEST_STARTED=str(install / (executable + ".started")),
                BBL_TEST_FAIL_NEW="1" if fail_replacement else "0",
            )
            powershell = """
                function Start-Process {
                    param([string]$FilePath, [string]$WorkingDirectory)
                    $version = Get-Content -LiteralPath $FilePath
                    if ($env:BBL_TEST_FAIL_NEW -eq "1" -and $version -eq "new") {
                        throw "Simulated new launcher start failure"
                    }
                    Set-Content -LiteralPath $env:BBL_TEST_STARTED -Value $version
                }
                & $env:BBL_TEST_HELPER_SCRIPT -LauncherProcessId 2147483647 `
                    -StagedRoot $env:BBL_TEST_STAGED -InstallRoot $env:BBL_TEST_INSTALL
            """
            command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", powershell]
        else:
            script = Path(command[0])
            command = [str(script), "2147483647", str(staged), str(install)]
            if fail_replacement:
                commands = root / "commands"
                commands.mkdir()
                real_mv = shutil.which("mv")
                fake_mv = commands / "mv"
                fake_mv.write_text(
                    '#!/bin/sh\nif [ "$2" = "$BBL_TEST_STAGED" ]; then exit 1; fi\n'
                    + f'exec "{real_mv}" "$@"\n',
                    encoding="utf-8",
                )
                fake_mv.chmod(0o700)
                environment["PATH"] = str(commands) + os.pathsep + environment["PATH"]
                environment["BBL_TEST_STAGED"] = str(staged)
        result = subprocess.run(
            command, cwd=root, env=environment, capture_output=True, text=True, timeout=20
        )
        assert bool(result.returncode) == fail_replacement, result.stdout + result.stderr
        marker = install / (executable + ".started")
        deadline = time.monotonic() + 3
        while not marker.is_file() and time.monotonic() < deadline:
            time.sleep(0.05)
        expected = "old" if fail_replacement else "new"
        assert marker.read_text().strip() == expected
        assert (install / ("old-only" if fail_replacement else "new-only")).is_file()
        assert not (install / ("new-only" if fail_replacement else "old-only")).exists()
        assert not list(root.glob("installed launcher.previous-*"))


def test_native_restart_helper_replaces_the_installation():
    _native_helper_test()


def test_native_restart_helper_restores_the_old_installation_on_failure():
    _native_helper_test(fail_replacement=True)


if __name__ == "__main__":
    for name, test in sorted(list(globals().items())):
        if name.startswith("test_") and callable(test):
            test()
            print(f"PASS {name}")
