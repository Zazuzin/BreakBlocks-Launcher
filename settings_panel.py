"""Settings controls for the shared desktop launcher."""

import tkinter as tk

import customtkinter as ctk

import launcher_preferences


def build(launcher, page, colors):
    p = colors
    settings = launcher.store.data["settings"]
    preferences = launcher_preferences.normalized(settings)
    launcher.preference_vars = {
        key: (
            tk.BooleanVar(value=value)
            if isinstance(value, bool)
            else tk.StringVar(value="" if key.startswith("window_") and value == 0 else str(value))
        )
        for key, value in preferences.items()
    }
    launcher.settings_sections = {}
    launcher.java = tk.StringVar(value=settings.get("java", "auto"))
    launcher.memory = tk.IntVar(value=int(settings.get("memory", 4096)))
    launcher.keep_launcher_open = tk.BooleanVar(
        value=bool(settings.get("keep_launcher_open", True))
    )
    launcher.update_enabled = tk.BooleanVar(value=bool(settings.get("update_enabled", True)))
    launcher.update_channel = tk.StringVar(value=settings.get("update_channel", "stable"))
    launcher.update_frequency = tk.StringVar(value=settings.get("update_frequency", "daily"))
    page.grid_columnconfigure(0, weight=1)
    page.grid_rowconfigure(1, weight=1)

    def button(parent, text, command, **kwargs):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            height=36,
            fg_color=p["CONTROL_SURFACE"],
            hover_color=p["ACCENT_HOVER"],
            font=launcher.font_small,
            **kwargs,
        )

    def label(parent, text):
        widget = ctk.CTkLabel(
            parent,
            text=text,
            text_color=p["TEXT"],
            font=launcher.font_small,
            justify="left",
            anchor="w",
            wraplength=720,
        )
        widget.pack(fill="x", padx=20, pady=(4, 8))

        def wrap(event):
            length = max(120, round(event.width / launcher.display_scale - 20))
            if widget.cget("wraplength") != length:
                widget.configure(wraplength=length)

        parent.bind("<Configure>", wrap, add="+")

    def switch(parent, text, variable):
        ctk.CTkSwitch(
            parent,
            text=text,
            variable=variable,
            progress_color=p["GREEN_BG"],
            button_color=p["GREEN"],
            text_color=p["TEXT"],
            font=launcher.font_body,
        ).pack(anchor="w", padx=20, pady=8)

    def row(parent, text):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=7)
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            frame, text=text, text_color=p["MUTED"], font=launcher.font_small, anchor="w"
        ).grid(row=0, column=0, sticky="w")
        return frame

    def option(parent, text, variable, values):
        frame = row(parent, text)
        menu = ctk.CTkOptionMenu(
            frame,
            variable=variable,
            values=values,
            width=140,
            height=34,
            fg_color=p["CONTROL_SURFACE"],
            button_color=p["ACCENT"],
            button_hover_color=p["ACCENT_HOVER"],
            dropdown_fg_color=p["SURFACE_ALT"],
            dropdown_hover_color=p["SURFACE_HOVER"],
            font=launcher.font_small,
        )
        menu.grid(row=0, column=1, sticky="e")
        return menu

    actions = ctk.CTkFrame(page, fg_color="transparent")
    actions.grid(row=0, column=0, sticky="ew", pady=(0, 12))
    button(actions, "Save Settings", launcher.save_settings, width=145).pack(side="right")
    button(actions, "Open Launcher Folder", launcher.open_data_folder, width=175).pack(
        side="right", padx=(0, 8)
    )
    content = ctk.CTkScrollableFrame(page, fg_color="transparent", corner_radius=0)
    content.grid(row=1, column=0, sticky="nsew")
    content.grid_columnconfigure(0, weight=1)
    launcher.settings_content = content
    card = launcher.settings_card(
        content, "Minecraft runtime", "Java and default memory for new instances.", 0
    )
    java_row = ctk.CTkFrame(card, fg_color="transparent")
    java_row.pack(fill="x", padx=20, pady=8)
    launcher.java_entry = ctk.CTkEntry(
        java_row,
        textvariable=launcher.java,
        height=38,
        font=launcher.font_body,
        fg_color=p["DARK_SURFACE"],
        border_color=p["BORDER"],
    )
    launcher.java_entry.pack(side="left", fill="x", expand=True)
    button(java_row, "Browse", launcher.browse_java, width=80).pack(side="left", padx=6)
    button(java_row, "Test Java", launcher.test_java_selection, width=90).pack(side="left")
    label(card, "Auto selects or downloads the Java version required by each instance.")
    memory_row = ctk.CTkFrame(card, fg_color="transparent")
    memory_row.pack(fill="x", padx=20, pady=10)
    launcher.memory_label = ctk.CTkLabel(
        memory_row, text=f"{launcher.memory.get()} MiB", width=105, font=launcher.font_button
    )
    launcher.memory_label.pack(side="right")
    launcher.memory_slider = ctk.CTkSlider(
        memory_row,
        from_=1024,
        to=32768,
        number_of_steps=124,
        command=launcher.memory_changed,
        button_color=p["ACCENT"],
        progress_color=p["ACCENT"],
    )
    launcher.memory_slider.pack(side="left", fill="x", expand=True, padx=(0, 15))
    launcher.memory_slider.set(launcher.memory.get())

    card = launcher.settings_card(
        content,
        "Startup and updates",
        "Background checks notify you about available updates. Installation stays your choice.",
        1,
    )
    switch(card, "Keep the launcher visible while Minecraft runs", launcher.keep_launcher_open)
    switch(card, "Automatic launcher update checks", launcher.update_enabled)
    switch(
        card,
        "Check launcher updates at startup",
        launcher.preference_vars["update_check_startup"],
    )
    switch(
        card,
        "Check installed mods at startup",
        launcher.preference_vars["mods_check_startup"],
    )
    option(card, "Launcher update channel", launcher.update_channel, ["stable", "alpha"])
    option(
        card,
        "Additional automatic checks",
        launcher.update_frequency,
        ["startup", "daily", "weekly", "never"],
    )
    launcher.update_status_text = tk.StringVar(value="No update check has run this session.")
    update_row = ctk.CTkFrame(card, fg_color="transparent")
    update_row.pack(fill="x", padx=20, pady=10)
    ctk.CTkLabel(
        update_row,
        textvariable=launcher.update_status_text,
        text_color=p["MUTED"],
        font=launcher.font_small,
        anchor="w",
        wraplength=510,
    ).pack(side="left", fill="x", expand=True)
    launcher.check_update_button = button(
        update_row, "Check now", lambda: launcher.check_for_launcher_update(manual=True), width=110
    )
    launcher.check_update_button.pack(side="right")
    button(card, "Check installed mods now", launcher.check_startup_mod_updates, width=205).pack(
        anchor="w", padx=20, pady=(0, 12)
    )

    card = launcher.settings_card(
        content,
        "Chat notifications",
        "Chat loads at startup using your saved website session. Website account preferences stay in Chat.",
        2,
    )
    switch(card, "Show notification pop-ups", launcher.preference_vars["chat_popups"])
    switch(card, "Play notification sound", launcher.preference_vars["chat_sound"])
    switch(
        card,
        "Hide message previews in notifications",
        launcher.preference_vars["chat_hide_previews"],
    )
    option(
        card,
        "Notification volume (%)",
        launcher.preference_vars["chat_volume"],
        ["0", "25", "50", "70", "100"],
    )
    option(
        card,
        "Notification duration (seconds)",
        launcher.preference_vars["chat_duration"],
        ["3", "5", "8", "15", "30"],
    )
    controls = ctk.CTkFrame(card, fg_color="transparent")
    controls.pack(fill="x", padx=20, pady=(8, 12))
    button(controls, "Test notification", launcher.preview_chat_notification, width=155).pack(
        side="left"
    )
    button(controls, "Open Chat", lambda: launcher.show_page("Chat"), width=110).pack(
        side="left", padx=8
    )

    card = launcher.settings_card(
        content,
        "Interface size",
        "Adjust control and text sizes. The dashboard scrolls when enlarged content needs more space.",
        3,
    )
    option(
        card,
        "Interface scaling (%)",
        launcher.preference_vars["ui_scale"],
        ["90", "100", "110", "125", "150"],
    )
    option(
        card, "Text size (%)", launcher.preference_vars["text_scale"], ["90", "100", "110", "125"]
    )

    card = launcher.settings_card(
        content,
        "Backups",
        "Recovery snapshots contain mods, configs and launch files. Export with worlds selected to copy worlds.",
        4,
    )
    switch(
        card,
        "Automatic backups before mod or loader changes",
        launcher.preference_vars["automatic_backups"],
    )
    option(
        card,
        "Recovery backups retained per instance",
        launcher.preference_vars["backup_count"],
        ["5", "10", "20"],
    )
    option(
        card,
        "Backup space per instance (MiB)",
        launcher.preference_vars["backup_max_mb"],
        ["1024", "2048", "5120", "10240"],
    )
    label(card, "The newest backup is always kept, even when it exceeds the space limit.")

    card = launcher.settings_card(
        content,
        "Minecraft window defaults",
        "Leave both fields blank to use Minecraft's default. Edit Instance → Window size can override these values.",
        5,
    )
    dimensions = ctk.CTkFrame(card, fg_color="transparent")
    dimensions.pack(fill="x", padx=20, pady=(4, 12))
    dimensions.grid_columnconfigure((0, 1), weight=1)
    launcher._settings_entry(
        dimensions,
        "WIDTH",
        launcher.preference_vars["window_width"],
        0,
        0,
        placeholder="Minecraft default",
    )
    launcher._settings_entry(
        dimensions,
        "HEIGHT",
        launcher.preference_vars["window_height"],
        0,
        1,
        placeholder="Minecraft default",
    )

    card = launcher.settings_card(
        content,
        "Storage and logs",
        "Inspect local usage and remove downloaded installation archives after installation.",
        6,
    )
    launcher.storage_status = tk.StringVar(value="Choose Refresh usage to measure local storage.")
    ctk.CTkLabel(
        card,
        textvariable=launcher.storage_status,
        text_color=p["MUTED"],
        font=launcher.font_small,
        justify="left",
        anchor="w",
        wraplength=720,
    ).pack(fill="x", padx=20, pady=8)
    controls = ctk.CTkFrame(card, fg_color="transparent")
    controls.pack(fill="x", padx=20, pady=8)
    button(controls, "Refresh usage", launcher.refresh_storage_usage, width=135).pack(side="left")
    button(controls, "Clear unused downloads", launcher.clear_unused_downloads, width=200).pack(
        side="left", padx=8
    )
    option(
        card,
        "Launch logs retained per instance",
        launcher.preference_vars["log_count"],
        ["3", "5", "10"],
    )

    if launcher.platform_is_windows:
        card = launcher.settings_card(
            content,
            "Windows chat overlay",
            "Show the existing chat over Minecraft sessions started by this launcher.",
            7,
        )
        switch(card, "Enable the in-game chat overlay", launcher.preference_vars["overlay_enabled"])
        field = ctk.CTkFrame(card, fg_color="transparent")
        field.pack(fill="x", padx=20, pady=8)
        launcher._settings_entry(
            field,
            "OVERLAY HOTKEY",
            launcher.preference_vars["overlay_hotkey"],
            0,
            0,
            placeholder="Ctrl+Shift+F9",
        )
        option(
            card,
            "Overlay text size (%)",
            launcher.preference_vars["overlay_text_scale"],
            ["80", "100", "125", "150", "200"],
        )

    card = launcher.settings_card(
        content, "Advanced", "Custom JVM options and Minecraft download controls.", 8
    )
    switch(card, "Detailed launch logging", launcher.preference_vars["detailed_logging"])
    field = ctk.CTkFrame(card, fg_color="transparent")
    field.pack(fill="x", padx=20, pady=8)
    field.grid_columnconfigure(0, weight=1)
    launcher._settings_entry(
        field,
        "CUSTOM JAVA ARGUMENTS",
        launcher.preference_vars["jvm_arguments"],
        0,
        0,
        placeholder="Optional JVM options",
    )
    option(
        card,
        "Concurrent Minecraft downloads",
        launcher.preference_vars["download_workers"],
        ["2", "4", "8", "10", "16"],
    )
    option(
        card,
        "Download timeout (seconds)",
        launcher.preference_vars["download_timeout"],
        ["30", "60", "120", "180"],
    )
    option(
        card, "Download retries", launcher.preference_vars["download_retries"], ["0", "1", "2", "3"]
    )
