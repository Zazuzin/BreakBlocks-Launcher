"""Check that existing accounts survive the launcher data-directory rename."""

import tempfile
from pathlib import Path

from launcher_paths import migrate_legacy_data


def test_existing_profiles_and_chat_session_move_to_breakblocks_folder():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        legacy = base / "Zazu Launcher"
        preferred = base / "BreakBlocks Launcher"
        (legacy / "instances" / "world").mkdir(parents=True)
        (legacy / "web-chat-profile").mkdir()
        (legacy / "launcher.json").write_text('{"accounts": ["existing-profile"]}')
        (legacy / "instances" / "world" / "config.txt").write_text("saved")
        (legacy / "web-chat-profile" / "Cookies").write_bytes(b"existing-session")

        migrate_legacy_data(preferred, legacy)

        assert not legacy.exists()
        assert (preferred / "launcher.json").read_text() == '{"accounts": ["existing-profile"]}'
        assert (preferred / "instances" / "world" / "config.txt").read_text() == "saved"
        assert (preferred / "web-chat-profile" / "Cookies").read_bytes() == b"existing-session"


def test_existing_log_folder_does_not_hide_older_accounts():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        legacy = base / "zazu-launcher"
        preferred = base / "breakblocks-launcher"
        legacy.mkdir()
        preferred.mkdir()
        (legacy / "launcher.json").write_text("older account")
        (legacy / "instances").mkdir()
        (legacy / "instances" / "profile.txt").write_text("saved")
        (preferred / "instances").mkdir()
        (preferred / "instances" / "new-profile.txt").write_text("new")
        (preferred / "launcher.log").write_text("new log")

        migrate_legacy_data(preferred, legacy)

        assert (preferred / "launcher.json").read_text() == "older account"
        assert (preferred / "instances" / "profile.txt").read_text() == "saved"
        assert (preferred / "instances" / "new-profile.txt").read_text() == "new"
        assert (preferred / "launcher.log").read_text() == "new log"


def test_existing_breakblocks_profile_is_not_overwritten():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        legacy = base / "zazu-launcher"
        preferred = base / "breakblocks-launcher"
        legacy.mkdir()
        preferred.mkdir()
        (legacy / "launcher.json").write_text("old")
        (preferred / "launcher.json").write_text("current")

        migrate_legacy_data(preferred, legacy)

        assert (preferred / "launcher.json").read_text() == "current"
        assert (legacy / "launcher.json").read_text() == "old"


if __name__ == "__main__":
    for name, test in sorted(globals().items()):
        if name.startswith("test_"):
            test()
    print("Launcher path tests passed")
