"""Check that existing accounts survive the launcher data-directory rename."""

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import launcher_paths
from launcher_paths import migrate_account_skin, migrate_legacy_data


def test_data_root_finds_historical_folders_on_both_platforms():
    for platform, state, environment in (
        ("nt", False, "LOCALAPPDATA"),
        ("nt", True, "LOCALAPPDATA"),
        ("posix", False, "XDG_DATA_HOME"),
        ("posix", True, "XDG_STATE_HOME"),
    ):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            legacy = base / launcher_paths.LEGACY_DATA_FOLDERS[platform]
            legacy.mkdir()
            (legacy / "launcher.json").write_text('{"accounts": ["existing"]}')
            platform_os = SimpleNamespace(
                name=platform, environ={environment: temporary}, chmod=os.chmod
            )
            with patch.object(launcher_paths, "os", platform_os):
                current = launcher_paths.launcher_data_root(state=state)
            expected = "BreakBlocks Launcher" if platform == "nt" else "breakblocks-launcher"
            assert current == base / expected
            assert (current / "launcher.json").read_text() == '{"accounts": ["existing"]}'
            assert not legacy.exists()


def test_existing_profiles_and_chat_session_move_to_breakblocks_folder():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        legacy = base / "Old Launcher"
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
        legacy = base / "old-launcher"
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
        legacy = base / "old-launcher"
        preferred = base / "breakblocks-launcher"
        legacy.mkdir()
        preferred.mkdir()
        (legacy / "launcher.json").write_text("old")
        (preferred / "launcher.json").write_text("current")

        migrate_legacy_data(preferred, legacy)

        assert (preferred / "launcher.json").read_text() == "current"
        assert (legacy / "launcher.json").read_text() == "old"


def test_moved_skin_cache_restores_profile_picture_without_changing_credentials():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary).resolve()
        legacy = base / "Old Launcher"
        current = base / "BreakBlocks Launcher"
        skin = legacy / "skins" / "player-id.png"
        skin.parent.mkdir(parents=True)
        skin.write_bytes(b"cached skin")
        account = {
            "id": "player-id",
            "name": "Player",
            "skin": str(skin),
            "refresh_token": "test-token",
            "minecraft_token": "test-session",
        }
        original = dict(account)
        migrate_legacy_data(current, legacy)
        assert migrate_account_skin(current, account)
        assert account["skin"] == str(current / "skins" / "player-id.png")
        assert Path(account["skin"]).read_bytes() == b"cached skin"
        assert {key: value for key, value in account.items() if key != "skin"} == {
            key: value for key, value in original.items() if key != "skin"
        }
        assert not migrate_account_skin(current, account)


def test_already_migrated_and_missing_skin_paths_use_the_matching_local_cache():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        skin = root / "skins" / "player-id.png"
        skin.parent.mkdir()
        skin.write_bytes(b"cached skin")
        for saved in (r"C:\Users\Player\AppData\Local\Old Launcher\skins\player-id.png", ""):
            account = {"id": "player-id", "skin": saved}
            assert migrate_account_skin(root, account)
            assert account["skin"] == str(skin)


def test_skin_migration_preserves_external_images_and_rejects_unsafe_cache_names():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        external = root / "portrait.png"
        external.write_bytes(b"external image")
        skin = root / "skins" / "player-id.png"
        skin.parent.mkdir()
        skin.write_bytes(b"cached skin")
        account = {"id": "player-id", "skin": str(external)}
        assert not migrate_account_skin(root, account)
        assert account["skin"] == str(external)
        unsafe = {"id": "../portrait", "skin": "../portrait.png"}
        assert not migrate_account_skin(root, unsafe)
        assert unsafe["skin"] == "../portrait.png"


if __name__ == "__main__":
    for name, test in sorted(globals().items()):
        if name.startswith("test_"):
            test()
    print("Launcher path tests passed")
