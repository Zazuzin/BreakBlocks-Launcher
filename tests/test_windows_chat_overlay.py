"""Small cross-process checks for the Windows chat overlay."""

import ctypes
import tempfile
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import chat_browser
from windows_chat_overlay import (
    HOTKEY_ID,
    WM_HOTKEY,
    WindowsChatOverlay,
    is_overlay_hotkey,
    read_game_pids,
)


def test_game_process_list_ignores_partial_and_invalid_entries():
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / chat_browser.GAME_PROCESS_FILE_NAME
        assert read_game_pids(path) == set()
        path.write_text("812\n0\n-6\nnot-a-pid\n1214\n", encoding="ascii")
        assert read_game_pids(path) == {812, 1214}


def test_hotkey_from_window_or_dispatcher_reaches_overlay():
    message = wintypes.MSG()
    message.message = WM_HOTKEY
    message.wParam = HOTKEY_ID
    address = ctypes.addressof(message)
    assert is_overlay_hotkey(b"windows_generic_MSG", address)
    assert is_overlay_hotkey(b"windows_dispatcher_MSG", address)
    message.wParam = HOTKEY_ID + 1
    assert not is_overlay_hotkey(b"windows_generic_MSG", address)
    assert not is_overlay_hotkey(b"xcb_generic_event_t", address)


def test_chat_notifications_are_not_unread_while_overlay_is_visible():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        unread = root / chat_browser.UNREAD_FILE_NAME
        launcher_visible = root / chat_browser.VISIBLE_FILE_NAME
        overlay_visible = root / chat_browser.OVERLAY_VISIBLE_FILE_NAME
        assert chat_browser.record_chat_notification(unread, launcher_visible, overlay_visible) == 1
        overlay_visible.write_text("visible\n", encoding="ascii")
        assert chat_browser.record_chat_notification(unread, launcher_visible, overlay_visible) == 1
        overlay_visible.unlink()
        assert chat_browser.record_chat_notification(unread, launcher_visible, overlay_visible) == 2


def test_overlay_settings_release_the_old_shortcut_and_disable_visible_overlay():
    overlay = SimpleNamespace(
        registered=True,
        hotkey="Ctrl+Shift+F9",
        enabled=True,
        visible=True,
        user32=SimpleNamespace(UnregisterHotKey=Mock()),
        window=SimpleNamespace(winId=lambda: 456),
        hotkey_hint=Mock(),
        hide=Mock(),
        update=Mock(),
    )
    WindowsChatOverlay.apply_preferences(
        overlay, {"overlay_enabled": False, "overlay_hotkey": "Alt+F10", "overlay_text_scale": 150}
    )
    overlay.user32.UnregisterHotKey.assert_called_once_with(456, HOTKEY_ID)
    assert not overlay.registered and not overlay.enabled
    assert overlay.hotkey_key == 0x79 and overlay.hotkey_modifiers == 1
    overlay.hide.assert_called_once()
    overlay.hotkey_hint.setText.assert_called_once_with("Alt+F10 or Esc to return to Minecraft")


if __name__ == "__main__":
    test_overlay_settings_release_the_old_shortcut_and_disable_visible_overlay()
    test_game_process_list_ignores_partial_and_invalid_entries()
    test_hotkey_from_window_or_dispatcher_reaches_overlay()
    test_chat_notifications_are_not_unread_while_overlay_is_visible()
