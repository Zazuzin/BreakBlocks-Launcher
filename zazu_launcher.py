#!/usr/bin/env python3
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser

APP_DIR = pathlib.Path(__file__).resolve().parent
VENDOR_DIR = APP_DIR / "vendor"
if VENDOR_DIR.is_dir():
    sys.path.insert(0, str(VENDOR_DIR))

import customtkinter as ctk
import tkinter as tk
import tkinter.font as tkfont
from PIL import Image

import minecraft_backend

APP_VERSION = "0.4.2 Alpha"
MICROSOFT_CLIENT_ID = "f621b9a7-a133-49c0-b04b-66de82aacb62"

BG = "#0b0f16"
SIDEBAR = "#101722"
SURFACE = "#151d2a"
SURFACE_ALT = "#1b2636"
SURFACE_HOVER = "#233248"
BORDER = "#2a3950"
TEXT = "#f4f7fb"
MUTED = "#93a4ba"
ACCENT = "#3282f6"
ACCENT_HOVER = "#246bd0"
RED = "#ef4b4b"
RED_HOVER = "#ca3b3b"
GREEN = "#36c991"


class Store:
    def __init__(self):
        if os.name == "nt":
            base = pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home() / "AppData/Local"))
            self.root = base / "Zazu Launcher"
        else:
            base = pathlib.Path(os.environ.get("XDG_DATA_HOME", pathlib.Path.home() / ".local/share"))
            self.root = base / "zazu-launcher"
        self.instances = self.root / "instances"
        self.file = self.root / "launcher.json"
        self.instances.mkdir(parents=True, exist_ok=True)
        try:
            self.data = json.loads(self.file.read_text())
        except Exception:
            self.data = {
                "accounts": [],
                "instances": [],
                "settings": {"theme": "dark", "java": "auto", "memory": 4096},
            }
        self.data.setdefault("accounts", [])
        self.data.setdefault("instances", [])
        self.data.setdefault("settings", {})
        self.data["settings"].setdefault("java", "auto")
        self.data["settings"].setdefault("memory", 4096)

    def save(self):
        self.file.write_text(json.dumps(self.data, indent=2))
        try:
            os.chmod(self.file, 0o600)
        except OSError:
            pass


class Launcher(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=BG)
        self.store = Store()
        self.title(f"Zazu Launcher {APP_VERSION}")
        self.geometry("1180x740")
        self.minsize(920, 620)

        families = set(tkfont.families())
        self.ui_font = next(
            (name for name in ("Segoe UI", "Calibri", "Carlito", "Noto Sans", "DejaVu Sans") if name in families),
            "TkDefaultFont",
        )
        self.font_title = ctk.CTkFont(self.ui_font, 28, "bold")
        self.font_heading = ctk.CTkFont(self.ui_font, 19, "bold")
        self.font_body = ctk.CTkFont(self.ui_font, 13)
        self.font_small = ctk.CTkFont(self.ui_font, 11)
        self.font_button = ctk.CTkFont(self.ui_font, 12, "bold")

        self.selected_instance_id = None
        self.selected_account_id = None
        self.instance_rows = {}
        self.account_rows = {}
        self.account_images = []
        self.nav_buttons = {}
        self.pages = {}

        self.build()
        self.refresh()

    def build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.build_sidebar()
        self.build_main()

    def build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=252, corner_radius=0, fg_color=SIDEBAR)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(2, weight=1)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=24, pady=(25, 24))
        ctk.CTkLabel(brand, text="ZAZU", text_color=RED, font=ctk.CTkFont(self.ui_font, 24, "bold")).pack(side="left")
        ctk.CTkLabel(brand, text="  LAUNCHER", text_color=TEXT, font=ctk.CTkFont(self.ui_font, 24, "bold")).pack(side="left")
        ctk.CTkLabel(
            sidebar,
            text=APP_VERSION.upper(),
            text_color=MUTED,
            font=ctk.CTkFont(self.ui_font, 10, "bold"),
        ).place(x=25, y=58)

        nav = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="new", padx=14)
        for name, icon in (("Instances", "▦"), ("Accounts", "●"), ("Settings", "⚙")):
            button = ctk.CTkButton(
                nav,
                text=f"  {icon}    {name}",
                command=lambda page=name: self.show_page(page),
                height=48,
                corner_radius=12,
                anchor="w",
                fg_color="transparent",
                hover_color=SURFACE_HOVER,
                text_color=MUTED,
                font=self.font_button,
            )
            button.pack(fill="x", pady=4)
            self.nav_buttons[name] = button

        account_card = ctk.CTkFrame(sidebar, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        account_card.grid(row=3, column=0, sticky="sew", padx=14, pady=(12, 16))
        ctk.CTkLabel(account_card, text="CURRENT LAUNCH ACCOUNT", text_color=MUTED, font=ctk.CTkFont(self.ui_font, 9, "bold")).pack(anchor="w", padx=15, pady=(13, 3))
        self.sidebar_account = ctk.CTkLabel(account_card, text="No account selected", text_color=TEXT, font=self.font_body, anchor="w")
        self.sidebar_account.pack(fill="x", padx=15, pady=(0, 13))

    def build_main(self):
        main = ctk.CTkFrame(self, corner_radius=0, fg_color=BG)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(main, fg_color="transparent", height=105)
        header.grid(row=0, column=0, sticky="ew", padx=32, pady=(24, 10))
        self.page_title = ctk.CTkLabel(header, text="Instances", text_color=TEXT, font=self.font_title, anchor="w")
        self.page_title.pack(anchor="w")
        self.page_subtitle = ctk.CTkLabel(header, text="Create and launch separate Minecraft installations", text_color=MUTED, font=self.font_body, anchor="w")
        self.page_subtitle.pack(anchor="w", pady=(3, 0))

        self.page_host = ctk.CTkFrame(main, fg_color="transparent")
        self.page_host.grid(row=1, column=0, sticky="nsew", padx=32, pady=(0, 20))
        self.page_host.grid_columnconfigure(0, weight=1)
        self.page_host.grid_rowconfigure(0, weight=1)

        self.pages["Instances"] = ctk.CTkFrame(self.page_host, fg_color="transparent")
        self.pages["Accounts"] = ctk.CTkFrame(self.page_host, fg_color="transparent")
        self.pages["Settings"] = ctk.CTkFrame(self.page_host, fg_color="transparent")
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        self.instances_ui(self.pages["Instances"])
        self.accounts_ui(self.pages["Accounts"])
        self.settings_ui(self.pages["Settings"])

        footer = ctk.CTkFrame(main, height=38, corner_radius=0, fg_color="#0e141e")
        footer.grid(row=2, column=0, sticky="ew")
        self.status = tk.StringVar(value="Ready")
        ctk.CTkLabel(footer, textvariable=self.status, text_color=MUTED, font=self.font_small, anchor="w").pack(fill="x", padx=32, pady=8)
        self.show_page("Instances")

    def instances_ui(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        toolbar = ctk.CTkFrame(page, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 13))
        ctk.CTkButton(
            toolbar,
            text="＋  Create instance",
            command=self.create_instance,
            width=165,
            height=42,
            corner_radius=11,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self.font_button,
        ).pack(side="left")
        ctk.CTkButton(
            toolbar,
            text="Remove",
            command=self.remove_instance,
            width=100,
            height=42,
            corner_radius=11,
            fg_color=SURFACE_ALT,
            hover_color=RED_HOVER,
            border_width=1,
            border_color=BORDER,
            font=self.font_button,
        ).pack(side="left", padx=9)

        self.instance_scroll = ctk.CTkScrollableFrame(page, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=BORDER)
        self.instance_scroll.grid(row=1, column=0, sticky="nsew")
        self.instance_scroll.grid_columnconfigure(0, weight=1)

        launch_card = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=BORDER)
        launch_card.grid(row=2, column=0, sticky="ew", pady=(13, 0))
        launch_card.grid_columnconfigure(0, weight=1)
        progress_header = ctk.CTkFrame(launch_card, fg_color="transparent")
        progress_header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 5))
        progress_header.grid_columnconfigure(0, weight=1)
        self.progress_text = tk.StringVar(value="Ready to launch")
        ctk.CTkLabel(progress_header, textvariable=self.progress_text, text_color=MUTED, font=self.font_small, anchor="w").grid(row=0, column=0, sticky="w")
        self.progress_percent = ctk.CTkLabel(progress_header, text="0%", text_color=TEXT, font=ctk.CTkFont(self.ui_font, 11, "bold"))
        self.progress_percent.grid(row=0, column=1, sticky="e")
        self.progress = ctk.CTkProgressBar(launch_card, height=10, corner_radius=5, fg_color="#253044", progress_color=ACCENT)
        self.progress.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 15))
        self.progress.set(0)
        ctk.CTkButton(
            launch_card,
            text="Launch Minecraft  ▶",
            command=self.launch,
            width=190,
            height=50,
            corner_radius=12,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(self.ui_font, 13, "bold"),
        ).grid(row=0, column=1, rowspan=2, padx=18, pady=14)

    def accounts_ui(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        toolbar = ctk.CTkFrame(page, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 13))
        ctk.CTkButton(
            toolbar,
            text="＋  Microsoft account",
            command=self.add_microsoft,
            height=42,
            corner_radius=11,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self.font_button,
        ).pack(side="left")
        ctk.CTkButton(
            toolbar,
            text="＋  Offline account",
            command=self.add_offline,
            height=42,
            corner_radius=11,
            fg_color=SURFACE_ALT,
            hover_color=SURFACE_HOVER,
            border_width=1,
            border_color=BORDER,
            font=self.font_button,
        ).pack(side="left", padx=9)
        ctk.CTkButton(
            toolbar,
            text="Remove",
            command=self.remove_account,
            width=100,
            height=42,
            corner_radius=11,
            fg_color="transparent",
            hover_color=RED_HOVER,
            border_width=1,
            border_color=BORDER,
            font=self.font_button,
        ).pack(side="right")
        self.account_scroll = ctk.CTkScrollableFrame(page, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=BORDER)
        self.account_scroll.grid(row=1, column=0, sticky="nsew")
        self.account_scroll.grid_columnconfigure(0, weight=1)

    def settings_ui(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)
        self.java = tk.StringVar(value="auto")
        self.memory = tk.IntVar(value=4096)

        java_card = self.settings_card(page, "Java runtime", "Use automatic Java selection, or provide a custom executable.", 0)
        self.java_entry = ctk.CTkEntry(
            java_card,
            textvariable=self.java,
            height=44,
            corner_radius=10,
            fg_color="#101722",
            border_color=BORDER,
            text_color=TEXT,
            placeholder_text="auto",
            font=self.font_body,
        )
        self.java_entry.pack(fill="x", padx=20, pady=(4, 18))

        memory_card = self.settings_card(page, "Memory", "Choose the default maximum memory available to new instances.", 1)
        memory_row = ctk.CTkFrame(memory_card, fg_color="transparent")
        memory_row.pack(fill="x", padx=20, pady=(5, 18))
        memory_row.grid_columnconfigure(0, weight=1)
        self.memory_slider = ctk.CTkSlider(
            memory_row,
            from_=1024,
            to=32768,
            number_of_steps=124,
            command=self.memory_changed,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            progress_color=ACCENT,
            fg_color="#273247",
        )
        self.memory_slider.grid(row=0, column=0, sticky="ew", padx=(0, 18))
        self.memory_label = ctk.CTkLabel(memory_row, text="4096 MiB", width=105, height=38, corner_radius=9, fg_color="#101722", text_color=TEXT, font=self.font_button)
        self.memory_label.grid(row=0, column=1)

        ctk.CTkButton(
            page,
            text="Save settings",
            command=self.save_settings,
            width=150,
            height=44,
            corner_radius=11,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self.font_button,
        ).grid(row=3, column=0, sticky="e", pady=(14, 0))

    def settings_card(self, parent, title, subtitle, row):
        card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=BORDER)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 13))
        ctk.CTkLabel(card, text=title, text_color=TEXT, font=self.font_heading, anchor="w").pack(fill="x", padx=20, pady=(17, 2))
        ctk.CTkLabel(card, text=subtitle, text_color=MUTED, font=self.font_small, anchor="w").pack(fill="x", padx=20, pady=(0, 12))
        return card

    def show_page(self, name):
        titles = {
            "Instances": ("Instances", "Create and launch separate Minecraft installations"),
            "Accounts": ("Accounts", "Choose which Microsoft or offline account launches Minecraft"),
            "Settings": ("Settings", "Configure Java and performance preferences"),
        }
        self.pages[name].tkraise()
        self.page_title.configure(text=titles[name][0])
        self.page_subtitle.configure(text=titles[name][1])
        for page_name, button in self.nav_buttons.items():
            active = page_name == name
            button.configure(fg_color=SURFACE_ALT if active else "transparent", text_color=TEXT if active else MUTED)

    def refresh(self):
        self.refresh_instances()
        self.refresh_accounts()
        settings = self.store.data["settings"]
        self.java.set(settings.get("java", "auto"))
        memory = int(settings.get("memory", 4096))
        self.memory.set(memory)
        self.memory_slider.set(memory)
        self.memory_label.configure(text=f"{memory} MiB")

    def refresh_instances(self):
        instances = self.store.data["instances"]
        if self.selected_instance_id not in {item["id"] for item in instances}:
            self.selected_instance_id = instances[0]["id"] if instances else None
        for child in self.instance_scroll.winfo_children():
            child.destroy()
        self.instance_rows = {}
        if not instances:
            empty = ctk.CTkFrame(self.instance_scroll, fg_color="transparent")
            empty.grid(row=0, column=0, sticky="nsew", pady=95)
            ctk.CTkLabel(empty, text="◇", text_color=BORDER, font=ctk.CTkFont(self.ui_font, 48)).pack()
            ctk.CTkLabel(empty, text="No instances yet", text_color=TEXT, font=self.font_heading).pack(pady=(10, 3))
            ctk.CTkLabel(empty, text="Create your first Minecraft instance to get started.", text_color=MUTED, font=self.font_body).pack()
            return
        for row_number, instance in enumerate(instances):
            selected = instance["id"] == self.selected_instance_id
            row = ctk.CTkFrame(
                self.instance_scroll,
                height=82,
                fg_color=SURFACE_HOVER if selected else SURFACE_ALT,
                corner_radius=13,
                border_width=2 if selected else 1,
                border_color=ACCENT if selected else BORDER,
            )
            row.grid(row=row_number, column=0, sticky="ew", padx=3, pady=5)
            row.grid_columnconfigure(1, weight=1)
            loader = instance.get("loader", "Vanilla")
            loader_color = {"Fabric": "#3b82f6", "Forge": "#e07a3f", "NeoForge": "#9b6df2", "Quilt": "#c657d4"}.get(loader, "#66758a")
            icon = ctk.CTkLabel(row, text=loader[:1], width=48, height=48, corner_radius=12, fg_color=loader_color, text_color="white", font=ctk.CTkFont(self.ui_font, 19, "bold"))
            icon.grid(row=0, column=0, rowspan=2, padx=16, pady=16)
            name = ctk.CTkLabel(row, text=instance["name"], text_color=TEXT, font=ctk.CTkFont(self.ui_font, 14, "bold"), anchor="w")
            name.grid(row=0, column=1, sticky="sw", pady=(14, 1))
            detail = ctk.CTkLabel(row, text=f"Minecraft {instance['version']}  •  {loader}", text_color=MUTED, font=self.font_small, anchor="w")
            detail.grid(row=1, column=1, sticky="nw", pady=(1, 14))
            ready = bool(instance.get("installed"))
            badge = ctk.CTkLabel(
                row,
                text="READY" if ready else "NOT INSTALLED",
                width=105,
                height=28,
                corner_radius=8,
                fg_color="#173d33" if ready else "#3a3030",
                text_color=GREEN if ready else "#e9a2a2",
                font=ctk.CTkFont(self.ui_font, 9, "bold"),
            )
            badge.grid(row=0, column=2, rowspan=2, padx=16)
            for widget in (row, icon, name, detail, badge):
                widget.bind("<Button-1>", lambda _event, ident=instance["id"]: self.select_instance(ident))
            self.instance_rows[instance["id"]] = row

    def select_instance(self, ident):
        self.selected_instance_id = ident
        self.refresh_instances()

    def refresh_accounts(self):
        accounts = self.store.data["accounts"]
        active = self.store.data["settings"].get("active_account", "")
        if self.selected_account_id not in {account["id"] for account in accounts}:
            self.selected_account_id = active if active in {account["id"] for account in accounts} else (accounts[0]["id"] if accounts else None)
        for child in self.account_scroll.winfo_children():
            child.destroy()
        self.account_rows = {}
        self.account_images = []
        active_account = next((account for account in accounts if account["id"] == active), None)
        self.sidebar_account.configure(text=active_account["name"] if active_account else "No account selected")
        if not accounts:
            empty = ctk.CTkFrame(self.account_scroll, fg_color="transparent")
            empty.grid(row=0, column=0, sticky="nsew", pady=95)
            ctk.CTkLabel(empty, text="◎", text_color=BORDER, font=ctk.CTkFont(self.ui_font, 48)).pack()
            ctk.CTkLabel(empty, text="No accounts added", text_color=TEXT, font=self.font_heading).pack(pady=(10, 3))
            ctk.CTkLabel(empty, text="Add a Microsoft or offline account to launch Minecraft.", text_color=MUTED, font=self.font_body).pack()
            return
        for row_number, account in enumerate(accounts):
            selected = account["id"] == self.selected_account_id
            is_active = account["id"] == active
            row = ctk.CTkFrame(
                self.account_scroll,
                height=82,
                fg_color=SURFACE_HOVER if selected or is_active else SURFACE_ALT,
                corner_radius=13,
                border_width=2 if selected else 1,
                border_color=ACCENT if selected else ("#315c50" if is_active else BORDER),
            )
            row.grid(row=row_number, column=0, sticky="ew", padx=3, pady=5)
            row.grid_columnconfigure(1, weight=1)
            image = self.skin_head(account.get("skin")) if account.get("type") == "Microsoft" else None
            if image:
                self.account_images.append(image)
                avatar = ctk.CTkLabel(row, text="", image=image, width=46, height=46)
            else:
                avatar = ctk.CTkLabel(row, text=account["name"][:1].upper(), width=46, height=46, corner_radius=12, fg_color="#48566a", text_color="white", font=ctk.CTkFont(self.ui_font, 18, "bold"))
            avatar.grid(row=0, column=0, rowspan=2, padx=16, pady=17)
            name = ctk.CTkLabel(row, text=account["name"], text_color=TEXT, font=ctk.CTkFont(self.ui_font, 14, "bold"), anchor="w")
            name.grid(row=0, column=1, sticky="sw", pady=(14, 1))
            detail = ctk.CTkLabel(row, text=account.get("type", "Account"), text_color=MUTED, font=self.font_small, anchor="w")
            detail.grid(row=1, column=1, sticky="nw", pady=(1, 14))
            if is_active:
                action = ctk.CTkLabel(row, text="✓  LAUNCH ACCOUNT", width=140, height=31, corner_radius=9, fg_color="#173d33", text_color=GREEN, font=ctk.CTkFont(self.ui_font, 9, "bold"))
            else:
                action = ctk.CTkButton(row, text="Use account", command=lambda ident=account["id"]: self.set_active_account(ident), width=115, height=34, corner_radius=9, fg_color="#26364c", hover_color=ACCENT_HOVER, font=ctk.CTkFont(self.ui_font, 10, "bold"))
            action.grid(row=0, column=2, rowspan=2, padx=16)
            for widget in (row, avatar, name, detail):
                widget.bind("<Button-1>", lambda _event, ident=account["id"]: self.select_account(ident))
            self.account_rows[account["id"]] = row

    def select_account(self, ident):
        self.selected_account_id = ident
        self.refresh_accounts()

    def create_instance(self):
        window, body = self.make_dialog("Create instance", 560, 490)
        ctk.CTkLabel(body, text="Create Minecraft instance", text_color=TEXT, font=self.font_title).pack(anchor="w", padx=26, pady=(24, 3))
        ctk.CTkLabel(body, text="Choose a version and loader. Downloads begin after creation.", text_color=MUTED, font=self.font_small).pack(anchor="w", padx=26, pady=(0, 18))

        name = tk.StringVar(value="")
        version = tk.StringVar(value=self.fallback_versions()[0])
        loader = tk.StringVar(value="Fabric")
        self.dialog_field(body, "INSTANCE NAME", ctk.CTkEntry(body, textvariable=name, height=43, corner_radius=10, fg_color="#101722", border_color=BORDER, placeholder_text="Optional — defaults to version and loader", font=self.font_body))
        version_box = ctk.CTkComboBox(body, variable=version, values=list(self.fallback_versions()), state="readonly", height=43, corner_radius=10, fg_color="#101722", border_color=BORDER, button_color="#26364c", button_hover_color=ACCENT_HOVER, dropdown_fg_color=SURFACE_ALT, dropdown_hover_color=SURFACE_HOVER, font=self.font_body, dropdown_font=self.font_body)
        self.dialog_field(body, "MINECRAFT VERSION", version_box)
        loader_box = ctk.CTkOptionMenu(body, variable=loader, values=["Vanilla", "Fabric", "Forge", "NeoForge", "Quilt"], height=43, corner_radius=10, fg_color="#101722", button_color="#26364c", button_hover_color=ACCENT_HOVER, dropdown_fg_color=SURFACE_ALT, dropdown_hover_color=SURFACE_HOVER, font=self.font_body, dropdown_font=self.font_body)
        self.dialog_field(body, "LOADER", loader_box)
        threading.Thread(target=self.load_versions, args=(window, version_box, version), daemon=True).start()

        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", padx=26, pady=(18, 24))
        ctk.CTkButton(buttons, text="Cancel", command=window.destroy, width=105, height=42, corner_radius=10, fg_color=SURFACE_ALT, hover_color=SURFACE_HOVER, font=self.font_button).pack(side="right")

        def save():
            selected_version = version.get()
            selected_loader = loader.get()
            instance_name = name.get().strip() or f"{selected_version} {selected_loader}"
            ident = re.sub(r"[^a-z0-9]+", "-", instance_name.lower()).strip("-") + "-" + uuid.uuid4().hex[:6]
            self.store.data["instances"].append({
                "id": ident,
                "name": instance_name,
                "version": selected_version,
                "loader": selected_loader,
                "memory": self.memory.get(),
                "installed": False,
            })
            (self.store.instances / ident / "minecraft").mkdir(parents=True)
            self.store.save()
            self.selected_instance_id = ident
            self.refresh_instances()
            window.destroy()
            self.start_install(ident, selected_version, selected_loader)

        ctk.CTkButton(buttons, text="Create instance", command=save, width=145, height=42, corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_HOVER, font=self.font_button).pack(side="right", padx=(0, 9))

    def dialog_field(self, parent, title, widget):
        ctk.CTkLabel(parent, text=title, text_color=MUTED, font=ctk.CTkFont(self.ui_font, 9, "bold")).pack(anchor="w", padx=26, pady=(7, 5))
        widget.pack(fill="x", padx=26, pady=(0, 7))

    def fallback_versions(self):
        return tuple("26.2 26.1 1.21.11 1.21.10 1.21.9 1.21.8 1.21.7 1.21.6 1.21.5 1.21.4 1.21.3 1.21.2 1.21.1 1.21 1.20.6 1.20.5 1.20.4 1.20.3 1.20.2 1.20.1 1.20 1.19.4 1.19.3 1.19.2 1.19.1 1.19 1.18.2 1.18.1 1.18 1.17.1 1.17 1.16.5 1.16.4 1.16.3 1.16.2 1.16.1 1.16 1.15.2 1.15.1 1.15 1.14.4 1.14.3 1.14.2 1.14.1 1.14 1.13.2 1.13.1 1.13 1.12.2 1.12.1 1.12 1.11.2 1.11.1 1.11 1.10.2 1.10.1 1.10 1.9.4 1.9.3 1.9.2 1.9.1 1.9 1.8.9 1.8.8 1.8.7 1.8.6 1.8.5 1.8.4 1.8.3 1.8.2 1.8.1 1.8 1.7.10 1.7.9 1.7.8 1.7.7 1.7.6 1.7.5 1.7.4 1.7.3 1.7.2 1.6.4 1.6.2 1.6.1 1.6 1.5.2 1.5.1 1.5 1.4.7 1.4.6 1.4.5 1.4.4 1.4.2 1.3.2 1.3.1 1.2.5 1.2.4 1.2.3 1.2.2 1.2.1 1.1 1.0.1 1.0".split())

    def load_versions(self, window, box, value):
        try:
            request = urllib.request.Request(minecraft_backend.MANIFEST, headers={"User-Agent": "Zazu-Launcher/0.4"})
            data = json.load(urllib.request.urlopen(request, timeout=10))
            items = [item["id"] for item in data["versions"]]
        except Exception:
            items = list(self.fallback_versions())

        def apply():
            try:
                if window.winfo_exists():
                    box.configure(values=items)
                    value.set(items[0])
            except tk.TclError:
                pass

        self.after(0, apply)

    def add_offline(self):
        window, body = self.make_dialog("Add offline account", 500, 320)
        ctk.CTkLabel(body, text="Add offline account", text_color=TEXT, font=self.font_title).pack(anchor="w", padx=26, pady=(25, 3))
        ctk.CTkLabel(body, text="Offline accounts do not authenticate with Microsoft servers.", text_color=MUTED, font=self.font_small).pack(anchor="w", padx=26, pady=(0, 19))
        name = tk.StringVar()
        entry = ctk.CTkEntry(body, textvariable=name, height=45, corner_radius=10, fg_color="#101722", border_color=BORDER, placeholder_text="Minecraft username", font=self.font_body)
        self.dialog_field(body, "USERNAME — 3 TO 16 CHARACTERS", entry)
        entry.focus_set()
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", padx=26, pady=(22, 24))
        ctk.CTkButton(buttons, text="Cancel", command=window.destroy, width=100, height=42, corner_radius=10, fg_color=SURFACE_ALT, hover_color=SURFACE_HOVER, font=self.font_button).pack(side="right")

        def save():
            username = name.get().strip()
            if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", username):
                self.show_notice("Invalid username", "Use 3–16 letters, numbers or underscores.", danger=True)
                return
            raw = hashlib.md5(("OfflinePlayer:" + username).encode()).digest()
            account_id = str(uuid.UUID(bytes=raw, version=3))
            self.store.data["accounts"] = [item for item in self.store.data["accounts"] if item["id"] != account_id]
            self.store.data["accounts"].append({"id": account_id, "name": username, "type": "Cracked / Offline"})
            if not self.store.data["settings"].get("active_account"):
                self.store.data["settings"]["active_account"] = account_id
            self.store.save()
            self.selected_account_id = account_id
            self.refresh_accounts()
            window.destroy()
            self.status.set(f"Added offline account {username}")

        ctk.CTkButton(buttons, text="Add account", command=save, width=130, height=42, corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_HOVER, font=self.font_button).pack(side="right", padx=(0, 9))

    def add_microsoft(self):
        window, body = self.make_dialog("Add Microsoft account", 590, 430)
        ctk.CTkLabel(body, text="Microsoft sign-in", text_color=TEXT, font=self.font_title).pack(pady=(25, 3))
        message = tk.StringVar(value="Requesting a secure sign-in code…")
        ctk.CTkLabel(body, textvariable=message, text_color=MUTED, font=self.font_small, wraplength=510, justify="center").pack(padx=26, pady=(0, 18))
        code = tk.StringVar(value="—")
        code_box = ctk.CTkEntry(body, textvariable=code, state="readonly", height=58, corner_radius=12, justify="center", fg_color="#101722", border_color=BORDER, text_color=TEXT, font=ctk.CTkFont(self.ui_font, 22, "bold"))
        code_box.pack(fill="x", padx=55)
        status = tk.StringVar(value="Waiting for Microsoft…")
        ctk.CTkLabel(body, textvariable=status, text_color=MUTED, font=self.font_small).pack(pady=(12, 10))
        button_row = ctk.CTkFrame(body, fg_color="transparent")
        button_row.pack(pady=(7, 12))
        open_button = ctk.CTkButton(button_row, text="Open Microsoft sign-in", state="disabled", width=190, height=43, corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_HOVER, font=self.font_button)
        open_button.pack(side="left", padx=5)

        def copy_code():
            self.clipboard_clear()
            self.clipboard_append(code.get())
            status.set("Code copied")

        copy_button = ctk.CTkButton(button_row, text="Copy code", command=copy_code, state="disabled", width=110, height=43, corner_radius=10, fg_color=SURFACE_ALT, hover_color=SURFACE_HOVER, font=self.font_button)
        copy_button.pack(side="left", padx=5)
        ctk.CTkButton(body, text="Cancel", command=window.destroy, width=90, height=36, corner_radius=9, fg_color="transparent", hover_color=SURFACE_HOVER, text_color=MUTED, font=self.font_small).pack()

        def worker():
            try:
                device = self.http_form(
                    "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode",
                    {"client_id": MICROSOFT_CLIENT_ID, "scope": "XboxLive.SignIn XboxLive.offline_access"},
                    "Microsoft device sign-in",
                )

                def show_code():
                    if not window.winfo_exists():
                        return
                    message.set(device["message"])
                    code.set(device["user_code"])
                    status.set("Complete sign-in in your browser")
                    open_button.configure(state="normal", command=lambda: webbrowser.open(device["verification_uri"]))
                    copy_button.configure(state="normal")

                self.after(0, show_code)
                token = self.poll_token(device)
                profile = self.minecraft_profile(token["access_token"])
                account = {
                    "id": profile["id"],
                    "name": profile["name"],
                    "type": "Microsoft",
                    "access_token": token["access_token"],
                    "refresh_token": token.get("refresh_token", ""),
                    "minecraft_token": profile["minecraft_token"],
                    "skin": self.download_skin(profile),
                }
                self.store.data["accounts"] = [item for item in self.store.data["accounts"] if item["id"] != account["id"]] + [account]
                if not self.store.data["settings"].get("active_account"):
                    self.store.data["settings"]["active_account"] = account["id"]
                self.store.save()

                def complete():
                    self.selected_account_id = account["id"]
                    self.refresh_accounts()
                    if window.winfo_exists():
                        window.destroy()
                    self.status.set(f"Added Microsoft account {account['name']}")

                self.after(0, complete)
            except Exception as error:
                self.after(0, lambda detail=str(error): status.set("Sign-in failed: " + detail) if window.winfo_exists() else None)

        threading.Thread(target=worker, daemon=True).start()

    def remove_instance(self):
        instance = next((item for item in self.store.data["instances"] if item["id"] == self.selected_instance_id), None)
        if not instance:
            self.show_notice("Select an instance", "Choose the instance you want to remove first.")
            return

        def remove():
            target = (self.store.instances / instance["id"]).resolve()
            if target.parent == self.store.instances.resolve():
                shutil.rmtree(target, ignore_errors=True)
            self.store.data["instances"] = [item for item in self.store.data["instances"] if item["id"] != instance["id"]]
            self.selected_instance_id = None
            self.store.save()
            self.refresh_instances()
            self.status.set(f"Removed {instance['name']}")

        self.confirm_action("Remove instance?", f"{instance['name']} and its Minecraft files will be permanently removed.", remove)

    def remove_account(self):
        account = next((item for item in self.store.data["accounts"] if item["id"] == self.selected_account_id), None)
        if not account:
            self.show_notice("Select an account", "Choose the account you want to remove first.")
            return

        def remove():
            self.store.data["accounts"] = [item for item in self.store.data["accounts"] if item["id"] != account["id"]]
            if self.store.data["settings"].get("active_account") == account["id"]:
                remaining = self.store.data["accounts"]
                self.store.data["settings"]["active_account"] = remaining[0]["id"] if remaining else ""
            self.selected_account_id = None
            self.store.save()
            self.refresh_accounts()
            self.status.set(f"Removed {account['name']}")

        self.confirm_action("Remove account?", f"Remove {account['name']} from Zazu Launcher?", remove)

    def set_active_account(self, ident=None):
        account_id = ident or self.selected_account_id
        if not account_id:
            self.show_notice("Select an account", "Choose an account first.")
            return
        self.store.data["settings"]["active_account"] = account_id
        self.selected_account_id = account_id
        self.store.save()
        self.refresh_accounts()
        self.status.set("Launch account changed")

    def memory_changed(self, value):
        memory = int(round(value / 256) * 256)
        self.memory.set(memory)
        self.memory_label.configure(text=f"{memory} MiB")

    def save_settings(self):
        self.store.data["settings"].update(java=self.java.get().strip() or "auto", memory=self.memory.get())
        self.store.save()
        self.status.set("Settings saved")
        self.show_notice("Settings saved", "Your Java and memory settings have been updated.")

    def start_install(self, ident, version, loader):
        self.progress.set(0)
        self.progress_percent.configure(text="0%")
        self.progress_text.set("Preparing download…")

        def update(percent, text):
            def apply():
                self.progress.set(max(0, min(100, percent)) / 100)
                self.progress_percent.configure(text=f"{percent}%")
                self.progress_text.set(text)

            self.after(0, apply)

        def worker():
            try:
                minecraft_backend.Installer(
                    self.store.root,
                    update,
                    self.store.data["settings"].get("java", "auto"),
                ).install(self.store.instances / ident, version, loader)
                for item in self.store.data["instances"]:
                    if item["id"] == ident:
                        item["installed"] = True
                self.store.save()
                self.after(0, lambda: (self.refresh_instances(), self.status.set("Instance installed")))
            except Exception as error:
                self.after(0, lambda detail=str(error): (self.progress_text.set("Installation failed"), self.show_notice("Installation failed", detail, danger=True)))

        threading.Thread(target=worker, daemon=True).start()

    def launch(self):
        instance = next((item for item in self.store.data["instances"] if item["id"] == self.selected_instance_id), None)
        active = self.store.data["settings"].get("active_account", "")
        account = next((item for item in self.store.data["accounts"] if item["id"] == active), None)
        if not instance:
            self.show_notice("Select an instance", "Choose a Minecraft instance first.")
            return
        if not account:
            self.show_notice("Select a launch account", "Choose the account Minecraft should launch with on the Accounts page.")
            return
        if not instance.get("installed"):
            self.show_notice("Instance not installed", "This instance has not finished installing.")
            return

        def worker():
            try:
                if account["type"] == "Microsoft":
                    self.after(0, lambda: self.status.set("Refreshing Microsoft session…"))
                    self.refresh_microsoft(account)
                launch_account = dict(account, memory=instance.get("memory", self.memory.get()))
                minecraft_backend.launch(self.store.instances / instance["id"], launch_account)
                self.after(0, lambda: self.status.set("Minecraft launched with " + account["name"]))
            except Exception as error:
                self.after(0, lambda detail=str(error): self.show_notice("Launch failed", detail, danger=True))

        threading.Thread(target=worker, daemon=True).start()

    def http_form(self, url, data, stage=None):
        body = urllib.parse.urlencode(data).encode()
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": "Zazu-Launcher/0.4.2",
            },
        )
        try:
            return json.load(urllib.request.urlopen(request, timeout=30))
        except urllib.error.HTTPError as error:
            if stage:
                raise self.http_failure(stage, error) from None
            raise

    def http_json(self, url, data, token=None, extra_headers=None, stage="Online service"):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Zazu-Launcher/0.4.2",
        }
        if token:
            headers["Authorization"] = "Bearer " + token
        if extra_headers:
            headers.update(extra_headers)
        request = urllib.request.Request(
            url,
            data=json.dumps(data).encode() if data is not None else None,
            headers=headers,
        )
        try:
            return json.load(urllib.request.urlopen(request, timeout=30))
        except urllib.error.HTTPError as error:
            raise self.http_failure(stage, error) from None

    def http_failure(self, stage, error):
        raw = error.read().decode("utf-8", "replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = {}
        xerr_messages = {
            2148916227: "This Microsoft account is banned from Xbox services.",
            2148916229: "This account is restricted by its Xbox family settings.",
            2148916233: "This Microsoft account does not have an Xbox profile. Open the Xbox app or xbox.com and create the profile first.",
            2148916234: "This account must accept the current Xbox terms before it can be used.",
            2148916235: "Xbox services are not available for this account's region.",
            2148916236: "This Microsoft account must provide proof of age.",
            2148916237: "This Microsoft account has reached an Xbox playtime limit.",
            2148916238: "This underage Microsoft account must be added to a Microsoft family.",
        }
        try:
            xerr = int(detail.get("XErr", 0))
        except (TypeError, ValueError):
            xerr = 0
        message = xerr_messages.get(xerr)
        if not message:
            message = detail.get("error_description") or detail.get("errorMessage") or detail.get("Message") or detail.get("message")
        if not message:
            message = raw.strip() or getattr(error, "reason", "Request rejected")
        message = " ".join(str(message).split())[:500]
        suffix = f" Xbox error {xerr}." if xerr else ""
        return RuntimeError(f"{stage} failed (HTTP {error.code}). {message}{suffix}")

    def poll_token(self, device):
        until = time.time() + device["expires_in"]
        interval = device.get("interval", 5)
        while time.time() < until:
            time.sleep(interval)
            try:
                return self.http_form(
                    "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
                    {
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        "client_id": MICROSOFT_CLIENT_ID,
                        "device_code": device["device_code"],
                    },
                )
            except urllib.error.HTTPError as error:
                try:
                    detail = json.loads(error.read())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise RuntimeError(f"Microsoft sign-in failed (HTTP {error.code})") from None
                if detail.get("error") == "slow_down":
                    interval += 5
                elif detail.get("error") != "authorization_pending":
                    raise RuntimeError(detail.get("error_description", detail.get("error")))
        raise RuntimeError("Microsoft sign-in timed out")

    def minecraft_profile(self, msa):
        contract_headers = {"x-xbl-contract-version": "1"}
        xbl = self.http_json(
            "https://user.auth.xboxlive.com/user/authenticate",
            {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": "d=" + msa}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"},
            extra_headers=contract_headers,
            stage="Xbox user authentication",
        )
        xsts = self.http_json(
            "https://xsts.auth.xboxlive.com/xsts/authorize",
            {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl["Token"]]}, "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"},
            extra_headers=contract_headers,
            stage="Minecraft authorization",
        )
        try:
            uhs = xsts["DisplayClaims"]["xui"][0]["uhs"]
            xsts_token = xsts["Token"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("Minecraft authorization returned an incomplete Xbox token") from None
        mc = self.http_json(
            "https://api.minecraftservices.com/launcher/login",
            {"xtoken": f"XBL3.0 x={uhs};{xsts_token}", "platform": "PC_LAUNCHER"},
            stage="Minecraft access-token exchange",
        )
        minecraft_token = mc.get("access_token")
        if not minecraft_token:
            raise RuntimeError("Minecraft access-token exchange returned no access token")
        entitlements = self.http_json(
            "https://api.minecraftservices.com/entitlements/license?requestId=" + uuid.uuid4().hex,
            None,
            minecraft_token,
            stage="Minecraft ownership check",
        )
        if not entitlements.get("items"):
            raise RuntimeError("This Microsoft account does not currently own Minecraft: Java Edition")
        profile = self.http_json(
            "https://api.minecraftservices.com/minecraft/profile",
            None,
            minecraft_token,
            stage="Minecraft profile lookup",
        )
        profile["minecraft_token"] = minecraft_token
        return profile

    def refresh_microsoft(self, account):
        refresh = account.get("refresh_token")
        if not refresh:
            raise RuntimeError("This Microsoft account must be signed in again")
        token = self.http_form(
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
            {"client_id": MICROSOFT_CLIENT_ID, "grant_type": "refresh_token", "refresh_token": refresh, "scope": "XboxLive.SignIn XboxLive.offline_access"},
            "Microsoft token refresh",
        )
        old_id = account["id"]
        profile = self.minecraft_profile(token["access_token"])
        account.update(
            id=profile["id"],
            name=profile["name"],
            access_token=token["access_token"],
            refresh_token=token.get("refresh_token", refresh),
            minecraft_token=profile["minecraft_token"],
        )
        if self.store.data["settings"].get("active_account") == old_id:
            self.store.data["settings"]["active_account"] = account["id"]
        self.store.save()
        return account

    def download_skin(self, profile):
        skins = profile.get("skins", [])
        if not skins:
            return ""
        folder = self.store.root / "skins"
        folder.mkdir(exist_ok=True)
        path = folder / (profile["id"] + ".png")
        request = urllib.request.Request(skins[0]["url"], headers={"User-Agent": "Zazu-Launcher/0.4.2"})
        with urllib.request.urlopen(request, timeout=30) as source, open(path, "wb") as target:
            target.write(source.read())
        return str(path)

    def skin_head(self, path):
        try:
            skin = Image.open(path).convert("RGBA")
            head = skin.crop((8, 8, 16, 16)).resize((42, 42), Image.Resampling.NEAREST)
            if skin.width >= 48:
                overlay = skin.crop((40, 8, 48, 16)).resize((42, 42), Image.Resampling.NEAREST)
                head.alpha_composite(overlay)
            return ctk.CTkImage(light_image=head, dark_image=head, size=(42, 42))
        except Exception:
            return None

    def load_asset(self, name, size):
        try:
            image = Image.open(APP_DIR / "assets" / name).convert("RGBA")
            return ctk.CTkImage(light_image=image, dark_image=image, size=size)
        except Exception:
            return None

    def make_dialog(self, title, width, height):
        window = ctk.CTkToplevel(self, fg_color=BG)
        window.title(title)
        window.resizable(False, False)
        x = self.winfo_x() + max(20, (self.winfo_width() - width) // 2)
        y = self.winfo_y() + max(20, (self.winfo_height() - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.transient(self)
        body = ctk.CTkFrame(window, fg_color=SURFACE, corner_radius=18, border_width=1, border_color=BORDER)
        body.pack(fill="both", expand=True, padx=14, pady=14)
        self.after(100, window.grab_set)
        return window, body

    def show_notice(self, title, message, danger=False):
        window, body = self.make_dialog(title, 470, 245)
        ctk.CTkLabel(body, text="!" if danger else "✓", width=45, height=45, corner_radius=22, fg_color="#4a2328" if danger else "#173d33", text_color=RED if danger else GREEN, font=ctk.CTkFont(self.ui_font, 20, "bold")).pack(pady=(23, 10))
        ctk.CTkLabel(body, text=title, text_color=TEXT, font=self.font_heading).pack()
        ctk.CTkLabel(body, text=message, text_color=MUTED, font=self.font_small, wraplength=400, justify="center").pack(padx=25, pady=(7, 14))
        ctk.CTkButton(body, text="Close", command=window.destroy, width=105, height=38, corner_radius=9, fg_color=RED if danger else ACCENT, hover_color=RED_HOVER if danger else ACCENT_HOVER, font=self.font_button).pack()

    def confirm_action(self, title, message, action):
        window, body = self.make_dialog(title, 490, 260)
        ctk.CTkLabel(body, text="!", width=45, height=45, corner_radius=22, fg_color="#4a2328", text_color=RED, font=ctk.CTkFont(self.ui_font, 20, "bold")).pack(pady=(24, 10))
        ctk.CTkLabel(body, text=title, text_color=TEXT, font=self.font_heading).pack()
        ctk.CTkLabel(body, text=message, text_color=MUTED, font=self.font_small, wraplength=420, justify="center").pack(padx=25, pady=(7, 15))
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack()
        ctk.CTkButton(buttons, text="Cancel", command=window.destroy, width=105, height=38, corner_radius=9, fg_color=SURFACE_ALT, hover_color=SURFACE_HOVER, font=self.font_button).pack(side="left", padx=5)

        def accept():
            window.destroy()
            action()

        ctk.CTkButton(buttons, text="Remove", command=accept, width=105, height=38, corner_radius=9, fg_color=RED, hover_color=RED_HOVER, font=self.font_button).pack(side="left", padx=5)


if __name__ == "__main__":
    Launcher().mainloop()
