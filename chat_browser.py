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

CHAT_URL = "https://irc.breakblocks.com/#/connect"
PROFILE_DIRECTORY_NAME = "web-chat-profile"


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

    def __init__(self, parent_handle: int, child_handle: int):
        self.parent_handle = parent_handle
        self.child_handle = child_handle
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
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        window_handle = ctypes.c_void_p
        user32.IsWindow.argtypes = (window_handle,)
        user32.IsWindow.restype = ctypes.c_int
        user32.SetParent.argtypes = (window_handle, window_handle)
        user32.SetParent.restype = window_handle
        get_style = user32.GetWindowLongPtrW
        set_style = user32.SetWindowLongPtrW
        get_style.argtypes = (window_handle, ctypes.c_int)
        get_style.restype = ctypes.c_ssize_t
        set_style.argtypes = (window_handle, ctypes.c_int, ctypes.c_ssize_t)
        set_style.restype = ctypes.c_ssize_t
        if not user32.IsWindow(self.parent_handle) or not user32.IsWindow(self.child_handle):
            raise OSError("The launcher chat window is no longer available")
        ctypes.set_last_error(0)
        previous_parent = user32.SetParent(self.child_handle, self.parent_handle)
        if not previous_parent:
            error = ctypes.get_last_error()
            if error:
                raise OSError(error, "Could not attach the web chat window")
        style = get_style(self.child_handle, -16)
        style = (style | 0x40000000 | 0x10000000) & ~(
            0x80000000 | 0x00C00000 | 0x00040000 | 0x00080000
        )
        set_style(self.child_handle, -16, style)
        self._resize_windows()

    def _resize_windows(self) -> bool:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        window_handle = ctypes.c_void_p
        user32.IsWindow.argtypes = (window_handle,)
        user32.IsWindow.restype = ctypes.c_int
        if not user32.IsWindow(self.parent_handle):
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
        user32.MoveWindow.argtypes = (
            window_handle,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        )
        user32.MoveWindow.restype = ctypes.c_int
        rectangle = Rect()
        if not user32.GetClientRect(self.parent_handle, ctypes.byref(rectangle)):
            return False
        width = max(1, rectangle.right - rectangle.left)
        height = max(1, rectangle.bottom - rectangle.top)
        return bool(user32.MoveWindow(self.child_handle, 0, 0, width, height, True))

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
    application.setQuitOnLastWindowClosed(False)
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

    host = NativeHost(parent_handle, int(view.winId()))
    host.attach()

    timer = QTimer(view)

    def keep_in_host() -> None:
        if shutdown_file.is_file():
            timer.stop()
            view.close()
            application.quit()
            return
        if not host.resize():
            timer.stop()
            application.quit()

    timer.timeout.connect(keep_in_host)
    timer.start(150)
    view.load(QUrl(CHAT_URL))
    return application.exec()


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--chat-browser", action="store_true")
    parser.add_argument("--parent-handle", required=True, type=parse_parent_handle)
    parser.add_argument("--profile-directory", required=True, type=pathlib.Path)
    parser.add_argument("--shutdown-file", required=True, type=pathlib.Path)
    options = parser.parse_args(arguments)
    return run_browser(
        options.parent_handle,
        options.profile_directory,
        options.shutdown_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
