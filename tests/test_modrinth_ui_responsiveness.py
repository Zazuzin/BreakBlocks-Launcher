import inspect
import queue
import time
from pathlib import Path
from types import SimpleNamespace

import zazu_launcher


def test_background_callbacks_are_queued_for_the_tk_thread():
    launcher = SimpleNamespace(ui_events=queue.Queue())

    def callback():
        return "done"

    zazu_launcher.Launcher.post_ui(launcher, callback)
    assert launcher.ui_events.get_nowait() is callback


def test_modrinth_worker_posts_results_instead_of_calling_tk_directly():
    source = inspect.getsource(zazu_launcher.Launcher.search_modrinth)
    assert "self.post_ui" in source
    assert "self.after(0" not in source


def test_modrinth_search_times_out_after_thirty_seconds():
    failures = []
    launcher = SimpleNamespace(
        mod_search_generation=7,
        mod_search_running=True,
        mod_search_started=time.monotonic() - 31,
        mod_context_alive=lambda: True,
        fail_modrinth_search=lambda detail, request_id: failures.append((detail, request_id)),
    )
    zazu_launcher.Launcher.check_modrinth_search_timeout(launcher, 7)
    assert failures == [
        ("Modrinth did not respond within 30 seconds. Check the connection and press Retry.", 7)
    ]


def test_late_worker_failure_does_not_replace_timeout_message():
    launcher = SimpleNamespace(
        mod_search_generation=9,
        mod_search_running=False,
        mod_context_alive=lambda: True,
        mod_search_button=SimpleNamespace(
            configure=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("late UI update"))
        ),
    )
    zazu_launcher.Launcher.fail_modrinth_search(launcher, "late network error", 9)


def test_sidebar_navigation_cleanly_leaves_integrated_mod_page():
    destinations = []
    launcher = SimpleNamespace(
        current_page="Mods",
        close_modrinth_manager=lambda destination="Launcher": destinations.append(destination),
    )
    zazu_launcher.Launcher.show_page(launcher, "Settings")
    assert destinations == ["Settings"]


def test_back_navigation_invalidates_pending_search_results():
    destinations = []
    progress = SimpleNamespace(grid_remove=lambda: None)
    launcher = SimpleNamespace(
        mod_context={"busy": False},
        mod_search_generation=12,
        mod_search_running=True,
        mod_page_active=True,
        modrinth_images=[object()],
        mod_progress_area=progress,
        show_page=lambda destination, force=False: destinations.append((destination, force)),
    )
    zazu_launcher.Launcher.close_modrinth_manager(launcher)
    assert launcher.mod_search_generation == 13
    assert launcher.mod_search_running is False
    assert launcher.mod_page_active is False
    assert launcher.mod_context is None
    assert launcher.modrinth_images == []
    assert destinations == [("Launcher", True)]


def test_modrinth_pages_keep_full_results_with_single_surface_rendering():
    search_source = inspect.getsource(zazu_launcher.Launcher.search_modrinth)
    paging_source = inspect.getsource(zazu_launcher.Launcher.change_mod_page)
    assert zazu_launcher.MODRINTH_PAGE_SIZE == 30
    assert "limit=MODRINTH_PAGE_SIZE" in search_source
    assert "MODRINTH_PAGE_SIZE * int(direction)" in paging_source
    ui_source = inspect.getsource(zazu_launcher.Launcher.modrinth_ui)
    assert ui_source.count("ModrinthCanvasList(") == 3
    assert "CTkScrollableFrame" not in ui_source


def test_rebuilt_modrinth_page_resets_scroll_now_and_after_layout():
    calls = []

    class Canvas:
        def winfo_exists(self):
            return True

        def yview_moveto(self, value):
            calls.append(("top", value))

    pending = []
    launcher = SimpleNamespace(after_idle=lambda callback: pending.append(callback))
    scroll = Canvas()
    zazu_launcher.Launcher.reset_scroll_to_top(launcher, scroll)
    assert calls == [("top", 0.0)]
    assert len(pending) == 1
    pending.pop()()
    assert calls == [("top", 0.0), ("top", 0.0)]


def test_main_pages_share_one_exclusive_display_slot():
    build_source = inspect.getsource(zazu_launcher.Launcher.build_main)
    switch_source = inspect.getsource(zazu_launcher.Launcher.show_page)
    assert 'page.grid(row=0, column=0, sticky="nsew")' not in build_source
    assert "previous_page.grid_remove()" in switch_source
    assert 'target_page.grid(row=0, column=0, sticky="nsew")' in switch_source
    assert "update_idletasks" not in switch_source
    assert "target_page.tkraise()" not in switch_source


def test_page_switch_unmaps_old_page_before_mapping_new_page():
    operations = []

    class Page:
        def __init__(self, name, manager):
            self.name = name
            self.manager = manager

        def winfo_manager(self):
            return self.manager

        def grid_remove(self):
            operations.append(("hide", self.name))
            self.manager = ""

        def grid(self, **_kwargs):
            operations.append(("show", self.name))
            self.manager = "grid"

    chat = Page("Chat", "grid")
    settings = Page("Settings", "")
    passive = SimpleNamespace(configure=lambda **_kwargs: None)
    launcher = SimpleNamespace(
        current_page="Chat",
        pages={"Chat": chat, "Settings": settings},
        main_header=SimpleNamespace(winfo_manager=lambda: "grid", grid=lambda: None),
        page_host=SimpleNamespace(grid_configure=lambda **_kwargs: None),
        page_title=passive,
        page_subtitle=SimpleNamespace(
            configure=lambda **_kwargs: None,
            winfo_manager=lambda: "pack",
            pack=lambda **_kwargs: None,
            pack_forget=lambda: None,
        ),
        nav_buttons={"Chat": passive, "Settings": passive},
        set_chat_page_visible=lambda _visible: None,
    )
    zazu_launcher.Launcher.show_page(launcher, "Settings")
    assert operations == [("hide", "Chat"), ("show", "Settings")]


def test_window_motion_uses_one_polling_timer_for_resize_work():
    source = inspect.getsource(zazu_launcher.Launcher.on_window_configure)
    close_source = inspect.getsource(zazu_launcher.Launcher.close_launcher)
    assert "brand_wordmark" not in source
    assert "self.after_cancel" not in source
    assert "self.after(70, self.finish_window_motion)" in source
    assert "self.after_cancel(self.window_motion_after_id)" in close_source


def test_customtkinter_resize_draws_are_coalesced():
    handler_source = inspect.getsource(zazu_launcher.install_ctk_resize_coalescing)
    queue_source = inspect.getsource(zazu_launcher.Launcher.queue_ctk_resize_draw)
    flush_source = inspect.getsource(zazu_launcher.Launcher.flush_ctk_resize_draws)
    assert "queue_ctk_resize_draw" in handler_source
    assert "WeakSet" in Path(zazu_launcher.__file__).read_text()
    assert "CTK_RESIZE_FRAME_MS" in queue_source
    assert "widget._draw(no_color_updates=True)" in flush_source


def test_modrinth_canvas_icons_are_applied_without_rebuilding_rows():
    source = inspect.getsource(zazu_launcher.ModrinthCanvasList.set_icon)
    assert "itemconfigure(image_item, image=photo)" in source
    assert "redraw(" not in source


def test_launcher_dashboard_is_one_native_live_surface():
    launcher_source = inspect.getsource(zazu_launcher.Launcher.launcher_ui)
    active_setup = launcher_source.split("        return", 1)[0]
    dashboard_source = inspect.getsource(zazu_launcher.LauncherDashboardCanvas)
    assert "LauncherDashboardCanvas(page, self)" in active_setup
    assert "CTkFrame" not in active_setup
    assert "CTkScrollableFrame" not in dashboard_source
    assert "CTkButton" not in dashboard_source
    assert "CTkLabel" not in dashboard_source


def test_single_surface_dashboard_redraws_live_at_a_bounded_rate():
    source = inspect.getsource(zazu_launcher.LauncherDashboardCanvas.schedule_redraw)
    assert "34 if moving else 16" in source
    assert "self._redraw_after_id is not None" in source
    assert "after_cancel" not in source


def test_dashboard_columns_still_fit_the_minimum_launcher_width():
    widths, gap = zazu_launcher.LauncherDashboardCanvas._column_widths(882)
    assert len(widths) == 3
    assert widths[0] > widths[1] > widths[2]
    assert sum(widths) + gap * 2 == 882


def test_dashboard_render_path_builds_all_regions_without_a_tk_display():
    class Store:
        data = {
            "instances": [
                {
                    "id": "i1",
                    "name": "Fabric Test",
                    "version": "26.2",
                    "loader": "Fabric",
                    "installed": True,
                    "memory": 4096,
                },
                {
                    "id": "i2",
                    "name": "Second",
                    "version": "26.3",
                    "loader": "Fabric",
                    "installed": False,
                },
            ],
            "accounts": [
                {"id": "m1", "name": "Microsoft User", "type": "Microsoft", "skin": ""},
                {"id": "c1", "name": "Offline User", "type": "Offline"},
            ],
            "settings": {"active_account": "m1", "memory": 4096},
        }

    def noop(*_args, **_kwargs):
        return None

    launcher = SimpleNamespace(
        ui_font="Arial",
        store=Store(),
        selected_instance_id="i1",
        selected_account_id="m1",
        active_installs=set(),
        running_instances={},
        launching_instances=set(),
        instance_mod_count=lambda instance: 3 if instance else 0,
        instance_playtime_seconds=lambda _instance: 125,
        instance_custom_icon_path=lambda _instance: "",
        open_modrinth_manager=noop,
        open_mods_folder=noop,
        edit_instance=noop,
        remove_instance=noop,
        launch=noop,
        create_instance=noop,
        add_microsoft=noop,
        add_offline=noop,
        remove_account=noop,
        select_instance=noop,
        select_account=noop,
        set_active_account=noop,
    )
    canvas = object.__new__(zazu_launcher.LauncherDashboardCanvas)
    canvas.launcher = launcher
    canvas._redraw_after_id = None
    canvas._hit_regions = []
    canvas._hover_region = None
    canvas._scroll_regions = {}
    canvas._scroll_drag = None
    canvas._scroll_index = {"instances": 0, "microsoft": 0, "offline": 0}
    canvas._photos = {}
    canvas.progress_visible = True
    canvas.progress_value = 0.42
    canvas.progress_message = "Installing test files"
    items = []

    def add_item(kind, *args, **kwargs):
        items.append((kind, args, kwargs))
        return len(items)

    canvas.winfo_exists = lambda: True
    canvas.winfo_width = lambda: 1000
    canvas.winfo_height = lambda: 620
    canvas.delete = noop
    canvas.configure = lambda **_kwargs: None
    canvas.create_polygon = lambda *args, **kwargs: add_item("polygon", *args, **kwargs)
    canvas.create_text = lambda *args, **kwargs: add_item("text", *args, **kwargs)
    canvas.create_image = lambda *args, **kwargs: add_item("image", *args, **kwargs)
    canvas.itemconfigure = noop
    canvas._instance_photo = lambda _instance, _size: None
    canvas._account_photo = lambda _account, _size: None
    canvas.redraw()

    assert len(items) > 50
    assert len(canvas._hit_regions) >= 10
    assert set(canvas._scroll_regions) == {"instances", "microsoft", "offline"}


def test_ui_callbacks_are_drained_in_small_batches():
    calls = []
    events = queue.Queue()
    for value in range(zazu_launcher.UI_EVENT_BATCH_LIMIT + 5):
        events.put(lambda item=value: calls.append(item))
    launcher = SimpleNamespace(
        ui_events=events,
        winfo_exists=lambda: False,
    )
    zazu_launcher.Launcher.drain_ui_events(launcher)
    assert calls == list(range(zazu_launcher.UI_EVENT_BATCH_LIMIT))
    assert events.qsize() == 5


def test_late_icons_from_a_previous_results_page_are_ignored():
    source = inspect.getsource(zazu_launcher.Launcher.apply_modrinth_icon)
    assert "generation != self.mod_search_generation" in source


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"Passed {len(tests)} Modrinth UI responsiveness tests")
