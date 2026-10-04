"""Move the existing chat session over launched Minecraft windows on X11."""

from __future__ import annotations

import os
import pathlib
import time

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import launcher_preferences
from x11_windows import X11Windows


def read_game_pids(path):
    try:
        return {
            int(line)
            for line in pathlib.Path(path).read_text(encoding="ascii").splitlines()
            if line.isdigit() and int(line) > 0
        }
    except OSError:
        return set()


class LinuxChatOverlay(QObject):
    def __init__(self, application, host, launcher_handle, game_file, visible_file, mark_read):
        super().__init__(application)
        self.application, self.host = application, host
        self.launcher_handle = launcher_handle
        self.game_file, self.visible_file = pathlib.Path(game_file), pathlib.Path(visible_file)
        self.mark_read = mark_read
        self.x11 = X11Windows()
        self.game_pids = set()
        self.game_window = 0
        self.visible = False
        self.enabled = True
        self.hotkey = "Ctrl+Shift+F9"
        self.registered_window = 0
        self.hotkey_target = 0
        self.last_registration_attempt = 0.0
        self.closed = False
        self.window = QWidget()
        self.window.setWindowTitle("BreakBlocks Chat Overlay")
        self.window.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.window.setStyleSheet("background: #202020; color: #f5f5f5;")
        layout = QVBoxLayout(self.window)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        heading = QWidget()
        row = QHBoxLayout(heading)
        row.setContentsMargins(16, 7, 10, 7)
        row.addWidget(QLabel("BREAKBLOCKS CHAT"))
        row.addStretch()
        self.hotkey_hint = QLabel("Ctrl+Shift+F9 or Esc to return to Minecraft")
        row.addWidget(self.hotkey_hint)
        close = QPushButton("×")
        close.setFixedWidth(32)
        close.clicked.connect(self.hide)
        row.addWidget(close)
        layout.addWidget(heading)
        self.browser_area = QWidget()
        self.browser_area.setAttribute(Qt.WA_NativeWindow, True)
        layout.addWidget(self.browser_area, 1)
        self.browser_area.winId()
        self.window.winId()
        self.window.installEventFilter(self)
        host.qt_view.installEventFilter(self)
        self.focus_proxy = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(50)
        print(
            "Chat overlay: Linux X11 ready; Minecraft must use X11/XWayland. "
            "Use a windowed or borderless game; native Wayland and Steam Deck "
            "Gaming Mode are not supported.",
            flush=True,
        )

    def apply_preferences(self, preferences):
        values = launcher_preferences.normalized(preferences)
        hotkey = values["overlay_hotkey"]
        if self.hotkey != hotkey or not values["overlay_enabled"]:
            self.release_hotkey()
        self.hotkey, self.enabled = hotkey, values["overlay_enabled"]
        self.hotkey_hint.setText(f"{hotkey} or Esc to return to Minecraft")
        self.hotkey_hint.setStyleSheet(
            f"font-size: {round(13 * values['overlay_text_scale'] / 100)}px;"
        )
        if not self.enabled:
            self.hide()
        self.update()

    def release_hotkey(self):
        self.x11.ungrab_hotkey()
        self.registered_window = 0
        self.hotkey_target = 0
        self.last_registration_attempt = 0.0

    def update(self):
        if self.closed:
            return
        proxy = self.host.qt_view.focusProxy()
        if proxy is not None and proxy is not self.focus_proxy:
            proxy.installEventFilter(self)
            self.focus_proxy = proxy
        self.game_pids = read_game_pids(self.game_file)
        if not self.game_pids or not self.enabled:
            self.hide(restore_focus=False)
            self.release_hotkey()
            return
        if self.x11.hotkey_pressed():
            self.toggle()
        foreground, pid = self.x11.foreground()
        if self.visible and (
            self.x11.property(self.game_window, "_NET_WM_PID") not in self.game_pids
            or not self.game_pids
            or (pid not in self.game_pids and pid != os.getpid())
        ):
            self.hide(restore_focus=False)
            foreground, pid = self.x11.foreground()
        target = 0
        if self.enabled:
            if self.visible:
                target = int(self.window.winId())
            elif pid in self.game_pids:
                target = foreground
        if self.hotkey_target != target:
            self.release_hotkey()
            self.hotkey_target = target
        if target and not self.registered_window:
            now = time.monotonic()
            if now - self.last_registration_attempt >= 5:
                self.last_registration_attempt = now
                if self.x11.grab_hotkey(target, self.hotkey):
                    self.registered_window = target
                    print(
                        f"Chat overlay: {self.hotkey} registered for Minecraft window {target}",
                        flush=True,
                    )
                else:
                    print(f"Chat overlay: {self.hotkey} is unavailable; retrying", flush=True)

    def toggle(self):
        if not self.enabled:
            return
        if self.visible:
            self.hide()
            return
        window, pid = self.x11.foreground()
        if pid not in self.game_pids:
            return
        bounds = self.x11.bounds(window)
        if bounds is None or bounds[2] < 640 or bounds[3] < 450:
            return
        self.game_window = window
        scale = self.window.devicePixelRatioF()
        x, y, width, height = bounds
        self.window.setGeometry(
            round((x + width * 0.1) / scale),
            round((y + height * 0.08) / scale),
            round(width * 0.8 / scale),
            round(height * 0.84 / scale),
        )
        self.window.layout().activate()
        # Inside the overlay both widgets belong to Qt. Give the browser a
        # real QWidget parent so Qt routes keyboard focus into WebEngine.
        # Native X11 parenting alone leaves two independent Qt focus windows.
        self.host.qt_view.setParent(self.browser_area)
        self.host.parent_handle = int(self.browser_area.winId())
        if not self.host._embed_x11_child():
            self.return_to_launcher()
            self.game_window = 0
            return
        self.visible = True
        self.window.show()
        self.host.qt_view.show()
        self.window.layout().activate()
        if not self.host.resize():
            self.hide()
            return
        self.visible_file.write_text("visible\n", encoding="ascii")
        self.mark_read()
        self.window.raise_()
        self.window.activateWindow()
        self.x11.focus(int(self.window.winId()))
        self.host.qt_view.setFocus()
        self.x11.focus(self.host.child_handle)
        self.release_hotkey()
        print("Chat overlay: Linux overlay shown", flush=True)

    def return_to_launcher(self):
        self.host.parent_handle = self.launcher_handle
        self.host.qt_view.setParent(None)
        self.host.qt_view.setWindowFlags(Qt.FramelessWindowHint | Qt.BypassWindowManagerHint)
        if not self.host.resize():
            print("Chat overlay: chat could not return to launcher", flush=True)
            return
        self.host.qt_view.show()
        self.host.resize()

    def hide(self, restore_focus=True):
        if not self.visible:
            return
        self.visible = False
        self.visible_file.unlink(missing_ok=True)
        self.release_hotkey()
        try:
            self.return_to_launcher()
        finally:
            self.window.hide()
            if (
                restore_focus
                and self.game_window
                and self.x11.property(self.game_window, "_NET_WM_PID") in self.game_pids
            ):
                self.x11.focus(self.game_window)
            self.game_window = 0
            print("Chat overlay: Linux overlay hidden", flush=True)

    def eventFilter(self, watched, event):
        if watched is self.window and self.visible:
            if event.type() == QEvent.Close:
                self.hide()
                event.ignore()
                return True
            if event.type() == QEvent.Hide:
                self.hide()
        if self.visible and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.hide()
            return True
        return False

    def shutdown(self):
        if self.closed:
            return
        self.timer.stop()
        self.hide(restore_focus=False)
        self.closed = True
        self.x11.close()
        self.window.removeEventFilter(self)
        self.host.qt_view.removeEventFilter(self)
        self.window.close()
