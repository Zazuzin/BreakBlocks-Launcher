import contextlib
import ctypes
import inspect
import io
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import breakblocks_launcher
import chat_browser


def test_chat_url_is_the_authenticated_breakblocks_connect_page():
    assert chat_browser.CHAT_URL == "https://irc.breakblocks.com/#/connect"
    assert breakblocks_launcher.BREAKBLOCKS_CHAT_WEB_URL == chat_browser.CHAT_URL


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
        assert (
            chat_browser.record_chat_notification(
                unread, launcher_visible, stale_overlay_marker, overlay_visible=False
            )
            == 1
        )
        assert (
            chat_browser.record_chat_notification(
                unread, launcher_visible, stale_overlay_marker, overlay_visible=True
            )
            == 1
        )


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
        assert chat_browser.record_chat_notification(unread, chat_marker, chat_visible=True) == 0
        foreground[0] = 789  # Minecraft is in front of the launcher.
        assert not chat_browser.chat_page_is_visible(chat_marker, 123, windows)
        assert chat_browser.record_chat_notification(unread, chat_marker, chat_visible=False) == 1


def test_web_page_goes_into_background_when_chat_tab_or_launcher_loses_focus():
    with tempfile.TemporaryDirectory() as temporary:
        marker = Path(temporary) / chat_browser.VISIBLE_FILE_NAME
        foreground = [456]
        roots = {123: 100, 456: 100, 789: 789}
        windows = SimpleNamespace(
            GetForegroundWindow=lambda: foreground[0],
            GetAncestor=lambda handle, _mode: roots[handle],
        )
        marker.write_text("visible\n", encoding="ascii")
        assert chat_browser.chat_content_is_visible(marker, 123, False, windows)
        marker.unlink()  # Launcher tab is selected, but the browser stays connected.
        assert not chat_browser.chat_content_is_visible(marker, 123, False, windows)
        marker.write_text("visible\n", encoding="ascii")
        foreground[0] = 789  # Minecraft is in front of the launcher.
        assert not chat_browser.chat_content_is_visible(marker, 123, False, windows)
        assert chat_browser.chat_content_is_visible(marker, 123, True, windows)


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
        GetTopWindow=lambda _parent: 77,
        GetWindowLongPtrW=lambda _child, _index: 0x10000000,
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


def test_windows_chat_recovers_from_being_hidden_or_covered_without_resizing():
    visible = [0x10000000]
    top_child = [77]
    raised = []
    host = chat_browser.NativeHost(99, 77, qt_view=SimpleNamespace(winId=lambda: 77))

    def get_client_rect(_parent, rect):
        rect._obj.right, rect._obj.bottom = 640, 480
        return 1

    def position(*arguments):
        raised.append(arguments)
        visible[0] |= 0x10000000
        top_child[0] = 77
        return 1

    api = SimpleNamespace(
        IsWindow=lambda _handle: True,
        GetParent=lambda _child: 99,
        GetTopWindow=lambda _parent: top_child[0],
        GetWindowLongPtrW=lambda _child, _index: visible[0],
        SetWindowPos=position,
        GetClientRect=get_client_rect,
        MoveWindow=lambda *_arguments: 1,
    )
    host._windows_api = lambda: (api, ctypes.c_void_p)
    assert host._resize_windows()
    assert not raised
    visible[0] = 0
    assert host._resize_windows()
    assert visible[0] & 0x10000000
    top_child[0] = 88
    assert host._resize_windows()
    assert top_child[0] == 77
    assert len(raised) == 2
    assert all(arguments[-1] & 0x0010 for arguments in raised)  # SWP_NOACTIVATE


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
        launcher = SimpleNamespace(
            store=SimpleNamespace(root=Path(temporary), data={"settings": {}})
        )
        command = breakblocks_launcher.Launcher.chat_browser_command(launcher, 456)
        assert "--chat-browser" in command
        assert command[command.index("--parent-handle") + 1] == "456"
        profile = Path(command[command.index("--profile-directory") + 1])
        assert profile == Path(temporary) / chat_browser.PROFILE_DIRECTORY_NAME
        assert profile.is_dir()
        shutdown = Path(command[command.index("--shutdown-file") + 1])
        assert shutdown.parent == profile
        assert not shutdown.exists()
        ready = Path(command[command.index("--ready-file") + 1])
        assert ready.parent == profile
        assert not ready.exists()
        unread = Path(command[command.index("--unread-file") + 1])
        visible = Path(command[command.index("--visible-file") + 1])
        assert unread == profile / chat_browser.UNREAD_FILE_NAME
        assert visible == profile / chat_browser.VISIBLE_FILE_NAME
        assert "--url" not in command


def test_chat_child_keeps_the_packaged_runtime_environment():
    retry = SimpleNamespace(pack_forget=lambda: None)
    status = SimpleNamespace(set=lambda _message: None)
    launcher = SimpleNamespace(
        closing=False,
        chat_browser_process=None,
        chat_browser_monitor_id=None,
        chat_browser_retry_button=retry,
        chat_browser_status=status,
        chat_browser_host=SimpleNamespace(winfo_id=lambda: 123),
        chat_browser_command=lambda _handle: ["launcher", "--chat-browser"],
        update_idletasks=lambda: None,
        after=lambda _delay, _callback: 1,
        monitor_chat_browser=lambda: None,
    )
    paths = {
        "LD_LIBRARY_PATH": "/launcher/_internal",
        "TCL_LIBRARY": "/launcher/_internal/_tcl_data",
        "TK_LIBRARY": "/launcher/_internal/_tk_data",
        "FONTCONFIG_PATH": "/launcher/fonts",
    }
    with (
        mock.patch.dict(os.environ, paths),
        mock.patch.object(breakblocks_launcher.subprocess, "Popen") as spawn,
    ):
        breakblocks_launcher.Launcher.ensure_chat_browser(launcher)
    for key, value in paths.items():
        assert spawn.call_args.kwargs["env"][key] == value


def test_linux_chat_uses_x11_even_when_the_desktop_prefers_wayland():
    launcher = SimpleNamespace(
        closing=False,
        chat_browser_process=None,
        chat_browser_monitor_id=None,
        chat_browser_retry_button=SimpleNamespace(pack_forget=lambda: None),
        chat_browser_status=SimpleNamespace(set=lambda _message: None),
        chat_browser_host=SimpleNamespace(winfo_id=lambda: 123),
        chat_browser_command=lambda _handle: ["launcher", "--chat-browser"],
        update_idletasks=lambda: None,
        after=lambda _delay, _callback: 1,
        monitor_chat_browser=lambda: None,
    )
    with (
        mock.patch.dict(os.environ, {"QT_QPA_PLATFORM": "wayland"}),
        mock.patch.object(sys, "platform", "linux"),
        mock.patch.object(breakblocks_launcher.subprocess, "Popen") as spawn,
    ):
        breakblocks_launcher.Launcher.ensure_chat_browser(launcher)
    assert spawn.call_args.kwargs["env"]["QT_QPA_PLATFORM"] == "xcb"


def test_linux_game_processes_reach_the_overlay():
    with tempfile.TemporaryDirectory() as temporary:
        launcher = SimpleNamespace(
            launching_instances={"example"},
            running_instances={},
            overlay_game_pids={},
            chat_game_file=Path(temporary) / "game-pids",
            refresh_instances=lambda: None,
            store=SimpleNamespace(data={"settings": {"keep_launcher_open": True}}),
            ensure_chat_browser=mock.Mock(),
        )
        launcher.write_chat_game_processes = (
            lambda: breakblocks_launcher.Launcher.write_chat_game_processes(launcher)
        )
        with mock.patch.object(breakblocks_launcher, "log_launcher_message"):
            breakblocks_launcher.Launcher.mark_instance_running(launcher, "example", 123.0, 456)
        assert launcher.chat_game_file.read_text(encoding="ascii") == "456\n"
        assert launcher.running_instances == {"example": 123.0}
        launcher.ensure_chat_browser.assert_called_once()
        launcher.overlay_game_pids.clear()
        launcher.write_chat_game_processes()
        assert launcher.chat_game_file.read_text(encoding="ascii") == ""


def test_chat_process_failure_displays_an_error_and_reload_control():
    messages = []
    retry_shown = []
    launcher = SimpleNamespace(
        closing=False,
        chat_browser_process=SimpleNamespace(poll=lambda: 1),
        chat_browser_ready_file=SimpleNamespace(unlink=lambda **_options: None),
        chat_browser_shutdown_file=None,
        chat_browser_status=SimpleNamespace(set=messages.append),
        chat_browser_retry_button=SimpleNamespace(pack=lambda **_options: retry_shown.append(True)),
        chat_browser_fallback=SimpleNamespace(pack=lambda **_options: None),
    )
    launcher.show_chat_startup_failure = lambda message: (
        breakblocks_launcher.Launcher.show_chat_startup_failure(launcher, message)
    )
    with contextlib.redirect_stderr(io.StringIO()):
        breakblocks_launcher.Launcher.monitor_chat_browser(launcher)
    assert launcher.chat_browser_process is None
    assert retry_shown == [True]
    assert "Reload Chat" in messages[-1]
    assert "log" in messages[-1]


def test_loading_panel_only_clears_after_the_current_browser_attaches():
    with tempfile.TemporaryDirectory() as temporary:
        ready = Path(temporary) / "ready"
        hidden = []
        launcher = SimpleNamespace(
            closing=False,
            chat_browser_process=SimpleNamespace(poll=lambda: None, pid=456),
            chat_browser_ready_file=ready,
            refresh_chat_unread_badge=lambda: None,
            chat_browser_fallback=SimpleNamespace(pack_forget=lambda: hidden.append(True)),
            chat_browser_status=SimpleNamespace(set=lambda _message: None),
            after=lambda *_args: 1,
            monitor_chat_browser=lambda: None,
        )
        for value in (None, "not ready", "123"):
            if value is not None:
                ready.write_text(value, encoding="ascii")
            breakblocks_launcher.Launcher.monitor_chat_browser(launcher)
            assert not hidden
        ready.write_text("456", encoding="ascii")
        breakblocks_launcher.Launcher.monitor_chat_browser(launcher)
        assert hidden == [True]


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
    assert 'preferences["chat_duration"] * 1000' in source


def test_launcher_restores_and_clears_the_chat_unread_badge():
    sidebar_source = inspect.getsource(breakblocks_launcher.Launcher.build_sidebar)
    show_page_source = inspect.getsource(breakblocks_launcher.Launcher.show_page)
    monitor_source = inspect.getsource(breakblocks_launcher.Launcher.monitor_chat_browser)
    assert "chat_unread_badge" in sidebar_source
    assert 'set_chat_page_visible(name == "Chat")' in show_page_source
    assert "refresh_chat_unread_badge" in monitor_source


def test_chat_unread_badge_matches_sidebar_and_hover_backgrounds():
    sidebar_source = inspect.getsource(breakblocks_launcher.Launcher.build_sidebar)
    update_source = inspect.getsource(
        breakblocks_launcher.Launcher.update_chat_unread_badge_background
    )
    assert "bg_color=SIDEBAR" in sidebar_source
    assert 'button.bind(\n                    "<Enter>"' in sidebar_source
    assert 'button.bind(\n                    "<Leave>"' in sidebar_source
    assert "SURFACE_HOVER if hovered else SIDEBAR" in update_source
    assert "badge.configure(bg_color=background)" in update_source


def test_chat_fills_the_complete_area_beside_the_sidebar():
    chat_source = inspect.getsource(breakblocks_launcher.Launcher.chat_web_ui)
    show_page_source = inspect.getsource(breakblocks_launcher.Launcher.show_page)
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
    sidebar_source = inspect.getsource(breakblocks_launcher.Launcher.build_sidebar)
    menu_source = inspect.getsource(breakblocks_launcher.Launcher.show_chat_context_menu)
    assert 'button.bind("<Button-3>", self.show_chat_context_menu)' in sidebar_source
    assert 'label="Open in browser"' in sidebar_source
    assert "BREAKBLOCKS_CHAT_WEB_URL" in sidebar_source
    assert "menu.tk_popup(event.x_root, event.y_root)" in menu_source


def test_native_irc_transport_and_credentials_are_not_used_by_launcher():
    source = Path(breakblocks_launcher.__file__).read_text(encoding="utf-8")
    assert "import irc_client" not in source
    assert "IrcClient(" not in source
    assert "irc_server_password" in source  # migration removes legacy saved values
    assert "settings.pop(obsolete_key, None)" in source
    assert not hasattr(breakblocks_launcher.Launcher, "connect_irc")
    assert not hasattr(breakblocks_launcher.Launcher, "send_irc_message")


def test_chat_starts_in_background_and_opening_the_tab_reuses_the_browser():
    source = inspect.getsource(breakblocks_launcher.Launcher.show_page)
    assert 'if name == "Chat"' in source
    assert "self.ensure_chat_browser()" in source
    constructor = inspect.getsource(breakblocks_launcher.Launcher.__init__)
    assert "self.after(500, self.ensure_chat_browser)" in constructor
    ensure = inspect.getsource(breakblocks_launcher.Launcher.ensure_chat_browser)
    assert "process.poll() is None" in ensure
    assert "connect_irc_on_startup" not in constructor


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"Passed {len(tests)} embedded chat browser tests")
