import contextlib
import ctypes
import inspect
import io
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import chat_browser
import zazu_launcher


def test_chat_url_is_the_authenticated_breakblocks_connect_page():
    assert chat_browser.CHAT_URL == "https://irc.breakblocks.com/#/connect"
    assert zazu_launcher.BREAKBLOCKS_CHAT_WEB_URL == chat_browser.CHAT_URL


def test_profile_directory_is_private_and_persistent():
    with tempfile.TemporaryDirectory() as temporary:
        profile = chat_browser.prepare_profile_directory(Path(temporary) / "profile")
        assert profile.is_dir()
        if os.name != "nt":
            assert profile.stat().st_mode & 0o777 == 0o700


def test_only_the_secure_breakblocks_chat_origin_is_trusted():
    assert chat_browser.is_trusted_chat_origin("https://irc.breakblocks.com")
    assert chat_browser.is_trusted_chat_origin("https://irc.breakblocks.com/#/connect")
    assert not chat_browser.is_trusted_chat_origin("http://irc.breakblocks.com")
    assert not chat_browser.is_trusted_chat_origin("https://evil.example")
    assert not chat_browser.is_trusted_chat_origin("https://irc.breakblocks.com.evil.example")


def test_chat_notification_counter_only_increments_while_chat_is_hidden():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        unread = root / chat_browser.UNREAD_FILE_NAME
        visible = root / chat_browser.VISIBLE_FILE_NAME
        assert chat_browser.record_chat_notification(unread, visible) == 1
        assert chat_browser.record_chat_notification(unread, visible) == 2
        visible.write_text("visible\n", encoding="utf-8")
        assert chat_browser.record_chat_notification(unread, visible) == 2
        assert chat_browser.write_unread_count(unread, 0) == 0
        assert chat_browser.read_unread_count(unread) == 0


def test_stale_overlay_marker_does_not_suppress_new_messages():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        unread = root / chat_browser.UNREAD_FILE_NAME
        launcher_visible = root / chat_browser.VISIBLE_FILE_NAME
        stale_overlay_marker = root / chat_browser.OVERLAY_VISIBLE_FILE_NAME
        stale_overlay_marker.write_text("visible\n", encoding="ascii")
        assert chat_browser.record_chat_notification(
            unread, launcher_visible, stale_overlay_marker, overlay_visible=False
        ) == 1
        assert chat_browser.record_chat_notification(
            unread, launcher_visible, stale_overlay_marker, overlay_visible=True
        ) == 1


def test_unread_messages_count_when_game_has_focus_even_if_chat_tab_is_selected():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        unread = root / chat_browser.UNREAD_FILE_NAME
        chat_marker = root / chat_browser.VISIBLE_FILE_NAME
        chat_marker.write_text("visible\n", encoding="ascii")
        foreground = [456]
        roots = {123: 100, 456: 100, 789: 789}
        windows = SimpleNamespace(
            GetForegroundWindow=lambda: foreground[0],
            GetAncestor=lambda handle, _mode: roots[handle],
        )
        assert chat_browser.chat_page_is_visible(chat_marker, 123, windows)
        assert chat_browser.record_chat_notification(
            unread, chat_marker, chat_visible=True
        ) == 0
        foreground[0] = 789  # Minecraft is in front of the launcher.
        assert not chat_browser.chat_page_is_visible(chat_marker, 123, windows)
        assert chat_browser.record_chat_notification(
            unread, chat_marker, chat_visible=False
        ) == 1


def test_browser_process_does_not_quit_when_reparented_into_tk():
    application = SimpleNamespace()
    application.setQuitOnLastWindowClosed = lambda value: setattr(
        application, "quit_on_last_window", value
    )
    chat_browser.configure_application_lifecycle(application)
    assert application.quit_on_last_window is False


def test_windows_host_uses_native_cross_process_parenting():
    source = inspect.getsource(chat_browser.NativeHost._attach_windows)
    embed_source = inspect.getsource(chat_browser.NativeHost._embed_windows_child)
    assert "_embed_windows_child" in source
    assert "SetParent" in embed_source
    assert "0x40000000" in embed_source  # WS_CHILD
    assert "GetParent" in embed_source
    assert "SetWindowPos" in embed_source


def test_windows_resize_refreshes_and_reattaches_qt_child_handle():
    source = inspect.getsource(chat_browser.NativeHost._resize_windows)
    assert "IsWindow(self.parent_handle)" in source
    assert "int(self.qt_view.winId())" in source
    assert "_embed_windows_child" in source
    assert "MoveWindow" in source


def test_windows_resize_skips_unchanged_geometry_and_resizes_after_parent_change():
    dimensions = [640, 480]
    moves = []
    host = chat_browser.NativeHost(99, 77, qt_view=SimpleNamespace(winId=lambda: 77))

    def get_client_rect(_parent, rect):
        rect._obj.right, rect._obj.bottom = dimensions
        return 1

    def move_window(*args):
        moves.append(args)
        return 1

    fake_api = SimpleNamespace(
        IsWindow=lambda _handle: True,
        GetParent=lambda _child: host.parent_handle,
        GetClientRect=get_client_rect,
        MoveWindow=move_window,
    )
    host._windows_api = lambda: (fake_api, ctypes.c_void_p)
    assert host._resize_windows()
    assert len(moves) == 1
    assert host._resize_windows()
    assert len(moves) == 1
    dimensions[0] = 800
    assert host._resize_windows()
    assert len(moves) == 2
    host.parent_handle = 100
    assert host._resize_windows()
    assert len(moves) == 3


def test_parent_handle_validation_rejects_invalid_values():
    assert chat_browser.parse_parent_handle("123") == 123
    assert chat_browser.parse_parent_handle("0x20") == 32
    for value in ("", "not-a-handle", "0", "-2"):
        try:
            chat_browser.parse_parent_handle(value)
        except Exception:
            pass
        else:
            raise AssertionError(f"Invalid parent handle was accepted: {value!r}")


def test_browser_helper_rejects_an_overridden_url():
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            chat_browser.main(
                [
                    "--chat-browser",
                    "--parent-handle",
                    "1",
                    "--profile-directory",
                    "/tmp/breakblocks-test-profile",
                    "--shutdown-file",
                    "/tmp/breakblocks-test-profile/stop",
                    "--url",
                    "https://example.invalid/",
                ]
            )
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("The embedded chat browser accepted an overridden URL")


def test_launcher_starts_browser_with_a_dedicated_local_profile():
    with tempfile.TemporaryDirectory() as temporary:
        launcher = SimpleNamespace(store=SimpleNamespace(root=Path(temporary)))
        command = zazu_launcher.Launcher.chat_browser_command(launcher, 456)
        assert "--chat-browser" in command
        assert command[command.index("--parent-handle") + 1] == "456"
        profile = Path(command[command.index("--profile-directory") + 1])
        assert profile == Path(temporary) / chat_browser.PROFILE_DIRECTORY_NAME
        assert profile.is_dir()
        shutdown = Path(command[command.index("--shutdown-file") + 1])
        assert shutdown.parent == profile
        assert not shutdown.exists()
        unread = Path(command[command.index("--unread-file") + 1])
        visible = Path(command[command.index("--visible-file") + 1])
        assert unread == profile / chat_browser.UNREAD_FILE_NAME
        assert visible == profile / chat_browser.VISIBLE_FILE_NAME
        assert "--url" not in command


def test_browser_grants_and_presents_breakblocks_notifications():
    source = inspect.getsource(chat_browser.run_browser)
    assert "PersistentPermissionsPolicy.StoreOnDisk" in source
    assert "setPushServiceEnabled(True)" in source
    assert "queryPermission" in source
    assert "PermissionType.Notifications" in source
    assert "page.permissionRequested.connect" in source
    assert "permission.deny()" in source
    assert "setNotificationPresenter" in source
    assert "record_chat_notification" in source


def test_chat_notification_uses_launcher_branding_and_compact_title():
    assert (
        chat_browser.format_notification_title("im_zazuzin (#BreakBlocks) says:")
        == "im_zazuzin · #BreakBlocks"
    )
    assert chat_browser.format_notification_title("Etianl says:") == "Etianl"
    assert chat_browser.format_notification_title("") == "BreakBlocks Chat"
    logo = chat_browser.notification_logo_path()
    assert logo is not None
    assert logo.name == "bbc_chicken_transparent.png"
    assert logo.is_file()
    source = inspect.getsource(chat_browser.run_browser)
    assert "notification_logo_path()" in source
    assert "format_notification_title(notification.title())" in source
    assert "self.setMinimumWidth(390)" in source
    assert "QTimer.singleShot(\n                8000," in source


def test_launcher_restores_and_clears_the_chat_unread_badge():
    sidebar_source = inspect.getsource(zazu_launcher.Launcher.build_sidebar)
    show_page_source = inspect.getsource(zazu_launcher.Launcher.show_page)
    monitor_source = inspect.getsource(zazu_launcher.Launcher.monitor_chat_browser)
    assert "chat_unread_badge" in sidebar_source
    assert 'set_chat_page_visible(name == "Chat")' in show_page_source
    assert "refresh_chat_unread_badge" in monitor_source


def test_chat_unread_badge_matches_sidebar_and_hover_backgrounds():
    sidebar_source = inspect.getsource(zazu_launcher.Launcher.build_sidebar)
    update_source = inspect.getsource(zazu_launcher.Launcher.update_chat_unread_badge_background)
    assert "bg_color=SIDEBAR" in sidebar_source
    assert 'button.bind(\n                    "<Enter>"' in sidebar_source
    assert 'button.bind(\n                    "<Leave>"' in sidebar_source
    assert "SURFACE_HOVER if hovered else SIDEBAR" in update_source
    assert "badge.configure(bg_color=background)" in update_source


def test_chat_fills_the_complete_area_beside_the_sidebar():
    chat_source = inspect.getsource(zazu_launcher.Launcher.chat_web_ui)
    show_page_source = inspect.getsource(zazu_launcher.Launcher.show_page)
    assert "page.grid_rowconfigure(0, weight=1)" in chat_source
    assert 'self.chat_browser_host.grid(row=0, column=0, sticky="nsew")' in chat_source
    assert "toolbar" not in chat_source
    chat_layout = show_page_source.index('if name == "Chat":')
    launcher_layout = show_page_source.index('elif name == "Launcher":')
    chat_layout_source = show_page_source[chat_layout:launcher_layout]
    assert "self.main_header.grid_remove()" in chat_layout_source
    assert "self.main_footer.grid_remove()" in chat_layout_source
    assert "self.page_host.grid_configure(padx=0, pady=0)" in chat_layout_source


def test_chat_sidebar_button_has_open_in_browser_context_menu():
    sidebar_source = inspect.getsource(zazu_launcher.Launcher.build_sidebar)
    menu_source = inspect.getsource(zazu_launcher.Launcher.show_chat_context_menu)
    assert 'button.bind("<Button-3>", self.show_chat_context_menu)' in sidebar_source
    assert 'label="Open in browser"' in sidebar_source
    assert "BREAKBLOCKS_CHAT_WEB_URL" in sidebar_source
    assert "menu.tk_popup(event.x_root, event.y_root)" in menu_source


def test_native_irc_transport_and_credentials_are_not_used_by_launcher():
    source = Path(zazu_launcher.__file__).read_text(encoding="utf-8")
    assert "import irc_client" not in source
    assert "IrcClient(" not in source
    assert "irc_server_password" in source  # migration removes legacy saved values
    assert "settings.pop(obsolete_key, None)" in source
    assert not hasattr(zazu_launcher.Launcher, "connect_irc")
    assert not hasattr(zazu_launcher.Launcher, "send_irc_message")


def test_chat_page_starts_the_browser_only_when_opened():
    source = inspect.getsource(zazu_launcher.Launcher.show_page)
    assert 'if name == "Chat"' in source
    assert "self.ensure_chat_browser()" in source
    constructor = inspect.getsource(zazu_launcher.Launcher.__init__)
    assert "connect_irc_on_startup" not in constructor


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"Passed {len(tests)} embedded chat browser tests")
