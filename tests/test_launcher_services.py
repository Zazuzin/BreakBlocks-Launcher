import hashlib
import inspect
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

import chat_browser
import launcher_update
import zazu_launcher
from app_config import APP_VERSION_NUMBER
from tools import collect_dependency_licenses, generate_update_manifest


class FakeResponse(io.BytesIO):
    def __init__(self, payload, content_type="application/json"):
        super().__init__(payload)
        self.headers = {
            "Content-Length": str(len(payload)),
            "Content-Type": content_type,
        }

    def __enter__(self):
        return self

    def __exit__(self, _kind, _value, _traceback):
        self.close()


class FakeOpener:
    def __init__(self, responses):
        self.responses = responses

    def __call__(self, request, timeout=0):
        del timeout
        url = request.full_url if hasattr(request, "full_url") else request
        payload = self.responses[url]
        return FakeResponse(payload)


def release_fixture(
    package=b"verified launcher package",
    platform_key=None,
    package_filename="BreakBlocks-Launcher.zip",
):
    manifest_url = "https://downloads.example.test/breakblocks-update.json"
    package_url = f"https://downloads.example.test/{package_filename}"
    platform_key = platform_key or launcher_update.current_platform_key()
    manifest = {
        "schema": 1,
        "version": "0.9.1",
        "display_version": "0.9.1 Alpha",
        "channel": "alpha",
        "notes": "Test update",
        "platforms": {
            platform_key: {
                "url": package_url,
                "filename": package_filename,
                "sha256": hashlib.sha256(package).hexdigest(),
                "size": len(package),
            }
        },
    }
    releases = [
        {
            "tag_name": "v0.9.1-alpha",
            "draft": False,
            "prerelease": True,
            "html_url": "https://github.com/Zazuzin/Zazu-Launcher/releases/tag/v0.9.1-alpha",
            "body": "Fallback notes",
            "assets": [
                {
                    "name": "breakblocks-update.json",
                    "browser_download_url": manifest_url,
                },
                {
                    "name": package_filename,
                    "browser_download_url": package_url,
                },
            ],
        }
    ]
    return {
        launcher_update.GITHUB_RELEASES_API: json.dumps(releases).encode(),
        manifest_url: json.dumps(manifest).encode(),
        package_url: package,
    }


def test_version_and_update_schedule_helpers():
    assert launcher_update.version_tuple("0.9.0 Alpha") == (0, 9, 0)
    assert launcher_update.version_tuple("v1.2.3-alpha") == (1, 2, 3)
    assert launcher_update.should_check(0, "daily", now=100_000)
    assert not launcher_update.should_check(99_900, "daily", now=100_000)
    assert not launcher_update.should_check(0, "never", now=100_000)


def test_update_client_reads_manifest_and_verifies_download():
    responses = release_fixture()
    client = launcher_update.UpdateClient("0.9.0 Alpha", opener=FakeOpener(responses))
    update = client.check("alpha")
    assert update is not None
    assert update.version == "0.9.1"
    assert update.display_version == "0.9.1 Alpha"
    with tempfile.TemporaryDirectory() as temporary:
        downloaded = client.download(update, Path(temporary))
        assert downloaded.read_bytes() == b"verified launcher package"


def test_update_client_selects_the_ubuntu_deb_manifest_asset():
    platform_key = "linux-deb-x86_64"
    filename = "BreakBlocks-Launcher-0.9.1-Ubuntu-amd64.deb"
    responses = release_fixture(platform_key=platform_key, package_filename=filename)
    client = launcher_update.UpdateClient(
        "0.9.0 Alpha",
        opener=FakeOpener(responses),
        platform_key=platform_key,
    )
    update = client.check("alpha")
    assert update is not None
    assert update.asset.filename == filename


def test_linux_install_detection_distinguishes_deb_portable_and_source():
    if not launcher_update.sys.platform.startswith("linux"):
        return
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "source"
        source.mkdir()
        assert launcher_update.detect_install_type(source) == launcher_update.INSTALL_SOURCE

        package_root = root / "package"
        app = package_root / "app"
        app.mkdir(parents=True)
        (package_root / "BreakBlocks Launcher").write_text("launcher", encoding="utf-8")
        assert launcher_update.detect_install_type(app) == launcher_update.INSTALL_LINUX_PORTABLE

        (package_root / ".deb-package").write_text("ubuntu-deb\n", encoding="utf-8")
        assert launcher_update.detect_install_type(app) == launcher_update.INSTALL_LINUX_DEB
        assert (
            launcher_update.platform_key_for_install_type(launcher_update.INSTALL_LINUX_DEB)
            == "linux-deb-x86_64"
        )
        assert (
            launcher_update.platform_key_for_install_type(launcher_update.INSTALL_SOURCE)
            == "linux-deb-x86_64"
        )


def test_debian_updater_uses_pkexec_without_a_shell():
    if not launcher_update.sys.platform.startswith("linux"):
        return
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / "BreakBlocks-Launcher.deb"
        archive.write_bytes(b"verified package")
        with mock.patch(
            "launcher_update.shutil.which",
            side_effect=lambda command: f"/usr/bin/{command}",
        ):
            command = launcher_update.debian_install_command(archive)
    assert command == [
        "/usr/bin/pkexec",
        "/usr/bin/apt-get",
        "install",
        "--yes",
        str(archive.resolve()),
    ]


def test_update_client_rejects_a_bad_download_digest():
    responses = release_fixture()
    client = launcher_update.UpdateClient("0.9.0", opener=FakeOpener(responses))
    update = client.check("alpha")
    responses[update.asset.url] = b"tampered"
    with tempfile.TemporaryDirectory() as temporary:
        try:
            client.download(update, Path(temporary))
        except launcher_update.UpdateError as error:
            assert "size mismatch" in str(error) or "SHA-256" in str(error)
        else:
            raise AssertionError("A tampered update package was accepted")


def test_update_client_rejects_a_package_outside_the_release():
    responses = release_fixture()
    releases = json.loads(responses[launcher_update.GITHUB_RELEASES_API])
    releases[0]["assets"] = releases[0]["assets"][:1]
    responses[launcher_update.GITHUB_RELEASES_API] = json.dumps(releases).encode()
    client = launcher_update.UpdateClient("0.9.0", opener=FakeOpener(responses))
    try:
        client.check("alpha")
    except launcher_update.UpdateError as error:
        assert "not attached" in str(error)
    else:
        raise AssertionError("An external update package was accepted")


def test_stable_channel_ignores_prereleases_and_accepts_full_releases():
    responses = release_fixture()
    releases = json.loads(responses[launcher_update.GITHUB_RELEASES_API])
    manifest_url = releases[0]["assets"][0]["browser_download_url"]
    prerelease = dict(releases[0], tag_name="v0.9.2-alpha", prerelease=True)
    stable = dict(releases[0], tag_name="v0.9.1", prerelease=False)
    responses[launcher_update.GITHUB_RELEASES_API] = json.dumps([prerelease, stable]).encode()
    manifest = json.loads(responses[manifest_url])
    manifest.update(display_version="0.9.1", channel="stable")
    responses[manifest_url] = json.dumps(manifest).encode()

    client = launcher_update.UpdateClient("0.9.0", opener=FakeOpener(responses))
    update = client.check()
    assert update is not None
    assert update.version == "0.9.1"
    assert update.channel == "stable"


def test_update_manifest_names_match_alpha_and_stable_release_assets():
    with tempfile.TemporaryDirectory() as temporary:
        assets = Path(temporary)
        for channel, suffix in (("alpha", "-alpha"), ("stable", "")):
            for pattern in generate_update_manifest.PLATFORM_ASSETS.values():
                (assets / pattern.format(version="1.2.3", suffix=suffix)).write_bytes(b"package")
            manifest = generate_update_manifest.build_manifest(
                "1.2.3",
                f"v1.2.3{suffix}",
                "Zazuzin/Zazu-Launcher",
                assets,
                channel,
            )
            assert manifest["channel"] == channel
            assert manifest["display_version"] == ("1.2.3 Alpha" if channel == "alpha" else "1.2.3")
            assert all(
                platform["filename"].startswith("BreakBlocks-Launcher-1.2.3-")
                for platform in manifest["platforms"].values()
            )
            assert set(manifest["platforms"]) == {
                "windows-x86_64",
                "linux-deb-x86_64",
                "linux-portable-x86_64",
                "linux-x86_64",
            }


def test_runtime_dependency_licence_versions_match_requirements():
    root = Path(zazu_launcher.__file__).resolve().parent
    requirements = "\n".join(
        (root / filename).read_text(encoding="utf-8")
        for filename in ("requirements.txt", "requirements-dev.txt")
    )
    pins = {
        name.casefold(): version
        for name, version in (
            line.strip().split("==", 1) for line in requirements.splitlines() if "==" in line
        )
    }
    for package, version in collect_dependency_licenses.PACKAGES.items():
        assert pins[package.casefold()] == version


def test_update_staging_rejects_archive_path_traversal():
    client = launcher_update.UpdateClient("0.9.0")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        archive = root / "unsafe.zip"
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("../escape.txt", "unsafe")
        try:
            client.stage(archive, root / "staged")
        except launcher_update.UpdateError as error:
            assert "Unsafe path" in str(error)
        else:
            raise AssertionError("An unsafe update archive was extracted")


def test_settings_defaults_and_legal_copy_are_present():
    old_xdg = os.environ.get("XDG_DATA_HOME")
    with tempfile.TemporaryDirectory() as temporary:
        os.environ["XDG_DATA_HOME"] = temporary
        try:
            store = zazu_launcher.Store()
            settings = store.data["settings"]
            store.file.write_text(
                json.dumps(
                    {
                        "accounts": [],
                        "instances": [],
                        "settings": {
                            "irc_host": "",
                            "irc_port": 6697,
                            "irc_tls": True,
                            "irc_channel": "#BreakBlocks",
                            "irc_nickname": "Guest",
                        },
                    }
                ),
                encoding="utf-8",
            )
            migrated_settings = zazu_launcher.Store().data["settings"]
        finally:
            if old_xdg is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = old_xdg
    assert settings["update_enabled"] is True
    assert settings["update_channel"] == "stable"
    assert "irc_host" not in settings
    assert "irc_port" not in settings
    assert "irc_tls" not in settings
    assert "irc_channel" not in settings
    assert settings["chat_browser_defaults_version"] == 1
    assert "irc_host" not in migrated_settings
    assert "irc_port" not in migrated_settings
    assert "irc_tls" not in migrated_settings
    assert "irc_channel" not in migrated_settings
    assert "irc_nickname" not in migrated_settings
    assert "irc_server_password" not in migrated_settings
    assert "irc_connect_on_startup" not in migrated_settings
    assert migrated_settings["chat_browser_defaults_version"] == 1
    assert settings["legal_notice_version"] == 0
    assert zazu_launcher.account_type_label({"type": "Microsoft"}) == "Microsoft"
    assert zazu_launcher.account_type_label({"type": "Offline"}) == "Offline"
    assert zazu_launcher.account_type_label({"type": "Cracked"}) == "Offline"
    assert zazu_launcher.has_verified_minecraft_ownership(
        [{"type": "Microsoft", "entitlement_verified_at": 1}]
    )
    assert not zazu_launcher.has_verified_minecraft_ownership(
        [
            {"type": "Microsoft"},
            {"type": "Offline", "entitlement_verified_at": 1},
        ]
    )

    source = Path(zazu_launcher.__file__).read_text(encoding="utf-8")
    assert '"OFFLINE ACCOUNTS"' in source
    assert 'text="Add offline account"' in source
    assert '"type": "Offline"' in source
    assert "not affiliated" in source
    assert "Microsoft Corporation or Mojang AB" in source
    assert "Minecraft Usage Guidelines" in source
    assert "NOT AN OFFICIAL MINECRAFT PRODUCT" in source
    assert "show_first_run_legal_notice" in source
    assert "Minecraft ownership required" in source
    assert "PRIVACY.md" in source
    assert "TERMS.md" in source
    assert "f\"{account['name']}  •  {account_type_label(account)}\"" in source
    assert "text=account_type_label(account)" in source
    about_source = inspect.getsource(zazu_launcher.Launcher.about_ui)
    assert "Created by Zazuzin for the BreakBlocks community" in about_source
    assert "Minecraft community hub" in about_source
    assert "Etianl" not in about_source
    assert "Created by Zazuzin and Etianl" not in source


def test_updates_tab_runs_one_automatic_check_per_opened_instance():
    source = inspect.getsource(zazu_launcher.Launcher.select_mod_tab)
    assert 'name == "Updates"' in source
    assert "not self.mod_updates_checked" in source
    assert "self.after(0, self.check_modrinth_updates)" in source


def test_legal_documents_cover_current_data_flows_and_are_packaged():
    root = Path(zazu_launcher.__file__).resolve().parent
    project_license = (root / "LICENSE").read_text(encoding="utf-8")
    project_metadata = (root / "pyproject.toml").read_text(encoding="utf-8")
    privacy = (root / "PRIVACY.md").read_text(encoding="utf-8")
    terms = (root / "TERMS.md").read_text(encoding="utf-8")
    notices = (root / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    checklist = (root / "LEGAL-RELEASE-CHECKLIST.md").read_text(encoding="utf-8")
    website_changes = (root / "WEBSITE-LEGAL-CHANGES.md").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    spec = (root / "BreakBlocksLauncher.spec").read_text(encoding="utf-8")
    bootstrap = (root / "zazu_launcher_boot.pyw").read_text(encoding="utf-8")

    for expected in (
        "Microsoft profile",
        "Offline profile",
        "GitHub Releases",
        "Modrinth",
        "web chat",
        "no advertising, analytics",
    ):
        assert expected in privacy
    assert "NOT AN OFFICIAL MINECRAFT PRODUCT" in terms
    assert "first verify ownership" in terms
    assert "GNU GENERAL PUBLIC LICENSE" in project_license
    assert "Version 3, 29 June 2007" in project_license
    assert 'license = "GPL-3.0-only"' in project_metadata
    assert "GPL-3.0-only" in notices
    assert "CustomTkinter" in notices
    assert "Python" in notices
    assert (root / "legal" / "INTER-OFL.txt").is_file()
    assert "INTER-OFL.txt" in inspect.getsource(collect_dependency_licenses.collect)
    assert "PySide6" in notices
    assert chat_browser.CHAT_URL == "https://irc.breakblocks.com/#/connect"
    assert "Sheepy confirmations needed" in checklist
    assert "Legal operator/data controller" in checklist
    assert "Privacy Policy — add" in website_changes
    assert "collect_dependency_licenses.py" in workflow
    assert 'Copy-Item "LICENSE", "PRIVACY.md", "TERMS.md"' in workflow
    assert "cp LICENSE PRIVACY.md TERMS.md THIRD-PARTY-NOTICES.md" in workflow
    assert 'cp -R fonts "dist/BreakBlocks Launcher/fonts"' in workflow
    for document in ("LICENSE", "PRIVACY.md", "TERMS.md", "THIRD-PARTY-NOTICES.md"):
        assert f'("{document}", ".")' in spec
    assert 'os.environ.setdefault("FONTCONFIG_PATH", str(font_directory))' in bootstrap


def test_legacy_microsoft_account_receives_entitlement_proof():
    old_xdg = os.environ.get("XDG_DATA_HOME")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "breakblocks-launcher"
        root.mkdir()
        (root / "launcher.json").write_text(
            json.dumps(
                {
                    "accounts": [
                        {
                            "id": "owned-profile",
                            "name": "Player",
                            "type": "Microsoft",
                            "minecraft_token": "existing-token",
                            "refresh_token": "existing-refresh-token",
                        }
                    ],
                    "instances": [],
                    "settings": {},
                }
            ),
            encoding="utf-8",
        )
        os.environ["XDG_DATA_HOME"] = temporary
        try:
            store = zazu_launcher.Store()
        finally:
            if old_xdg is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = old_xdg
        account = store.data["accounts"][0]
        assert account["entitlement_verified_at"] > 0
        assert zazu_launcher.has_verified_minecraft_ownership(store.data["accounts"])


def test_legacy_offline_account_label_is_migrated():
    old_xdg = os.environ.get("XDG_DATA_HOME")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "breakblocks-launcher"
        root.mkdir()
        (root / "launcher.json").write_text(
            json.dumps(
                {
                    "accounts": [{"id": "legacy", "name": "Player", "type": "Cracked"}],
                    "instances": [],
                    "settings": {},
                }
            ),
            encoding="utf-8",
        )
        os.environ["XDG_DATA_HOME"] = temporary
        try:
            store = zazu_launcher.Store()
        finally:
            if old_xdg is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = old_xdg
        assert store.data["accounts"][0]["type"] == "Offline"
        persisted = json.loads((root / "launcher.json").read_text(encoding="utf-8"))
        assert persisted["accounts"][0]["type"] == "Offline"


def test_removed_dashboard_implementation_does_not_remain_after_return():
    source = Path(zazu_launcher.__file__).read_text(encoding="utf-8")
    assert "setup_launcher_dashboard" not in source
    assert "dashboard_scaled_font" not in source
    assert "self.instance_scroll" not in source


def test_linux_launcher_uses_the_desktop_file_window_class():
    source = inspect.getsource(zazu_launcher.Launcher.__init__)
    assert 'className="BreakBlocksLauncher"' in source
    desktop = (
        Path(zazu_launcher.__file__).resolve().parent
        / "packaging"
        / "linux"
        / "breakblocks-launcher.desktop"
    ).read_text(encoding="utf-8")
    assert "StartupWMClass=Breakblockslauncher" in desktop


def test_navigation_icons_are_real_antialiased_images():
    for name in ("launcher", "chat", "settings", "about"):
        image = zazu_launcher.nav_icon_image(name)
        assert image.mode == "RGBA"
        assert image.size == (80, 80)
        assert image.getchannel("A").getbbox() is not None


def test_transparent_icon_trim_removes_padding_and_preserves_a_square():
    image = zazu_launcher.Image.new("RGBA", (20, 12), (0, 0, 0, 0))
    zazu_launcher.ImageDraw.Draw(image).rectangle((4, 2, 9, 9), fill="white")
    trimmed = zazu_launcher.trim_transparent_square(image)
    assert trimmed.size == (8, 8)
    assert trimmed.getchannel("A").getbbox() == (1, 0, 7, 8)


def test_linux_package_records_the_permission_and_runtime_fixes():
    root = Path(zazu_launcher.__file__).resolve().parent / "packaging" / "linux"
    control = (root / "control").read_text(encoding="utf-8")
    wrapper = (root / "breakblocks-launcher").read_text(encoding="utf-8")
    postinst = (root / "postinst").read_text(encoding="utf-8")
    assert f"Version: {APP_VERSION_NUMBER}" in control
    assert "python3-tk" in control
    assert '/usr/bin/python3 "$app_dir/app/zazu_launcher.py"' in wrapper
    assert "chmod -R a+rX /usr/lib/breakblocks-launcher" in postinst
    build_script = (root / "build-deb.sh").read_text(encoding="utf-8")
    assert '"$install_root/.deb-package"' in build_script


def test_update_dialog_routes_packaged_installs_to_the_self_updater():
    dialog_source = inspect.getsource(zazu_launcher.Launcher.show_launcher_update)
    download_source = inspect.getsource(zazu_launcher.Launcher.download_launcher_update)
    assert 'INSTALL_LINUX_DEB: "Download and install"' in dialog_source
    assert 'INSTALL_SOURCE: "Open release page"' in dialog_source
    assert "install_debian_update(archive)" in download_source
    assert "self.update_client.stage" in download_source


def test_release_workflow_publishes_every_update_target():
    root = Path(zazu_launcher.__file__).resolve().parent
    workflow = (root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "BreakBlocks-Launcher-$env:VERSION-Windows-x86_64.zip" in workflow
    assert "BreakBlocks-Launcher-${VERSION}-Ubuntu-amd64.deb" in workflow
    assert "BreakBlocks-Launcher-${VERSION}-SteamDeck-x86_64.tar.gz" in workflow
    assert "breakblocks-update.json" in workflow


def test_manual_test_workflow_builds_but_does_not_publish_packages():
    root = Path(zazu_launcher.__file__).resolve().parent
    workflow = (root / ".github" / "workflows" / "test-build.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "- main" in workflow
    assert "BreakBlocks-Launcher-${{ env.VERSION }}-Windows-test" in workflow
    assert "BreakBlocks-Launcher-${VERSION}-Ubuntu-amd64.deb" in workflow
    assert "BreakBlocks-Launcher-${VERSION}-SteamDeck-x86_64.tar.gz" in workflow
    assert "BreakBlocks-Launcher-${{ env.VERSION }}-Linux-test" in workflow
    assert "gh release create" not in workflow
    assert "SIGNING_CERTIFICATE" not in workflow


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"Passed {len(tests)} launcher service tests")
