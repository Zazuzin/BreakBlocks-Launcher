"""Windows hotkey overlay for the already embedded BreakBlocks web chat.

The same QWebEngineView is moved between the launcher host and this window.
No second website session or Minecraft mod is created.
"""

from __future__ import annotations

import ctypes
import os
import pathlib
import time
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

HOTKEY_ID = 0xBBC1
WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
VK_F9 = 0x78


def is_overlay_hotkey(event_type, message) -> bool:
    """Match a WM_HOTKEY delivered either to a Qt window or its event dispatcher."""
    if bytes(event_type) not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
        return False
    event = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
    return event.message == WM_HOTKEY and event.wParam == HOTKEY_ID


def read_game_pids(path: pathlib.Path) -> set[int]:
    """Treat an absent or partially written game list as empty."""
    try:
        return {int(line) for line in path.read_text(encoding="ascii").splitlines() if line.isdigit() and int(line) > 0}
    except OSError:
        return set()


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        if is_overlay_hotkey(event_type, message):
            self.callback()
            return True, 0
        return False, 0


class WindowsChatOverlay(QObject):
    """Move the live chat view over a launched Minecraft window on Ctrl+Shift+F9."""

    def __init__(self, application, host, launcher_handle, game_file, visible_file, mark_read):
        super().__init__(application)
        self.application = application
        self.host = host
        self.launcher_handle = launcher_handle
        self.game_file = pathlib.Path(game_file)
        self.visible_file = pathlib.Path(visible_file)
        self.mark_read = mark_read
        self.game_pids = set()
        self.game_window = 0
        self.visible = False
        self.registered = False
        self.last_registration_attempt = 0.0
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
        self.user32.RegisterHotKey.restype = wintypes.BOOL
        self.user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
        self.user32.UnregisterHotKey.restype = wintypes.BOOL
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        self.user32.GetWindowRect.restype = wintypes.BOOL
        self.user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
        self.user32.SetWindowPos.restype = wintypes.BOOL
        self.user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
        self.user32.SetForegroundWindow.restype = wintypes.BOOL

        self.window = QWidget()
        self.window.setWindowTitle("BreakBlocks Chat")
        self.window.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.window.setStyleSheet("background: #202020; color: #f5f5f5;")
        layout = QVBoxLayout(self.window)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        heading = QWidget()
        row = QHBoxLayout(heading)
        row.setContentsMargins(16, 7, 10, 7)
        row.addWidget(QLabel("BREAKBLOCKS CHAT"))
        row.addStretch()
        row.addWidget(QLabel("Ctrl+Shift+F9 or Esc to return to Minecraft"))
        close = QPushButton("×")
        close.setFixedWidth(32)
        close.clicked.connect(self.hide)
        row.addWidget(close)
        layout.addWidget(heading)
        self.browser_area = QWidget()
        self.browser_area.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        layout.addWidget(self.browser_area, 1)
        self.browser_area.winId()
        self.window.winId()

        self.hotkey_filter = _HotkeyFilter(self.toggle)
        application.installNativeEventFilter(self.hotkey_filter)
        application.installEventFilter(self)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(250)
        print(f"Chat overlay: ready; waiting for Minecraft PIDs in {self.game_file}", flush=True)

    def _foreground(self):
        handle = self.user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        if handle:
            self.user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        return handle, pid.value

    def update(self):
        active = read_game_pids(self.game_file)
        if active != self.game_pids:
            self.game_pids = active
            print(f"Chat overlay: active Minecraft PIDs {sorted(active)}", flush=True)
        if active and not self.registered:
            # Register for this real HWND. Qt delivers its WM_HOTKEY as a
            # windows_generic_MSG, even while the overlay is hidden.
            now = time.monotonic()
            if now - self.last_registration_attempt >= 5:
                self.last_registration_attempt = now
                ctypes.set_last_error(0)
                self.registered = bool(self.user32.RegisterHotKey(
                    int(self.window.winId()), HOTKEY_ID,
                    MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_F9,
                ))
                if self.registered:
                    print("Chat overlay: Ctrl+Shift+F9 registered", flush=True)
                else:
                    print(
                        f"Chat overlay: Ctrl+Shift+F9 registration failed "
                        f"(Windows error {ctypes.get_last_error()}); retrying",
                        flush=True,
                    )
        elif not active and self.registered:
            self.user32.UnregisterHotKey(int(self.window.winId()), HOTKEY_ID)
            self.registered = False
            print("Chat overlay: hotkey released", flush=True)
        if self.visible:
            _, pid = self._foreground()
            if not active or (pid not in active and pid != os.getpid()):
                self.hide()

    def toggle(self):
        print("Chat overlay: Ctrl+Shift+F9 received", flush=True)
        if self.visible:
            self.hide()
            return
        handle, pid = self._foreground()
        if pid not in self.game_pids:
            print(
                f"Chat overlay: foreground PID {pid} is not a launched Minecraft "
                f"PID {sorted(self.game_pids)}",
                flush=True,
            )
            return
        bounds = wintypes.RECT()
        if not self.user32.GetWindowRect(handle, ctypes.byref(bounds)):
            print(
                f"Chat overlay: could not read Minecraft window bounds "
                f"(Windows error {ctypes.get_last_error()})",
                flush=True,
            )
            return
        width = max(1, bounds.right - bounds.left)
        height = max(1, bounds.bottom - bounds.top)
        if width < 640 or height < 450:
            print(f"Chat overlay: Minecraft window is too small: {width}x{height}", flush=True)
            return
        self.game_window = handle
        self.window.show()
        # Use native window coordinates so mixed-DPI monitors position correctly.
        positioned = self.user32.SetWindowPos(
            int(self.window.winId()), -1,
            bounds.left + round(width * 0.1), bounds.top + round(height * 0.08),
            round(width * 0.8), round(height * 0.84), 0x0040,
        )
        if not positioned:
            print(
                f"Chat overlay: positioning failed (Windows error "
                f"{ctypes.get_last_error()})",
                flush=True,
            )
            self.window.hide()
            return
        self.host.parent_handle = int(self.browser_area.winId())
        if not self.host._embed_windows_child():
            print("Chat overlay: could not move the chat window into the overlay", flush=True)
            self.host.parent_handle = self.launcher_handle
            self.window.hide()
            return
        if not self.host.resize():
            print("Chat overlay: could not size the chat window", flush=True)
        self.visible = True
        self.visible_file.write_text("visible\n", encoding="ascii")
        self.mark_read()
        self.window.activateWindow()
        focused = bool(self.user32.SetForegroundWindow(int(self.window.winId())))
        print(f"Chat overlay: shown; focused={focused}", flush=True)

    def hide(self):
        if not self.visible:
            return
        self.visible = False
        self.host.parent_handle = self.launcher_handle
        self.host._embed_windows_child()
        self.host.resize()
        self.visible_file.unlink(missing_ok=True)
        self.window.hide()
        print("Chat overlay: hidden", flush=True)
        if self.game_window:
            self.user32.SetForegroundWindow(self.game_window)
            self.game_window = 0

    def eventFilter(self, watched, event):
        if self.visible and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.hide()
            return True
        return False

    def shutdown(self):
        self.timer.stop()
        self.hide()
        if self.registered:
            self.user32.UnregisterHotKey(int(self.window.winId()), HOTKEY_ID)
            self.registered = False
        self.application.removeNativeEventFilter(self.hotkey_filter)
        self.application.removeEventFilter(self)
        self.window.close()
