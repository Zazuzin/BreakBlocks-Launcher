"""Real Linux windows: render embedded chat, use its hotkey, restore the view."""

from __future__ import annotations

import ctypes
import os
import pathlib
import subprocess
import sys
import tempfile
import time


def test_linux_chat_and_overlay():
    if not sys.platform.startswith("linux") or not os.environ.get("DISPLAY"):
        print("Skipped Linux chat/overlay integration check (no X11 display)")
        return
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    import tkinter as tk

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    from chat_browser import NativeHost, configure_application_lifecycle
    from linux_chat_overlay import LinuxChatOverlay
    from x11_windows import X11Windows

    application = QApplication.instance() or QApplication([])
    configure_application_lifecycle(application)
    root = tk.Tk()
    root.geometry("900x650")
    frame = tk.Frame(root)
    frame.pack(fill="both", expand=True)
    root.update()
    view = QWebEngineView()
    view.setWindowFlags(Qt.FramelessWindowHint | Qt.BypassWindowManagerHint)
    host = NativeHost(frame.winfo_id(), int(view.winId()), view)
    host.attach()
    view.show()
    windows = X11Windows()
    game = None
    overlay = None

    def pump():
        root.update()
        application.processEvents()
        host.resize()
        time.sleep(0.02)

    def wait_for(condition, message, seconds=10):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            pump()
            if condition():
                return
        raise AssertionError(message + " " + repr(windows.foreground()))

    xtest = ctypes.cdll.LoadLibrary("libXtst.so.6")
    xtest.XTestFakeKeyEvent.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_int,
        ctypes.c_ulong,
    )

    def key(name, down):
        symbol = windows.lib.XStringToKeysym(name.encode("ascii"))
        code = windows.lib.XKeysymToKeycode(windows.display, symbol)
        assert code
        xtest.XTestFakeKeyEvent(windows.display, code, down, 0)
        windows.lib.XFlush(windows.display)

    def shortcut():
        for name in ("Control_L", "Shift_L", "F9"):
            key(name, True)
        for name in ("F9", "Shift_L", "Control_L"):
            key(name, False)

    try:
        view.setHtml(
            '<html><body style="margin:0;background:#136a44">'
            '<input id="message" value="saved session"></body></html>'
        )
        wait_for(
            lambda: view.grab().toImage().pixelColor(400, 300).name() == "#136a44",
            "The embedded web page did not render",
        )
        assert windows.parent(host.child_handle) == frame.winfo_id()
        assert windows.reparent(host.child_handle, windows.root)
        host.resize()
        assert windows.parent(host.child_handle) == frame.winfo_id(), "Detached chat stayed outside"
        assert windows.bounds(0x7FFFFFFE) is None, "A closed window was reported as live"
        with tempfile.TemporaryDirectory(prefix="breakblocks-overlay-test-") as temporary:
            folder = pathlib.Path(temporary)
            handle_file = folder / "game-window"
            game = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "from PySide6.QtWidgets import QApplication,QWidget\n"
                    "from pathlib import Path\nimport sys\n"
                    "app=QApplication([])\nw=QWidget()\nw.setWindowTitle('Minecraft test window')\n"
                    "w.resize(1000,700)\nw.show()\n"
                    "Path(sys.argv[1]).write_text(str(int(w.winId())))\napp.exec()",
                    str(handle_file),
                ],
                stdin=subprocess.DEVNULL,
            )
            wait_for(handle_file.is_file, "The game test window did not start")
            game_handle = int(handle_file.read_text())
            game_file, visible = folder / "game-pids", folder / "overlay-visible"
            game_file.write_text(str(game.pid) + "\n", encoding="ascii")
            marked_read = []
            overlay = LinuxChatOverlay(
                application,
                host,
                frame.winfo_id(),
                game_file,
                visible,
                lambda: marked_read.append(True),
            )
            for _ in range(25):
                pump()
            windows.focus(game_handle)
            wait_for(
                lambda: overlay.registered_window == game_handle,
                "The overlay shortcut was not registered for the game",
            )
            shortcut()
            wait_for(lambda: overlay.visible, "The real X11 shortcut did not open the overlay")
            assert visible.is_file() and marked_read
            assert windows.parent(host.child_handle) == int(overlay.browser_area.winId())
            result = []
            view.page().runJavaScript("document.getElementById('message').value", result.append)
            wait_for(lambda: result, "The overlay lost its live web page")
            assert result == ["saved session"]
            view.page().runJavaScript("document.getElementById('message').focus()")
            for _ in range(10):
                pump()
            key("x", True)
            key("x", False)
            for _ in range(10):
                pump()
            typed = []
            view.page().runJavaScript("document.getElementById('message').value", typed.append)
            wait_for(lambda: typed, "Chat did not receive input")
            assert "x" in typed[0], "The overlay did not receive typing: " + repr(typed)
            wait_for(
                lambda: overlay.registered_window == int(overlay.window.winId()),
                "The overlay could not receive its close shortcut",
            )
            shortcut()
            wait_for(lambda: not overlay.visible, "The shortcut did not return to Minecraft")
            assert not visible.exists()
            assert windows.parent(host.child_handle) == frame.winfo_id()
            windows.focus(frame.winfo_id())
            wait_for(
                lambda: not overlay.registered_window, "Shortcut remained active outside Minecraft"
            )
            shortcut()
            for _ in range(10):
                pump()
            assert not overlay.visible, "The game shortcut was intercepted outside Minecraft"
            windows.focus(game_handle)
            wait_for(
                lambda: overlay.registered_window == game_handle,
                "The game did not regain its shortcut",
            )
            shortcut()
            wait_for(lambda: overlay.visible, "The overlay did not reopen")
            reopened = []
            view.page().runJavaScript("document.getElementById('message').value", reopened.append)
            wait_for(lambda: reopened, "Chat lost its session when reopened")
            assert reopened == typed, "Moving chat replaced the page or discarded typed text"
            QTest.keyClick(view.focusProxy() or view, Qt.Key_Escape)
            wait_for(lambda: not overlay.visible, "Escape did not close the overlay")
            overlay.apply_preferences({"overlay_enabled": False})
            assert not overlay.registered_window
            overlay.apply_preferences({"overlay_enabled": True, "overlay_hotkey": "Alt+F10"})
            wait_for(lambda: overlay.registered_window == game_handle, "Changed shortcut failed")
            key("Alt_L", True)
            key("F10", True)
            key("F10", False)
            key("Alt_L", False)
            wait_for(lambda: overlay.visible, "The custom shortcut did not open chat")
            game_file.write_text("", encoding="ascii")
            wait_for(lambda: not overlay.visible, "The overlay remained after the game ended")
            assert windows.parent(host.child_handle) == frame.winfo_id()
        print(
            "Passed Linux rendered chat, detach recovery, real shortcuts, session reuse, "
            "Escape, settings and game-exit checks",
            flush=True,
        )
    finally:
        if overlay is not None:
            overlay.shutdown()
        if game is not None:
            game.terminate()
            game.wait(timeout=5)
        view.close()
        host.close()
        windows.close()
        root.destroy()


if __name__ == "__main__":
    test_linux_chat_and_overlay()
