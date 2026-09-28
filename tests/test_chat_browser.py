import contextlib
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


def test_browser_process_does_not_quit_when_reparented_into_tk():
    application = SimpleNamespace()
    application.setQuitOnLastWindowClosed = lambda value: setattr(
        application, "quit_on_last_window", value
    )
    chat_browser.configure_application_lifecycle(application)
    assert application.quit_on_last_window is False


def test_windows_host_uses_qt_foreign_window_parenting():
    source = inspect.getsource(chat_browser.NativeHost._attach_windows)
    assert "QWindow.fromWinId" in source
    assert "user32.SetParent" not in source


def test_windows_resize_does_not_treat_qt_child_handle_as_dead():
    source = inspect.getsource(chat_browser.NativeHost._resize_windows)
    assert "IsWindow(self.parent_handle)" in source
    assert "IsWindow(self.child_handle)" not in source


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
        assert "--url" not in command


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
