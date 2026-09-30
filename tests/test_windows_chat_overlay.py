"""Small cross-process checks for the Windows chat overlay."""

import tempfile
from pathlib import Path

import chat_browser
from windows_chat_overlay import read_game_pids


def test_game_process_list_ignores_partial_and_invalid_entries():
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / chat_browser.GAME_PROCESS_FILE_NAME
        assert read_game_pids(path) == set()
        path.write_text("812\n0\n-6\nnot-a-pid\n1214\n", encoding="ascii")
        assert read_game_pids(path) == {812, 1214}


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


if __name__ == "__main__":
    test_game_process_list_ignores_partial_and_invalid_entries()
    test_chat_notifications_are_not_unread_while_overlay_is_visible()
