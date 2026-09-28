#!/usr/bin/env python3
"""Native web-chat surface hosted inside the launcher's Chat page.

The browser runs in a separate process because Tk and Qt each require their
own GUI event loop.  Its native window is attached to the Tk host window, so
the browser follows the launcher's page visibility and remains isolated from
the Minecraft launcher process.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import pathlib
import sys
import traceback

CHAT_URL = "https://irc.breakblocks.com/#/connect"
PROFILE_DIRECTORY_NAME = "web-chat-profile"


def log_browser_message(message: str) -> None:
    print(f"Embedded chat browser: {message}", flush=True)


def configure_application_lifecycle(application) -> None:
    """Keep Qt alive after its window becomes a child of the Tk launcher."""
    application.setQuitOnLastWindowClosed(False)


def parse_parent_handle(value: str) -> int:
    try:
        handle = int(value, 0)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("parent handle must be an integer") from None
    if handle <= 0:
        raise argparse.ArgumentTypeError("parent handle must be positive")
    return handle


def prepare_profile_directory(path: pathlib.Path) -> pathlib.Path:
    profile = path.expanduser().resolve()
    profile.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(profile, 0o700)
    except OSError:
        pass
    return profile


class NativeHost:
    """Attach and resize a Qt window inside an existing native parent."""

    def __init__(self, parent_handle: int, child_handle: int, qt_view=None):
        self.parent_handle = parent_handle
        self.child_handle = child_handle
        self.qt_view = qt_view
        self._foreign_parent = None
        self._display = None
        self._x11 = None

    def attach(self) -> None:
        if os.name == "nt":
            self._attach_windows()
            return
        if sys.platform.startswith("linux"):
            self._attach_x11()
            return
        raise RuntimeError("The embedded chat browser supports Windows and Linux")

    def resize(self) -> bool:
        if os.name == "nt":
            return self._resize_windows()
        return self._resize_x11()

    def _attach_windows(self) -> None:
        """Attach through Qt's supported foreign-window API.

        Raw Win32 SetParent works for many ordinary windows, but it leaves Qt
        unaware that its QWebEngineView became a child of the Tk window.  Qt
        can then tear down its final top-level window and stop the event loop
        with exit code 0.  QWindow.fromWinId represents the Tk HWND inside Qt,
        so Qt owns the child relationship and keeps the web view alive.
        """
        if self.qt_view is None:
            raise RuntimeError("The Windows web chat host requires its Qt view")

        from PySide6.QtGui import QWindow

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        window_handle = ctypes.c_void_p
        user32.IsWindow.argtypes = (window_handle,)
        user32.IsWindow.restype = ctypes.c_int
        if not user32.IsWindow(self.parent_handle) or not user32.IsWindow(self.child_handle):
            raise OSError("The launcher chat window is no longer available")

        foreign_parent = QWindow.fromWinId(self.parent_handle)
        child_window = self.qt_view.windowHandle()
        if foreign_parent is None or child_window is None:
            raise RuntimeError("Qt could not represent the launcher chat window")
        child_window.setParent(foreign_parent)
        self._foreign_parent = foreign_parent
        self.child_handle = int(self.qt_view.winId())
        self.qt_view.show()
        if not self._resize_windows():
            raise OSError("The launcher chat window could not be sized")

    def _resize_windows(self) -> bool:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        window_handle = ctypes.c_void_p
        user32.IsWindow.argtypes = (window_handle,)
        user32.IsWindow.restype = ctypes.c_int
        if not user32.IsWindow(self.parent_handle) or not user32.IsWindow(self.child_handle):
            return False

        class Rect(ctypes.Structure):
            _fields_ = (
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            )

        user32.GetClientRect.argtypes = (window_handle, ctypes.POINTER(Rect))
        user32.GetClientRect.restype = ctypes.c_int
        rectangle = Rect()
        if not user32.GetClientRect(self.parent_handle, ctypes.byref(rectangle)):
            # A valid host HWND can be temporarily unavailable while Tk is
            # changing page layout.  Keep the browser alive and retry.
            return True
        width = max(1, rectangle.right - rectangle.left)
        height = max(1, rectangle.bottom - rectangle.top)
        self.qt_view.setGeometry(0, 0, width, height)
        return True

    def _attach_x11(self) -> None:
        self._x11 = ctypes.cdll.LoadLibrary("libX11.so.6")
        self._x11.XOpenDisplay.argtypes = (ctypes.c_char_p,)
        self._x11.XOpenDisplay.restype = ctypes.c_void_p
        self._x11.XReparentWindow.argtypes = (
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_int,
        )
        self._x11.XMapWindow.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
        self._x11.XMoveResizeWindow.argtypes = (
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_uint,
        )
        self._x11.XGetGeometry.argtypes = (
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
        )
        self._x11.XGetGeometry.restype = ctypes.c_int
        self._x11.XFlush.argtypes = (ctypes.c_void_p,)
        self._display = self._x11.XOpenDisplay(None)
        if not self._display:
            raise RuntimeError("Could not open the X11 display for embedded web chat")
        self._x11.XReparentWindow(
            self._display,
            self.child_handle,
            self.parent_handle,
            0,
            0,
        )
        self._x11.XMapWindow(self._display, self.child_handle)
        self._x11.XFlush(self._display)
        self._resize_x11()

    def _resize_x11(self) -> bool:
        if not self._display or not self._x11:
            return False
        root = ctypes.c_ulong()
        x = ctypes.c_int()
        y = ctypes.c_int()
        width = ctypes.c_uint()
        height = ctypes.c_uint()
        border = ctypes.c_uint()
        depth = ctypes.c_uint()
        available = self._x11.XGetGeometry(
            self._display,
            self.parent_handle,
            ctypes.byref(root),
            ctypes.byref(x),
            ctypes.byref(y),
            ctypes.byref(width),
            ctypes.byref(height),
            ctypes.byref(border),
            ctypes.byref(depth),
        )
        if not available:
            return False
        self._x11.XMoveResizeWindow(
            self._display,
            self.child_handle,
            0,
            0,
            max(1, width.value),
            max(1, height.value),
        )
        self._x11.XFlush(self._display)
        return True


def run_browser(
    parent_handle: int,
    profile_directory: pathlib.Path,
    shutdown_file: pathlib.Path,
) -> int:
    if sys.platform.startswith("linux"):
        # Tk runs through X11/XWayland.  Matching that backend permits the Qt
        # window to become a real child of the Tk Chat host under Wayland too.
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    from PySide6.QtCore import Qt, QTimer, QUrl
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    profile_directory = prepare_profile_directory(profile_directory)
    application = QApplication.instance() or QApplication(sys.argv[:1])
    configure_application_lifecycle(application)
    application.setApplicationName("BreakBlocks Chat")
    application.setOrganizationName("BreakBlocks")

    profile = QWebEngineProfile("BreakBlocksChat", application)
    profile.setPersistentStoragePath(str(profile_directory / "storage"))
    profile.setCachePath(str(profile_directory / "cache"))
    profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
    profile.setHttpUserAgent(f"{profile.httpUserAgent()} BreakBlocks-Launcher")

    page = QWebEnginePage(profile, application)
    view = QWebEngineView()
    view.setPage(page)
    view.setWindowTitle("BreakBlocks Chat")
    view.setWindowFlag(Qt.FramelessWindowHint, True)
    view.setAttribute(Qt.WA_NativeWindow, True)
    view.resize(900, 600)
    view.show()

    host = NativeHost(parent_handle, int(view.winId()), qt_view=view)
    host.attach()
    log_browser_message(
        f"attached child window {int(view.winId())} to launcher host {parent_handle}"
    )

    timer = QTimer(view)
    unavailable_checks = 0

    def keep_in_host() -> None:
        nonlocal unavailable_checks
        if shutdown_file.is_file():
            log_browser_message("received launcher shutdown request")
            timer.stop()
            view.close()
            application.quit()
            return
        if not host.resize():
            unavailable_checks += 1
            if unavailable_checks >= 20:
                log_browser_message("launcher host or embedded window is no longer available")
                timer.stop()
                application.quit()
            return
        unavailable_checks = 0

    timer.timeout.connect(keep_in_host)
    timer.start(150)
    view.load(QUrl(CHAT_URL))
    log_browser_message(f"loading {CHAT_URL}")
    return_code = application.exec()
    log_browser_message(f"event loop stopped with exit code {return_code}")
    return return_code


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--chat-browser", action="store_true")
    parser.add_argument("--parent-handle", required=True, type=parse_parent_handle)
    parser.add_argument("--profile-directory", required=True, type=pathlib.Path)
    parser.add_argument("--shutdown-file", required=True, type=pathlib.Path)
    options = parser.parse_args(arguments)
    try:
        return run_browser(
            options.parent_handle,
            options.profile_directory,
            options.shutdown_file,
        )
    except Exception:
        log_browser_message("could not start or remain attached")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
