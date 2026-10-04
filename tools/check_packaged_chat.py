"""Exercise the installed chat executable in a hidden, then visible Tk host."""

from __future__ import annotations

import argparse
import os
import pathlib
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
            page.pack(fill="both", expand=True)
            root.chat_web_ui(page)
            root.update()
            page.pack_forget()
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
                print(output, flush=True)
                print("Packaged chat started in the background and survived opening Chat.")
            finally:
                root.stop_chat_browser()
                root.destroy()
                if root.chat_browser_process is not None:
                    root.chat_browser_process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=pathlib.Path)
    options = parser.parse_args()
    check(options.executable.resolve(strict=True))
