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
import re
import sys
import traceback
import urllib.parse

CHAT_URL = "https://irc.breakblocks.com/#/connect"
CHAT_ORIGIN = "https://irc.breakblocks.com"
PROFILE_DIRECTORY_NAME = "web-chat-profile"
UNREAD_FILE_NAME = "unread-notifications.count"
VISIBLE_FILE_NAME = ".chat-visible"
OVERLAY_VISIBLE_FILE_NAME = ".overlay-visible"
GAME_PROCESS_FILE_NAME = ".active-game-pids.txt"


def notification_logo_path() -> pathlib.Path | None:
    """Return the bundled BBC chicken logo when it is available."""
    roots = []
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        roots.append(pathlib.Path(frozen_root))
    roots.extend(
        (
            pathlib.Path(__file__).resolve().parent,
            pathlib.Path(sys.executable).resolve().parent,
        )
    )
    for root in roots:
        candidate = root / "assets" / "community" / "bbc_chicken_transparent.png"
        if candidate.is_file():
            return candidate
    return None


def format_notification_title(title: str) -> str:
    """Turn the website notification title into a compact launcher heading."""
    value = str(title or "").strip()
    match = re.match(r"^(.+?)\s*\((#[^)]+)\)\s+says:\s*$", value, re.IGNORECASE)
    if match:
        nickname, channel = (part.strip() for part in match.groups())
        return f"{nickname} · {channel}"
    value = re.sub(r"\s+says:\s*$", "", value, flags=re.IGNORECASE).strip()
    return value or "BreakBlocks Chat"


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


def is_trusted_chat_origin(origin) -> bool:
    """Return whether a WebEngine permission belongs to BreakBlocks chat."""
    value = origin.toString() if hasattr(origin, "toString") else str(origin)
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError):
        return False
    return (
        parsed.scheme.lower() == "https"
        and (parsed.hostname or "").lower() == "irc.breakblocks.com"
        and port in (None, 443)
    )


def read_unread_count(path: pathlib.Path) -> int:
    try:
        return max(0, min(999, int(path.read_text(encoding="utf-8").strip())))
    except (OSError, TypeError, ValueError):
        return 0


def write_unread_count(path: pathlib.Path, count: int) -> int:
    """Atomically update the tiny counter shared with the Tk launcher."""
    value = max(0, min(999, int(count)))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(f"{value}\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return value


def record_chat_notification(
    unread_file: pathlib.Path,
    visible_file: pathlib.Path,
    overlay_visible_file: pathlib.Path | None = None,
    *,
    overlay_visible: bool | None = None,
) -> int:
    """Increment unread chat unless the launcher page or overlay is visible."""
    if overlay_visible is None:
        overlay_visible = overlay_visible_file is not None and overlay_visible_file.is_file()
    if visible_file.is_file() or overlay_visible:
        return read_unread_count(unread_file)
    return write_unread_count(unread_file, read_unread_count(unread_file) + 1)


class NativeHost:
    """Attach and resize a Qt window inside an existing native parent."""

    def __init__(self, parent_handle: int, child_handle: int, qt_view=None):
        self.parent_handle = parent_handle
        self.child_handle = child_handle
        self.qt_view = qt_view
        self._windows_resize_state = None
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
        """Attach the browser HWND to the Tk host HWND.

        The launcher and browser deliberately run in separate processes, so a
        Qt foreign-window parent is not sufficient on Windows: it can leave the
        QWebEngineView as an ordinary external top-level window.  Win32
        SetParent is the native cross-process embedding mechanism.  The resize
        timer refreshes and reattaches the HWND if Qt recreates it while the
        page is loading.
        """
        if self.qt_view is None:
            raise RuntimeError("The Windows web chat host requires its Qt view")
        self.child_handle = int(self.qt_view.winId())
        self.qt_view.show()
        if not self._embed_windows_child():
            raise OSError("The launcher chat window could not be embedded")
        if not self._resize_windows():
            raise OSError("The launcher chat window could not be sized")

    def _windows_api(self):
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        window_handle = ctypes.c_void_p
        user32.IsWindow.argtypes = (window_handle,)
        user32.IsWindow.restype = ctypes.c_int
        user32.GetParent.argtypes = (window_handle,)
        user32.GetParent.restype = window_handle
        user32.SetParent.argtypes = (window_handle, window_handle)
        user32.SetParent.restype = window_handle
        user32.GetWindowLongPtrW.argtypes = (window_handle, ctypes.c_int)
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = (
            window_handle,
            ctypes.c_int,
            ctypes.c_ssize_t,
        )
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowPos.argtypes = (
            window_handle,
            window_handle,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        )
        user32.SetWindowPos.restype = ctypes.c_int
        return user32, window_handle

    def _embed_windows_child(self, user32=None) -> bool:
        if self.qt_view is None:
            return False
        if user32 is None:
            user32, _ = self._windows_api()

        child_handle = int(self.qt_view.winId())
        if not user32.IsWindow(self.parent_handle) or not user32.IsWindow(child_handle):
            return False

        # SetParent does not alter WS_CHILD/WS_POPUP itself.  Apply the child
        # style explicitly so Windows keeps the browser inside the launcher,
        # out of Alt+Tab and off the taskbar.
        style = user32.GetWindowLongPtrW(child_handle, -16)
        child_style = (style | 0x40000000 | 0x10000000) & ~(
            0x80000000 | 0x00C00000 | 0x00040000 | 0x00080000 | 0x00020000 | 0x00010000
        )
        user32.SetWindowLongPtrW(child_handle, -16, child_style)
        extended_style = user32.GetWindowLongPtrW(child_handle, -20)
        user32.SetWindowLongPtrW(child_handle, -20, extended_style & ~0x00040000)

        ctypes.set_last_error(0)
        user32.SetParent(child_handle, self.parent_handle)
        if user32.GetParent(child_handle) != self.parent_handle:
            return False

        # Recalculate the non-client area after changing the native styles,
        # show the browser, and place it above the launcher's loading fallback.
        user32.SetWindowPos(
            child_handle,
            0,
            0,
            0,
            0,
            0,
            0x0001 | 0x0002 | 0x0010 | 0x0020 | 0x0040,
        )

        self.child_handle = child_handle
        self._windows_resize_state = None
        return True

    def _resize_windows(self) -> bool:
        user32, window_handle = self._windows_api()
        if not user32.IsWindow(self.parent_handle):
            return False

        if self.qt_view is None:
            return False

        child_handle = int(self.qt_view.winId())
        if not user32.IsWindow(child_handle):
            # Qt can briefly replace its native handle while WebEngine starts.
            # Keep the process alive and retry on the next timer tick.
            return True
        if (
            child_handle != self.child_handle
            or user32.GetParent(child_handle) != self.parent_handle
        ):
            self.child_handle = child_handle
            if not self._embed_windows_child(user32):
                return True

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
            # A valid host HWND can be temporarily unavailable while Tk is
            # changing page layout.  Keep the browser alive and retry.
            return True
        width = max(1, rectangle.right - rectangle.left)
        height = max(1, rectangle.bottom - rectangle.top)
        state = (self.parent_handle, child_handle, width, height)
        if state == self._windows_resize_state:
            return True
        moved = bool(user32.MoveWindow(child_handle, 0, 0, width, height, True))
        if moved:
            self._windows_resize_state = state
        return moved

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
    unread_file: pathlib.Path,
    visible_file: pathlib.Path,
    game_process_file: pathlib.Path | None = None,
) -> int:
    if sys.platform.startswith("linux"):
        # Tk runs through X11/XWayland.  Matching that backend permits the Qt
        # window to become a real child of the Tk Chat host under Wayland too.
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    from PySide6.QtCore import QPoint, Qt, QTimer, QUrl
    from PySide6.QtGui import QMouseEvent, QPixmap
    from PySide6.QtWebEngineCore import (
        QWebEnginePage,
        QWebEnginePermission,
        QWebEngineProfile,
    )
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    profile_directory = prepare_profile_directory(profile_directory)
    game_process_file = game_process_file or profile_directory / GAME_PROCESS_FILE_NAME
    overlay_visible_file = profile_directory / OVERLAY_VISIBLE_FILE_NAME
    # This file is only a hint for other processes; a prior crashed helper may
    # have left it behind. The live Qt overlay state controls unread messages.
    overlay_visible_file.unlink(missing_ok=True)
    application = QApplication.instance() or QApplication(sys.argv[:1])
    configure_application_lifecycle(application)
    application.setApplicationName("BreakBlocks Chat")
    application.setOrganizationName("BreakBlocks")

    profile = QWebEngineProfile("BreakBlocksChat", application)
    profile.setPersistentStoragePath(str(profile_directory / "storage"))
    profile.setCachePath(str(profile_directory / "cache"))
    profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
    profile.setPersistentPermissionsPolicy(
        QWebEngineProfile.PersistentPermissionsPolicy.StoreOnDisk
    )
    profile.setPushServiceEnabled(True)
    profile.setHttpUserAgent(f"{profile.httpUserAgent()} BreakBlocks-Launcher")

    page = QWebEnginePage(profile, application)

    notification_type = QWebEnginePermission.PermissionType.Notifications
    profile.queryPermission(QUrl(CHAT_ORIGIN), notification_type).grant()

    def handle_permission_request(permission) -> None:
        if permission.permissionType() != notification_type:
            return
        if is_trusted_chat_origin(permission.origin()):
            permission.grant()
        else:
            permission.deny()

    page.permissionRequested.connect(handle_permission_request)

    class ChatNotificationPopup(QWidget):
        """Small cross-platform desktop popup for WebEngine notifications."""

        def __init__(self):
            super().__init__(None)
            self.notification = None
            self.setWindowFlags(
                Qt.WindowType.ToolTip
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.setMinimumWidth(390)
            self.setStyleSheet(
                "QWidget { background: #242424; color: #f2f2f2; "
                "border: 1px solid #4b4b4b; border-radius: 8px; } "
                "QLabel { border: none; background: transparent; } "
                "QPushButton { border: none; background: transparent; "
                "color: #b8b8b8; font-weight: bold; padding: 3px 7px; } "
                "QPushButton:hover { color: white; }"
            )
            outer = QHBoxLayout(self)
            outer.setContentsMargins(14, 12, 10, 12)
            outer.setSpacing(12)
            self.icon_label = QLabel()
            self.icon_label.setFixedSize(46, 46)
            outer.addWidget(self.icon_label)
            text_layout = QVBoxLayout()
            text_layout.setSpacing(3)
            self.title_label = QLabel()
            self.title_label.setStyleSheet("font-weight: 700; font-size: 13px;")
            self.message_label = QLabel()
            self.message_label.setWordWrap(True)
            self.message_label.setMaximumWidth(420)
            text_layout.addWidget(self.title_label)
            text_layout.addWidget(self.message_label)
            outer.addLayout(text_layout, 1)
            close_button = QPushButton("×")
            close_button.clicked.connect(lambda _checked=False: self.close_notification())
            outer.addWidget(close_button, 0, Qt.AlignmentFlag.AlignTop)

        def present(self, notification) -> None:
            if self.notification is not None:
                self.close_notification()
            self.notification = notification
            self.title_label.setText(format_notification_title(notification.title()))
            self.message_label.setText(notification.message())
            logo_path = notification_logo_path()
            icon = QPixmap(str(logo_path)) if logo_path is not None else QPixmap()
            if not icon.isNull():
                self.icon_label.setPixmap(
                    icon.scaled(
                        self.icon_label.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self.icon_label.show()
            else:
                self.icon_label.hide()
            notification.closed.connect(self.close_notification)
            self.adjustSize()
            screen = QApplication.primaryScreen()
            if screen is not None:
                corner = screen.availableGeometry().bottomRight()
                self.move(corner - QPoint(self.width() + 18, self.height() + 18))
            self.show()
            notification.show()
            QTimer.singleShot(
                8000,
                lambda current=notification: self.close_if_current(current),
            )

        def close_if_current(self, notification) -> None:
            if self.notification is notification:
                self.close_notification()

        def close_notification(self) -> None:
            notification = self.notification
            self.notification = None
            self.hide()
            if notification is not None:
                notification.close()

        def mouseReleaseEvent(self, event: QMouseEvent) -> None:
            super().mouseReleaseEvent(event)
            if self.notification is not None and event.button() == Qt.MouseButton.LeftButton:
                self.notification.click()
                self.close_notification()

    notification_popup = ChatNotificationPopup()
    overlay = None

    def present_notification(notification) -> None:
        overlay_open = overlay is not None and overlay.visible
        count = record_chat_notification(
            unread_file, visible_file, overlay_visible_file,
            overlay_visible=overlay_open,
        )
        log_browser_message(
            f"notification received; unread={count}; overlay_open={overlay_open}; "
            f"launcher_chat_visible={visible_file.is_file()}"
        )
        notification_popup.present(notification)

    profile.setNotificationPresenter(present_notification)

    view = QWebEngineView()
    view.setPage(page)
    view.setWindowTitle("BreakBlocks Chat")
    view.setWindowFlag(Qt.FramelessWindowHint, True)
    view.setAttribute(Qt.WA_NativeWindow, True)
    view.resize(900, 600)
    view.show()

    host = NativeHost(parent_handle, int(view.winId()), qt_view=view)
    host.attach()
    if os.name == "nt":
        from windows_chat_overlay import WindowsChatOverlay

        overlay = WindowsChatOverlay(
            application, host, parent_handle, game_process_file, overlay_visible_file,
            lambda: write_unread_count(unread_file, 0),
        )
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
            if overlay is not None:
                overlay.shutdown()
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
    if overlay is not None:
        overlay.shutdown()
    log_browser_message(f"event loop stopped with exit code {return_code}")
    return return_code


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--chat-browser", action="store_true")
    parser.add_argument("--parent-handle", required=True, type=parse_parent_handle)
    parser.add_argument("--profile-directory", required=True, type=pathlib.Path)
    parser.add_argument("--shutdown-file", required=True, type=pathlib.Path)
    parser.add_argument("--unread-file", required=True, type=pathlib.Path)
    parser.add_argument("--visible-file", required=True, type=pathlib.Path)
    parser.add_argument("--game-process-file", type=pathlib.Path)
    options = parser.parse_args(arguments)
    try:
        return run_browser(
            options.parent_handle,
            options.profile_directory,
            options.shutdown_file,
            options.unread_file,
            options.visible_file,
            options.game_process_file,
        )
    except Exception:
        log_browser_message("could not start or remain attached")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
