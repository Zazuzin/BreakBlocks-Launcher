"""Exercise the installed chat executable in a hidden, then visible Tk host."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest import mock

import customtkinter as ctk

from breakblocks_launcher import Launcher


class ChatHost(ctk.CTk):
    chat_web_ui = Launcher.chat_web_ui
    chat_browser_command = Launcher.chat_browser_command
    ensure_chat_browser = Launcher.ensure_chat_browser
    stop_chat_browser = Launcher.stop_chat_browser
    restart_chat_browser = Launcher.restart_chat_browser

    def show_chat_startup_failure(self, message):
        self.chat_browser_status.set(message)

    def monitor_chat_browser(self):
        pass


def check(executable: pathlib.Path) -> None:
    with tempfile.TemporaryDirectory(prefix="breakblocks-chat-check-") as temporary:
        folder = pathlib.Path(temporary)
        environment = {
            "LOCALAPPDATA": str(folder / "data"),
            "XDG_STATE_HOME": str(folder / "state"),
            "XDG_DATA_HOME": str(folder / "data"),
        }
        with mock.patch.dict(os.environ, environment):
            check_launcher_startup(executable, folder)
            root = ChatHost()
            root.geometry("900x650")
            root.closing = False
            root.chat_browser_process = None
            root.chat_browser_monitor_id = None
            root.chat_browser_shutdown_file = None
            root.store = SimpleNamespace(root=folder / "profile", data={"settings": {}})
            root.font_heading = ctk.CTkFont(size=20, weight="bold")
            root.font_body = ctk.CTkFont(size=13)
            page = ctk.CTkFrame(root)
            root.chat_web_ui(page)
            root.update()
            try:
                with (
                    mock.patch.object(sys, "frozen", True, create=True),
                    mock.patch.object(sys, "executable", str(executable)),
                ):
                    root.ensure_chat_browser()
                process = root.chat_browser_process
                assert process is not None, "Chat did not create its process"
                deadline = time.monotonic() + 25
                log_path = (
                    folder / "data/BreakBlocks Launcher/launcher.log"
                    if os.name == "nt"
                    else folder / "state/breakblocks-launcher/launcher.log"
                )
                output = ""
                while time.monotonic() < deadline:
                    root.update()
                    if log_path.exists():
                        output = log_path.read_text(encoding="utf-8", errors="replace")
                    if process.poll() is not None:
                        raise AssertionError(f"Chat exited with {process.returncode}:\n{output}")
                    if "loading https://irc.breakblocks.com" in output:
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError(f"Chat never attached and loaded:\n{output}")
                page.pack(fill="both", expand=True)
                root.update()
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    root.update()
                    assert process.poll() is None, log_path.read_text(errors="replace")
                    time.sleep(0.05)
                if os.name == "nt":
                    user32 = ctypes.WinDLL("user32", use_last_error=True)
                    user32.GetTopWindow.argtypes = (ctypes.c_void_p,)
                    user32.GetTopWindow.restype = ctypes.c_void_p
                    user32.GetClassNameW.argtypes = (
                        ctypes.c_void_p,
                        ctypes.c_wchar_p,
                        ctypes.c_int,
                    )
                    top = user32.GetTopWindow(root.chat_browser_host.winfo_id())
                    name = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(top, name, len(name))
                    assert name.value.startswith(
                        "Qt"
                    ), f"Loading panel covers the browser: top child class is {name.value!r}"
                print(output, flush=True)
                print("Packaged chat started in the background and survived opening Chat.")
            finally:
                root.stop_chat_browser()
                root.destroy()
                if root.chat_browser_process is not None:
                    root.chat_browser_process.wait(timeout=5)


def check_launcher_startup(executable: pathlib.Path, folder: pathlib.Path) -> None:
    """Start the real frozen parent so its bootloader environment reaches chat."""
    data = (
        folder / "data/BreakBlocks Launcher"
        if os.name == "nt"
        else folder / "data/breakblocks-launcher"
    )
    data.mkdir(parents=True)
    (data / "launcher.json").write_text(
        json.dumps(
            {
                "settings": {
                    "legal_notice_version": 1,
                    "update_check_startup": False,
                    "mods_check_startup": False,
                }
            }
        ),
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [str(executable)], stdin=subprocess.DEVNULL, start_new_session=os.name != "nt"
    )
    log_path = (
        data / "launcher.log"
        if os.name == "nt"
        else folder / "state/breakblocks-launcher/launcher.log"
    )
    try:
        deadline = time.monotonic() + 30
        output = ""
        while time.monotonic() < deadline:
            if log_path.exists():
                output = log_path.read_text(encoding="utf-8", errors="replace")
            assert process.poll() is None, f"Launcher exited: {output}"
            if "loading https://irc.breakblocks.com" in output:
                break
            time.sleep(0.1)
        else:
            raise AssertionError(f"Real launcher did not start chat:\n{output}")
        print(output, flush=True)
        print("Frozen launcher automatically started its frozen chat child.", flush=True)
    finally:
        if log_path.exists():
            output = log_path.read_text(encoding="utf-8", errors="replace")
            match = re.search(r"attached child window \d+ to launcher host (\d+)", output)
            if match:
                stop_file = data / "web-chat-profile" / f".stop-{process.pid}-{match[1]}"
                stop_file.write_text("stop\n", encoding="utf-8")
        if os.name == "nt":
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_ssize_t)
            user32.GetWindowThreadProcessId.argtypes = (
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_ulong),
            )
            user32.PostMessageW.argtypes = (
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.c_size_t,
                ctypes.c_ssize_t,
            )

            @callback_type
            def close_window(handle, _parameter):
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
                if pid.value == process.pid:
                    user32.PostMessageW(handle, 0x0010, 0, 0)
                return 1

            user32.EnumWindows(close_window, 0)
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=pathlib.Path)
    options = parser.parse_args()
    check(options.executable.resolve(strict=True))
