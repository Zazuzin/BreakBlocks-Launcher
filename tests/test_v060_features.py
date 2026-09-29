import hashlib
import inspect
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import display_environment
import mod_sources
import zazu_launcher


def test_block_icon_catalogue():
    assert zazu_launcher.APP_NAME == "BreakBlocks Launcher"
    assert zazu_launcher.APP_VERSION == "0.9.13 Alpha"
    assert len(zazu_launcher.BLOCK_ICONS) == 25
    assert len(zazu_launcher.BLOCK_ICON_KEYS) == 25
    asset_root = Path(zazu_launcher.__file__).resolve().parent / "assets" / "instance_icons"
    for key, label in zazu_launcher.BLOCK_ICONS:
        assert label
        path = asset_root / f"{key}.png"
        assert path.is_file(), path
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.size == (64, 64)


def test_existing_instances_receive_stable_icons():
    with tempfile.TemporaryDirectory() as temporary:
        old_xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = temporary
        try:
            root = Path(temporary) / "zazu-launcher"
            root.mkdir(parents=True)
            (root / "launcher.json").write_text(
                json.dumps(
                    {
                        "accounts": [],
                        "instances": [{"id": "example-instance", "name": "Example"}],
                        "settings": {},
                    }
                )
            )
            first = zazu_launcher.Store()
            assigned = first.data["instances"][0]["icon"]
            second = zazu_launcher.Store()
            assert assigned in zazu_launcher.BLOCK_ICON_KEYS
            assert second.data["instances"][0]["icon"] == assigned
        finally:
            if old_xdg is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = old_xdg


def test_rebrand_uses_new_data_root_without_hiding_legacy_data():
    with tempfile.TemporaryDirectory() as temporary:
        old_xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = temporary
        try:
            fresh = zazu_launcher.Store()
            assert fresh.root == Path(temporary) / "breakblocks-launcher"
        finally:
            if old_xdg is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = old_xdg


def test_custom_icon_path_stays_inside_instance_root():
    with tempfile.TemporaryDirectory() as temporary:
        store = SimpleNamespace(instances=Path(temporary) / "instances")
        store.instances.mkdir()
        launcher = SimpleNamespace(store=store)
        safe = zazu_launcher.Launcher.instance_custom_icon_path(launcher, {"id": "safe-instance"})
        assert safe == store.instances / "safe-instance" / "launcher-icon.png"
        try:
            zazu_launcher.Launcher.instance_custom_icon_path(launcher, {"id": "../escape"})
        except ValueError:
            pass
        else:
            raise AssertionError("Traversal instance id was accepted")


def test_launcher_page_contains_profiles_and_idle_progress_is_hidden():
    source = Path(zazu_launcher.__file__).read_text()
    dashboard_source = inspect.getsource(zazu_launcher.LauncherDashboardCanvas)
    assert 'self.pages["Launcher"]' in source
    assert 'self.pages["Accounts"]' not in source
    assert 'title = "MICROSOFT PROFILES"' in dashboard_source
    assert '"OFFLINE ACCOUNTS"' in dashboard_source
    assert "self.progress_visible = False" in dashboard_source
    assert '"Modrinth"' in dashboard_source and "launcher.open_modrinth_manager" in dashboard_source
    assert '"Mods Folder"' in dashboard_source and "launcher.open_mods_folder" in dashboard_source
    assert '"Edit Instance"' in dashboard_source and "launcher.edit_instance" in dashboard_source
    assert 'tab_names = ("Browse Modrinth", "Installed", "Updates")' in source
    assert 'uniform="mod_tabs"' in source
    assert "def select_mod_tab" in source


def test_modrinth_manager_is_an_integrated_page_not_a_popup():
    source = Path(zazu_launcher.__file__).read_text()
    manager_source = source[
        source.index("    def open_modrinth_manager") : source.index("    def mod_context_alive")
    ]
    assert 'self.pages["Mods"]' in source
    assert 'text="←  Back to Launcher"' in source
    assert "def close_modrinth_manager" in source
    assert 'self.show_page("Mods", force=True)' in manager_source
    assert 'self.make_dialog("Modrinth Mod Manager"' not in manager_source
    assert "self.mod_window" not in source


def test_breakblocks_branding_assets_are_packaged_and_used():
    app_root = Path(zazu_launcher.__file__).resolve().parent
    logo_path = app_root / "assets" / "branding" / "breakblocks_launcher_logo.png"
    icon_path = app_root / "assets" / "branding" / "breakblocks_launcher_icon.png"
    windows_icon_path = app_root / "assets" / "branding" / "breakblocks_launcher.ico"
    for path in (logo_path, icon_path, windows_icon_path):
        assert path.is_file(), path
    with Image.open(logo_path) as image:
        assert image.format == "PNG"
        assert image.mode in {"RGB", "RGBA"}
        assert image.size[0] == image.size[1]
    with Image.open(icon_path) as image:
        assert image.format == "PNG"
        assert image.size == (512, 512)
    source = Path(zazu_launcher.__file__).read_text()
    assert "SetCurrentProcessExplicitAppUserModelID" in source
    assert 'self.title(f"{APP_NAME} {APP_VERSION}")' in source
    assert '"BreakBlocks.Launcher"' in source
    assert "self.iconphoto(True, self.window_icon)" in source
    assert "image=self.brand_image" not in source


def test_windows_enables_native_per_monitor_dpi_before_tk_loads():
    app_root = Path(zazu_launcher.__file__).resolve().parent
    launcher_source = (app_root / "zazu_launcher.py").read_text(encoding="utf-8")
    boot_source = (app_root / "zazu_launcher_boot.pyw").read_text(encoding="utf-8")
    assert launcher_source.index("enable_windows_per_monitor_dpi()") < launcher_source.index(
        "import tkinter as tk"
    )
    assert boot_source.index("enable_windows_per_monitor_dpi()") < boot_source.index(
        "from zazu_launcher import Launcher"
    )
    dpi_source = inspect.getsource(display_environment.enable_windows_per_monitor_dpi)
    assert "SetProcessDpiAwarenessContext" in dpi_source
    assert "ctypes.c_void_p(-4)" in dpi_source
    if os.name != "nt":
        assert display_environment.enable_windows_per_monitor_dpi() is False


def test_fixed_launcher_layout_matches_the_requested_three_columns():
    source = Path(zazu_launcher.__file__).read_text()
    launcher_source = inspect.getsource(zazu_launcher.Launcher.launcher_ui)
    redraw_source = inspect.getsource(zazu_launcher.LauncherDashboardCanvas.redraw)
    launch_card_source = inspect.getsource(zazu_launcher.LauncherDashboardCanvas._draw_launch_card)
    assert 'text="READY TO LAUNCH"' in launch_card_source
    assert "self.launch_dashboard = LauncherDashboardCanvas(page, self)" in launcher_source
    assert 'self.launch_dashboard.grid(row=0, column=0, sticky="nsew")' in launcher_source
    assert "CURRENT LAUNCH ACCOUNT" not in source
    assert "Choose an instance and profile, then launch Minecraft" not in source
    assert "self._draw_launch_card(left_x1, 0, left_x2, launch_height)" in redraw_source
    assert (
        "self._draw_instances_card(left_x1, launch_height + gap, left_x2, height)" in redraw_source
    )
    assert 'self._draw_accounts_card("microsoft"' in redraw_source
    assert 'self._draw_accounts_card("offline"' in redraw_source


def test_fixed_launcher_proportions_fit_the_minimum_window():
    columns = zazu_launcher.LAUNCHER_COLUMN_SPECS
    rows = zazu_launcher.LAUNCHER_ROW_SPECS
    assert columns == ((14, 420), (6, 220), (5, 205))
    assert rows == ((0, 350), (1, 205))
    assert columns[0][0] > columns[1][0] + columns[2][0]
    assert rows[0][0] < rows[1][0]
    usable_width = 1200 - 270 - (2 * 24)
    horizontal_card_gaps = 24
    assert sum(minimum for _weight, minimum in columns) + horizontal_card_gaps <= usable_width
    usable_height = 650 - 38 - 24 - 20
    vertical_card_gap = 12
    assert sum(minimum for _weight, minimum in rows) + vertical_card_gap <= usable_height
    redraw_source = inspect.getsource(zazu_launcher.LauncherDashboardCanvas.redraw)
    assert "launch_height = min(430, max(300, height - 205 - gap))" in redraw_source


def test_narrow_account_cards_stack_controls_instead_of_clipping():
    source = inspect.getsource(zazu_launcher.LauncherDashboardCanvas._draw_accounts_card)
    assert "button_width = (x2 - x1 - 28 - button_gap) / 2" in source
    assert '"Use this account"' in source
    assert "content_right - 10" in source
    assert "width=max(60, content_right - text_x - 8)" in source


def test_launcher_customisation_and_manual_geometry_are_removed():
    source = Path(zazu_launcher.__file__).read_text()
    show_page_source = inspect.getsource(zazu_launcher.Launcher.show_page)
    assert 'text="Edit layout"' not in source
    assert 'text="Reset layout"' not in source
    assert "dashboard_dock_layout" not in source
    assert "setup_dashboard_layout" not in source
    assert "start_dashboard_drag" not in source
    assert "start_dashboard_divider" not in source
    assert "tk.Place.place_configure" not in source
    assert "dashboard_resize_shield" not in source
    assert "self.main_header.grid_remove()" in show_page_source
    assert "self.page_host.grid_configure(padx=24, pady=(24, 20))" in show_page_source


def test_compact_community_card_contains_verified_links():
    source = Path(zazu_launcher.__file__).read_text()
    asset_root = Path(zazu_launcher.__file__).resolve().parent / "assets" / "community"
    assert zazu_launcher.BREAKBLOCKS_URL == "https://breakblocks.com"
    assert zazu_launcher.BREAKBLOCKS_DISCORD_URL == "https://breakblocks.com/discord"
    assert zazu_launcher.BREAKBLOCKS_PATREON_URL == "https://www.patreon.com/cw/BreakBlocks"
    assert (
        zazu_launcher.MOUNTAINS_OF_LAVA_YOUTUBE_URL
        == "https://www.youtube.com/@mountainsoflavainc.6913"
    )
    assert zazu_launcher.ZAZUZIN_GITHUB_URL == "https://github.com/Zazuzin"
    assert zazu_launcher.ETIANL_GITHUB_URL == "https://github.com/etianl"
    expected_assets = {
        "breakblocks_wordmark.png": (317, 48),
        "breakblocks_wordmark_transparent.png": (317, 48),
        "bbc_chicken.jfif": (360, 360),
        "bbc_chicken_transparent.png": (360, 360),
        "mountains_of_lava_youtube.png": (160, 160),
        "zazuzin_github.png": (460, 460),
        "etianl_github.png": (460, 460),
    }
    for name, size in expected_assets.items():
        path = asset_root / name
        assert path.is_file(), path
        with Image.open(path) as image:
            assert image.size == size
            image.verify()
    for name in ("breakblocks_wordmark_transparent.png", "bbc_chicken_transparent.png"):
        with Image.open(asset_root / name).convert("RGBA") as image:
            assert image.getchannel("A").getextrema() == (0, 255)
    assert 'text="" if self.breakblocks_wordmark_image else "BREAKBLOCKS.COM"' in source
    assert 'text="Join Discord"' in source
    assert 'text="Support on Patreon"' in source
    assert 'text="Mountains of Lava Inc."' in source
    assert 'text="Zazuzin"' in source
    assert 'text="Etianl"' in source
    assert "image=self.bbc_chicken_image" in source
    assert "image=self.mountains_of_lava_image" in source
    assert "image=self.zazuzin_github_image" in source
    assert "image=self.etianl_github_image" in source
    assert "fg_color=BBC_CHARCOAL" in source
    assert 'fg_color="#131313"' in source
    sidebar_source = inspect.getsource(zazu_launcher.Launcher.build_sidebar)
    zazuzin_start = sidebar_source.index('text="Zazuzin"')
    etianl_start = sidebar_source.index('text="Etianl"')
    assert "fg_color=BBC_CHARCOAL" in sidebar_source[zazuzin_start:etianl_start]
    assert "hover_color=SURFACE_HOVER" in sidebar_source[zazuzin_start:etianl_start]
    assert "border_width=1" in sidebar_source[zazuzin_start:etianl_start]
    assert "border_color=BORDER" in sidebar_source[zazuzin_start:etianl_start]
    assert "fg_color=BBC_CHARCOAL" in sidebar_source[etianl_start:]
    assert "hover_color=SURFACE_HOVER" in sidebar_source[etianl_start:]
    assert "border_width=1" in sidebar_source[etianl_start:]
    assert "border_color=BORDER" in sidebar_source[etianl_start:]
    assert 'text="COMMUNITY"' not in source
    assert "community = tk.Frame(sidebar, bg=SIDEBAR, bd=0, highlightthickness=0)" in source
    assert "community.grid(row=3" in source
    assert "community/breakblocks_wordmark_transparent.png" in source
    assert "community/bbc_chicken_transparent.png" in source
    assert "community/mountains_of_lava_youtube.png" in source
    with Image.open(asset_root / "mountains_of_lava_youtube.png").convert("RGBA") as image:
        assert image.getchannel("A").getextrema() == (0, 255)
        assert not any(
            alpha > 0
            and min(red, green, blue) > 175
            and max(red, green, blue) - min(red, green, blue) < 30
            for red, green, blue, alpha in image.get_flattened_data()
        )


def test_dashboard_uses_neutral_panels_and_a_logo_matched_brand_band():
    dashboard_source = inspect.getsource(zazu_launcher.LauncherDashboardCanvas)
    sidebar_source = inspect.getsource(zazu_launcher.Launcher.build_sidebar)
    assert zazu_launcher.BBC_CHARCOAL == "#2d2d2d"
    assert dashboard_source.count('fill=BBC_CHARCOAL, outline=""') >= 3
    assert (
        "brand_band = tk.Frame(sidebar, bg=BRAND_WORDMARK_BG, bd=0, highlightthickness=0)"
        in sidebar_source
    )
    assert 'brand_band.grid(row=0, column=0, sticky="ew")' in sidebar_source
    assert (
        "brand = tk.Frame(brand_band, bg=BRAND_WORDMARK_BG, bd=0, highlightthickness=0)"
        in sidebar_source
    )


def test_launcher_palette_is_neutral_and_keeps_semantic_colours():
    assert zazu_launcher.BG == "#181818"
    assert zazu_launcher.SIDEBAR == zazu_launcher.BBC_CHARCOAL
    assert zazu_launcher.SURFACE == zazu_launcher.BBC_CHARCOAL
    assert zazu_launcher.SURFACE_ALT == "#383838"
    assert zazu_launcher.ACCENT == "#5a5a5a"
    assert zazu_launcher.SELECTION == "#c2c2c2"
    assert zazu_launcher.RED == "#ef4b4b"
    assert zazu_launcher.GREEN == "#7ce7b3"
    assert zazu_launcher.GREEN_BG == "#20543f"
    assert zazu_launcher.GREEN_BORDER == "#62a98b"


def test_discord_button_keeps_charcoal_background_with_a_complete_outline():
    sidebar_source = inspect.getsource(zazu_launcher.Launcher.build_sidebar)
    discord_start = sidebar_source.index('text="Join Discord"')
    discord_end = sidebar_source.index('text="Support on Patreon"')
    discord_source = sidebar_source[discord_start:discord_end]
    assert "fg_color=BBC_CHARCOAL" in discord_source
    assert "hover_color=SURFACE_HOVER" in discord_source
    assert "border_width=1" in discord_source
    assert "border_color=BORDER" in discord_source


def test_instance_icons_render_without_a_button_shell():
    launcher_source = inspect.getsource(zazu_launcher.Launcher.launcher_ui)
    row_source = inspect.getsource(zazu_launcher.LauncherDashboardCanvas._draw_instances_card)
    launch_source = inspect.getsource(zazu_launcher.LauncherDashboardCanvas._draw_launch_card)
    assert "self.create_image(list_x1 + 42, top + 43, image=photo)" in row_source
    assert "self.create_image(x1 + 55, summary_top + 41, image=photo)" in launch_source
    assert "CTkButton" not in row_source
    assert "CTkLabel" not in row_source
    assert "LauncherDashboardCanvas(page, self)" in launcher_source


def test_active_profile_is_stably_sorted_to_the_top():
    accounts = [
        {"id": "first", "name": "First"},
        {"id": "active", "name": "Active"},
        {"id": "third", "name": "Third"},
    ]
    ordered = zazu_launcher.active_account_first(accounts, "active")
    assert [account["id"] for account in ordered] == ["active", "first", "third"]
    assert [account["id"] for account in accounts] == ["first", "active", "third"]
    account_source = inspect.getsource(zazu_launcher.LauncherDashboardCanvas._draw_accounts_card)
    assert "accounts = active_account_first(" in account_source


def test_sidebar_uses_the_approved_static_stacked_breakblocks_logo():
    asset = (
        Path(zazu_launcher.__file__).resolve().parent
        / "assets"
        / "branding"
        / "breakblocks_original_logo_stacked.png"
    )
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == (
        "4261297f57279b34f3439c97e40486bdab1935db164d8e88afb717bae7de913c"
    )
    with Image.open(asset) as logo:
        assert logo.format == "PNG"
        assert logo.size == (161, 63)
        assert getattr(logo, "n_frames", 1) == 1
        assert logo.getpixel((0, 0)) == (19, 19, 19)
    assert zazu_launcher.BRAND_WORDMARK_BG == "#131313"
    wordmark = zazu_launcher.load_brand_wordmark(asset)
    assert wordmark.mode == "RGBA"
    assert wordmark.size == (161, 63)
    sidebar_source = inspect.getsource(zazu_launcher.Launcher.build_sidebar)
    assert "ImageTk.PhotoImage(self.brand_wordmark_image)" in sidebar_source
    assert "width=BRAND_WORDMARK_SIZE[0]" in sidebar_source
    assert "height=BRAND_WORDMARK_SIZE[1]" in sidebar_source
    assert "image=self.brand_image" not in sidebar_source
    assert ').pack(anchor="center", pady=(9, 0))' in sidebar_source
    assert "UNOFFICIAL MINECRAFT LAUNCHER" not in sidebar_source
    source = Path(zazu_launcher.__file__).read_text(encoding="utf-8")
    assert "brand_wordmark_animation" not in source
    assert "breakblocks_wordmark_animated.gif" not in source


def test_canvas_buttons_use_integer_aligned_corner_geometry():
    button_source = inspect.getsource(zazu_launcher.LauncherDashboardCanvas._button)
    shape_source = inspect.getsource(zazu_launcher.LauncherDashboardCanvas._button_rectangle)
    assert "self._button_rectangle(" in button_source
    assert "int(round(value))" in shape_source
    assert "smooth=False" in shape_source
    assert "smooth=True" not in shape_source


def test_fabric_creation_offers_breakblocks_essentials_and_all_mod_inventory():
    source = Path(zazu_launcher.__file__).read_text()
    assert 'text="BREAKBLOCKS ESSENTIALS — FABRIC ONLY"' in source
    assert '("meteor-client", "Meteor Client")' in source
    assert '("trouser-streak", "Trouser Streak")' in source
    assert '("zazus-server-seeker", "Zazu\'s Server Seeker")' in source
    assert '("fabric-api", "Fabric API")' in source
    assert (
        mod_sources.ESSENTIAL_SOURCES["zazus-server-seeker"]["repo"]
        == "Zazuzin/Zazus-Server-Seeker"
    )
    assert (
        mod_sources.ESSENTIAL_SOURCES["zazus-server-scanner"]
        is mod_sources.ESSENTIAL_SOURCES["zazus-server-seeker"]
    )
    assert mod_sources.KNOWN_MOD_IDS["zazus-server-tool"] == "zazus-server-seeker"
    assert "manager.install_essentials(essentials)" in source
    assert '"Local file — update source unknown"' in source


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"Passed {len(tests)} retained feature tests")
