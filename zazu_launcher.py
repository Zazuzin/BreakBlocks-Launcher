#!/usr/bin/env python3
import base64
import hashlib
import http.client
import io
import json
import math
import os
import pathlib
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
import weakref

APP_DIR = pathlib.Path(__file__).resolve().parent
VENDOR_DIR = APP_DIR / "vendor"
if VENDOR_DIR.is_dir():
    sys.path.insert(0, str(VENDOR_DIR))

from display_environment import enable_windows_per_monitor_dpi

enable_windows_per_monitor_dpi()

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog

import customtkinter as ctk
from customtkinter.windows.widgets.core_rendering import DrawEngine
from PIL import Image, ImageDraw, ImageTk

import chat_browser
import launcher_update
import minecraft_backend
import modrinth_client
from app_config import (
    APP_NAME,
    APP_USER_AGENT,
    APP_VERSION,
    DEFAULT_UPDATE_CHANNEL,
    UPDATE_CHANNELS,
)
from process_environment import open_system_target, system_process_environment

BRAND_WORDMARK_SIZE = (161, 63)
BRAND_WORDMARK_BG = "#131313"
MICROSOFT_CLIENT_ID = "f621b9a7-a133-49c0-b04b-66de82aacb62"
MINECRAFT_TOKEN_REFRESH_MARGIN = 5 * 60
MODRINTH_SEARCH_TIMEOUT_SECONDS = 30
MODRINTH_PAGE_SIZE = 30
UI_EVENT_BATCH_LIMIT = 12
UI_EVENT_TIME_BUDGET_SECONDS = 0.008
CTK_RESIZE_FRAME_MS = 42
WINDOW_MOTION_IDLE_MS = 140
LEGAL_NOTICE_VERSION = 1
BREAKBLOCKS_URL = "https://breakblocks.com"
BREAKBLOCKS_DISCORD_URL = "https://breakblocks.com/discord"
BREAKBLOCKS_PATREON_URL = "https://www.patreon.com/cw/BreakBlocks"
BREAKBLOCKS_CHAT_WEB_URL = chat_browser.CHAT_URL
BREAKBLOCKS_CONTACT_URL = "https://www.breakblocks.com/contact"
BREAKBLOCKS_PRIVACY_URL = "https://www.breakblocks.com/privacy-policy"
BREAKBLOCKS_TERMS_URL = "https://www.breakblocks.com/terms"
MINECRAFT_EULA_URL = "https://www.minecraft.net/eula"
MINECRAFT_USAGE_GUIDELINES_URL = "https://www.minecraft.net/usage-guidelines"
MICROSOFT_PRIVACY_URL = "https://www.microsoft.com/privacy/privacystatement"
MOUNTAINS_OF_LAVA_YOUTUBE_URL = "https://www.youtube.com/@mountainsoflavainc.6913"
ZAZUZIN_GITHUB_URL = "https://github.com/Zazuzin"
ETIANL_GITHUB_URL = "https://github.com/etianl"


def create_ipv4_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
    """Open a TCP connection using IPv4, avoiding broken Linux IPv6 routes."""
    host, port = address
    errors = []
    for family, socktype, protocol, _canonical_name, socket_address in socket.getaddrinfo(
        host, port, socket.AF_INET, socket.SOCK_STREAM
    ):
        connection = None
        try:
            connection = socket.socket(family, socktype, protocol)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                connection.settimeout(timeout)
            if source_address:
                connection.bind(source_address)
            connection.connect(socket_address)
            return connection
        except OSError as error:
            errors.append(error)
            if connection is not None:
                connection.close()
    if errors:
        raise errors[-1]
    raise OSError(f"No IPv4 address found for {host}")


class IPv4HTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = create_ipv4_connection


class IPv4HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, request):
        return self.do_open(
            IPv4HTTPSConnection,
            request,
            context=self._context,
        )


def open_online_request(request, timeout):
    """Open a request, preferring IPv4 for Microsoft sign-in on Linux."""
    hostname = urllib.parse.urlparse(request.full_url).hostname
    if sys.platform.startswith("linux") and hostname == "login.microsoftonline.com":
        return urllib.request.build_opener(IPv4HTTPSHandler()).open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


def curl_form_json(url, body, headers, timeout=20):
    """POST a form with curl on Linux and preserve urllib-style HTTP errors."""
    curl = shutil.which("curl")
    if not curl:
        raise FileNotFoundError("curl is not installed")
    command = [
        curl,
        "--silent",
        "--show-error",
        "--location",
        "--ipv4",
        "--proto",
        "=https",
        "--connect-timeout",
        "8",
        "--max-time",
        str(timeout),
    ]
    for name, value in headers.items():
        command.extend(("--header", f"{name}: {value}"))
    command.extend(("--data-binary", "@-", "--write-out", "\n%{http_code}", url))
    try:
        completed = subprocess.run(
            command,
            input=body,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=system_process_environment(),
            timeout=timeout + 3,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Microsoft did not respond within {timeout} seconds") from None
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(detail or f"curl stopped with exit code {completed.returncode}")
    payload, separator, status_text = completed.stdout.rpartition(b"\n")
    if not separator or not status_text.isdigit():
        raise RuntimeError("Microsoft returned an unreadable response")
    status_code = int(status_text)
    if status_code >= 400:
        raise urllib.error.HTTPError(
            url,
            status_code,
            f"HTTP {status_code}",
            None,
            io.BytesIO(payload),
        )
    try:
        return json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("Microsoft returned an unreadable response") from None


BLOCK_ICONS = (
    ("grass_block", "Grass"),
    ("stone", "Stone"),
    ("dirt", "Dirt"),
    ("cobblestone", "Cobblestone"),
    ("oak_planks", "Oak planks"),
    ("bricks", "Bricks"),
    ("glass", "Glass"),
    ("obsidian", "Obsidian"),
    ("netherrack", "Netherrack"),
    ("end_stone", "End stone"),
    ("diamond_ore", "Diamond ore"),
    ("emerald_ore", "Emerald ore"),
    ("gold_ore", "Gold ore"),
    ("iron_ore", "Iron ore"),
    ("redstone_ore", "Redstone ore"),
    ("amethyst_block", "Amethyst"),
    ("copper_block", "Copper"),
    ("deepslate", "Deepslate"),
    ("moss_block", "Moss"),
    ("sand", "Sand"),
    ("snow_block", "Snow"),
    ("pumpkin", "Pumpkin"),
    ("melon", "Melon"),
    ("crafting_table", "Crafting table"),
    ("bookshelf", "Bookshelf"),
)
BLOCK_ICON_KEYS = {key for key, _label in BLOCK_ICONS}


def default_instance_icon(identifier):
    """Choose a stable built-in icon for new and existing instances."""
    digest = hashlib.sha256(str(identifier).encode("utf-8")).digest()
    return BLOCK_ICONS[int.from_bytes(digest[:2], "big") % len(BLOCK_ICONS)][0]


def format_playtime(seconds):
    """Format a stored number of seconds for the compact launch summary."""
    try:
        total_seconds = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        total_seconds = 0
    if total_seconds == 0:
        return "0m"
    if total_seconds < 60:
        return "<1m"
    total_minutes = total_seconds // 60
    if total_minutes < 60:
        return f"{total_minutes}m"
    total_hours, minutes = divmod(total_minutes, 60)
    if total_hours < 24:
        return f"{total_hours}h" + (f" {minutes}m" if minutes else "")
    days, hours = divmod(total_hours, 24)
    return f"{days}d" + (f" {hours}h" if hours else "")


def read_report_text(path, limit=2_000_000):
    """Read a local crash report or launch log without loading an unbounded file."""
    path = pathlib.Path(path)
    with path.open("rb") as source:
        payload = source.read(limit + 1)
    truncated = len(payload) > limit
    text = payload[:limit].decode("utf-8", errors="replace")
    if truncated:
        text += "\n\n[Report shortened by BreakBlocks Launcher.]"
    return text


def active_account_first(accounts, active_id):
    """Return a stable view with the current launch account at the top."""
    return sorted(accounts, key=lambda account: account.get("id") != active_id)


def account_type_label(account):
    """Return the public account label while accepting legacy saved values."""
    return "Microsoft" if account.get("type") == "Microsoft" else "Offline"


def has_verified_minecraft_ownership(accounts):
    """Return whether this installation has completed a Microsoft entitlement check."""
    for account in accounts:
        if account.get("type") != "Microsoft":
            continue
        try:
            if float(account.get("entitlement_verified_at", 0)) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def load_brand_wordmark(path):
    """Load the approved static stacked BreakBlocks wordmark without altering it."""
    with Image.open(path) as image:
        if image.format != "PNG":
            raise ValueError("the BreakBlocks wordmark is not a PNG")
        if image.size != BRAND_WORDMARK_SIZE:
            raise ValueError(
                f"the BreakBlocks wordmark must be {BRAND_WORDMARK_SIZE[0]}x"
                f"{BRAND_WORDMARK_SIZE[1]} pixels"
            )
        return image.convert("RGBA")


def trim_transparent_square(image):
    """Crop transparent padding and centre an icon on a square canvas."""
    rgba = image.convert("RGBA")
    bounds = rgba.getchannel("A").getbbox()
    if not bounds:
        return rgba
    cropped = rgba.crop(bounds)
    side = max(cropped.size)
    squared = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    squared.alpha_composite(
        cropped,
        ((side - cropped.width) // 2, (side - cropped.height) // 2),
    )
    return squared


def nav_icon_image(kind, size=80, color=(220, 220, 220, 255)):
    """Draw a crisp high-resolution sidebar icon for scaled Tk displays."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    width = max(4, size // 12)
    if kind == "launcher":
        gap = size // 12
        start = size // 6
        cell = (size - (2 * start) - gap) // 2
        for row in range(2):
            for column in range(2):
                left = start + column * (cell + gap)
                top = start + row * (cell + gap)
                draw.rounded_rectangle(
                    (left, top, left + cell, top + cell),
                    radius=max(2, size // 20),
                    outline=color,
                    width=width,
                )
    elif kind == "chat":
        draw.rounded_rectangle(
            (size * 0.12, size * 0.16, size * 0.88, size * 0.68),
            radius=size // 8,
            outline=color,
            width=width,
        )
        draw.line(
            (size * 0.30, size * 0.68, size * 0.20, size * 0.84, size * 0.45, size * 0.68),
            fill=color,
            width=width,
            joint="curve",
        )
    elif kind == "settings":
        centre = size / 2
        for index in range(8):
            angle = math.radians(index * 45)
            draw.line(
                (
                    centre + math.cos(angle) * size * 0.26,
                    centre + math.sin(angle) * size * 0.26,
                    centre + math.cos(angle) * size * 0.39,
                    centre + math.sin(angle) * size * 0.39,
                ),
                fill=color,
                width=width,
            )
        draw.ellipse(
            (size * 0.22, size * 0.22, size * 0.78, size * 0.78),
            outline=color,
            width=width,
        )
        draw.ellipse(
            (size * 0.40, size * 0.40, size * 0.60, size * 0.60),
            outline=color,
            width=width,
        )
    elif kind == "about":
        draw.ellipse(
            (size * 0.13, size * 0.13, size * 0.87, size * 0.87),
            outline=color,
            width=width,
        )
        draw.ellipse(
            (size * 0.46, size * 0.27, size * 0.54, size * 0.35),
            fill=color,
        )
        draw.line(
            (size * 0.50, size * 0.43, size * 0.50, size * 0.68),
            fill=color,
            width=width,
        )
    else:
        raise ValueError(f"Unknown navigation icon: {kind}")
    return image


BBC_CHARCOAL = "#2d2d2d"
BG = "#181818"
SIDEBAR = BBC_CHARCOAL
SURFACE = BBC_CHARCOAL
SURFACE_ALT = "#383838"
SURFACE_HOVER = "#454545"
BORDER = "#505050"
TEXT = "#f4f4f4"
MUTED = "#b0b0b0"
ACCENT = "#5a5a5a"
ACCENT_HOVER = "#6a6a6a"
SELECTION = "#c2c2c2"
DARK_SURFACE = "#202020"
DEEP_SURFACE = "#191919"
CONTROL_SURFACE = "#444444"
PROGRESS_STATUS_BG = "#514522"
PROGRESS_STATUS_TEXT = "#f0cf78"
WARNING_BG = "#393127"
WARNING_BORDER = "#66543e"
WARNING_TEXT = "#d8c4a8"
RED = "#ef4b4b"
RED_HOVER = "#ca3b3b"
GREEN = "#7ce7b3"
GREEN_BG = "#20543f"
GREEN_BORDER = "#62a98b"

# Fixed launcher proportions.  At the 1200 px minimum window width these
# minimums, card gaps and page padding fit without horizontal clipping.
LAUNCHER_COLUMN_SPECS = ((14, 420), (6, 220), (5, 205))
LAUNCHER_ROW_SPECS = ((0, 350), (1, 205))


class ServiceRateLimitError(RuntimeError):
    pass


class LauncherDashboardCanvas(tk.Canvas):
    """Render the complete launcher dashboard as one native canvas surface."""

    INSTANCE_ROW_HEIGHT = 86
    ACCOUNT_ROW_HEIGHT = 100
    ROW_GAP = 10

    def __init__(self, master, launcher):
        super().__init__(master=master, bg=BG, bd=0, highlightthickness=0, relief="flat")
        self.launcher = launcher
        self._redraw_after_id = None
        self._hit_regions = []
        self._hover_region = None
        self._scroll_regions = {}
        self._scroll_drag = None
        self._scroll_index = {"instances": 0, "microsoft": 0, "offline": 0}
        self._photos = {}
        self.progress_visible = False
        self.progress_value = 0.0
        self.progress_message = ""

        self.bind("<Configure>", self._on_configure, add="+")
        self.bind("<Motion>", self._on_motion, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<ButtonPress-1>", self._on_button_press, add="+")
        self.bind("<B1-Motion>", self._on_button_drag, add="+")
        self.bind("<ButtonRelease-1>", self._on_button_release, add="+")
        self.bind("<MouseWheel>", self._on_mousewheel, add="+")
        self.bind("<Button-4>", lambda event: self._scroll_at(event.x, event.y, -1), add="+")
        self.bind("<Button-5>", lambda event: self._scroll_at(event.x, event.y, 1), add="+")

    def destroy(self):
        if self._redraw_after_id is not None:
            try:
                self.after_cancel(self._redraw_after_id)
            except tk.TclError:
                pass
            self._redraw_after_id = None
        super().destroy()

    def _on_configure(self, _event=None):
        self.schedule_redraw()

    def schedule_redraw(self):
        if self._redraw_after_id is not None:
            return
        moving = bool(getattr(self.winfo_toplevel(), "_window_motion_active", False))
        self._redraw_after_id = self.after(34 if moving else 16, self._scheduled_redraw)

    def _scheduled_redraw(self):
        self._redraw_after_id = None
        self.redraw()

    def refresh(self):
        self.schedule_redraw()

    def set_progress(self, value=None, message=None, visible=None):
        if value is not None:
            self.progress_value = max(0.0, min(1.0, float(value)))
        if message is not None:
            self.progress_message = str(message)
        if visible is not None:
            self.progress_visible = bool(visible)
        self.schedule_redraw()

    @staticmethod
    def _clean_text(value, limit=80):
        text = " ".join(str(value or "").split())
        return text if len(text) <= limit else text[: max(1, limit - 1)].rstrip() + "…"

    def _font(self, size, weight=None):
        if sys.platform.startswith("linux") and size <= 10:
            size = max(10, size + 1)
        return (self.launcher.ui_font, size, weight) if weight else (self.launcher.ui_font, size)

    def _rounded_rectangle(self, x1, y1, x2, y2, radius, **kwargs):
        radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
        points = (
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        )
        return self.create_polygon(points, smooth=True, splinesteps=18, **kwargs)

    def _button_rectangle(self, x1, y1, x2, y2, radius, **kwargs):
        """Draw an integer-aligned rounded button without Bézier edge artefacts."""
        left, top, right, bottom = (int(round(value)) for value in (x1, y1, x2, y2))
        radius = int(max(0, min(round(radius), (right - left) // 2, (bottom - top) // 2)))
        if radius == 0:
            return self.create_rectangle(left, top, right, bottom, **kwargs)

        points = []
        steps = max(3, min(8, radius))
        corners = (
            (left + radius, top + radius, 180, 270),
            (right - radius, top + radius, 270, 360),
            (right - radius, bottom - radius, 0, 90),
            (left + radius, bottom - radius, 90, 180),
        )
        for centre_x, centre_y, start, end in corners:
            for step in range(steps + 1):
                angle = math.radians(start + ((end - start) * step / steps))
                point = (
                    int(round(centre_x + radius * math.cos(angle))),
                    int(round(centre_y + radius * math.sin(angle))),
                )
                if not points or points[-1] != point:
                    points.append(point)
        return self.create_polygon(points, smooth=False, **kwargs)

    def _register_hit(self, bounds, callback, shape=None, normal=None, hover=None):
        region = {
            "bounds": tuple(bounds),
            "callback": callback,
            "shape": shape,
            "normal": normal,
            "hover": hover,
        }
        self._hit_regions.append(region)
        return region

    def _button(
        self,
        x1,
        y1,
        x2,
        y2,
        text,
        callback,
        fill=ACCENT,
        hover=ACCENT_HOVER,
        enabled=True,
        text_color=TEXT,
        font_size=10,
    ):
        normal_fill = fill if enabled else "#373737"
        color = text_color if enabled else "#777777"
        shape = self._button_rectangle(x1, y1, x2, y2, 8, fill=normal_fill, outline="")
        self.create_text(
            (x1 + x2) / 2,
            (y1 + y2) / 2,
            text=text,
            fill=color,
            font=self._font(font_size, "bold"),
        )
        if enabled and callback is not None:
            self._register_hit((x1, y1, x2, y2), callback, shape, normal_fill, hover)

    def _pill(self, x1, y1, x2, y2, text, fill, text_color, font_size=9):
        self._rounded_rectangle(x1, y1, x2, y2, 8, fill=fill, outline="")
        self.create_text(
            (x1 + x2) / 2,
            (y1 + y2) / 2,
            text=text,
            fill=text_color,
            font=self._font(font_size, "bold"),
        )

    def _hit_at(self, x, y):
        for region in reversed(self._hit_regions):
            x1, y1, x2, y2 = region["bounds"]
            if x1 <= x <= x2 and y1 <= y <= y2:
                return region
        return None

    def _set_hover(self, region):
        if region is self._hover_region:
            return
        previous = self._hover_region
        self._hover_region = region
        if previous and previous["shape"] is not None:
            try:
                self.itemconfigure(previous["shape"], fill=previous["normal"])
            except tk.TclError:
                pass
        if region and region["shape"] is not None:
            try:
                self.itemconfigure(region["shape"], fill=region["hover"])
            except tk.TclError:
                pass
        self.configure(cursor="hand2" if region else "")

    def _on_motion(self, event):
        if self._scroll_drag is None:
            self._set_hover(self._hit_at(event.x, event.y))

    def _on_leave(self, _event=None):
        self._set_hover(None)

    def _on_button_press(self, event):
        for key, region in self._scroll_regions.items():
            if (
                region["track_x1"] <= event.x <= region["track_x2"]
                and region["y1"] <= event.y <= region["y2"]
            ):
                self._scroll_drag = key
                self._set_scroll_from_y(key, event.y)
                return "break"
        return None

    def _on_button_drag(self, event):
        if self._scroll_drag is not None:
            self._set_scroll_from_y(self._scroll_drag, event.y)
            return "break"
        return None

    def _on_button_release(self, event):
        blocker = getattr(self.launcher, "modal_action_blocked", None)
        if callable(blocker) and blocker():
            self._scroll_drag = None
            return "break"
        if self._scroll_drag is not None:
            self._set_scroll_from_y(self._scroll_drag, event.y)
            self._scroll_drag = None
            return "break"
        region = self._hit_at(event.x, event.y)
        if region is not None:
            region["callback"]()
            return "break"
        return None

    def _on_mousewheel(self, event):
        if not event.delta:
            return None
        direction = -1 if event.delta > 0 else 1
        return self._scroll_at(event.x, event.y, direction)

    def _scroll_at(self, x, y, direction):
        for key, region in self._scroll_regions.items():
            if region["x1"] <= x <= region["x2"] and region["y1"] <= y <= region["y2"]:
                maximum = max(0, region["total"] - region["visible"])
                new_value = max(0, min(maximum, self._scroll_index[key] + int(direction)))
                if new_value != self._scroll_index[key]:
                    self._scroll_index[key] = new_value
                    self.redraw()
                return "break"
        return None

    def _set_scroll_from_y(self, key, y):
        region = self._scroll_regions.get(key)
        if not region:
            return
        maximum = max(0, region["total"] - region["visible"])
        if maximum <= 0:
            return
        track_height = max(1, region["y2"] - region["y1"])
        fraction = max(0.0, min(1.0, (y - region["y1"]) / track_height))
        self._scroll_index[key] = int(round(fraction * maximum))
        self.redraw()

    def _draw_scrollbar(self, key, x1, y1, x2, y2, total, visible):
        maximum = max(0, total - visible)
        start = max(0, min(maximum, self._scroll_index[key]))
        self._scroll_index[key] = start
        self._scroll_regions[key] = {
            "x1": x1,
            "x2": x2,
            "y1": y1,
            "y2": y2,
            "track_x1": x2 - 8,
            "track_x2": x2,
            "total": total,
            "visible": visible,
        }
        if maximum <= 0:
            return
        track_x1 = x2 - 6
        self._rounded_rectangle(track_x1, y1, x2, y2, 3, fill="#242424", outline="")
        track_height = y2 - y1
        thumb_height = max(32, track_height * (visible / total))
        travel = max(1, track_height - thumb_height)
        thumb_y = y1 + travel * (start / maximum)
        self._rounded_rectangle(
            track_x1, thumb_y, x2, thumb_y + thumb_height, 3, fill="#777777", outline=""
        )

    @staticmethod
    def _column_widths(total_width):
        gap = 12
        usable = max(300, total_width - gap * 2)
        minimums = (420, 220, 205)
        weights = (14, 6, 5)
        minimum_total = sum(minimums)
        if usable >= minimum_total:
            extra = usable - minimum_total
            widths = [
                minimums[index] + int(extra * weights[index] / sum(weights)) for index in range(3)
            ]
            widths[0] += usable - sum(widths)
            return widths, gap
        scale = usable / minimum_total
        widths = [max(150, int(value * scale)) for value in minimums]
        widths[0] += usable - sum(widths)
        return widths, gap

    def _photo_from_path(self, path, size, skin_head=False):
        if not path:
            return None
        try:
            source = pathlib.Path(path)
            stamp = source.stat().st_mtime_ns
            key = (str(source.resolve()), tuple(size), bool(skin_head), stamp)
            cached = self._photos.get(key)
            if cached is not None:
                return cached
            image = Image.open(source).convert("RGBA")
            if skin_head:
                head = image.crop((8, 8, 16, 16)).resize(size, Image.Resampling.NEAREST)
                if image.width >= 48:
                    overlay = image.crop((40, 8, 48, 16)).resize(size, Image.Resampling.NEAREST)
                    head.alpha_composite(overlay)
                image = head
            else:
                image = image.resize(size, Image.Resampling.NEAREST)
            photo = ImageTk.PhotoImage(image=image, master=self)
            self._photos[key] = photo
            return photo
        except (OSError, ValueError, RuntimeError, tk.TclError):
            return None

    def _instance_photo(self, instance, size):
        key = instance.get("icon") or default_instance_icon(instance.get("id", "instance"))
        if key == "custom":
            try:
                path = self.launcher.instance_custom_icon_path(instance)
            except ValueError:
                return None
        else:
            if key not in BLOCK_ICON_KEYS:
                key = default_instance_icon(instance.get("id", "instance"))
            path = APP_DIR / "assets" / "instance_icons" / f"{key}.png"
        return self._photo_from_path(path, (size, size))

    def _account_photo(self, account, size):
        if account.get("type") != "Microsoft":
            return None
        return self._photo_from_path(account.get("skin"), (size, size), skin_head=True)

    def redraw(self):
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        width = max(845 + 24, self.winfo_width())
        height = max(500, self.winfo_height())
        self.delete("all")
        self._hit_regions = []
        self._hover_region = None
        self._scroll_regions = {}
        self.configure(cursor="")

        widths, gap = self._column_widths(width)
        left_x1 = 0
        left_x2 = widths[0]
        microsoft_x1 = left_x2 + gap
        microsoft_x2 = microsoft_x1 + widths[1]
        offline_x1 = microsoft_x2 + gap
        offline_x2 = width
        launch_height = min(430, max(300, height - 205 - gap))
        self._draw_launch_card(left_x1, 0, left_x2, launch_height)
        self._draw_instances_card(left_x1, launch_height + gap, left_x2, height)
        self._draw_accounts_card("microsoft", microsoft_x1, 0, microsoft_x2, height)
        self._draw_accounts_card("offline", offline_x1, 0, offline_x2, height)

    def _draw_launch_card(self, x1, y1, x2, y2):
        launcher = self.launcher
        instances = launcher.store.data["instances"]
        instance = next(
            (item for item in instances if item.get("id") == launcher.selected_instance_id), None
        )
        active_id = launcher.store.data["settings"].get("active_account", "")
        account = next(
            (item for item in launcher.store.data["accounts"] if item.get("id") == active_id), None
        )
        installing = bool(instance and instance.get("id") in launcher.active_installs)
        running = bool(
            instance
            and (
                instance.get("id") in launcher.running_instances
                or instance.get("id") in launcher.launching_instances
            )
        )
        installed = bool(instance and instance.get("installed"))
        can_launch = bool(instance and installed and not installing and not running)
        selected = instance is not None

        self._rounded_rectangle(x1, y1, x2, y2, 16, fill=BBC_CHARCOAL, outline="")
        self.create_text(
            x1 + 15,
            y1 + 20,
            text="READY TO LAUNCH",
            fill=TEXT,
            font=self._font(12, "bold"),
            anchor="w",
        )
        if not instance:
            badge_text, badge_fill, badge_color = "SELECT AN INSTANCE", SURFACE_ALT, MUTED
        elif running:
            badge_text, badge_fill, badge_color = "RUNNING", GREEN_BG, GREEN
        elif installing:
            badge_text, badge_fill, badge_color = (
                "INSTALLING",
                PROGRESS_STATUS_BG,
                PROGRESS_STATUS_TEXT,
            )
        elif installed:
            badge_text, badge_fill, badge_color = "READY", GREEN_BG, GREEN
        else:
            badge_text, badge_fill, badge_color = "NOT INSTALLED", "#3a3030", "#e9a2a2"
        self._pill(x2 - 120, y1 + 9, x2 - 14, y1 + 32, badge_text, badge_fill, badge_color)

        summary_top = y1 + 43
        summary_bottom = summary_top + 82
        self._rounded_rectangle(
            x1 + 12,
            summary_top,
            x2 - 12,
            summary_bottom,
            13,
            fill=SURFACE_ALT,
            outline=BORDER,
            width=1,
        )
        if instance:
            photo = self._instance_photo(instance, 62)
            if photo:
                self.create_image(x1 + 55, summary_top + 41, image=photo)
            else:
                self.create_text(
                    x1 + 55,
                    summary_top + 41,
                    text=instance.get("loader", "V")[:1],
                    fill=TEXT,
                    font=self._font(28, "bold"),
                )
            self.create_text(
                x1 + 98,
                summary_top + 28,
                text=self._clean_text(instance.get("name"), 55),
                fill=TEXT,
                font=self._font(15, "bold"),
                anchor="w",
                width=max(120, x2 - x1 - 125),
            )
            self.create_text(
                x1 + 98,
                summary_top + 54,
                text=f"Minecraft {instance.get('version', 'Unknown')}  •  {instance.get('loader', 'Vanilla')}",
                fill=MUTED,
                font=self._font(10),
                anchor="w",
                width=max(120, x2 - x1 - 125),
            )
        else:
            self.create_text(x1 + 55, summary_top + 41, text="◇", fill=BORDER, font=self._font(29))
            self.create_text(
                x1 + 98,
                summary_top + 28,
                text="No instance selected",
                fill=TEXT,
                font=self._font(15, "bold"),
                anchor="w",
            )
            self.create_text(
                x1 + 98,
                summary_top + 54,
                text="Choose an instance from the library",
                fill=MUTED,
                font=self._font(10),
                anchor="w",
            )

        detail_top = summary_bottom + 10
        detail_bottom = detail_top + 42
        detail_gap = 6
        detail_width = (x2 - x1 - 24 - detail_gap * 4) / 5
        mod_count = launcher.instance_mod_count(instance) if instance else 0
        memory = (
            int(instance.get("memory", launcher.store.data["settings"].get("memory", 4096)))
            if instance
            else None
        )
        values = (
            ("VERSION", instance.get("version") if instance else "—"),
            ("LOADER", instance.get("loader", "Vanilla") if instance else "—"),
            ("MODS", str(mod_count) if instance else "—"),
            ("RAM", f"{memory} MiB" if memory is not None else "—"),
            (
                "PLAYTIME",
                format_playtime(launcher.instance_playtime_seconds(instance)) if instance else "—",
            ),
        )
        for index, (title, value) in enumerate(values):
            box_x1 = x1 + 12 + index * (detail_width + detail_gap)
            box_x2 = box_x1 + detail_width
            self._rounded_rectangle(
                box_x1,
                detail_top,
                box_x2,
                detail_bottom,
                9,
                fill=DARK_SURFACE,
                outline=BORDER,
                width=1,
            )
            self.create_text(
                box_x1 + 8,
                detail_top + 11,
                text=title,
                fill=MUTED,
                font=self._font(8, "bold"),
                anchor="w",
            )
            self.create_text(
                box_x1 + 8,
                detail_top + 29,
                text=self._clean_text(value, 18),
                fill=TEXT,
                font=self._font(10, "bold"),
                anchor="w",
                width=max(25, detail_width - 14),
            )

        bottom = y2 - 12
        launch_top = bottom - 40
        actions_top = launch_top - 38
        progress_top = actions_top - 28 if self.progress_visible else actions_top
        profile_bottom = progress_top - 6
        profile_top = profile_bottom - 38
        self._rounded_rectangle(
            x1 + 12,
            profile_top,
            x2 - 12,
            profile_bottom,
            9,
            fill=DARK_SURFACE,
            outline=BORDER,
            width=1,
        )
        self.create_text(
            x1 + 21,
            profile_top + 11,
            text="LAUNCH PROFILE",
            fill=MUTED,
            font=self._font(8, "bold"),
            anchor="w",
        )
        profile_text = (
            f"{account['name']}  •  {account_type_label(account)}"
            if account
            else "No active profile — choose an account on the right"
        )
        self.create_text(
            x1 + 21,
            profile_top + 27,
            text=self._clean_text(profile_text, 75),
            fill=TEXT if account else MUTED,
            font=self._font(10, "bold"),
            anchor="w",
            width=max(120, x2 - x1 - 44),
        )

        action_labels = (
            ("Modrinth", launcher.open_modrinth_manager, selected, SURFACE_ALT, SURFACE_HOVER),
            ("Mods Folder", launcher.open_mods_folder, selected, SURFACE_ALT, SURFACE_HOVER),
            (
                "Edit Instance",
                launcher.edit_instance,
                selected and not installing and not running,
                SURFACE_ALT,
                SURFACE_HOVER,
            ),
            (
                "Remove",
                launcher.remove_instance,
                selected and not installing and not running,
                RED,
                RED_HOVER,
            ),
        )
        action_gap = 6
        action_width = (x2 - x1 - 24 - action_gap * 3) / 4
        for index, (label, callback, enabled, fill, hover) in enumerate(action_labels):
            button_x1 = x1 + 12 + index * (action_width + action_gap)
            self._button(
                button_x1,
                actions_top,
                button_x1 + action_width,
                actions_top + 32,
                label,
                callback,
                fill=fill,
                hover=hover,
                enabled=enabled,
            )

        if self.progress_visible:
            percent = int(round(self.progress_value * 100))
            self.create_text(
                x1 + 14,
                progress_top + 8,
                text=self._clean_text(self.progress_message, 70),
                fill=MUTED,
                font=self._font(9),
                anchor="w",
                width=max(120, x2 - x1 - 80),
            )
            self.create_text(
                x2 - 14,
                progress_top + 8,
                text=f"{percent}%",
                fill=TEXT,
                font=self._font(9, "bold"),
                anchor="e",
            )
            bar_y = progress_top + 17
            self._rounded_rectangle(
                x1 + 14, bar_y, x2 - 14, bar_y + 6, 3, fill=CONTROL_SURFACE, outline=""
            )
            if self.progress_value > 0:
                fill_right = x1 + 14 + (x2 - x1 - 28) * self.progress_value
                self._rounded_rectangle(
                    x1 + 14, bar_y, fill_right, bar_y + 6, 3, fill=ACCENT_HOVER, outline=""
                )

        launch_text = (
            "Starting Minecraft…"
            if instance and instance.get("id") in launcher.launching_instances
            else ("Minecraft is running" if running else "Launch Minecraft  ▶")
        )
        self._button(
            x1 + 12,
            launch_top,
            x2 - 12,
            bottom,
            launch_text,
            launcher.launch,
            fill=ACCENT,
            hover=ACCENT_HOVER,
            enabled=can_launch,
            font_size=12,
        )

    def _draw_instances_card(self, x1, y1, x2, y2):
        launcher = self.launcher
        instances = launcher.store.data["instances"]
        self._rounded_rectangle(x1, y1, x2, y2, 16, fill=BBC_CHARCOAL, outline="")
        self.create_text(
            x1 + 18, y1 + 23, text="INSTANCES", fill=TEXT, font=self._font(12, "bold"), anchor="w"
        )
        self.create_text(
            x1 + 18,
            y1 + 47,
            text="Your installed Minecraft environments",
            fill=MUTED,
            font=self._font(10),
            anchor="w",
        )
        self._pill(
            x2 - 194, y1 + 13, x2 - 158, y1 + 38, str(len(instances)), SURFACE_ALT, MUTED, 10
        )
        self._button(
            x2 - 148,
            y1 + 8,
            x2 - 14,
            y1 + 46,
            "＋  Create instance",
            launcher.create_instance,
            font_size=10,
        )
        list_x1, list_x2 = x1 + 10, x2 - 10
        list_y1, list_y2 = y1 + 66, y2 - 10
        if not instances:
            centre_y = (list_y1 + list_y2) / 2
            self.create_text(
                (x1 + x2) / 2, centre_y - 30, text="◇", fill=BORDER, font=self._font(42)
            )
            self.create_text(
                (x1 + x2) / 2,
                centre_y + 9,
                text="No instances yet",
                fill=TEXT,
                font=self._font(18, "bold"),
            )
            self.create_text(
                (x1 + x2) / 2,
                centre_y + 36,
                text="Create your first Minecraft instance to get started.",
                fill=MUTED,
                font=self._font(11),
            )
            self._draw_scrollbar("instances", list_x1, list_y1, list_x2, list_y2, 0, 1)
            return
        visible = max(
            1, int((list_y2 - list_y1 + self.ROW_GAP) // (self.INSTANCE_ROW_HEIGHT + self.ROW_GAP))
        )
        maximum = max(0, len(instances) - visible)
        start = max(0, min(maximum, self._scroll_index["instances"]))
        self._scroll_index["instances"] = start
        content_right = list_x2 - (12 if maximum else 0)
        for visible_index, instance in enumerate(instances[start : start + visible]):
            top = list_y1 + visible_index * (self.INSTANCE_ROW_HEIGHT + self.ROW_GAP)
            bottom = top + self.INSTANCE_ROW_HEIGHT
            selected = instance.get("id") == launcher.selected_instance_id
            fill = SURFACE_HOVER if selected else SURFACE_ALT
            shape = self._rounded_rectangle(
                list_x1,
                top,
                content_right,
                bottom,
                13,
                fill=fill,
                outline=SELECTION if selected else BORDER,
                width=2 if selected else 1,
            )
            hover = "#4c4c4c" if selected else SURFACE_HOVER
            self._register_hit(
                (list_x1, top, content_right, bottom),
                lambda ident=instance.get("id"): launcher.select_instance(ident),
                shape,
                fill,
                hover,
            )
            photo = self._instance_photo(instance, 54)
            if photo:
                self.create_image(list_x1 + 42, top + 43, image=photo)
            else:
                self.create_text(
                    list_x1 + 42,
                    top + 43,
                    text=instance.get("loader", "V")[:1],
                    fill=TEXT,
                    font=self._font(20, "bold"),
                )
            name_x = list_x1 + 82
            self.create_text(
                name_x,
                top + 29,
                text=self._clean_text(instance.get("name"), 45),
                fill=TEXT,
                font=self._font(13, "bold"),
                anchor="w",
                width=max(100, content_right - name_x - 120),
            )
            mod_count = launcher.instance_mod_count(instance)
            mod_suffix = f"  •  {mod_count} mod{'s' if mod_count != 1 else ''}" if mod_count else ""
            detail = f"Minecraft {instance.get('version', 'Unknown')}  •  {instance.get('loader', 'Vanilla')}{mod_suffix}"
            self.create_text(
                name_x,
                top + 56,
                text=self._clean_text(detail, 70),
                fill=MUTED,
                font=self._font(10),
                anchor="w",
                width=max(100, content_right - name_x - 120),
            )
            ready = bool(instance.get("installed"))
            installing = instance.get("id") in launcher.active_installs
            running = (
                instance.get("id") in launcher.running_instances
                or instance.get("id") in launcher.launching_instances
            )
            badge_text = (
                "RUNNING"
                if running
                else ("INSTALLING" if installing else ("READY" if ready else "NOT INSTALLED"))
            )
            badge_fill = (
                GREEN_BG if running or ready else (PROGRESS_STATUS_BG if installing else "#3a3030")
            )
            badge_color = (
                GREEN if running or ready else (PROGRESS_STATUS_TEXT if installing else "#e9a2a2")
            )
            self._pill(
                content_right - 112,
                top + 29,
                content_right - 16,
                top + 57,
                badge_text,
                badge_fill,
                badge_color,
            )
        self._draw_scrollbar(
            "instances", list_x1, list_y1, list_x2, list_y2, len(instances), visible
        )

    def _draw_accounts_card(self, kind, x1, y1, x2, y2):
        launcher = self.launcher
        active = launcher.store.data["settings"].get("active_account", "")
        is_microsoft = kind == "microsoft"
        accounts = active_account_first(
            [
                account
                for account in launcher.store.data["accounts"]
                if (account.get("type") == "Microsoft") == is_microsoft
            ],
            active,
        )
        selected = next(
            (
                account
                for account in launcher.store.data["accounts"]
                if account.get("id") == launcher.selected_account_id
            ),
            None,
        )
        remove_enabled = bool(selected and ((selected.get("type") == "Microsoft") == is_microsoft))
        title = "MICROSOFT PROFILES" if is_microsoft else "OFFLINE ACCOUNTS"
        subtitle = "Authenticated Minecraft accounts" if is_microsoft else "Offline usernames"
        add_text = "＋ Microsoft" if is_microsoft else "＋ Offline"
        add_callback = launcher.add_microsoft if is_microsoft else launcher.add_offline
        empty_title = "No Microsoft accounts" if is_microsoft else "No offline accounts"
        empty_message = (
            "Add an authenticated Minecraft profile."
            if is_microsoft
            else "Add an offline Minecraft username."
        )

        self._rounded_rectangle(x1, y1, x2, y2, 16, fill=BBC_CHARCOAL, outline="")
        self.create_text(
            x1 + 14,
            y1 + 27,
            text=title,
            fill=TEXT,
            font=self._font(10, "bold"),
            anchor="w",
            width=max(80, x2 - x1 - 60),
        )
        self._pill(x2 - 43, y1 + 14, x2 - 14, y1 + 39, str(len(accounts)), SURFACE_ALT, MUTED, 10)
        self.create_text(
            x1 + 14,
            y1 + 55,
            text=subtitle,
            fill=MUTED,
            font=self._font(9),
            anchor="w",
            width=max(100, x2 - x1 - 28),
        )
        button_gap = 8
        button_width = (x2 - x1 - 28 - button_gap) / 2
        self._button(
            x1 + 14, y1 + 76, x1 + 14 + button_width, y1 + 110, add_text, add_callback, font_size=9
        )
        self._button(
            x1 + 14 + button_width + button_gap,
            y1 + 76,
            x2 - 14,
            y1 + 110,
            "Remove",
            launcher.remove_account,
            fill=RED,
            hover=RED_HOVER,
            enabled=remove_enabled,
            font_size=9,
        )

        list_x1, list_x2 = x1 + 10, x2 - 10
        list_y1, list_y2 = y1 + 122, y2 - 10
        if not accounts:
            centre_y = min(list_y1 + 100, (list_y1 + list_y2) / 2)
            self.create_text(
                (x1 + x2) / 2, centre_y - 28, text="◎", fill=BORDER, font=self._font(34)
            )
            self.create_text(
                (x1 + x2) / 2,
                centre_y + 8,
                text=empty_title,
                fill=TEXT,
                font=self._font(12, "bold"),
                width=max(100, x2 - x1 - 30),
            )
            self.create_text(
                (x1 + x2) / 2,
                centre_y + 36,
                text=empty_message,
                fill=MUTED,
                font=self._font(9),
                width=max(100, x2 - x1 - 35),
                justify="center",
            )
            self._draw_scrollbar(kind, list_x1, list_y1, list_x2, list_y2, 0, 1)
            return
        visible = max(
            1, int((list_y2 - list_y1 + self.ROW_GAP) // (self.ACCOUNT_ROW_HEIGHT + self.ROW_GAP))
        )
        maximum = max(0, len(accounts) - visible)
        start = max(0, min(maximum, self._scroll_index[kind]))
        self._scroll_index[kind] = start
        content_right = list_x2 - (12 if maximum else 0)
        for visible_index, account in enumerate(accounts[start : start + visible]):
            top = list_y1 + visible_index * (self.ACCOUNT_ROW_HEIGHT + self.ROW_GAP)
            bottom = top + self.ACCOUNT_ROW_HEIGHT
            row_selected = account.get("id") == launcher.selected_account_id
            is_active = account.get("id") == active
            fill = SURFACE_HOVER if row_selected or is_active else SURFACE_ALT
            border = SELECTION if row_selected else (GREEN_BORDER if is_active else BORDER)
            shape = self._rounded_rectangle(
                list_x1,
                top,
                content_right,
                bottom,
                13,
                fill=fill,
                outline=border,
                width=2 if row_selected else 1,
            )
            self._register_hit(
                (list_x1, top, content_right, bottom),
                lambda ident=account.get("id"): launcher.select_account(ident),
                shape,
                fill,
                "#4c4c4c",
            )
            avatar_size = 38
            photo = self._account_photo(account, avatar_size)
            avatar_x = list_x1 + 30
            avatar_y = top + 29
            if photo:
                self.create_image(avatar_x, avatar_y, image=photo)
            else:
                self._rounded_rectangle(
                    avatar_x - 19,
                    avatar_y - 19,
                    avatar_x + 19,
                    avatar_y + 19,
                    10,
                    fill="#5c5c5c",
                    outline="",
                )
                self.create_text(
                    avatar_x,
                    avatar_y,
                    text=str(account.get("name") or "?")[:1].upper(),
                    fill=TEXT,
                    font=self._font(16, "bold"),
                )
            text_x = list_x1 + 57
            self.create_text(
                text_x,
                top + 20,
                text=self._clean_text(account.get("name"), 24),
                fill=TEXT,
                font=self._font(11, "bold"),
                anchor="w",
                width=max(60, content_right - text_x - 8),
            )
            self.create_text(
                text_x,
                top + 43,
                text=account_type_label(account),
                fill=MUTED,
                font=self._font(9),
                anchor="w",
                width=max(60, content_right - text_x - 8),
            )
            if is_active:
                self._pill(
                    list_x1 + 10,
                    top + 64,
                    content_right - 10,
                    top + 91,
                    "✓  ACTIVE",
                    GREEN_BG,
                    GREEN,
                    8,
                )
            else:
                self._button(
                    list_x1 + 10,
                    top + 62,
                    content_right - 10,
                    top + 92,
                    "Use this account",
                    lambda ident=account.get("id"): launcher.set_active_account(ident),
                    fill=CONTROL_SURFACE,
                    hover=ACCENT_HOVER,
                    font_size=8,
                )
        self._draw_scrollbar(kind, list_x1, list_y1, list_x2, list_y2, len(accounts), visible)


class ModrinthCanvasList(tk.Frame):
    """A single-surface mod list that avoids nested Tk windows while scrolling.

    CTkScrollableFrame places a real child window inside a canvas for every
    frame, label and button.  On Windows those child windows can be exposed at
    different times during a fast scrollbar drag, leaving fragments of old
    rows behind.  This list paints each page onto one native canvas instead.
    """

    def __init__(self, master, launcher):
        super().__init__(master=master, bg=DARK_SURFACE, bd=0, highlightthickness=0)
        self.launcher = launcher
        self.mode = "empty"
        self.payload = []
        self.installed = {}
        self.empty_title = ""
        self.empty_message = ""
        self.generation = 0
        self._redraw_after_id = None
        self._reset_on_redraw = False
        self._action_number = 0
        self._photos = {}
        self._avatar_items = {}

        self.canvas = tk.Canvas(
            self,
            bg=DARK_SURFACE,
            bd=0,
            highlightthickness=0,
            relief="flat",
            yscrollincrement=24,
        )
        self.scrollbar = ctk.CTkScrollbar(
            self,
            orientation="vertical",
            command=self.canvas.yview,
            width=13,
            fg_color=DARK_SURFACE,
            button_color=CONTROL_SURFACE,
            button_hover_color=ACCENT_HOVER,
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y", padx=(3, 1), pady=2)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_configure, add="+")
        self.canvas.bind("<MouseWheel>", self._on_mousewheel, add="+")
        self.canvas.bind("<Button-4>", lambda _event: self._scroll_units(-3), add="+")
        self.canvas.bind("<Button-5>", lambda _event: self._scroll_units(3), add="+")

    def destroy(self):
        if self._redraw_after_id is not None:
            try:
                self.after_cancel(self._redraw_after_id)
            except tk.TclError:
                pass
            self._redraw_after_id = None
        super().destroy()

    def _on_mousewheel(self, event):
        if not event.delta:
            return None
        steps = (
            -int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
        )
        self._scroll_units(steps * 3)
        return "break"

    def _scroll_units(self, units):
        try:
            self.canvas.yview_scroll(int(units), "units")
        except tk.TclError:
            pass
        return "break"

    def yview_moveto(self, fraction):
        self.canvas.yview_moveto(fraction)

    def _on_canvas_configure(self, _event=None):
        self.schedule_redraw()

    def schedule_redraw(self, reset=False):
        self._reset_on_redraw = self._reset_on_redraw or reset
        if self._redraw_after_id is not None:
            return
        moving = bool(getattr(self.winfo_toplevel(), "_window_motion_active", False))
        self._redraw_after_id = self.after(70 if moving else 24, self._scheduled_redraw)

    def _scheduled_redraw(self):
        self._redraw_after_id = None
        if bool(getattr(self.winfo_toplevel(), "_window_motion_active", False)):
            self._redraw_after_id = self.after(70, self._scheduled_redraw)
            return
        reset = self._reset_on_redraw
        self._reset_on_redraw = False
        self.redraw(reset=reset)

    def show_empty(self, title, message, reset=True):
        self.mode = "empty"
        self.payload = []
        self.installed = {}
        self.empty_title = str(title)
        self.empty_message = str(message)
        self._photos = {}
        self.redraw(reset=reset)

    def show_browse(self, projects, installed, generation):
        self.mode = "browse"
        self.payload = list(projects)
        self.installed = dict(installed)
        self.generation = generation
        self._photos = {}
        self.redraw(reset=True)

    def show_installed(self, records, updates):
        self.mode = "installed"
        self.payload = list(records)
        self.installed = dict(updates)
        self._photos = {}
        self.redraw(reset=True)

    def show_updates(self, updates):
        self.mode = "updates"
        self.payload = list(updates)
        self.installed = {}
        self._photos = {}
        self.redraw(reset=True)

    def set_icon(self, key, image, generation):
        if self.mode != "browse" or generation != self.generation:
            return
        try:
            photo = ImageTk.PhotoImage(image=image, master=self.canvas)
            self._photos[key] = photo
            image_item, fallback_item = self._avatar_items.get(key, (None, None))
            if image_item is not None:
                self.canvas.itemconfigure(image_item, image=photo)
                self.canvas.itemconfigure(fallback_item, state="hidden")
        except (RuntimeError, tk.TclError):
            pass

    @staticmethod
    def _clean_text(value, limit=180):
        text = " ".join(str(value or "").split())
        return text if len(text) <= limit else text[: max(1, limit - 1)].rstrip() + "…"

    def _rounded_rectangle(self, x1, y1, x2, y2, radius, **kwargs):
        radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
        points = (
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        )
        return self.canvas.create_polygon(points, smooth=True, splinesteps=18, **kwargs)

    def _button(
        self,
        x1,
        y1,
        x2,
        y2,
        text,
        callback,
        fill=ACCENT,
        hover=ACCENT_HOVER,
        text_color=TEXT,
        font_size=10,
    ):
        self._action_number += 1
        tag = f"mod-action-{self._action_number}"
        shape = self._rounded_rectangle(x1, y1, x2, y2, 8, fill=fill, outline="", tags=(tag,))
        self.canvas.create_text(
            (x1 + x2) / 2,
            (y1 + y2) / 2,
            text=text,
            fill=text_color,
            font=(self.launcher.ui_font, font_size, "bold"),
            tags=(tag,),
        )

        def enter(_event):
            self.canvas.itemconfigure(shape, fill=hover)
            self.canvas.configure(cursor="hand2")

        def leave(_event):
            self.canvas.itemconfigure(shape, fill=fill)
            self.canvas.configure(cursor="")

        def invoke(_event):
            callback()
            return "break"

        self.canvas.tag_bind(tag, "<Enter>", enter)
        self.canvas.tag_bind(tag, "<Leave>", leave)
        self.canvas.tag_bind(tag, "<ButtonRelease-1>", invoke)

    def _pill(self, x1, y1, x2, y2, text, fill, text_color, font_size=9):
        self._rounded_rectangle(x1, y1, x2, y2, 8, fill=fill, outline="")
        self.canvas.create_text(
            (x1 + x2) / 2,
            (y1 + y2) / 2,
            text=text,
            fill=text_color,
            font=(self.launcher.ui_font, font_size, "bold"),
        )

    def redraw(self, reset=False):
        try:
            old_fraction = 0.0 if reset else self.canvas.yview()[0]
        except (IndexError, tk.TclError):
            old_fraction = 0.0
        width = max(520, self.canvas.winfo_width())
        height = max(180, self.canvas.winfo_height())
        self.canvas.delete("all")
        self._action_number = 0
        self._avatar_items = {}

        if self.mode == "browse":
            content_height = self._draw_browse(width)
        elif self.mode == "installed":
            content_height = self._draw_installed(width)
        elif self.mode == "updates":
            content_height = self._draw_updates(width)
        else:
            content_height = self._draw_empty(width, height)

        self.canvas.configure(scrollregion=(0, 0, width, max(height, content_height)))
        self.canvas.yview_moveto(0.0 if reset else old_fraction)

    def _draw_empty(self, width, height):
        centre_y = max(86, height / 2 - 20)
        self.canvas.create_text(
            width / 2, centre_y - 35, text="◇", fill=BORDER, font=(self.launcher.ui_font, 38)
        )
        self.canvas.create_text(
            width / 2,
            centre_y + 4,
            text=self.empty_title,
            fill=TEXT,
            font=(self.launcher.ui_font, 18, "bold"),
        )
        self.canvas.create_text(
            width / 2,
            centre_y + 34,
            text=self.empty_message,
            fill=MUTED,
            font=(self.launcher.ui_font, 11),
            width=min(560, width - 60),
            justify="center",
        )
        return height

    def _draw_browse(self, width):
        row_height = 100
        gap = 10
        right = width - 8
        action_left = right - 104
        text_right = action_left - 14
        for index, project in enumerate(self.payload):
            top = 5 + index * (row_height + gap)
            bottom = top + row_height
            self._rounded_rectangle(
                4, top, right, bottom, 13, fill=SURFACE_ALT, outline=BORDER, width=1
            )

            project_id = str(project.get("project_id", ""))
            key = project_id or f"project-{index}"
            title = self._clean_text(project.get("title", "Unknown project"), 80)
            self._rounded_rectangle(
                16, top + 20, 72, top + 76, 11, fill=CONTROL_SURFACE, outline=""
            )
            image_item = self.canvas.create_image(44, top + 48)
            fallback_item = self.canvas.create_text(
                44,
                top + 48,
                text=(title[:1] or "M").upper(),
                fill=TEXT,
                font=(self.launcher.ui_font, 20, "bold"),
            )
            self._avatar_items[key] = (image_item, fallback_item)
            if key in self._photos:
                self.canvas.itemconfigure(image_item, image=self._photos[key])
                self.canvas.itemconfigure(fallback_item, state="hidden")

            text_left = 88
            self.canvas.create_text(
                text_left,
                top + 15,
                text=title,
                fill=TEXT,
                font=(self.launcher.ui_font, 14, "bold"),
                anchor="nw",
                width=max(120, text_right - text_left),
            )
            try:
                downloads = int(project.get("downloads", 0))
            except (TypeError, ValueError):
                downloads = 0
            byline = f"by {self._clean_text(project.get('author', 'Unknown'), 45)}  •  {downloads:,} downloads"
            self.canvas.create_text(
                text_left,
                top + 40,
                text=byline,
                fill=MUTED,
                font=(self.launcher.ui_font, 10),
                anchor="nw",
                width=max(120, text_right - text_left),
            )
            description = self._clean_text(project.get("description", ""), 170)
            self.canvas.create_text(
                text_left,
                top + 61,
                text=description,
                fill=MUTED,
                font=(self.launcher.ui_font, 10),
                anchor="nw",
                width=max(120, text_right - text_left),
            )

            record = self.installed.get(project_id)
            if record:
                self._pill(
                    action_left, top + 16, right - 8, top + 48, "✓ INSTALLED", GREEN_BG, GREEN
                )
            else:
                self._button(
                    action_left,
                    top + 16,
                    right - 8,
                    top + 50,
                    "Install",
                    lambda item=project: self.launcher.install_modrinth_project(item),
                )
            slug = project.get("slug") or project_id
            self._button(
                action_left,
                top + 57,
                right - 8,
                top + 87,
                "View page",
                lambda value=slug: self.launcher.open_external_url(
                    f"https://modrinth.com/mod/{value}", "Modrinth project"
                ),
                fill=SURFACE_HOVER,
            )
        return 10 + len(self.payload) * (row_height + gap)

    def _draw_installed(self, width):
        row_height = 78
        gap = 10
        right = width - 8
        for index, record in enumerate(self.payload):
            top = 5 + index * (row_height + gap)
            bottom = top + row_height
            self._rounded_rectangle(
                4, top, right, bottom, 13, fill=SURFACE_ALT, outline=BORDER, width=1
            )
            record_id = record.get("record_id") or record.get("project_id")
            update = self.installed.get(record_id)
            actions = []
            if update:
                actions.append(
                    (
                        "Update",
                        lambda item=record: self.launcher.update_modrinth_project(item),
                        ACCENT,
                        ACCENT_HOVER,
                        78,
                    )
                )
            state_text = "Disable" if record.get("enabled", True) else "Enable"
            state_fill = SURFACE_HOVER if record.get("enabled", True) else GREEN_BG
            actions.append(
                (
                    state_text,
                    lambda item=record: self.launcher.toggle_modrinth_record(item),
                    state_fill,
                    ACCENT_HOVER,
                    76,
                )
            )
            if record.get("manual"):
                actions.append(
                    (
                        "Remove",
                        lambda item=record: self.launcher.confirm_remove_modrinth(item),
                        SURFACE_HOVER,
                        RED_HOVER,
                        78,
                    )
                )

            action_width = sum(item[4] for item in actions) + max(0, len(actions) - 1) * 6
            if not record.get("manual"):
                action_width += 94
            action_left = right - 12 - action_width
            text_left = 18
            text_width = max(140, action_left - text_left - 12)
            title = self._clean_text(record.get("title", record_id), 90)
            self.canvas.create_text(
                text_left,
                top + 15,
                text=title,
                fill=TEXT,
                font=(self.launcher.ui_font, 14, "bold"),
                anchor="nw",
                width=text_width,
            )
            provider = {
                "modrinth": "Modrinth",
                "meteor": "Meteor official",
                "github": "GitHub",
                "local": "Local file — update source unknown",
            }.get(record.get("provider"), "Local file")
            role = (
                "Installed directly"
                if record.get("manual", True)
                else f"Required dependency for {len(record.get('required_by', []))} mod(s)"
            )
            detail = self._clean_text(
                f"{record.get('version_number', 'Unknown version')}  •  {provider}  •  {role}  •  {record.get('filename', '')}",
                170,
            )
            self.canvas.create_text(
                text_left,
                top + 43,
                text=detail,
                fill=MUTED,
                font=(self.launcher.ui_font, 10),
                anchor="nw",
                width=text_width,
            )

            x = action_left
            for label, callback, fill, hover, button_width in actions:
                self._button(
                    x, top + 23, x + button_width, top + 57, label, callback, fill=fill, hover=hover
                )
                x += button_width + 6
            if not record.get("manual"):
                self._pill(x, top + 25, x + 88, top + 55, "DEPENDENCY", CONTROL_SURFACE, MUTED)
        return 10 + len(self.payload) * (row_height + gap)

    def _draw_updates(self, width):
        row_height = 76
        gap = 10
        right = width - 8
        for index, item in enumerate(self.payload):
            record = item["record"]
            version = item["version"]
            top = 5 + index * (row_height + gap)
            bottom = top + row_height
            self._rounded_rectangle(
                4, top, right, bottom, 13, fill=SURFACE_ALT, outline=BORDER, width=1
            )
            title = self._clean_text(
                record.get("title", record.get("record_id", record.get("project_id", "mod"))), 90
            )
            self.canvas.create_text(
                18,
                top + 15,
                text=title,
                fill=TEXT,
                font=(self.launcher.ui_font, 14, "bold"),
                anchor="nw",
                width=max(160, width - 140),
            )
            detail = f"{record.get('version_number', 'Unknown')}  →  {version.get('version_number', version.get('name', 'Latest'))}"
            self.canvas.create_text(
                18,
                top + 43,
                text=detail,
                fill=MUTED,
                font=(self.launcher.ui_font, 10),
                anchor="nw",
                width=max(160, width - 140),
            )
            self._button(
                right - 96,
                top + 21,
                right - 12,
                top + 55,
                "Update",
                lambda value=record: self.launcher.update_modrinth_project(value),
            )
        return 10 + len(self.payload) * (row_height + gap)


def install_ctk_resize_coalescing():
    """Coalesce CustomTkinter canvas redraws during live window resizing."""
    base_class = ctk.CTkBaseClass
    if getattr(base_class, "_breakblocks_resize_coalescing", False):
        return

    def coalesced_dimensions_event(widget, event):
        width = widget._reverse_widget_scaling(event.width)
        height = widget._reverse_widget_scaling(event.height)
        if round(widget._current_width) == round(width) and round(widget._current_height) == round(
            height
        ):
            return
        widget._current_width = width
        widget._current_height = height
        try:
            toplevel = widget.winfo_toplevel()
            queue_draw = getattr(toplevel, "queue_ctk_resize_draw", None)
            if callable(queue_draw) and hasattr(toplevel, "_ctk_resize_widgets"):
                queue_draw(widget)
                return
        except tk.TclError:
            return
        widget._draw(no_color_updates=True)

    base_class._update_dimensions_event = coalesced_dimensions_event
    base_class._breakblocks_resize_coalescing = True


install_ctk_resize_coalescing()


def log_launcher_message(scope, message):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {scope}: {message}", file=sys.stderr, flush=True)


def log_launcher_error(scope, error):
    log_launcher_message(scope, f"{type(error).__name__}: {error}")
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


class Store:
    DEFAULT_SETTINGS = {
        "theme": "dark",
        "java": "auto",
        "memory": 4096,
        "keep_launcher_open": True,
        "update_enabled": True,
        "update_channel": DEFAULT_UPDATE_CHANNEL,
        "update_frequency": "daily",
        "last_update_check": 0,
        "chat_browser_defaults_version": 1,
        "legal_notice_version": 0,
    }

    def __init__(self):
        self._save_lock = threading.RLock()
        if os.name == "nt":
            base = pathlib.Path(
                os.environ.get("LOCALAPPDATA", pathlib.Path.home() / "AppData/Local")
            )
            preferred_root = base / APP_NAME
            legacy_root = base / "Zazu Launcher"
        else:
            base = pathlib.Path(
                os.environ.get("XDG_DATA_HOME", pathlib.Path.home() / ".local/share")
            )
            preferred_root = base / "breakblocks-launcher"
            legacy_root = base / "zazu-launcher"
        # Existing users keep their instances and accounts without a risky move.
        # New installations use the rebranded data directory.
        self.root = (
            legacy_root if legacy_root.exists() and not preferred_root.exists() else preferred_root
        )
        self.instances = self.root / "instances"
        self.file = self.root / "launcher.json"
        self.instances.mkdir(parents=True, exist_ok=True)
        for directory in (self.root, self.instances):
            try:
                os.chmod(directory, 0o700)
            except OSError:
                pass
        try:
            self.data = json.loads(self.file.read_text(encoding="utf-8"))
        except Exception:
            self.data = {
                "accounts": [],
                "instances": [],
                "settings": dict(self.DEFAULT_SETTINGS),
            }
        self.data.setdefault("accounts", [])
        self.data.setdefault("instances", [])
        self.data.setdefault("settings", {})
        settings = self.data["settings"]
        migrate_chat_browser = settings.get("chat_browser_defaults_version") != 1
        for key, value in self.DEFAULT_SETTINGS.items():
            settings.setdefault(key, value)
        migrated = False
        if migrate_chat_browser:
            for obsolete_key in (
                "irc_host",
                "irc_port",
                "irc_tls",
                "irc_channel",
                "irc_nickname",
                "irc_server_password",
                "irc_connect_on_startup",
                "irc_notification_sound",
                "irc_show_formatting",
                "irc_defaults_version",
            ):
                settings.pop(obsolete_key, None)
            settings["chat_browser_defaults_version"] = 1
            migrated = True
        for account in self.data["accounts"]:
            if account.get("type") != "Microsoft" and account.get("type") != "Offline":
                account["type"] = "Offline"
                migrated = True
            if (
                account.get("type") == "Microsoft"
                and not account.get("entitlement_verified_at")
                and account.get("minecraft_token")
                and account.get("refresh_token")
            ):
                # Microsoft profiles saved by earlier releases already passed
                # minecraft_profile(), including its entitlement request. Keep
                # those legitimate users from having to sign in again solely
                # because the proof timestamp is new in 0.9.1.
                account["entitlement_verified_at"] = int(time.time())
                migrated = True
        for instance in self.data["instances"]:
            if instance.get("icon") not in BLOCK_ICON_KEYS | {"custom"}:
                instance["icon"] = default_instance_icon(
                    instance.get("id", instance.get("name", "instance"))
                )
                migrated = True
            try:
                playtime = max(0, int(float(instance.get("playtime_seconds", 0))))
            except (TypeError, ValueError):
                playtime = 0
            if instance.get("playtime_seconds") != playtime:
                instance["playtime_seconds"] = playtime
                migrated = True
        if migrated:
            self.save()

    def save(self):
        with self._save_lock:
            # Playtime can be written by a hidden watcher after the visible
            # launcher has been reopened. Preserve the highest persisted value
            # whenever either process saves other launcher settings.
            try:
                persisted = json.loads(self.file.read_text(encoding="utf-8"))
                persisted_instances = {
                    item.get("id"): item
                    for item in persisted.get("instances", [])
                    if isinstance(item, dict) and item.get("id")
                }
                for instance in self.data.get("instances", []):
                    previous = persisted_instances.get(instance.get("id"), {})
                    try:
                        current_playtime = int(float(instance.get("playtime_seconds", 0)))
                    except (TypeError, ValueError):
                        current_playtime = 0
                    try:
                        previous_playtime = int(float(previous.get("playtime_seconds", 0)))
                    except (TypeError, ValueError):
                        previous_playtime = 0
                    instance["playtime_seconds"] = max(0, current_playtime, previous_playtime)
                    try:
                        current_last_played = int(float(instance.get("last_played_at", 0)))
                    except (TypeError, ValueError):
                        current_last_played = 0
                    try:
                        previous_last_played = int(float(previous.get("last_played_at", 0)))
                    except (TypeError, ValueError):
                        previous_last_played = 0
                    latest_played = max(current_last_played, previous_last_played)
                    if latest_played:
                        instance["last_played_at"] = latest_played
            except (OSError, ValueError, TypeError, AttributeError):
                pass
            temporary = self.file.with_name(
                f".{self.file.name}.{os.getpid()}.{threading.get_ident()}.tmp"
            )
            try:
                temporary.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
                try:
                    os.chmod(temporary, 0o600)
                except OSError:
                    pass
                os.replace(temporary, self.file)
            finally:
                temporary.unlink(missing_ok=True)


class Launcher(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        if sys.platform.startswith("linux"):
            super().__init__(fg_color=BG, className="BreakBlocksLauncher")
        else:
            super().__init__(fg_color=BG)
        self.store = Store()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1280x760")
        self.minsize(1200, 650)
        self.brand_logo_path = APP_DIR / "assets" / "branding" / "breakblocks_launcher_icon.png"
        self.brand_icon_path = APP_DIR / "assets" / "branding" / "breakblocks_launcher.ico"
        self.brand_wordmark_path = (
            APP_DIR / "assets" / "branding" / "breakblocks_original_logo_stacked.png"
        )
        self.window_icon = None
        self.brand_wordmark_image = None
        self.brand_wordmark_photo = None
        self.brand_wordmark_label = None
        self.window_motion_after_id = None
        self.apply_app_branding()

        families = set(tkfont.families())
        if sys.platform.startswith("linux") and "CustomTkinter_shapes_font" not in families:
            # Missing shape fonts otherwise appear as literal glyphs around controls.
            DrawEngine.preferred_drawing_method = "polygon_shapes"
        preferred_ui_fonts = (
            ("Ubuntu Sans", "Ubuntu", "Noto Sans", "DejaVu Sans", "Inter", "Carlito")
            if sys.platform.startswith("linux")
            else ("Segoe UI", "Calibri", "Carlito", "Noto Sans", "DejaVu Sans")
        )
        self.ui_font = next(
            (name for name in preferred_ui_fonts if name in families),
            "TkDefaultFont",
        )
        for named_font in (
            "TkDefaultFont",
            "TkTextFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkCaptionFont",
            "TkSmallCaptionFont",
        ):
            try:
                tkfont.nametofont(named_font, root=self).configure(family=self.ui_font)
            except tk.TclError:
                pass
        try:
            resolved_ui_font = tkfont.Font(root=self, family=self.ui_font, size=12).actual("family")
        except tk.TclError:
            resolved_ui_font = self.ui_font
        log_launcher_message(
            "UI font",
            f"requested={self.ui_font}; resolved={resolved_ui_font}; platform={sys.platform}",
        )
        linux_font_adjustment = 1 if sys.platform.startswith("linux") else 0
        self.font_title = ctk.CTkFont(self.ui_font, 28, "bold")
        self.font_heading = ctk.CTkFont(self.ui_font, 19, "bold")
        self.font_body = ctk.CTkFont(self.ui_font, 13 + linux_font_adjustment)
        self.font_small = ctk.CTkFont(self.ui_font, 11 + linux_font_adjustment)
        self.font_button = ctk.CTkFont(self.ui_font, 12 + linux_font_adjustment, "bold")

        self.selected_instance_id = None
        self.selected_account_id = None
        self.active_installs = set()
        self.nav_buttons = {}
        self.pages = {}
        self.current_page = None
        self.mod_context = None
        self.mod_page_active = False
        self.mod_search_generation = 0
        self.mod_search_running = False
        self.mod_search_started = 0.0
        self.mod_active_tab = None
        self.mod_updates_checked = False
        self.mod_scroll_bindings = []
        self.modrinth_images = []
        self.modrinth_updates = {}
        self.update_install_type = launcher_update.detect_install_type(APP_DIR)
        self.update_client = launcher_update.UpdateClient(
            APP_VERSION,
            platform_key=launcher_update.platform_key_for_install_type(self.update_install_type),
        )
        self.available_update = None
        self.update_check_running = False
        self.chat_browser_process = None
        self.chat_browser_monitor_id = None
        self.chat_browser_shutdown_file = None
        chat_profile = self.store.root / chat_browser.PROFILE_DIRECTORY_NAME
        self.chat_unread_file = chat_profile / chat_browser.UNREAD_FILE_NAME
        self.chat_visible_file = chat_profile / chat_browser.VISIBLE_FILE_NAME
        self.chat_game_file = chat_profile / chat_browser.GAME_PROCESS_FILE_NAME
        self.overlay_game_pids = {}
        self.chat_game_file.unlink(missing_ok=True)
        self.chat_unread_count = chat_browser.write_unread_count(self.chat_unread_file, 0)
        self.chat_visible_file.unlink(missing_ok=True)
        self.chat_unread_badge = None
        self.chat_context_menu = None
        self.ui_events = queue.Queue()
        self.store_lock = threading.RLock()
        self.running_instances = {}
        self.launching_instances = set()
        self.closing = False
        self._window_motion_active = False
        self._window_motion_last = 0.0
        self._ctk_resize_widgets = weakref.WeakSet()
        self._ctk_resize_after_id = None
        self._modal_windows = weakref.WeakSet()
        self._modal_input_block_until = 0.0

        self.build()
        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self.close_launcher)
        self.bind("<Configure>", self.on_window_configure, add="+")
        self.after(50, self.drain_ui_events)
        self.after(250, self.show_first_run_legal_notice)
        self.after(1800, self.check_updates_on_schedule)
        self.after(30000, self.refresh_playtime_clock)

    def apply_app_branding(self):
        """Apply the BBC Chicken window icon and load the sidebar wordmark."""
        if os.name == "nt":
            try:
                import ctypes

                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "BreakBlocks.Launcher"
                )
                if self.brand_icon_path.is_file():
                    self.iconbitmap(default=str(self.brand_icon_path))
            except Exception as error:
                log_launcher_message("Branding", f"Windows icon setup skipped: {error}")
        try:
            self.window_icon = tk.PhotoImage(file=str(self.brand_logo_path))
            self.iconphoto(True, self.window_icon)
        except Exception as error:
            log_launcher_message("Branding", f"Logo setup skipped: {error}")
        try:
            self.brand_wordmark_image = load_brand_wordmark(self.brand_wordmark_path)
        except Exception as error:
            log_launcher_message("Branding", f"Sidebar wordmark setup skipped: {error}")

    def on_window_configure(self, event):
        """Mark a native move/resize without creating a timer per OS event."""
        if event.widget is not self or self.closing:
            return
        self._window_motion_last = time.monotonic()
        if not self._window_motion_active:
            self._window_motion_active = True
        if self.window_motion_after_id is None:
            self.window_motion_after_id = self.after(70, self.finish_window_motion)

    def finish_window_motion(self):
        self.window_motion_after_id = None
        if self.closing:
            return
        quiet_for = time.monotonic() - self._window_motion_last
        required_quiet = WINDOW_MOTION_IDLE_MS / 1000
        if quiet_for < required_quiet:
            delay = max(20, int((required_quiet - quiet_for) * 1000))
            self.window_motion_after_id = self.after(delay, self.finish_window_motion)
            return
        self._window_motion_active = False
        if self._ctk_resize_after_id is not None:
            try:
                self.after_cancel(self._ctk_resize_after_id)
            except tk.TclError:
                pass
            self._ctk_resize_after_id = None
        self.flush_ctk_resize_draws(force=True)

    def queue_ctk_resize_draw(self, widget):
        """Keep only the newest pending draw for each resized CTk widget."""
        if self.closing:
            return
        self._ctk_resize_widgets.add(widget)
        if self._ctk_resize_after_id is None:
            self._ctk_resize_after_id = self.after(CTK_RESIZE_FRAME_MS, self.flush_ctk_resize_draws)

    def flush_ctk_resize_draws(self, force=False):
        self._ctk_resize_after_id = None
        if self._window_motion_active and not force:
            self._ctk_resize_after_id = self.after(CTK_RESIZE_FRAME_MS, self.flush_ctk_resize_draws)
            return
        widgets = sorted(tuple(self._ctk_resize_widgets), key=lambda item: str(item).count("."))
        self._ctk_resize_widgets.clear()
        for widget in widgets:
            try:
                if widget.winfo_exists():
                    widget._draw(no_color_updates=True)
            except (AttributeError, RuntimeError, tk.TclError):
                pass
        if self._ctk_resize_widgets and not self.closing:
            self._ctk_resize_after_id = self.after(CTK_RESIZE_FRAME_MS, self.flush_ctk_resize_draws)

    def post_ui(self, callback):
        """Safely pass work from a background thread to Tk's main thread."""
        self.ui_events.put(callback)

    def drain_ui_events(self):
        deadline = time.perf_counter() + UI_EVENT_TIME_BUDGET_SECONDS
        processed = 0
        while processed < UI_EVENT_BATCH_LIMIT and time.perf_counter() < deadline:
            try:
                callback = self.ui_events.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception as error:
                log_launcher_error("UI event failed", error)
            processed += 1
        try:
            if self.winfo_exists():
                self.after(16 if not self.ui_events.empty() else 50, self.drain_ui_events)
        except tk.TclError:
            pass

    def close_launcher(self):
        """Close the window while launch watchers finish tracking game time."""
        self.closing = True
        self.stop_chat_browser()
        self.chat_game_file.unlink(missing_ok=True)
        if self.window_motion_after_id is not None:
            try:
                self.after_cancel(self.window_motion_after_id)
            except tk.TclError:
                pass
            self.window_motion_after_id = None
        if self._ctk_resize_after_id is not None:
            try:
                self.after_cancel(self._ctk_resize_after_id)
            except tk.TclError:
                pass
            self._ctk_resize_after_id = None
        self._ctk_resize_widgets.clear()
        self.destroy()

    def instance_playtime_seconds(self, instance):
        try:
            total = max(0, int(float(instance.get("playtime_seconds", 0))))
        except (TypeError, ValueError):
            total = 0
        started = self.running_instances.get(instance.get("id"))
        if started is not None:
            total += max(0, int(time.monotonic() - started))
        return total

    def refresh_playtime_clock(self):
        if self.closing:
            return
        try:
            if self.running_instances:
                self.refresh_launch_summary()
            self.after(30000, self.refresh_playtime_clock)
        except tk.TclError:
            pass

    def write_chat_game_processes(self):
        """Share only Minecraft process IDs with the Windows chat helper."""
        if os.name != "nt":
            return
        self.chat_game_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.chat_game_file.with_name(f".{self.chat_game_file.name}.{os.getpid()}.tmp")
        temporary.write_text(
            "".join(f"{pid}\n" for pid in self.overlay_game_pids.values()), encoding="ascii"
        )
        os.replace(temporary, self.chat_game_file)

    def mark_instance_running(self, ident, started, pid=None):
        self.launching_instances.discard(ident)
        self.running_instances[ident] = started
        if os.name == "nt" and pid is not None:
            self.overlay_game_pids[ident] = pid
            self.write_chat_game_processes()
            self.ensure_chat_browser()
        self.refresh_instances()
        if not self.store.data["settings"].get("keep_launcher_open", True):
            self.iconify()

    def record_instance_playtime(self, ident, elapsed, launched_at):
        seconds = max(1, int(round(elapsed)))
        with self.store_lock:
            # A closed launcher can remain in the background solely to watch
            # Minecraft. Merge the newest file first so a reopened launcher is
            # never overwritten with that watcher's older in-memory snapshot.
            try:
                latest = json.loads(self.store.file.read_text())
                if isinstance(latest, dict) and isinstance(latest.get("instances"), list):
                    self.store.data = latest
            except (AttributeError, OSError, ValueError, TypeError):
                pass
            instance = next(
                (item for item in self.store.data["instances"] if item.get("id") == ident), None
            )
            if not instance:
                return
            try:
                previous = max(0, int(float(instance.get("playtime_seconds", 0))))
            except (TypeError, ValueError):
                previous = 0
            instance["playtime_seconds"] = previous + seconds
            instance["last_played_at"] = int(launched_at)
            self.store.save()

    def finish_instance_session(self, ident, elapsed, exit_code=0, crash_report=None):
        self.running_instances.pop(ident, None)
        if self.overlay_game_pids.pop(ident, None) is not None:
            self.write_chat_game_processes()
        self.launching_instances.discard(ident)
        self.refresh_instances()
        if not self.store.data["settings"].get("keep_launcher_open", True):
            self.deiconify()
            self.lift()
        clean_shutdown = bool(
            exit_code
            and crash_report is None
            and minecraft_backend.launch_log_indicates_clean_shutdown(self.store.instances / ident)
        )
        if crash_report is not None or (exit_code and not clean_shutdown):
            self.status.set(f"Minecraft crashed — exit code {exit_code}")
            self.show_minecraft_crash(ident, exit_code, crash_report)
        else:
            self.status.set(f"Minecraft closed — added {format_playtime(elapsed)} of playtime")

    def show_minecraft_crash(self, ident, exit_code, crash_report=None):
        instance = next(
            (item for item in self.store.data["instances"] if item.get("id") == ident),
            {"name": "Minecraft"},
        )
        instance_root = self.store.instances / ident
        report_path = pathlib.Path(crash_report) if crash_report else None
        if report_path is not None and not report_path.is_file():
            report_path = None
        evidence_path = report_path or (instance_root / "latest-launch.log")
        crash_folder = instance_root / "minecraft" / "crash-reports"
        report_description = (
            f"Minecraft created {report_path.name}."
            if report_path is not None
            else "Minecraft did not create a crash report, so the latest launch log will be used."
        )

        window, body = self.make_dialog("Minecraft crashed", 660, 340)
        ctk.CTkLabel(
            body,
            text="!",
            width=45,
            height=45,
            corner_radius=22,
            fg_color="#4a2328",
            text_color=RED,
            font=ctk.CTkFont(self.ui_font, 20, "bold"),
        ).pack(pady=(24, 9))
        ctk.CTkLabel(
            body,
            text=f"{instance.get('name', 'Minecraft')} crashed",
            text_color=TEXT,
            font=self.font_heading,
        ).pack()
        ctk.CTkLabel(
            body,
            text=f"The game exited with code {exit_code}. {report_description}",
            text_color=MUTED,
            font=self.font_small,
            wraplength=570,
            justify="center",
        ).pack(padx=30, pady=(8, 18))

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.pack()
        button_options = {
            "height": 38,
            "corner_radius": 9,
            "font": self.font_small,
        }
        ctk.CTkButton(
            actions,
            text="View report",
            command=lambda: self.show_report_viewer(evidence_path),
            width=120,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            state="normal" if evidence_path.is_file() else "disabled",
            **button_options,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            actions,
            text="Open crash folder",
            command=lambda: self.open_local_folder(crash_folder, "crash reports folder"),
            width=145,
            fg_color=CONTROL_SURFACE,
            hover_color=SURFACE_HOVER,
            **button_options,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            actions,
            text="Copy report",
            command=lambda: self.copy_report(evidence_path),
            width=120,
            fg_color=CONTROL_SURFACE,
            hover_color=SURFACE_HOVER,
            state="normal" if evidence_path.is_file() else "disabled",
            **button_options,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            body,
            text="Close",
            command=window.destroy,
            width=105,
            height=38,
            corner_radius=9,
            fg_color=RED,
            hover_color=RED_HOVER,
            font=self.font_button,
        ).pack(pady=(20, 22))

    def show_report_viewer(self, path):
        path = pathlib.Path(path)
        try:
            report = read_report_text(path)
        except OSError as error:
            self.show_notice("Could not read report", str(error), danger=True)
            return
        window, body = self.make_dialog(path.name, 850, 620)
        ctk.CTkLabel(
            body,
            text=path.name,
            text_color=TEXT,
            font=self.font_heading,
            anchor="w",
        ).pack(fill="x", padx=22, pady=(18, 8))
        report_box = ctk.CTkTextbox(
            body,
            fg_color=DARK_SURFACE,
            border_width=1,
            border_color=BORDER,
            corner_radius=10,
            text_color=TEXT,
            font=ctk.CTkFont("Consolas", 11),
            wrap="none",
        )
        report_box.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        report_box.insert("1.0", report)
        report_box.configure(state="disabled")
        ctk.CTkButton(
            body,
            text="Close",
            command=window.destroy,
            width=105,
            height=38,
            corner_radius=9,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self.font_button,
        ).pack(pady=(0, 17))

    def copy_report(self, path):
        path = pathlib.Path(path)
        try:
            report = read_report_text(path)
            self.clipboard_clear()
            self.clipboard_append(report)
            self.status.set(f"Copied {path.name}")
        except (OSError, tk.TclError) as error:
            self.show_notice("Could not copy report", str(error), danger=True)

    def cancel_instance_launch(self, ident, detail):
        self.launching_instances.discard(ident)
        self.refresh_instances()
        self.show_notice("Launch failed", detail, danger=True)

    def build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.build_sidebar()
        self.build_main()

    def build_sidebar(self):
        sidebar = tk.Frame(self, width=270, bg=SIDEBAR, bd=0, highlightthickness=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(2, weight=1)

        brand_band = tk.Frame(sidebar, bg=BRAND_WORDMARK_BG, bd=0, highlightthickness=0)
        brand_band.grid(row=0, column=0, sticky="ew")
        brand = tk.Frame(brand_band, bg=BRAND_WORDMARK_BG, bd=0, highlightthickness=0)
        brand.pack(fill="x", padx=15, pady=(16, 13))
        brand_text = tk.Frame(brand, bg=BRAND_WORDMARK_BG, bd=0, highlightthickness=0)
        brand_text.pack(fill="x")
        if self.brand_wordmark_image is not None:
            self.brand_wordmark_photo = ImageTk.PhotoImage(self.brand_wordmark_image)
            self.brand_wordmark_label = tk.Label(
                brand_text,
                image=self.brand_wordmark_photo,
                width=BRAND_WORDMARK_SIZE[0],
                height=BRAND_WORDMARK_SIZE[1],
                bg=BRAND_WORDMARK_BG,
                borderwidth=0,
                highlightthickness=0,
            )
            self.brand_wordmark_label.pack(anchor="center")
        else:
            ctk.CTkLabel(
                brand_text,
                text="BREAKBLOCKS",
                text_color=TEXT,
                font=ctk.CTkFont(self.ui_font, 17, "bold"),
            ).pack(anchor="center")
            ctk.CTkLabel(
                brand_text,
                text="LAUNCHER",
                text_color=RED,
                font=ctk.CTkFont(self.ui_font, 15, "bold"),
            ).pack(anchor="center", pady=(0, 1))
        ctk.CTkLabel(
            brand_text,
            text=APP_VERSION.upper(),
            text_color=TEXT,
            font=ctk.CTkFont(self.ui_font, 10, "bold"),
        ).pack(anchor="center", pady=(9, 0))
        nav = tk.Frame(sidebar, bg=SIDEBAR, bd=0, highlightthickness=0)
        nav.grid(row=1, column=0, sticky="new", padx=14)
        self.nav_icon_images = {
            name: ctk.CTkImage(
                light_image=nav_icon_image(name.lower()),
                dark_image=nav_icon_image(name.lower()),
                size=(20, 20),
            )
            for name in ("Launcher", "Chat", "Settings", "About")
        }
        for name in ("Launcher", "Chat", "Settings", "About"):
            nav_row = tk.Frame(nav, bg=SIDEBAR, bd=0, highlightthickness=0)
            nav_row.pack(fill="x", pady=4)
            button = ctk.CTkButton(
                nav_row,
                text=f"  {name}",
                image=self.nav_icon_images[name],
                compound="left",
                command=lambda page=name: self.show_page(page),
                height=54,
                corner_radius=12,
                anchor="w",
                fg_color="transparent",
                hover_color=SURFACE_HOVER,
                text_color=MUTED,
                font=ctk.CTkFont(self.ui_font, 14, "bold"),
            )
            button.pack(fill="x")
            self.nav_buttons[name] = button
            if name == "Chat":
                button.bind("<Button-3>", self.show_chat_context_menu)
                self.chat_unread_badge = ctk.CTkLabel(
                    nav_row,
                    text="",
                    width=24,
                    height=24,
                    corner_radius=12,
                    bg_color=SIDEBAR,
                    fg_color=RED,
                    text_color="#ffffff",
                    font=ctk.CTkFont(self.ui_font, 11, "bold"),
                )
                self.chat_unread_badge.bind("<Button-1>", lambda _event: self.show_page("Chat"))
                self.chat_unread_badge.bind("<Button-3>", self.show_chat_context_menu)
                button.bind(
                    "<Enter>",
                    lambda _event: self.update_chat_unread_badge_background(True),
                    add=True,
                )
                button.bind(
                    "<Leave>",
                    lambda _event: self.update_chat_unread_badge_background(False),
                    add=True,
                )
                self.chat_unread_badge.bind(
                    "<Enter>",
                    lambda _event: self.update_chat_unread_badge_background(True),
                )
                self.chat_unread_badge.bind(
                    "<Leave>",
                    lambda _event: self.update_chat_unread_badge_background(False),
                )

                self.chat_context_menu = tk.Menu(
                    self,
                    tearoff=False,
                    bg=CONTROL_SURFACE,
                    fg=TEXT,
                    activebackground=ACCENT,
                    activeforeground="#ffffff",
                    borderwidth=1,
                    relief="flat",
                    font=(self.ui_font, 11),
                )
                self.chat_context_menu.add_command(
                    label="Open in browser",
                    command=lambda: self.open_external_url(
                        BREAKBLOCKS_CHAT_WEB_URL, "BreakBlocks Chat"
                    ),
                )

        community = tk.Frame(sidebar, bg=SIDEBAR, bd=0, highlightthickness=0)
        community.grid(row=3, column=0, sticky="sew", padx=14, pady=(10, 16))
        community.grid_columnconfigure((0, 1), weight=1, uniform="community_links")
        self.breakblocks_wordmark_image = self.load_asset(
            "community/breakblocks_wordmark_transparent.png", (198, 30)
        )
        self.bbc_chicken_image = self.load_asset(
            "community/bbc_chicken_transparent.png", (22, 22), crop_transparent=True
        )
        self.mountains_of_lava_image = self.load_asset(
            "community/mountains_of_lava_youtube.png", (22, 22)
        )
        self.zazuzin_github_image = self.load_asset("community/zazuzin_github.png", (22, 22))
        self.etianl_github_image = self.load_asset("community/etianl_github.png", (22, 22))
        ctk.CTkButton(
            community,
            text="" if self.breakblocks_wordmark_image else "BREAKBLOCKS.COM",
            image=self.breakblocks_wordmark_image,
            command=lambda: self.open_external_url(BREAKBLOCKS_URL, "BreakBlocks.com"),
            height=42,
            corner_radius=9,
            fg_color="#131313",
            hover_color="#1b1b1b",
            border_width=0,
            font=ctk.CTkFont(self.ui_font, 11, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="ew")
        ctk.CTkButton(
            community,
            text="Join Discord",
            image=self.bbc_chicken_image,
            compound="left",
            command=lambda: self.open_external_url(BREAKBLOCKS_DISCORD_URL, "BreakBlocks Discord"),
            height=40,
            corner_radius=8,
            fg_color=BBC_CHARCOAL,
            hover_color=SURFACE_HOVER,
            border_width=1,
            border_color=BORDER,
            font=self.font_small,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        ctk.CTkButton(
            community,
            text="Support on Patreon",
            command=lambda: self.open_external_url(BREAKBLOCKS_PATREON_URL, "BreakBlocks Patreon"),
            height=40,
            corner_radius=8,
            fg_color="#ff424d",
            hover_color="#d93641",
            text_color="#ffffff",
            border_width=0,
            font=self.font_small,
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        ctk.CTkButton(
            community,
            text="Mountains of Lava Inc.",
            image=self.mountains_of_lava_image,
            compound="left",
            command=lambda: self.open_external_url(
                MOUNTAINS_OF_LAVA_YOUTUBE_URL, "Mountains of Lava Inc. YouTube"
            ),
            height=40,
            corner_radius=8,
            fg_color=BBC_CHARCOAL,
            hover_color=SURFACE_HOVER,
            text_color="#ffffff",
            border_width=1,
            border_color=BORDER,
            font=self.font_small,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        ctk.CTkButton(
            community,
            text="Zazuzin",
            image=self.zazuzin_github_image,
            compound="left",
            command=lambda: self.open_external_url(ZAZUZIN_GITHUB_URL, "Zazuzin GitHub"),
            height=40,
            corner_radius=8,
            fg_color=BBC_CHARCOAL,
            hover_color=SURFACE_HOVER,
            border_width=1,
            border_color=BORDER,
            font=self.font_small,
        ).grid(row=4, column=0, sticky="ew", padx=(0, 4), pady=(7, 0))
        ctk.CTkButton(
            community,
            text="Etianl",
            image=self.etianl_github_image,
            compound="left",
            command=lambda: self.open_external_url(ETIANL_GITHUB_URL, "Etianl GitHub"),
            height=40,
            corner_radius=8,
            fg_color=BBC_CHARCOAL,
            hover_color=SURFACE_HOVER,
            border_width=1,
            border_color=BORDER,
            font=self.font_small,
        ).grid(row=4, column=1, sticky="ew", padx=(4, 0), pady=(7, 0))

    def build_main(self):
        main = tk.Frame(self, bg=BG, bd=0, highlightthickness=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        header = tk.Frame(main, bg=BG, height=105, bd=0, highlightthickness=0)
        header.grid(row=0, column=0, sticky="ew", padx=32, pady=(24, 10))
        self.main_header = header
        self.page_title = ctk.CTkLabel(
            header, text="Launcher", text_color=TEXT, font=self.font_title, anchor="w"
        )
        self.page_title.pack(anchor="w")
        self.page_subtitle = ctk.CTkLabel(
            header, text="", text_color=MUTED, font=self.font_body, anchor="w"
        )

        self.page_host = tk.Frame(main, bg=BG, bd=0, highlightthickness=0)
        self.page_host.grid(row=1, column=0, sticky="nsew", padx=32, pady=(0, 20))
        self.page_host.grid_columnconfigure(0, weight=1)
        self.page_host.grid_rowconfigure(0, weight=1)

        self.pages["Launcher"] = tk.Frame(self.page_host, bg=BG, bd=0, highlightthickness=0)
        self.pages["Mods"] = tk.Frame(self.page_host, bg=BG, bd=0, highlightthickness=0)
        self.pages["Chat"] = tk.Frame(self.page_host, bg=BG, bd=0, highlightthickness=0)
        self.pages["Settings"] = tk.Frame(self.page_host, bg=BG, bd=0, highlightthickness=0)
        self.pages["About"] = tk.Frame(self.page_host, bg=BG, bd=0, highlightthickness=0)

        self.launcher_ui(self.pages["Launcher"])
        self.modrinth_ui(self.pages["Mods"])
        self.chat_web_ui(self.pages["Chat"])
        self.settings_ui(self.pages["Settings"])
        self.about_ui(self.pages["About"])

        footer = tk.Frame(main, height=38, bg=DEEP_SURFACE, bd=0, highlightthickness=0)
        footer.grid(row=2, column=0, sticky="ew")
        self.main_footer = footer
        self.status = tk.StringVar(value="Ready")
        ctk.CTkLabel(
            footer, textvariable=self.status, text_color=MUTED, font=self.font_small, anchor="w"
        ).pack(fill="x", padx=32, pady=8)
        self.show_page("Launcher")

    def open_external_url(self, url, label):
        try:
            open_system_target(url)
            self.status.set(f"Opened {label} in your browser")
        except Exception as error:
            log_launcher_error(f"Open external link {url}", error)
            self.show_notice(
                "Could not open link", f"Open this address manually:\n\n{url}", danger=True
            )

    def show_chat_context_menu(self, event):
        menu = self.chat_context_menu
        if menu is None:
            return "break"
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def open_local_document(self, filename, label):
        path = APP_DIR / filename
        if not path.is_file():
            self.show_notice(
                "Document unavailable",
                f"{label} was not included in this launcher package.",
                danger=True,
            )
            return
        self.open_external_url(path.resolve().as_uri(), label)

    def open_local_folder(self, path, label):
        path = pathlib.Path(path)
        try:
            path.mkdir(parents=True, exist_ok=True)
            open_system_target(path)
            self.status.set(f"Opened {label}")
        except (OSError, subprocess.SubprocessError) as error:
            self.show_notice("Could not open folder", str(error), danger=True)

    def show_first_run_legal_notice(self):
        if self.closing:
            return
        try:
            shown_version = int(self.store.data["settings"].get("legal_notice_version", 0) or 0)
        except (TypeError, ValueError):
            shown_version = 0
        if shown_version >= LEGAL_NOTICE_VERSION:
            return

        window, body = self.make_dialog("Before you continue", 620, 440)
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        ctk.CTkLabel(
            body,
            text="UNOFFICIAL MINECRAFT LAUNCHER",
            text_color=RED,
            font=self.font_heading,
        ).pack(pady=(27, 8))
        ctk.CTkLabel(
            body,
            text=(
                "NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH "
                "MOJANG OR MICROSOFT."
            ),
            text_color=TEXT,
            font=self.font_button,
            wraplength=540,
            justify="center",
        ).pack(padx=30)
        ctk.CTkLabel(
            body,
            text=(
                "You need a legitimate right to use Minecraft: Java Edition. Microsoft sign-in "
                "checks ownership; Offline profiles are available only after that check. The "
                "launcher stores profiles, sign-in tokens, settings and logs on this device and "
                "has no analytics or automatic crash uploads."
            ),
            text_color=MUTED,
            font=self.font_body,
            wraplength=540,
            justify="left",
        ).pack(padx=32, pady=(20, 18))

        links = ctk.CTkFrame(body, fg_color="transparent")
        links.pack()
        ctk.CTkButton(
            links,
            text="Privacy notice",
            command=lambda: self.open_local_document("PRIVACY.md", "Launcher Privacy Notice"),
            width=145,
            height=39,
            corner_radius=9,
            fg_color=CONTROL_SURFACE,
            hover_color=ACCENT_HOVER,
            font=self.font_small,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            links,
            text="Launcher terms",
            command=lambda: self.open_local_document("TERMS.md", "Launcher Terms"),
            width=145,
            height=39,
            corner_radius=9,
            fg_color=CONTROL_SURFACE,
            hover_color=ACCENT_HOVER,
            font=self.font_small,
        ).pack(side="left", padx=4)

        def continue_to_launcher():
            self.store.data["settings"]["legal_notice_version"] = LEGAL_NOTICE_VERSION
            self.store.save()
            window.destroy()

        ctk.CTkButton(
            body,
            text="Continue",
            command=continue_to_launcher,
            width=155,
            height=42,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self.font_button,
        ).pack(pady=(18, 24))

    def launcher_ui(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        # The dashboard is intentionally one native canvas.  The previous
        # version built this screen from scores of nested CustomTkinter canvases
        # and child windows, which caused the same Windows compositor trails
        # that the Modrinth single-surface renderer already solved.
        self.launch_dashboard = LauncherDashboardCanvas(page, self)
        self.launch_dashboard.grid(row=0, column=0, sticky="nsew")
        self.dashboard_host = self.launch_dashboard

    def chat_web_ui(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        self.chat_browser_status = tk.StringVar(
            value="The secure BreakBlocks website handles chat sign-in."
        )

        self.chat_browser_host = tk.Frame(
            page,
            bg="#181818",
            bd=0,
            highlightthickness=0,
        )
        self.chat_browser_host.grid(row=0, column=0, sticky="nsew")
        fallback = ctk.CTkFrame(self.chat_browser_host, fg_color=DARK_SURFACE, corner_radius=0)
        fallback.pack(fill="both", expand=True)
        ctk.CTkLabel(
            fallback,
            text="BREAKBLOCKS CHAT",
            text_color=TEXT,
            font=self.font_heading,
        ).pack(pady=(90, 8))
        ctk.CTkLabel(
            fallback,
            text=(
                "Loading the secure BreakBlocks web chat…\n"
                "Your website session is kept on this device."
            ),
            text_color=MUTED,
            font=self.font_body,
            justify="center",
        ).pack()

    def chat_browser_command(self, parent_handle):
        profile_directory = self.store.root / chat_browser.PROFILE_DIRECTORY_NAME
        profile_directory.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(profile_directory, 0o700)
        except OSError:
            pass
        self.chat_browser_shutdown_file = profile_directory / (
            f".stop-{os.getpid()}-{parent_handle}"
        )
        self.chat_browser_shutdown_file.unlink(missing_ok=True)
        self.chat_unread_file = getattr(
            self,
            "chat_unread_file",
            profile_directory / chat_browser.UNREAD_FILE_NAME,
        )
        self.chat_visible_file = getattr(
            self,
            "chat_visible_file",
            profile_directory / chat_browser.VISIBLE_FILE_NAME,
        )
        arguments = [
            "--chat-browser",
            "--parent-handle",
            str(parent_handle),
            "--profile-directory",
            str(profile_directory),
            "--shutdown-file",
            str(self.chat_browser_shutdown_file),
            "--unread-file",
            str(self.chat_unread_file),
            "--visible-file",
            str(self.chat_visible_file),
            "--game-process-file",
            str(getattr(self, "chat_game_file", profile_directory / chat_browser.GAME_PROCESS_FILE_NAME)),
        ]
        if getattr(sys, "frozen", False):
            return [sys.executable, *arguments]
        return [sys.executable, str(APP_DIR / "zazu_launcher.py"), *arguments]

    def ensure_chat_browser(self):
        if self.closing:
            return
        process = self.chat_browser_process
        if process is not None and process.poll() is None:
            return
        self.update_idletasks()
        parent_handle = int(self.chat_browser_host.winfo_id())
        environment = system_process_environment()
        if sys.platform.startswith("linux"):
            environment.setdefault("QT_QPA_PLATFORM", "xcb")
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self.chat_browser_process = subprocess.Popen(
                self.chat_browser_command(parent_handle),
                cwd=str(APP_DIR),
                env=environment,
                stdin=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
        except (OSError, ValueError) as error:
            self.chat_browser_process = None
            self.chat_browser_status.set("The embedded chat browser could not start.")
            log_launcher_error("Embedded chat browser", error)
            return
        self.chat_browser_status.set("Loading the secure BreakBlocks web chat…")
        if self.chat_browser_monitor_id is not None:
            try:
                self.after_cancel(self.chat_browser_monitor_id)
            except tk.TclError:
                pass
        self.chat_browser_monitor_id = self.after(1000, self.monitor_chat_browser)

    def monitor_chat_browser(self):
        self.chat_browser_monitor_id = None
        if self.closing:
            return
        process = self.chat_browser_process
        if process is None:
            return
        return_code = process.poll()
        if return_code is None:
            self.refresh_chat_unread_badge()
            self.chat_browser_status.set(
                "Secure BreakBlocks web chat — your website session stays on this device."
            )
            self.chat_browser_monitor_id = self.after(1500, self.monitor_chat_browser)
            return
        self.chat_browser_process = None
        if self.chat_browser_shutdown_file is not None:
            self.chat_browser_shutdown_file.unlink(missing_ok=True)
            self.chat_browser_shutdown_file = None
        self.chat_browser_status.set(
            "The embedded chat browser closed. Choose Reload Chat to try again."
        )
        log_launcher_message("Embedded chat browser", f"Stopped with exit code {return_code}")

    def set_chat_unread_badge(self, count):
        self.chat_unread_count = max(0, min(999, int(count)))
        badge = self.chat_unread_badge
        if badge is None:
            return
        if not self.chat_unread_count:
            badge.place_forget()
            return
        badge.configure(
            text="99+" if self.chat_unread_count > 99 else str(self.chat_unread_count),
            width=30 if self.chat_unread_count > 99 else 24,
        )
        self.update_chat_unread_badge_background(False)
        badge.place(relx=0.89, rely=0.5, anchor="center")
        badge.lift()

    def update_chat_unread_badge_background(self, hovered=False):
        badge = self.chat_unread_badge
        if badge is None:
            return
        if self.current_page == "Chat":
            background = SURFACE_ALT
        else:
            background = SURFACE_HOVER if hovered else SIDEBAR
        badge.configure(bg_color=background)

    def refresh_chat_unread_badge(self):
        count = chat_browser.read_unread_count(self.chat_unread_file)
        if self.current_page == "Chat":
            if count:
                chat_browser.write_unread_count(self.chat_unread_file, 0)
            count = 0
        self.set_chat_unread_badge(count)

    def set_chat_page_visible(self, visible):
        try:
            if visible:
                self.chat_visible_file.parent.mkdir(parents=True, exist_ok=True)
                self.chat_visible_file.write_text("visible\n", encoding="utf-8")
                chat_browser.write_unread_count(self.chat_unread_file, 0)
                self.set_chat_unread_badge(0)
                return
            self.chat_visible_file.unlink(missing_ok=True)
        except OSError as error:
            log_launcher_error("Updating chat visibility", error)

    def stop_chat_browser(self):
        if self.chat_browser_monitor_id is not None:
            try:
                self.after_cancel(self.chat_browser_monitor_id)
            except tk.TclError:
                pass
            self.chat_browser_monitor_id = None
        process = self.chat_browser_process
        self.chat_browser_process = None
        shutdown_file = self.chat_browser_shutdown_file
        self.chat_browser_shutdown_file = None
        try:
            if process is None or process.poll() is not None:
                return
            if shutdown_file is not None:
                shutdown_file.write_text("stop\n", encoding="utf-8")
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
        except OSError as error:
            log_launcher_error("Stopping embedded chat browser", error)
        finally:
            self.chat_visible_file.unlink(missing_ok=True)
            if shutdown_file is not None:
                shutdown_file.unlink(missing_ok=True)

    def restart_chat_browser(self):
        self.stop_chat_browser()
        self.ensure_chat_browser()

    def about_ui(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        content = ctk.CTkScrollableFrame(
            page,
            fg_color="transparent",
            corner_radius=0,
        )
        content.grid(row=0, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)

        project = self.settings_card(
            content,
            APP_NAME,
            f"Version {APP_VERSION} — an independent launcher built for the BreakBlocks community.",
            0,
        )
        ctk.CTkLabel(
            project,
            text=(
                "Created by Zazuzin for the BreakBlocks community.\n\n"
                "BreakBlocks is a Minecraft community hub for finding servers and players, "
                "checking server status, reading news, and getting help through its forums "
                "and authenticated web chat.\n\n"
                "The launcher brings Microsoft sign-in and ownership checks, separate game "
                "instances, common mod loaders, and Modrinth mod management together for "
                "Windows and Linux. It downloads Minecraft from Mojang's services and does "
                "not bundle the game."
            ),
            text_color=TEXT,
            font=self.font_body,
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(fill="x", padx=20, pady=(3, 12))
        project_links = ctk.CTkFrame(project, fg_color="transparent")
        project_links.pack(anchor="w", padx=20, pady=(0, 18))
        ctk.CTkButton(
            project_links,
            text="Project on GitHub",
            command=lambda: self.open_external_url(
                "https://github.com/Zazuzin/Zazu-Launcher",
                "BreakBlocks Launcher GitHub",
            ),
            width=150,
            height=38,
            corner_radius=9,
            fg_color=CONTROL_SURFACE,
            hover_color=ACCENT_HOVER,
            font=self.font_small,
        ).pack(side="left")
        ctk.CTkButton(
            project_links,
            text="BreakBlocks.com",
            command=lambda: self.open_external_url(BREAKBLOCKS_URL, "BreakBlocks.com"),
            width=140,
            height=38,
            corner_radius=9,
            fg_color=CONTROL_SURFACE,
            hover_color=ACCENT_HOVER,
            font=self.font_small,
        ).pack(side="left", padx=(8, 0))

        legal = self.settings_card(
            content,
            "Legal notice",
            "Ownership and non-affiliation statement",
            1,
        )
        ctk.CTkLabel(
            legal,
            text=(
                "NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH "
                "MOJANG OR MICROSOFT.\n\n"
                "BreakBlocks Launcher is an independent community project. It is not affiliated "
                "with, endorsed by, sponsored by, or approved by Microsoft Corporation or Mojang AB.\n\n"
                "Minecraft and related assets are © Mojang AB. “Minecraft” is a trademark of "
                "Microsoft Corporation. Microsoft, Mojang, Minecraft and all other third-party "
                "names, logos and trademarks belong to their respective owners."
            ),
            text_color=TEXT,
            font=self.font_body,
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(fill="x", padx=20, pady=(3, 13))
        legal_links = ctk.CTkFrame(legal, fg_color="transparent")
        legal_links.pack(anchor="w", padx=20, pady=(0, 18))
        for text, url, label in (
            (
                "Minecraft Usage Guidelines",
                MINECRAFT_USAGE_GUIDELINES_URL,
                "Minecraft Usage Guidelines",
            ),
            ("Minecraft EULA", MINECRAFT_EULA_URL, "Minecraft EULA"),
            ("Microsoft Privacy", MICROSOFT_PRIVACY_URL, "Microsoft Privacy Statement"),
        ):
            ctk.CTkButton(
                legal_links,
                text=text,
                command=lambda address=url, name=label: self.open_external_url(address, name),
                width=185,
                height=38,
                corner_radius=9,
                fg_color=CONTROL_SURFACE,
                hover_color=ACCENT_HOVER,
                font=self.font_small,
            ).pack(side="left", padx=(0, 8))

        privacy = self.settings_card(
            content,
            "Privacy and data",
            "What the launcher stores and which online services it contacts",
            2,
        )
        ctk.CTkLabel(
            privacy,
            text=(
                "The launcher has no advertising, analytics or automatic crash reporting. "
                "Profiles, Microsoft sign-in tokens, instance settings, playtime and logs are "
                "stored on this device. Microsoft tokens are sent only to Microsoft/Xbox/"
                "Minecraft services for sign-in and ownership checks; they are not sent to "
                "BreakBlocks. Searches and downloads contact the selected third-party service. "
                "Opening Chat loads the authenticated BreakBlocks website in an embedded browser. "
                "Its cookies and site data are kept locally so your website session can persist; "
                "the launcher does not receive the password entered into that website."
            ),
            text_color=TEXT,
            font=self.font_body,
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(fill="x", padx=20, pady=(3, 13))
        privacy_links = ctk.CTkFrame(privacy, fg_color="transparent")
        privacy_links.pack(anchor="w", padx=20, pady=(0, 18))
        for text, filename, label in (
            ("Privacy notice", "PRIVACY.md", "Launcher Privacy Notice"),
            ("Launcher terms", "TERMS.md", "Launcher Terms"),
            ("Third-party notices", "THIRD-PARTY-NOTICES.md", "Third-party Notices"),
        ):
            ctk.CTkButton(
                privacy_links,
                text=text,
                command=lambda file=filename, name=label: self.open_local_document(file, name),
                width=160,
                height=38,
                corner_radius=9,
                fg_color=CONTROL_SURFACE,
                hover_color=ACCENT_HOVER,
                font=self.font_small,
            ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            privacy_links,
            text="Contact BreakBlocks",
            command=lambda: self.open_external_url(BREAKBLOCKS_CONTACT_URL, "BreakBlocks contact"),
            width=165,
            height=38,
            corner_radius=9,
            fg_color=CONTROL_SURFACE,
            hover_color=ACCENT_HOVER,
            font=self.font_small,
        ).pack(side="left")

        ownership = self.settings_card(
            content,
            "Minecraft ownership",
            "Offline profiles do not bypass the Microsoft entitlement check",
            3,
        )
        ctk.CTkLabel(
            ownership,
            text=(
                "A Microsoft account that owns Minecraft: Java Edition must be verified on this "
                "installation before an Offline profile can be added or launched. The launcher "
                "downloads game files from Mojang's services and does not include or redistribute "
                "Minecraft in its own packages."
            ),
            text_color=TEXT,
            font=self.font_body,
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(fill="x", padx=20, pady=(3, 18))

    def settings_ui(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        settings = self.store.data["settings"]
        self.java = tk.StringVar(value=settings.get("java", "auto"))
        self.memory = tk.IntVar(value=int(settings.get("memory", 4096)))
        self.keep_launcher_open = tk.BooleanVar(
            value=bool(settings.get("keep_launcher_open", True))
        )
        self.update_enabled = tk.BooleanVar(value=bool(settings.get("update_enabled", True)))
        self.update_channel = tk.StringVar(
            value=settings.get("update_channel", DEFAULT_UPDATE_CHANNEL)
        )
        self.update_frequency = tk.StringVar(value=settings.get("update_frequency", "daily"))

        actions = ctk.CTkFrame(page, fg_color="transparent")
        actions.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        actions.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            actions,
            text="Open Launcher Folder",
            command=self.open_data_folder,
            width=175,
            height=42,
            corner_radius=10,
            fg_color=CONTROL_SURFACE,
            hover_color=ACCENT_HOVER,
            font=self.font_button,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Save Settings",
            command=self.save_settings,
            width=150,
            height=42,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self.font_button,
        ).grid(row=0, column=2)

        content = ctk.CTkScrollableFrame(
            page,
            fg_color="transparent",
            corner_radius=0,
        )
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)

        runtime_card = self.settings_card(
            content,
            "Minecraft runtime",
            "Choose Java automatically or provide an executable, and set the default RAM for new instances.",
            0,
        )
        self.java_entry = ctk.CTkEntry(
            runtime_card,
            textvariable=self.java,
            height=42,
            corner_radius=9,
            fg_color=DARK_SURFACE,
            border_color=BORDER,
            text_color=TEXT,
            placeholder_text="auto",
            font=self.font_body,
        )
        self.java_entry.pack(fill="x", padx=20, pady=(3, 12))

        memory_row = ctk.CTkFrame(runtime_card, fg_color="transparent")
        memory_row.pack(fill="x", padx=20, pady=(0, 18))
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
            fg_color=CONTROL_SURFACE,
        )
        self.memory_slider.grid(row=0, column=0, sticky="ew", padx=(0, 18))
        self.memory_label = ctk.CTkLabel(
            memory_row,
            text="4096 MiB",
            width=105,
            height=38,
            corner_radius=9,
            fg_color=DARK_SURFACE,
            text_color=TEXT,
            font=self.font_button,
        )
        self.memory_label.grid(row=0, column=1)

        launch_card = self.settings_card(
            content,
            "Launch behaviour",
            "Control what happens to the launcher after Minecraft starts.",
            1,
        )
        ctk.CTkSwitch(
            launch_card,
            text="Keep the launcher visible while Minecraft is running",
            variable=self.keep_launcher_open,
            progress_color=GREEN_BG,
            button_color=GREEN,
            button_hover_color=GREEN_BORDER,
            text_color=TEXT,
            font=self.font_body,
        ).pack(anchor="w", padx=20, pady=(4, 18))

        update_card = self.settings_card(
            content,
            "Launcher updates",
            "Check GitHub Releases for verified BreakBlocks Launcher packages.",
            2,
        )
        update_controls = ctk.CTkFrame(update_card, fg_color="transparent")
        update_controls.pack(fill="x", padx=20, pady=(3, 10))
        update_controls.grid_columnconfigure(3, weight=1)
        ctk.CTkSwitch(
            update_controls,
            text="Automatic checks",
            variable=self.update_enabled,
            progress_color=GREEN_BG,
            button_color=GREEN,
            button_hover_color=GREEN_BORDER,
            text_color=TEXT,
            font=self.font_body,
        ).grid(row=0, column=0, sticky="w", padx=(0, 18))
        ctk.CTkLabel(
            update_controls,
            text="Channel",
            text_color=MUTED,
            font=self.font_small,
        ).grid(row=0, column=1, padx=(0, 7))
        ctk.CTkOptionMenu(
            update_controls,
            variable=self.update_channel,
            values=list(UPDATE_CHANNELS),
            width=105,
            height=36,
            fg_color=CONTROL_SURFACE,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=SURFACE_ALT,
            dropdown_hover_color=SURFACE_HOVER,
            font=self.font_small,
        ).grid(row=0, column=2, padx=(0, 18))
        ctk.CTkLabel(
            update_controls,
            text="Frequency",
            text_color=MUTED,
            font=self.font_small,
        ).grid(row=0, column=3, sticky="e", padx=(0, 7))
        ctk.CTkOptionMenu(
            update_controls,
            variable=self.update_frequency,
            values=["startup", "daily", "weekly", "never"],
            width=110,
            height=36,
            fg_color=CONTROL_SURFACE,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=SURFACE_ALT,
            dropdown_hover_color=SURFACE_HOVER,
            font=self.font_small,
        ).grid(row=0, column=4)

        update_footer = ctk.CTkFrame(update_card, fg_color="transparent")
        update_footer.pack(fill="x", padx=20, pady=(0, 18))
        update_footer.grid_columnconfigure(0, weight=1)
        self.update_status_text = tk.StringVar(value="No update check has run this session.")
        ctk.CTkLabel(
            update_footer,
            textvariable=self.update_status_text,
            text_color=MUTED,
            font=self.font_small,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self.check_update_button = ctk.CTkButton(
            update_footer,
            text="Check now",
            command=lambda: self.check_for_launcher_update(manual=True),
            width=110,
            height=36,
            corner_radius=9,
            fg_color=CONTROL_SURFACE,
            hover_color=ACCENT_HOVER,
            font=self.font_small,
        )
        self.check_update_button.grid(row=0, column=1, padx=(12, 0))

        chat_card = self.settings_card(
            content,
            "BreakBlocks Chat",
            "Chat sign-in and preferences are managed by the secure BreakBlocks website.",
            3,
        )
        ctk.CTkLabel(
            chat_card,
            text=(
                "The launcher stores the web chat's cookies and site data locally so you do not "
                "need to sign in every time. Use the website's own Log out control to end the session."
            ),
            text_color=TEXT,
            font=self.font_body,
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(fill="x", padx=20, pady=(3, 12))
        ctk.CTkButton(
            chat_card,
            text="Open Chat",
            command=lambda: self.show_page("Chat"),
            width=125,
            height=38,
            corner_radius=9,
            fg_color=CONTROL_SURFACE,
            hover_color=ACCENT_HOVER,
            font=self.font_small,
        ).pack(anchor="w", padx=20, pady=(0, 18))

    def _settings_entry(
        self,
        parent,
        label,
        variable,
        row,
        column,
        width=None,
        placeholder=None,
        show=None,
    ):
        field = ctk.CTkFrame(parent, fg_color="transparent")
        field.grid(row=row, column=column, sticky="ew", padx=(0, 9) if column < 3 else 0)
        ctk.CTkLabel(
            field,
            text=label,
            text_color=MUTED,
            font=ctk.CTkFont(self.ui_font, 9, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))
        entry = ctk.CTkEntry(
            field,
            textvariable=variable,
            width=width or 180,
            height=38,
            corner_radius=9,
            fg_color=DARK_SURFACE,
            border_color=BORDER,
            text_color=TEXT,
            placeholder_text=placeholder,
            show=show,
            font=self.font_body,
        )
        entry.pack(fill="x")
        return entry

    def settings_card(self, parent, title, subtitle, row):
        card = ctk.CTkFrame(
            parent, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=BORDER
        )
        card.grid(row=row, column=0, sticky="ew", pady=(0, 13))
        ctk.CTkLabel(card, text=title, text_color=TEXT, font=self.font_heading, anchor="w").pack(
            fill="x", padx=20, pady=(17, 2)
        )
        ctk.CTkLabel(card, text=subtitle, text_color=MUTED, font=self.font_small, anchor="w").pack(
            fill="x", padx=20, pady=(0, 12)
        )
        return card

    def show_page(self, name, force=False):
        if self.current_page == "Mods" and name != "Mods" and not force:
            self.close_modrinth_manager(name)
            return
        titles = {
            "Launcher": ("Launcher", ""),
            "Mods": (
                "Modrinth Mod Manager",
                "Browse and manage compatible mods for the selected instance",
            ),
            "Chat": ("BreakBlocks Chat", "Secure community chat powered by BreakBlocks.com"),
            "Settings": ("Settings", "Configure launcher and update preferences"),
            "About": ("About", f"{APP_NAME} {APP_VERSION}"),
        }
        target_page = self.pages[name]
        previous_page = self.pages.get(self.current_page)

        # CustomTkinter pages contain native child windows that do not always
        # follow their parent's stacking order on Windows. Keep just one page
        # mapped in this display slot, but retain every page and its state in
        # memory. Doing both operations in this callback avoids an intermediate
        # redraw, so there is no mixed-page frame or full page rebuild.
        if previous_page is not None and previous_page is not target_page:
            previous_page.grid_remove()

        if name == "Chat":
            self.main_header.grid_remove()
            self.main_footer.grid_remove()
            self.page_host.grid_configure(padx=0, pady=0)
        elif name == "Launcher":
            self.main_header.grid_remove()
            if not self.main_footer.winfo_manager():
                self.main_footer.grid()
            self.page_host.grid_configure(padx=24, pady=(24, 20))
        else:
            if not self.main_header.winfo_manager():
                self.main_header.grid()
            if not self.main_footer.winfo_manager():
                self.main_footer.grid()
            self.page_host.grid_configure(padx=32, pady=(0, 20))
        self.page_title.configure(text=titles[name][0])
        subtitle = titles[name][1]
        self.page_subtitle.configure(text=subtitle)
        if subtitle:
            if not self.page_subtitle.winfo_manager():
                self.page_subtitle.pack(anchor="w", pady=(3, 0))
        else:
            self.page_subtitle.pack_forget()
        for page_name, button in self.nav_buttons.items():
            active = page_name == name
            button.configure(
                fg_color=SURFACE_ALT if active else "transparent",
                text_color=TEXT if active else MUTED,
            )
        if target_page.winfo_manager() != "grid":
            target_page.grid(row=0, column=0, sticky="nsew")
        self.current_page = name
        self.set_chat_page_visible(name == "Chat")
        if name == "Chat":
            self.ensure_chat_browser()
        if name == "Launcher" and hasattr(self, "launch_dashboard"):
            self.launch_dashboard.refresh()

    def refresh(self):
        self.refresh_instances()
        self.refresh_accounts()
        settings = self.store.data["settings"]
        self.java.set(settings.get("java", "auto"))
        memory = int(settings.get("memory", 4096))
        self.memory.set(memory)
        self.memory_slider.set(memory)
        self.memory_label.configure(text=f"{memory} MiB")
        self.keep_launcher_open.set(bool(settings.get("keep_launcher_open", True)))
        self.update_enabled.set(bool(settings.get("update_enabled", True)))
        self.update_channel.set(settings.get("update_channel", DEFAULT_UPDATE_CHANNEL))
        self.update_frequency.set(settings.get("update_frequency", "daily"))

    def refresh_instances(self):
        instances = self.store.data["instances"]
        instance_ids = {item["id"] for item in instances}
        if self.selected_instance_id not in instance_ids:
            self.selected_instance_id = instances[0]["id"] if instances else None
        self.launch_dashboard.refresh()

    def refresh_launch_summary(self):
        self.launch_dashboard.refresh()

    def select_instance(self, ident):
        self.selected_instance_id = ident
        self.refresh_instances()

    def instance_mod_count(self, instance):
        if not instance:
            return 0
        try:
            instances_root = self.store.instances.resolve()
            instance_root = (instances_root / str(instance["id"])).resolve()
            if instance_root.parent != instances_root:
                return 0
            mods_dir = instance_root / "minecraft" / "mods"
            return sum(
                1
                for path in mods_dir.iterdir()
                if path.is_file()
                and (path.name.endswith(".jar") or path.name.endswith(".jar.disabled"))
            )
        except OSError:
            return 0

    def instance_icon_image(self, instance, size=(52, 52)):
        key = instance.get("icon") or default_instance_icon(instance.get("id", "instance"))
        if key == "custom":
            try:
                path = self.instance_custom_icon_path(instance)
            except ValueError:
                return None
        else:
            if key not in BLOCK_ICON_KEYS:
                key = default_instance_icon(instance.get("id", "instance"))
            path = APP_DIR / "assets" / "instance_icons" / f"{key}.png"
        try:
            image = Image.open(path).convert("RGBA")
            return ctk.CTkImage(light_image=image, dark_image=image, size=size)
        except (OSError, ValueError):
            return None

    def instance_custom_icon_path(self, instance):
        instances_root = self.store.instances.resolve()
        instance_root = (instances_root / str(instance["id"])).resolve()
        if instance_root.parent != instances_root:
            raise ValueError("The selected instance has an invalid folder path")
        return instance_root / "launcher-icon.png"

    def edit_instance(self):
        instance = next(
            (
                item
                for item in self.store.data["instances"]
                if item["id"] == self.selected_instance_id
            ),
            None,
        )
        if not instance:
            self.show_notice("Select an instance", "Choose the instance you want to edit first.")
            return
        if instance["id"] in self.active_installs:
            self.show_notice(
                "Installation in progress",
                "Wait for this instance to finish installing before editing it.",
            )
            return
        if instance["id"] in self.running_instances or instance["id"] in self.launching_instances:
            self.show_notice(
                "Instance is running", "Close Minecraft before changing this instance."
            )
            return

        window, body = self.make_dialog("Edit instance", 590, 590)
        ctk.CTkLabel(body, text="Edit instance", text_color=TEXT, font=self.font_title).pack(
            anchor="w", padx=26, pady=(23, 3)
        )
        ctk.CTkLabel(
            body,
            text="Rename it, change its loader, or set how much RAM Minecraft can use.",
            text_color=MUTED,
            font=self.font_small,
        ).pack(anchor="w", padx=26, pady=(0, 16))

        name = tk.StringVar(value=instance.get("name", ""))
        loader = tk.StringVar(value=instance.get("loader", "Vanilla"))
        try:
            initial_memory = max(1024, min(32768, int(instance.get("memory", self.memory.get()))))
        except (TypeError, ValueError):
            initial_memory = int(self.memory.get())
        memory = tk.IntVar(value=initial_memory)

        name_entry = ctk.CTkEntry(
            body,
            textvariable=name,
            height=43,
            corner_radius=10,
            fg_color=DARK_SURFACE,
            border_color=BORDER,
            font=self.font_body,
        )
        self.dialog_field(body, "INSTANCE NAME", name_entry)

        details = ctk.CTkFrame(body, fg_color="transparent")
        details.pack(fill="x", padx=26, pady=(4, 7))
        details.grid_columnconfigure((0, 1), weight=1, uniform="edit_instance_details")
        version_card = ctk.CTkFrame(
            details, fg_color=DARK_SURFACE, corner_radius=10, border_width=1, border_color=BORDER
        )
        version_card.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkLabel(
            version_card,
            text="MINECRAFT VERSION",
            text_color=MUTED,
            font=ctk.CTkFont(self.ui_font, 9, "bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(7, 0))
        ctk.CTkLabel(
            version_card,
            text=instance.get("version", "—"),
            text_color=TEXT,
            font=self.font_body,
            anchor="w",
        ).pack(fill="x", padx=12, pady=(1, 8))
        loader_card = ctk.CTkFrame(
            details, fg_color=DARK_SURFACE, corner_radius=10, border_width=1, border_color=BORDER
        )
        loader_card.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ctk.CTkLabel(
            loader_card,
            text="LOADER",
            text_color=MUTED,
            font=ctk.CTkFont(self.ui_font, 9, "bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(6, 0))
        loader_box = ctk.CTkOptionMenu(
            loader_card,
            variable=loader,
            values=["Vanilla", "Fabric", "Forge", "NeoForge", "Quilt"],
            height=28,
            corner_radius=8,
            fg_color=DARK_SURFACE,
            button_color=CONTROL_SURFACE,
            button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=SURFACE_ALT,
            dropdown_hover_color=SURFACE_HOVER,
            font=self.font_body,
            dropdown_font=self.font_body,
        )
        loader_box.pack(fill="x", padx=5, pady=(0, 5))

        memory_card = ctk.CTkFrame(
            body, fg_color=DARK_SURFACE, corner_radius=11, border_width=1, border_color=BORDER
        )
        memory_card.pack(fill="x", padx=26, pady=(8, 7))
        memory_header = ctk.CTkFrame(memory_card, fg_color="transparent")
        memory_header.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(
            memory_header,
            text="RAM ALLOCATION",
            text_color=MUTED,
            font=ctk.CTkFont(self.ui_font, 9, "bold"),
        ).pack(side="left")
        memory_label = ctk.CTkLabel(
            memory_header,
            text=f"{initial_memory} MiB",
            width=92,
            height=27,
            corner_radius=8,
            fg_color=SURFACE_ALT,
            text_color=TEXT,
            font=self.font_small,
        )
        memory_label.pack(side="right")

        def memory_changed(value):
            selected = max(1024, min(32768, int(round(float(value) / 256) * 256)))
            memory.set(selected)
            memory_label.configure(text=f"{selected} MiB")

        memory_slider = ctk.CTkSlider(
            memory_card,
            from_=1024,
            to=32768,
            number_of_steps=124,
            command=memory_changed,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            progress_color=ACCENT,
            fg_color=CONTROL_SURFACE,
        )
        memory_slider.pack(fill="x", padx=15, pady=(5, 13))
        memory_slider.set(initial_memory)

        warning = ctk.CTkFrame(
            body, fg_color=WARNING_BG, corner_radius=10, border_width=1, border_color=WARNING_BORDER
        )
        warning.pack(fill="x", padx=26, pady=(8, 4))
        ctk.CTkLabel(
            warning,
            text="Changing the loader reinstalls the launch profile. Saves, configs and mods are kept, but loader-specific mods may need compatible replacements.",
            text_color=WARNING_TEXT,
            font=self.font_small,
            justify="left",
            anchor="w",
            wraplength=495,
        ).pack(fill="x", padx=13, pady=10)

        validation = tk.StringVar(value="")
        ctk.CTkLabel(
            body,
            textvariable=validation,
            text_color=RED,
            font=self.font_small,
            height=18,
            anchor="w",
        ).pack(fill="x", padx=26, pady=(3, 0))
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", padx=26, pady=(10, 22))
        ctk.CTkButton(
            buttons,
            text="Change Icon…",
            command=self.change_instance_icon,
            width=118,
            height=42,
            corner_radius=10,
            fg_color=SURFACE_ALT,
            hover_color=SURFACE_HOVER,
            border_width=1,
            border_color=BORDER,
            font=self.font_button,
        ).pack(side="left")
        ctk.CTkButton(
            buttons,
            text="Cancel",
            command=window.destroy,
            width=100,
            height=42,
            corner_radius=10,
            fg_color=SURFACE_ALT,
            hover_color=SURFACE_HOVER,
            font=self.font_button,
        ).pack(side="right")

        def save_changes():
            new_name = name.get().strip()
            if not new_name:
                validation.set("Enter an instance name.")
                name_entry.focus_set()
                return
            if len(new_name) > 80:
                validation.set("Keep the instance name to 80 characters or fewer.")
                name_entry.focus_set()
                return
            new_memory = max(1024, min(32768, int(memory.get())))
            old_loader = instance.get("loader", "Vanilla")
            old_installed = bool(instance.get("installed"))
            new_loader = loader.get()
            instance["name"] = new_name
            instance["memory"] = new_memory
            if new_loader != old_loader:
                instance["loader"] = new_loader
                instance["installed"] = False
            self.store.save()
            window.destroy()
            if new_loader != old_loader:
                self.status.set(f"Changing {new_name} from {old_loader} to {new_loader}…")
                self.start_install(
                    instance["id"],
                    instance["version"],
                    new_loader,
                    rollback={"loader": old_loader, "installed": old_installed},
                    success_message=f"{new_name} now uses {new_loader}",
                    failure_title="Loader change failed",
                )
            self.refresh_instances()
            if new_loader == old_loader:
                self.status.set(f"Saved changes to {new_name}")

        ctk.CTkButton(
            buttons,
            text="Save Changes",
            command=save_changes,
            width=135,
            height=42,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self.font_button,
        ).pack(side="right", padx=(0, 9))

    def change_instance_icon(self):
        instance = next(
            (
                item
                for item in self.store.data["instances"]
                if item["id"] == self.selected_instance_id
            ),
            None,
        )
        if not instance:
            self.show_notice(
                "Select an instance", "Choose the instance whose icon you want to change first."
            )
            return

        window, body = self.make_dialog("Choose instance icon", 660, 625)
        ctk.CTkLabel(
            body, text="Choose an instance icon", text_color=TEXT, font=self.font_title
        ).pack(anchor="w", padx=24, pady=(20, 2))
        ctk.CTkLabel(
            body,
            text="Pick one of 25 block icons, or use your own square image.",
            text_color=MUTED,
            font=self.font_small,
        ).pack(anchor="w", padx=24, pady=(0, 12))
        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=18)
        grid.icon_images = []
        for column in range(5):
            grid.grid_columnconfigure(column, weight=1, uniform="icons")

        def choose(key):
            try:
                custom_path = self.instance_custom_icon_path(instance)
            except ValueError:
                self.show_notice(
                    "Could not change icon",
                    "The selected instance has an invalid folder path.",
                    danger=True,
                )
                return
            instance["icon"] = key
            if key != "custom":
                custom_path.unlink(missing_ok=True)
            self.store.save()
            self.refresh_instances()
            window.destroy()
            self.status.set(f"Changed icon for {instance['name']}")

        for index, (key, label) in enumerate(BLOCK_ICONS):
            preview = self.instance_icon_image({"id": instance["id"], "icon": key}, (40, 40))
            if preview:
                grid.icon_images.append(preview)
            button = ctk.CTkButton(
                grid,
                text=label,
                image=preview,
                compound="top",
                command=lambda selected=key: choose(selected),
                width=108,
                height=76,
                corner_radius=11,
                fg_color=SURFACE_HOVER if instance.get("icon") == key else SURFACE_ALT,
                hover_color=ACCENT_HOVER,
                border_width=2 if instance.get("icon") == key else 1,
                border_color=SELECTION if instance.get("icon") == key else BORDER,
                font=ctk.CTkFont(self.ui_font, 10, "bold"),
            )
            button.grid(row=index // 5, column=index % 5, sticky="nsew", padx=5, pady=5)

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.pack(fill="x", padx=24, pady=(10, 18))
        ctk.CTkButton(
            actions,
            text="Use custom PNG, JPG or WebP",
            command=lambda: self.choose_custom_instance_icon(instance, window),
            height=42,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self.font_button,
        ).pack(side="left")
        ctk.CTkButton(
            actions,
            text="Cancel",
            command=window.destroy,
            width=100,
            height=42,
            corner_radius=10,
            fg_color=SURFACE_ALT,
            hover_color=SURFACE_HOVER,
            font=self.font_button,
        ).pack(side="right")

    def choose_custom_instance_icon(self, instance, window):
        selected = filedialog.askopenfilename(
            parent=window,
            title="Choose an instance icon",
            filetypes=(("Image files", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            image = Image.open(selected).convert("RGBA")
            side = min(image.size)
            left = (image.width - side) // 2
            top = (image.height - side) // 2
            image = image.crop((left, top, left + side, top + side)).resize(
                (128, 128), Image.Resampling.LANCZOS
            )
            target = self.instance_custom_icon_path(instance)
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(target, "PNG")
            instance["icon"] = "custom"
            self.store.save()
            self.refresh_instances()
            window.destroy()
            self.status.set(f"Changed icon for {instance['name']}")
        except (OSError, ValueError) as error:
            self.show_notice(
                "Could not use image",
                f"Choose a valid PNG, JPG or WebP image.\n\n{error}",
                danger=True,
            )

    def open_mods_folder(self):
        instance = next(
            (
                item
                for item in self.store.data["instances"]
                if item["id"] == self.selected_instance_id
            ),
            None,
        )
        if not instance:
            self.show_notice(
                "Select an instance",
                "Choose the instance whose mods folder you want to open first.",
            )
            return

        instances_root = self.store.instances.resolve()
        instance_root = (instances_root / instance["id"]).resolve()
        mods_folder = (instance_root / "minecraft" / "mods").resolve()
        if instance_root.parent != instances_root or instance_root not in mods_folder.parents:
            self.show_notice(
                "Could not open folder",
                "The selected instance has an invalid folder path.",
                danger=True,
            )
            return
        try:
            mods_folder.mkdir(parents=True, exist_ok=True)
            open_system_target(mods_folder)
            self.status.set(f"Opened mods folder for {instance['name']}")
        except (OSError, subprocess.SubprocessError) as error:
            self.show_notice("Could not open folder", str(error), danger=True)

    def modrinth_ui(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(page, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkButton(
            toolbar,
            text="←  Back to Launcher",
            command=self.close_modrinth_manager,
            width=155,
            height=42,
            corner_radius=11,
            fg_color=SURFACE_ALT,
            hover_color=SURFACE_HOVER,
            border_width=1,
            border_color=BORDER,
            font=self.font_button,
        ).pack(side="left")
        self.mod_instance_label = ctk.CTkLabel(
            toolbar,
            text="Select a modded instance",
            text_color=MUTED,
            font=self.font_body,
            anchor="w",
        )
        self.mod_instance_label.pack(side="left", fill="x", expand=True, padx=16)
        ctk.CTkButton(
            toolbar,
            text="Open mods folder",
            command=self.open_mods_folder,
            width=135,
            height=42,
            corner_radius=11,
            fg_color=SURFACE_ALT,
            hover_color=SURFACE_HOVER,
            border_width=1,
            border_color=BORDER,
            font=self.font_button,
        ).pack(side="right")

        mod_panel = ctk.CTkFrame(page, fg_color=DARK_SURFACE, corner_radius=13)
        mod_panel.grid(row=1, column=0, sticky="nsew")
        mod_panel.grid_columnconfigure(0, weight=1)
        mod_panel.grid_rowconfigure(1, weight=1)

        tab_bar = ctk.CTkFrame(mod_panel, fg_color=SURFACE_ALT, corner_radius=10)
        tab_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        tab_names = ("Browse Modrinth", "Installed", "Updates")
        for column in range(len(tab_names)):
            tab_bar.grid_columnconfigure(column, weight=1, uniform="mod_tabs")
        self.mod_tab_buttons = {}
        for column, tab_name in enumerate(tab_names):
            button = ctk.CTkButton(
                tab_bar,
                text=tab_name,
                command=lambda selected=tab_name: self.select_mod_tab(selected),
                height=36,
                corner_radius=8,
                fg_color="transparent",
                hover_color=SURFACE_HOVER,
                text_color=MUTED,
                font=self.font_small,
            )
            button.grid(row=0, column=column, sticky="ew", padx=3, pady=3)
            self.mod_tab_buttons[tab_name] = button

        mod_body = ctk.CTkFrame(mod_panel, fg_color="transparent")
        mod_body.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        mod_body.grid_columnconfigure(0, weight=1)
        mod_body.grid_rowconfigure(0, weight=1)
        self.mod_tab_pages = {}
        for tab_name in tab_names:
            tab_page = ctk.CTkFrame(mod_body, fg_color=DARK_SURFACE, corner_radius=0)
            tab_page.grid(row=0, column=0, sticky="nsew")
            tab_page.grid_remove()
            self.mod_tab_pages[tab_name] = tab_page
        browse = self.mod_tab_pages["Browse Modrinth"]
        installed = self.mod_tab_pages["Installed"]
        updates = self.mod_tab_pages["Updates"]

        search_row = ctk.CTkFrame(browse, fg_color="transparent")
        search_row.pack(fill="x", padx=8, pady=(10, 8))
        self.mod_search_value = tk.StringVar(value="")
        self.mod_search_entry = ctk.CTkEntry(
            search_row,
            textvariable=self.mod_search_value,
            height=42,
            corner_radius=10,
            fg_color=SURFACE,
            border_color=BORDER,
            text_color=TEXT,
            placeholder_text="Search compatible Modrinth mods…",
            font=self.font_body,
        )
        self.mod_search_entry.pack(side="left", fill="x", expand=True)
        self.mod_search_entry.bind("<Return>", lambda _event: self.search_modrinth(reset=True))
        self.mod_sort_value = tk.StringVar(value="Relevance")
        ctk.CTkOptionMenu(
            search_row,
            variable=self.mod_sort_value,
            values=["Relevance", "Most downloaded", "Recently updated"],
            width=150,
            height=42,
            corner_radius=10,
            fg_color=SURFACE_ALT,
            button_color=CONTROL_SURFACE,
            button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=SURFACE_ALT,
            dropdown_hover_color=SURFACE_HOVER,
            font=self.font_small,
            dropdown_font=self.font_small,
        ).pack(side="left", padx=8)
        self.mod_search_button = ctk.CTkButton(
            search_row,
            text="Search",
            command=lambda: self.search_modrinth(reset=True),
            width=100,
            height=42,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self.font_button,
        )
        self.mod_search_button.pack(side="left")
        self.mod_results_scroll = ModrinthCanvasList(browse, self)
        self.mod_results_scroll.pack(fill="both", expand=True, padx=2)
        pager = ctk.CTkFrame(browse, fg_color="transparent")
        pager.pack(fill="x", padx=8, pady=(5, 8))
        self.mod_previous_button = ctk.CTkButton(
            pager,
            text="‹ Previous",
            command=lambda: self.change_mod_page(-1),
            width=95,
            height=34,
            corner_radius=9,
            fg_color=SURFACE_ALT,
            hover_color=SURFACE_HOVER,
            font=self.font_small,
        )
        self.mod_previous_button.pack(side="left")
        self.mod_page_label = ctk.CTkLabel(pager, text="", text_color=MUTED, font=self.font_small)
        self.mod_page_label.pack(side="left", expand=True)
        self.mod_next_button = ctk.CTkButton(
            pager,
            text="Next ›",
            command=lambda: self.change_mod_page(1),
            width=95,
            height=34,
            corner_radius=9,
            fg_color=SURFACE_ALT,
            hover_color=SURFACE_HOVER,
            font=self.font_small,
        )
        self.mod_next_button.pack(side="right")

        installed_header = ctk.CTkFrame(installed, fg_color="transparent")
        installed_header.pack(fill="x", padx=8, pady=(10, 6))
        self.mod_installed_summary = ctk.CTkLabel(
            installed_header, text="", text_color=MUTED, font=self.font_small, anchor="w"
        )
        self.mod_installed_summary.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            installed_header,
            text="Open mods folder",
            command=self.open_mods_folder,
            width=130,
            height=36,
            corner_radius=9,
            fg_color=SURFACE_ALT,
            hover_color=SURFACE_HOVER,
            font=self.font_small,
        ).pack(side="right")
        self.mod_installed_scroll = ModrinthCanvasList(installed, self)
        self.mod_installed_scroll.pack(fill="both", expand=True, padx=2, pady=(0, 8))

        update_header = ctk.CTkFrame(updates, fg_color="transparent")
        update_header.pack(fill="x", padx=8, pady=(10, 6))
        self.mod_update_summary = ctk.CTkLabel(
            update_header,
            text="Check installed mods for compatible updates.",
            text_color=MUTED,
            font=self.font_small,
            anchor="w",
        )
        self.mod_update_summary.pack(side="left", fill="x", expand=True)
        self.mod_update_all_button = ctk.CTkButton(
            update_header,
            text="Update all",
            command=self.update_all_modrinth,
            width=100,
            height=36,
            corner_radius=9,
            fg_color=SURFACE_ALT,
            hover_color=ACCENT_HOVER,
            font=self.font_small,
            state="disabled",
        )
        self.mod_update_all_button.pack(side="right", padx=(7, 0))
        self.mod_check_updates_button = ctk.CTkButton(
            update_header,
            text="Check updates",
            command=self.check_modrinth_updates,
            width=110,
            height=36,
            corner_radius=9,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self.font_small,
        )
        self.mod_check_updates_button.pack(side="right")
        self.mod_updates_scroll = ModrinthCanvasList(updates, self)
        self.mod_updates_scroll.pack(fill="both", expand=True, padx=2, pady=(0, 8))

        status_card = ctk.CTkFrame(
            page, fg_color=SURFACE, corner_radius=13, border_width=1, border_color=BORDER
        )
        status_card.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        status_card.grid_columnconfigure(0, weight=1)
        self.mod_progress_area = ctk.CTkFrame(status_card, fg_color="transparent")
        self.mod_progress_area.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 2))
        self.mod_progress_area.grid_columnconfigure(0, weight=1)
        self.mod_progress_text = tk.StringVar(value="")
        ctk.CTkLabel(
            self.mod_progress_area,
            textvariable=self.mod_progress_text,
            text_color=MUTED,
            font=self.font_small,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.mod_progress_percent = ctk.CTkLabel(
            self.mod_progress_area,
            text="",
            text_color=TEXT,
            font=ctk.CTkFont(self.ui_font, 11, "bold"),
        )
        self.mod_progress_percent.grid(row=0, column=1, sticky="e")
        self.mod_progress = ctk.CTkProgressBar(
            self.mod_progress_area,
            height=8,
            corner_radius=4,
            fg_color=CONTROL_SURFACE,
            progress_color=ACCENT,
        )
        self.mod_progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        self.mod_progress.set(0)
        self.mod_progress_area.grid_remove()

        status_row = ctk.CTkFrame(status_card, fg_color="transparent")
        status_row.grid(row=1, column=0, sticky="ew", padx=16, pady=10)
        self.mod_status = tk.StringVar(value="Only compatible mods for this instance are shown.")
        ctk.CTkLabel(
            status_row,
            textvariable=self.mod_status,
            text_color=MUTED,
            font=self.font_small,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        self.select_mod_tab("Browse Modrinth")

    def select_mod_tab(self, name):
        page = getattr(self, "mod_tab_pages", {}).get(name)
        if page is None:
            return
        previous = self.mod_tab_pages.get(self.mod_active_tab)
        if previous is not None and previous is not page:
            previous.grid_remove()
        if page.winfo_manager() != "grid":
            page.grid(row=0, column=0, sticky="nsew")
        page.tkraise()
        self.mod_active_tab = name
        for tab_name, button in self.mod_tab_buttons.items():
            active = tab_name == name
            button.configure(
                fg_color=ACCENT if active else "transparent",
                hover_color=ACCENT_HOVER if active else SURFACE_HOVER,
                text_color=TEXT if active else MUTED,
            )
        if (
            name == "Updates"
            and not self.mod_updates_checked
            and self.mod_context_alive()
            and not self.mod_context["busy"]
        ):
            self.mod_updates_checked = True
            self.after(0, self.check_modrinth_updates)

    def open_modrinth_manager(self):
        instance = next(
            (
                item
                for item in self.store.data["instances"]
                if item["id"] == self.selected_instance_id
            ),
            None,
        )
        if not instance:
            self.show_notice(
                "Select an instance", "Choose the instance whose mods you want to manage first."
            )
            return
        if instance.get("loader") not in modrinth_client.SUPPORTED_LOADERS:
            self.show_notice(
                "Mod loader required",
                "Modrinth mods can be installed into Fabric, Forge, NeoForge or Quilt instances. Vanilla instances cannot load mod JARs.",
            )
            return
        instances_root = self.store.instances.resolve()
        instance_root = (instances_root / str(instance["id"])).resolve()
        if instance_root.parent != instances_root:
            self.show_notice(
                "Could not manage mods",
                "The selected instance has an invalid folder path.",
                danger=True,
            )
            return
        try:
            manager = modrinth_client.ModManager(
                instance_root,
                instance["version"],
                instance["loader"],
                progress=lambda percent, message: self.post_ui(
                    lambda value=percent, detail=message: self.update_mod_progress(value, detail)
                ),
            )
        except Exception as error:
            self.show_notice("Could not manage mods", str(error), danger=True)
            return

        self.modrinth_images = []
        self.modrinth_updates = {}
        self.mod_search_offset = 0
        self.mod_search_total = 0
        self.mod_search_running = False
        self.mod_updates_checked = False
        self.mod_search_generation += 1
        self.mod_search_started = 0.0
        self.mod_context = {
            "instance": instance,
            "root": instance_root,
            "manager": manager,
            "busy": False,
        }
        self.mod_page_active = True
        self.mod_instance_label.configure(
            text=f"{instance['name']}  •  Minecraft {instance['version']}  •  {instance['loader']}"
        )
        self.mod_search_value.set("")
        self.mod_sort_value.set("Relevance")
        self.mod_search_button.configure(state="normal", text="Search")
        self.mod_check_updates_button.configure(state="normal", text="Check updates")
        self.mod_update_all_button.configure(state="disabled")
        self.mod_update_summary.configure(text="Check installed mods for compatible updates.")
        self.mod_page_label.configure(text="")
        self.mod_previous_button.configure(state="disabled")
        self.mod_next_button.configure(state="disabled")
        self.mod_progress_area.grid_remove()
        self.select_mod_tab("Browse Modrinth")
        self.mod_status.set("Opening mod manager…")
        self.show_page("Mods", force=True)
        self.page_subtitle.configure(
            text=f"{instance['name']}  •  Minecraft {instance['version']}  •  {instance['loader']}"
        )
        open_token = self.mod_search_generation
        self.after(60, lambda token=open_token: self.finish_open_modrinth_manager(token))

    def finish_open_modrinth_manager(self, open_token):
        if not self.mod_context_alive() or open_token != self.mod_search_generation:
            return
        self.refresh_modrinth_installed()
        self.render_modrinth_updates([])
        self.search_modrinth(reset=True)

    def close_modrinth_manager(self, destination="Launcher"):
        if self.mod_context and self.mod_context.get("busy"):
            self.show_notice(
                "Mod operation in progress",
                "Wait for the current mod installation or update to finish before leaving this page.",
            )
            return
        self.mod_search_generation += 1
        self.mod_search_running = False
        self.mod_page_active = False
        self.mod_context = None
        self.modrinth_images = []
        self.mod_progress_area.grid_remove()
        self.show_page(destination, force=True)

    def mod_context_alive(self):
        try:
            return bool(
                self.mod_page_active and self.mod_context and self.pages["Mods"].winfo_exists()
            )
        except tk.TclError:
            return False

    @staticmethod
    def clear_widget_children(widget):
        for child in widget.winfo_children():
            child.destroy()

    def reset_scroll_to_top(self, scroll):
        """Reset a rebuilt results page now and once more after layout settles."""

        def apply():
            try:
                if scroll.winfo_exists():
                    scroll.yview_moveto(0.0)
            except tk.TclError:
                pass

        apply()
        self.after_idle(apply)

    def render_modrinth_empty(self, parent, title, message):
        parent.show_empty(title, message)

    def search_modrinth(self, reset=False):
        if not self.mod_context_alive() or self.mod_context["busy"] or self.mod_search_running:
            return
        if reset:
            self.mod_search_offset = 0
        context = self.mod_context
        instance = context["instance"]
        query = self.mod_search_value.get().strip()
        index = {
            "Relevance": "relevance",
            "Most downloaded": "downloads",
            "Recently updated": "updated",
        }.get(self.mod_sort_value.get(), "relevance")
        if not query and index == "relevance":
            index = "downloads"
        self.mod_search_generation += 1
        request_id = self.mod_search_generation
        offset = self.mod_search_offset
        self.mod_search_started = time.monotonic()
        self.mod_search_button.configure(state="disabled", text="Searching…")
        self.mod_search_running = True
        self.mod_status.set("Searching Modrinth for compatible mods…")
        self.render_modrinth_empty(
            self.mod_results_scroll,
            "Searching Modrinth…",
            "Loading compatible projects for this instance.",
        )
        log_launcher_message(
            "Modrinth search",
            f"started request={request_id} version={instance['version']} loader={instance['loader']} query={query!r}",
        )

        def worker():
            try:
                result = context["manager"].client.search(
                    query,
                    instance["version"],
                    instance["loader"],
                    offset=offset,
                    limit=MODRINTH_PAGE_SIZE,
                    index=index,
                )
                self.post_ui(
                    lambda payload=result, token=request_id: self.finish_modrinth_search(
                        payload, token
                    )
                )
            except Exception as error:
                log_launcher_error(f"Modrinth search request={request_id}", error)
                self.post_ui(
                    lambda detail=str(error), token=request_id: self.fail_modrinth_search(
                        detail, token
                    )
                )

        threading.Thread(target=worker, daemon=True).start()
        self.after(250, lambda token=request_id: self.check_modrinth_search_timeout(token))

    def check_modrinth_search_timeout(self, request_id):
        if (
            not self.mod_context_alive()
            or request_id != self.mod_search_generation
            or not self.mod_search_running
        ):
            return
        elapsed = time.monotonic() - self.mod_search_started
        if elapsed < MODRINTH_SEARCH_TIMEOUT_SECONDS:
            remaining_ms = max(50, int((MODRINTH_SEARCH_TIMEOUT_SECONDS - elapsed) * 1000))
            self.after(
                min(250, remaining_ms),
                lambda token=request_id: self.check_modrinth_search_timeout(token),
            )
            return
        log_launcher_message(
            "Modrinth search", f"request={request_id} timed out after {elapsed:.1f}s"
        )
        self.fail_modrinth_search(
            "Modrinth did not respond within 30 seconds. Check the connection and press Retry.",
            request_id,
        )

    def finish_modrinth_search(self, result, request_id=None):
        if not self.mod_context_alive() or (
            request_id is not None and request_id != self.mod_search_generation
        ):
            return
        if request_id is not None and not self.mod_search_running:
            return
        self.mod_search_total = int(result.get("total_hits", 0))
        self.mod_search_running = False
        self.mod_search_button.configure(state="normal", text="Search")
        self.mod_status.set(f"Found {self.mod_search_total:,} compatible Modrinth projects")
        log_launcher_message(
            "Modrinth search",
            f"completed request={request_id} total={self.mod_search_total} returned={len(result.get('hits', []))}",
        )
        self.render_modrinth_results(result.get("hits", []))
        self.reset_scroll_to_top(self.mod_results_scroll)
        start = self.mod_search_offset + 1 if self.mod_search_total else 0
        end = min(self.mod_search_offset + len(result.get("hits", [])), self.mod_search_total)
        self.mod_page_label.configure(text=f"{start:,}–{end:,} of {self.mod_search_total:,}")
        self.mod_previous_button.configure(
            state="normal" if self.mod_search_offset > 0 else "disabled"
        )
        self.mod_next_button.configure(
            state=(
                "normal"
                if self.mod_search_offset + MODRINTH_PAGE_SIZE < self.mod_search_total
                else "disabled"
            )
        )

    def fail_modrinth_search(self, detail, request_id=None):
        if not self.mod_context_alive() or (
            request_id is not None and request_id != self.mod_search_generation
        ):
            return
        if request_id is not None and not self.mod_search_running:
            return
        self.mod_search_running = False
        self.mod_search_button.configure(state="normal", text="Retry")
        self.mod_status.set("Modrinth search failed")
        self.render_modrinth_empty(self.mod_results_scroll, "Could not search Modrinth", detail)
        self.reset_scroll_to_top(self.mod_results_scroll)

    def change_mod_page(self, direction):
        if self.mod_search_running:
            return
        new_offset = max(0, self.mod_search_offset + (MODRINTH_PAGE_SIZE * int(direction)))
        if new_offset >= self.mod_search_total and direction > 0:
            return
        self.mod_search_offset = new_offset
        self.search_modrinth(reset=False)

    def render_modrinth_results(self, hits):
        self.modrinth_images = []
        if not hits:
            self.render_modrinth_empty(
                self.mod_results_scroll,
                "No compatible mods found",
                "Try another search term. Results are filtered to this instance's version and loader.",
            )
            return
        try:
            installed = {
                str(record.get("project_id")): record
                for record in self.mod_context["manager"].installed()
                if record.get("project_id")
            }
        except Exception:
            installed = {}
        generation = self.mod_search_generation
        self.mod_results_scroll.show_browse(hits, installed, generation)
        for project in hits:
            self.load_modrinth_icon(project, self.mod_results_scroll, generation)

    def load_modrinth_icon(self, project, widget, generation):
        url = project.get("icon_url")
        project_id = str(project.get("project_id", ""))
        if not url or not re.fullmatch(r"[A-Za-z0-9]+", project_id):
            return
        cache = self.store.root / "modrinth-icons"
        cache.mkdir(exist_ok=True)
        path = cache / f"{project_id}.png"

        def worker():
            try:
                if path.exists():
                    image = Image.open(path).convert("RGBA")
                else:
                    parsed = urllib.parse.urlsplit(url)
                    if parsed.scheme != "https" or parsed.hostname != "cdn.modrinth.com":
                        return
                    request = urllib.request.Request(
                        url, headers={"User-Agent": modrinth_client.USER_AGENT}
                    )
                    with urllib.request.urlopen(request, timeout=20) as response:
                        data = response.read(3 * 1024 * 1024 + 1)
                    if len(data) > 3 * 1024 * 1024:
                        return
                    image = Image.open(io.BytesIO(data)).convert("RGBA")
                    image.thumbnail((128, 128), Image.Resampling.LANCZOS)
                    image.save(path, "PNG")
                side = min(image.size)
                left = (image.width - side) // 2
                top = (image.height - side) // 2
                image = image.crop((left, top, left + side, top + side)).resize(
                    (52, 52), Image.Resampling.LANCZOS
                )
                self.post_ui(
                    lambda picture=image, token=generation, key=project_id: self.apply_modrinth_icon(
                        widget, picture, token, key
                    )
                )
            except Exception as error:
                log_launcher_error(f"Modrinth icon project={project_id}", error)
                return

        threading.Thread(target=worker, daemon=True).start()

    def apply_modrinth_icon(self, widget, image, generation, project_id=None):
        try:
            if (
                generation != self.mod_search_generation
                or not widget.winfo_exists()
                or not self.mod_context_alive()
            ):
                return
            widget.set_icon(project_id, image, generation)
        except (AttributeError, tk.TclError):
            pass

    def update_mod_progress(self, percent, message):
        if not self.mod_context_alive():
            return
        value = max(0, min(100, int(percent)))
        dashboard = getattr(self, "launch_dashboard", None)
        if dashboard is not None:
            dashboard.set_progress(value=value / 100, message=message, visible=True)
        else:
            self.progress.set(value / 100)
            self.progress_percent.configure(text=f"{value}%")
            self.progress_text.set(message)
        self.mod_progress_area.grid()
        self.mod_progress.set(value / 100)
        self.mod_progress_percent.configure(text=f"{value}%")
        self.mod_progress_text.set(message)
        self.mod_status.set(message)

    def run_modrinth_operation(self, label, operation, complete):
        if not self.mod_context_alive() or self.mod_context["busy"]:
            return
        context = self.mod_context
        context["busy"] = True
        operation_id = "modrinth:" + context["instance"]["id"]
        self.show_install_progress(operation_id)
        self.mod_progress_area.grid()
        self.mod_progress.set(0)
        self.mod_progress_percent.configure(text="0%")
        self.mod_progress_text.set(label)
        self.mod_status.set(label)

        def worker():
            try:
                result = operation()
                self.post_ui(
                    lambda payload=result: self.finish_modrinth_operation(
                        operation_id, payload, complete
                    )
                )
            except Exception as error:
                log_launcher_error(operation_id, error)
                self.post_ui(
                    lambda detail=str(error): self.fail_modrinth_operation(operation_id, detail)
                )

        threading.Thread(target=worker, daemon=True).start()

    def finish_modrinth_operation(self, operation_id, result, complete):
        self.finish_install_progress(operation_id)
        if not self.mod_context_alive():
            return
        self.mod_context["busy"] = False
        self.mod_progress_area.grid_remove()
        complete(result)

    def fail_modrinth_operation(self, operation_id, detail):
        self.finish_install_progress(operation_id)
        if self.mod_context_alive():
            self.mod_context["busy"] = False
            self.mod_progress_area.grid_remove()
            self.mod_status.set("Mod operation failed")
            self.mod_check_updates_button.configure(state="normal", text="Check updates")
            self.mod_search_button.configure(state="normal", text="Search")
        self.show_notice("Mod operation failed", detail, danger=True)

    def install_modrinth_project(self, project):
        project_id = str(project.get("project_id", ""))
        title = project.get("title", "mod")
        manager = self.mod_context["manager"]

        def complete(_record):
            self.mod_status.set(f"Installed {title} and its required dependencies")
            self.status.set(f"Installed Modrinth mod {title}")
            self.modrinth_updates.pop(project_id, None)
            self.refresh_modrinth_installed()
            self.refresh_instances()
            self.search_modrinth(reset=False)

        self.run_modrinth_operation(
            f"Installing {title}…",
            lambda: manager.install_project(project_id, project),
            complete,
        )

    def refresh_modrinth_installed(self):
        if not self.mod_context_alive():
            return
        scroll = self.mod_installed_scroll
        try:
            records = self.mod_context["manager"].installed()
        except Exception as error:
            self.render_modrinth_empty(scroll, "Could not read installed mods", str(error))
            return
        tracked = sum(record.get("provider") != "local" for record in records)
        local = len(records) - tracked
        self.mod_installed_summary.configure(
            text=f"{len(records)} installed  •  {tracked} with update sources  •  {local} local-only"
        )
        if not records:
            self.render_modrinth_empty(
                scroll,
                "No mods installed",
                "Browse Modrinth or add a JAR to this instance's Mods Folder.",
            )
            return
        scroll.show_installed(records, self.modrinth_updates)

    def toggle_modrinth_record(self, record):
        enable = not bool(record.get("enabled", True))
        title = record.get("title", "mod")
        manager = self.mod_context["manager"]

        def complete(_result):
            self.refresh_modrinth_installed()
            self.mod_status.set(f"{'Enabled' if enable else 'Disabled'} {title}")

        self.run_modrinth_operation(
            f"{'Enabling' if enable else 'Disabling'} {title}…",
            lambda: manager.set_enabled(
                record.get("record_id") or record.get("project_id"), enable
            ),
            complete,
        )

    def confirm_remove_modrinth(self, record):
        title = record.get("title", "this mod")
        manager = self.mod_context["manager"]

        def remove():
            record_id = record.get("record_id") or record.get("project_id")

            def complete(result):
                if result.get("kept"):
                    self.mod_status.set(
                        f"{title} remains installed because another mod requires it"
                    )
                else:
                    self.mod_status.set(f"Removed {title} and unused dependencies")
                self.modrinth_updates.pop(record_id, None)
                self.refresh_modrinth_installed()
                self.refresh_instances()
                self.render_modrinth_updates(list(self.modrinth_updates.values()))
                self.search_modrinth(reset=False)

            self.run_modrinth_operation(
                f"Removing {title}…",
                lambda: manager.remove_project(record_id),
                complete,
            )

        self.confirm_action(
            "Remove mod?",
            f"Remove {title} from this instance? Required dependencies that are no longer used will also be removed.",
            remove,
        )

    def check_modrinth_updates(self):
        if not self.mod_context_alive() or self.mod_context["busy"]:
            return
        manager = self.mod_context["manager"]
        self.mod_check_updates_button.configure(state="disabled", text="Checking…")

        def complete(updates):
            self.modrinth_updates = {
                item["record"].get("record_id") or item["record"].get("project_id"): item
                for item in updates
            }
            self.mod_check_updates_button.configure(state="normal", text="Check updates")
            self.mod_update_all_button.configure(state="normal" if updates else "disabled")
            self.mod_update_summary.configure(
                text=f"{len(updates)} compatible update{'s' if len(updates) != 1 else ''} available"
            )
            self.render_modrinth_updates(updates)
            self.refresh_modrinth_installed()
            self.mod_status.set("Update check complete")

        self.run_modrinth_operation(
            "Checking installed mods for updates…", manager.check_updates, complete
        )

    def render_modrinth_updates(self, updates):
        if not self.mod_context_alive():
            return
        if not updates:
            self.render_modrinth_empty(
                self.mod_updates_scroll,
                "No updates listed",
                "Run Check updates to compare every installed mod with its available compatible source.",
            )
            return
        self.mod_updates_scroll.show_updates(updates)

    def update_modrinth_project(self, record):
        title = record.get("title", "mod")
        manager = self.mod_context["manager"]
        record_id = record.get("record_id") or record.get("project_id")

        def complete(_result):
            self.modrinth_updates.pop(record_id, None)
            remaining = list(self.modrinth_updates.values())
            self.render_modrinth_updates(remaining)
            self.mod_update_all_button.configure(state="normal" if remaining else "disabled")
            self.mod_update_summary.configure(
                text=f"{len(remaining)} compatible update{'s' if len(remaining) != 1 else ''} available"
            )
            self.refresh_modrinth_installed()
            self.refresh_instances()
            self.mod_status.set(f"Updated {title}")

        self.run_modrinth_operation(
            f"Updating {title}…",
            lambda: manager.update_record(record),
            complete,
        )

    def update_all_modrinth(self):
        if not self.mod_context_alive() or self.mod_context["busy"] or not self.modrinth_updates:
            return
        updates = list(self.modrinth_updates.values())
        manager = self.mod_context["manager"]

        def operation():
            results = []
            for index, item in enumerate(updates):
                record = item["record"]
                percent = int((index / max(1, len(updates))) * 100)
                self.post_ui(
                    lambda value=percent, name=record.get("title", "mod"): self.update_mod_progress(
                        value, f"Updating {name}…"
                    )
                )
                results.append(manager.update_record(record))
            return results

        def complete(_results):
            self.modrinth_updates = {}
            self.mod_update_all_button.configure(state="disabled")
            self.mod_update_summary.configure(text="0 compatible updates available")
            self.render_modrinth_updates([])
            self.refresh_modrinth_installed()
            self.refresh_instances()
            self.mod_status.set("All mods with compatible update sources are up to date")

        self.run_modrinth_operation("Updating all compatible mods…", operation, complete)

    def refresh_accounts(self):
        accounts = self.store.data["accounts"]
        active_id = self.store.data["settings"].get("active_account", "")
        account_ids = {account["id"] for account in accounts}
        if self.selected_account_id not in account_ids:
            self.selected_account_id = (
                active_id if active_id in account_ids else accounts[0]["id"] if accounts else None
            )
        self.launch_dashboard.refresh()

    def select_account(self, ident):
        self.selected_account_id = ident
        self.refresh_accounts()

    def create_instance(self):
        window, body = self.make_dialog("Create instance", 610, 690)
        ctk.CTkLabel(
            body, text="Create Minecraft instance", text_color=TEXT, font=self.font_title
        ).pack(anchor="w", padx=26, pady=(24, 3))
        ctk.CTkLabel(
            body,
            text="Choose a version and loader. Downloads begin after creation.",
            text_color=MUTED,
            font=self.font_small,
        ).pack(anchor="w", padx=26, pady=(0, 18))

        name = tk.StringVar(value="")
        version = tk.StringVar(value=self.fallback_versions()[0])
        loader = tk.StringVar(value="Fabric")
        self.dialog_field(
            body,
            "INSTANCE NAME",
            ctk.CTkEntry(
                body,
                textvariable=name,
                height=43,
                corner_radius=10,
                fg_color=DARK_SURFACE,
                border_color=BORDER,
                placeholder_text="Optional — defaults to version and loader",
                font=self.font_body,
            ),
        )
        version_box = ctk.CTkComboBox(
            body,
            variable=version,
            values=list(self.fallback_versions()),
            state="readonly",
            height=43,
            corner_radius=10,
            fg_color=DARK_SURFACE,
            border_color=BORDER,
            button_color=CONTROL_SURFACE,
            button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=SURFACE_ALT,
            dropdown_hover_color=SURFACE_HOVER,
            font=self.font_body,
            dropdown_font=self.font_body,
        )
        self.dialog_field(body, "MINECRAFT VERSION", version_box)
        loader_box = ctk.CTkOptionMenu(
            body,
            variable=loader,
            values=["Vanilla", "Fabric", "Forge", "NeoForge", "Quilt"],
            height=43,
            corner_radius=10,
            fg_color=DARK_SURFACE,
            button_color=CONTROL_SURFACE,
            button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=SURFACE_ALT,
            dropdown_hover_color=SURFACE_HOVER,
            font=self.font_body,
            dropdown_font=self.font_body,
        )
        self.dialog_field(body, "LOADER", loader_box)

        essential_choices = (
            ("meteor-client", "Meteor Client"),
            ("trouser-streak", "Trouser Streak"),
            ("zazus-server-seeker", "Zazu's Server Seeker"),
            ("fabric-api", "Fabric API"),
        )
        essential_vars = {key: tk.BooleanVar(value=True) for key, _label in essential_choices}
        essentials = ctk.CTkFrame(
            body, fg_color=DARK_SURFACE, corner_radius=11, border_width=1, border_color=BORDER
        )
        essentials.pack(fill="x", padx=26, pady=(9, 2))
        ctk.CTkLabel(
            essentials,
            text="BREAKBLOCKS ESSENTIALS — FABRIC ONLY",
            text_color=MUTED,
            font=ctk.CTkFont(self.ui_font, 9, "bold"),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(11, 4))
        ctk.CTkLabel(
            essentials,
            text="Install the latest compatible builds when this instance is created.",
            text_color=MUTED,
            font=self.font_small,
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 5))
        essentials_grid = ctk.CTkFrame(essentials, fg_color="transparent")
        essentials_grid.pack(fill="x", padx=10, pady=(0, 10))
        essentials_grid.grid_columnconfigure((0, 1), weight=1)
        essential_checks = []
        for index, (key, label) in enumerate(essential_choices):
            check = ctk.CTkCheckBox(
                essentials_grid,
                text=label,
                variable=essential_vars[key],
                onvalue=True,
                offvalue=False,
                checkbox_width=21,
                checkbox_height=21,
                corner_radius=5,
                fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
                border_color=BORDER,
                font=self.font_small,
            )
            check.grid(row=index // 2, column=index % 2, sticky="w", padx=6, pady=6)
            essential_checks.append(check)

        def loader_changed(selected):
            enabled = selected == "Fabric"
            for check in essential_checks:
                check.configure(state="normal" if enabled else "disabled")

        loader_box.configure(command=loader_changed)
        loader_changed(loader.get())
        threading.Thread(
            target=self.load_versions, args=(window, version_box, version), daemon=True
        ).start()

        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", padx=26, pady=(18, 24))
        ctk.CTkButton(
            buttons,
            text="Cancel",
            command=window.destroy,
            width=105,
            height=42,
            corner_radius=10,
            fg_color=SURFACE_ALT,
            hover_color=SURFACE_HOVER,
            font=self.font_button,
        ).pack(side="right")

        def save():
            selected_version = version.get()
            selected_loader = loader.get()
            selected_essentials = [
                key
                for key, _label in essential_choices
                if selected_loader == "Fabric" and essential_vars[key].get()
            ]
            instance_name = name.get().strip() or f"{selected_version} {selected_loader}"
            ident = (
                re.sub(r"[^a-z0-9]+", "-", instance_name.lower()).strip("-")
                + "-"
                + uuid.uuid4().hex[:6]
            )
            self.store.data["instances"].append(
                {
                    "id": ident,
                    "name": instance_name,
                    "version": selected_version,
                    "loader": selected_loader,
                    "memory": self.memory.get(),
                    "installed": False,
                    "icon": default_instance_icon(ident),
                    "playtime_seconds": 0,
                    "essential_mods": selected_essentials,
                }
            )
            (self.store.instances / ident / "minecraft").mkdir(parents=True)
            self.store.save()
            self.selected_instance_id = ident
            self.refresh_instances()
            window.destroy()
            self.start_install(ident, selected_version, selected_loader, selected_essentials)

        ctk.CTkButton(
            buttons,
            text="Create instance",
            command=save,
            width=145,
            height=42,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self.font_button,
        ).pack(side="right", padx=(0, 9))

    def dialog_field(self, parent, title, widget):
        ctk.CTkLabel(
            parent, text=title, text_color=MUTED, font=ctk.CTkFont(self.ui_font, 9, "bold")
        ).pack(anchor="w", padx=26, pady=(7, 5))
        widget.pack(fill="x", padx=26, pady=(0, 7))

    def fallback_versions(self):
        return tuple(
            "26.2 26.1 1.21.11 1.21.10 1.21.9 1.21.8 1.21.7 1.21.6 1.21.5 1.21.4 1.21.3 1.21.2 1.21.1 1.21 1.20.6 1.20.5 1.20.4 1.20.3 1.20.2 1.20.1 1.20 1.19.4 1.19.3 1.19.2 1.19.1 1.19 1.18.2 1.18.1 1.18 1.17.1 1.17 1.16.5 1.16.4 1.16.3 1.16.2 1.16.1 1.16 1.15.2 1.15.1 1.15 1.14.4 1.14.3 1.14.2 1.14.1 1.14 1.13.2 1.13.1 1.13 1.12.2 1.12.1 1.12 1.11.2 1.11.1 1.11 1.10.2 1.10.1 1.10 1.9.4 1.9.3 1.9.2 1.9.1 1.9 1.8.9 1.8.8 1.8.7 1.8.6 1.8.5 1.8.4 1.8.3 1.8.2 1.8.1 1.8 1.7.10 1.7.9 1.7.8 1.7.7 1.7.6 1.7.5 1.7.4 1.7.3 1.7.2 1.6.4 1.6.2 1.6.1 1.6 1.5.2 1.5.1 1.5 1.4.7 1.4.6 1.4.5 1.4.4 1.4.2 1.3.2 1.3.1 1.2.5 1.2.4 1.2.3 1.2.2 1.2.1 1.1 1.0.1 1.0".split()
        )

    def load_versions(self, window, box, value):
        try:
            request = urllib.request.Request(
                minecraft_backend.MANIFEST, headers={"User-Agent": APP_USER_AGENT}
            )
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
        if not has_verified_minecraft_ownership(self.store.data["accounts"]):
            self.show_notice(
                "Minecraft ownership required",
                "Sign in with a Microsoft account that owns Minecraft: Java Edition before "
                "adding an Offline profile. Offline profiles are for legitimate local or "
                "offline play; they do not bypass ownership.",
                danger=True,
            )
            return

        window, body = self.make_dialog("Add offline account", 500, 350)
        ctk.CTkLabel(body, text="Add offline account", text_color=TEXT, font=self.font_title).pack(
            anchor="w", padx=26, pady=(25, 3)
        )
        ctk.CTkLabel(
            body,
            text=(
                "Offline profiles use a local username and do not authenticate each launch. "
                "They are available only after this launcher has verified ownership through "
                "Microsoft."
            ),
            text_color=MUTED,
            font=self.font_small,
            wraplength=440,
            justify="left",
        ).pack(anchor="w", padx=26, pady=(0, 19))
        name = tk.StringVar()
        entry = ctk.CTkEntry(
            body,
            textvariable=name,
            height=45,
            corner_radius=10,
            fg_color=DARK_SURFACE,
            border_color=BORDER,
            placeholder_text="Minecraft username",
            font=self.font_body,
        )
        self.dialog_field(body, "USERNAME — 3 TO 16 CHARACTERS", entry)
        entry.focus_set()
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", padx=26, pady=(22, 24))
        ctk.CTkButton(
            buttons,
            text="Cancel",
            command=window.destroy,
            width=100,
            height=42,
            corner_radius=10,
            fg_color=SURFACE_ALT,
            hover_color=SURFACE_HOVER,
            font=self.font_button,
        ).pack(side="right")

        def save():
            username = name.get().strip()
            if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", username):
                self.show_notice(
                    "Invalid username", "Use 3–16 letters, numbers or underscores.", danger=True
                )
                return
            # Minecraft's offline UUID format is specified as a name-based MD5 UUID.
            raw = hashlib.md5(
                ("OfflinePlayer:" + username).encode(), usedforsecurity=False
            ).digest()
            account_id = str(uuid.UUID(bytes=raw, version=3))
            self.store.data["accounts"] = [
                item for item in self.store.data["accounts"] if item["id"] != account_id
            ]
            self.store.data["accounts"].append(
                {"id": account_id, "name": username, "type": "Offline"}
            )
            if not self.store.data["settings"].get("active_account"):
                self.store.data["settings"]["active_account"] = account_id
            self.store.save()
            self.selected_account_id = account_id
            self.refresh_accounts()
            window.destroy()
            self.status.set(f"Added offline account {username}")

        ctk.CTkButton(
            buttons,
            text="Add account",
            command=save,
            width=130,
            height=42,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self.font_button,
        ).pack(side="right", padx=(0, 9))

    def add_microsoft(self):
        window, body = self.make_dialog("Add Microsoft account", 590, 430)
        ctk.CTkLabel(body, text="Microsoft sign-in", text_color=TEXT, font=self.font_title).pack(
            pady=(25, 3)
        )
        message = tk.StringVar(value="Requesting a secure sign-in code…")
        ctk.CTkLabel(
            body,
            textvariable=message,
            text_color=MUTED,
            font=self.font_small,
            wraplength=510,
            justify="center",
        ).pack(padx=26, pady=(0, 18))
        code = tk.StringVar(value="—")
        code_box = ctk.CTkEntry(
            body,
            textvariable=code,
            state="readonly",
            height=58,
            corner_radius=12,
            justify="center",
            fg_color=DARK_SURFACE,
            border_color=BORDER,
            text_color=TEXT,
            font=ctk.CTkFont(self.ui_font, 22, "bold"),
        )
        code_box.pack(fill="x", padx=55)
        status = tk.StringVar(value="Waiting for Microsoft…")
        ctk.CTkLabel(body, textvariable=status, text_color=MUTED, font=self.font_small).pack(
            pady=(12, 10)
        )
        button_row = ctk.CTkFrame(body, fg_color="transparent")
        button_row.pack(pady=(7, 12))
        open_button = ctk.CTkButton(
            button_row,
            text="Open Microsoft sign-in",
            state="disabled",
            width=190,
            height=43,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self.font_button,
        )
        open_button.pack(side="left", padx=5)

        def copy_code():
            self.clipboard_clear()
            self.clipboard_append(code.get())
            status.set("Code copied")

        copy_button = ctk.CTkButton(
            button_row,
            text="Copy code",
            command=copy_code,
            state="disabled",
            width=110,
            height=43,
            corner_radius=10,
            fg_color=SURFACE_ALT,
            hover_color=SURFACE_HOVER,
            font=self.font_button,
        )
        copy_button.pack(side="left", padx=5)
        ctk.CTkButton(
            body,
            text="Cancel",
            command=window.destroy,
            width=90,
            height=36,
            corner_radius=9,
            fg_color="transparent",
            hover_color=SURFACE_HOVER,
            text_color=MUTED,
            font=self.font_small,
        ).pack()

        def worker():
            try:
                log_launcher_message("Microsoft sign-in", "Requesting device code")
                device = self.http_form(
                    "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode",
                    {
                        "client_id": MICROSOFT_CLIENT_ID,
                        "scope": "XboxLive.SignIn XboxLive.offline_access",
                    },
                    "Microsoft device sign-in",
                )
                log_launcher_message("Microsoft sign-in", "Device code received")

                def show_code():
                    if not window.winfo_exists():
                        return
                    message.set(device["message"])
                    code.set(device["user_code"])
                    status.set("Complete sign-in in your browser")
                    open_button.configure(
                        state="normal",
                        command=lambda: self.open_external_url(
                            device["verification_uri"], "Microsoft sign-in"
                        ),
                    )
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
                    "minecraft_token_expires_at": profile["minecraft_token_expires_at"],
                    "entitlement_verified_at": profile["entitlement_verified_at"],
                    "skin": self.download_skin(profile),
                }
                self.store.data["accounts"] = [
                    item for item in self.store.data["accounts"] if item["id"] != account["id"]
                ] + [account]
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
                log_launcher_error("Microsoft sign-in", error)
                self.after(
                    0,
                    lambda detail=str(error): (
                        status.set("Sign-in failed: " + detail) if window.winfo_exists() else None
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def remove_instance(self):
        instance = next(
            (
                item
                for item in self.store.data["instances"]
                if item["id"] == self.selected_instance_id
            ),
            None,
        )
        if not instance:
            self.show_notice("Select an instance", "Choose the instance you want to remove first.")
            return

        def remove():
            target = (self.store.instances / instance["id"]).resolve()
            if target.parent == self.store.instances.resolve():
                shutil.rmtree(target, ignore_errors=True)
            self.store.data["instances"] = [
                item for item in self.store.data["instances"] if item["id"] != instance["id"]
            ]
            self.selected_instance_id = None
            self.store.save()
            self.refresh_instances()
            self.status.set(f"Removed {instance['name']}")

        self.confirm_action(
            "Remove instance?",
            f"{instance['name']} and its Minecraft files will be permanently removed.",
            remove,
        )

    def remove_account(self):
        account = next(
            (
                item
                for item in self.store.data["accounts"]
                if item["id"] == self.selected_account_id
            ),
            None,
        )
        if not account:
            self.show_notice("Select an account", "Choose the account you want to remove first.")
            return

        def remove():
            self.store.data["accounts"] = [
                item for item in self.store.data["accounts"] if item["id"] != account["id"]
            ]
            if self.store.data["settings"].get("active_account") == account["id"]:
                remaining = self.store.data["accounts"]
                self.store.data["settings"]["active_account"] = (
                    remaining[0]["id"] if remaining else ""
                )
            self.selected_account_id = None
            self.store.save()
            self.refresh_accounts()
            self.status.set(f"Removed {account['name']}")

        self.confirm_action("Remove account?", f"Remove {account['name']} from {APP_NAME}?", remove)

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
        self.store.data["settings"].update(
            java=self.java.get().strip() or "auto",
            memory=self.memory.get(),
            keep_launcher_open=bool(self.keep_launcher_open.get()),
            update_enabled=bool(self.update_enabled.get()),
            update_channel=self.update_channel.get(),
            update_frequency=self.update_frequency.get(),
        )
        self.store.save()
        self.status.set("Settings saved")
        self.show_notice("Settings saved", "Your launcher and update settings have been updated.")

    def open_data_folder(self):
        try:
            open_system_target(self.store.root)
            self.status.set("Opened launcher folder")
        except Exception as error:
            self.show_notice("Could not open folder", str(error), danger=True)

    def check_updates_on_schedule(self):
        settings = self.store.data["settings"]
        if not settings.get("update_enabled", True):
            return
        frequency = settings.get("update_frequency", "daily")
        last_checked = float(settings.get("last_update_check", 0) or 0)
        try:
            due = launcher_update.should_check(last_checked, frequency)
        except ValueError as error:
            log_launcher_error("Update schedule", error)
            return
        if due:
            self.check_for_launcher_update(manual=False)

    def check_for_launcher_update(self, manual=False):
        if self.update_check_running:
            if manual:
                self.status.set("An update check is already running")
            return
        self.update_check_running = True
        self.check_update_button.configure(state="disabled", text="Checking…")
        self.update_status_text.set("Checking for launcher updates…")
        channel = self.update_channel.get()

        def worker():
            try:
                result = self.update_client.check(channel)
            except Exception as error:
                self.post_ui(
                    lambda detail=str(error): self.finish_update_check(None, detail, manual)
                )
                return
            self.post_ui(lambda: self.finish_update_check(result, "", manual))

        threading.Thread(target=worker, daemon=True, name="launcher-update-check").start()

    def finish_update_check(self, update, error, manual):
        self.update_check_running = False
        self.check_update_button.configure(state="normal", text="Check now")
        self.store.data["settings"]["last_update_check"] = int(time.time())
        self.store.save()
        if error:
            self.update_status_text.set("Update check failed")
            log_launcher_message("Launcher update", error)
            if manual:
                self.show_notice("Update check failed", error, danger=True)
            return
        if update is None:
            self.available_update = None
            self.update_status_text.set(f"{APP_VERSION} is up to date.")
            self.status.set("Launcher is up to date")
            if manual:
                self.show_notice("No update available", f"You are running {APP_VERSION}.")
            return

        self.available_update = update
        self.update_status_text.set(f"{update.display_version} is available.")
        self.status.set(f"Launcher update {update.display_version} is available")
        self.show_launcher_update(update)

    def show_launcher_update(self, update):
        window, body = self.make_dialog("Launcher update available", 570, 470)
        ctk.CTkLabel(
            body,
            text=f"{update.display_version} is available",
            text_color=TEXT,
            font=self.font_heading,
        ).pack(anchor="w", padx=24, pady=(23, 3))
        ctk.CTkLabel(
            body,
            text=(
                "The package will be verified before installation."
                if self.update_install_type == launcher_update.INSTALL_LINUX_DEB
                else "The package will be verified before the launcher asks to restart."
            ),
            text_color=MUTED,
            font=self.font_small,
        ).pack(anchor="w", padx=24, pady=(0, 12))
        notes = ctk.CTkTextbox(
            body,
            height=235,
            fg_color=DARK_SURFACE,
            border_width=1,
            border_color=BORDER,
            corner_radius=9,
            text_color=TEXT,
            font=self.font_body,
            wrap="word",
        )
        notes.pack(fill="both", expand=True, padx=24, pady=(0, 13))
        notes.insert("1.0", (update.notes or "No release notes were supplied.")[:6000])
        notes.configure(state="disabled")
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=(0, 20))
        buttons.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            buttons,
            text="Later",
            command=window.destroy,
            width=100,
            height=40,
            corner_radius=9,
            fg_color=CONTROL_SURFACE,
            hover_color=ACCENT_HOVER,
            font=self.font_button,
        ).grid(row=0, column=1, padx=(0, 8))
        button_text = {
            launcher_update.INSTALL_SOURCE: "Open release page",
            launcher_update.INSTALL_LINUX_DEB: "Download and install",
        }.get(self.update_install_type, "Download and restart")
        install_button = ctk.CTkButton(
            buttons,
            text=button_text,
            width=175,
            height=40,
            corner_radius=9,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self.font_button,
        )
        install_button.grid(row=0, column=2)
        if self.update_install_type == launcher_update.INSTALL_SOURCE:
            install_button.configure(
                command=lambda: self.open_external_url(update.release_url, "launcher release")
            )
        else:
            install_button.configure(
                command=lambda: self.download_launcher_update(update, window, install_button)
            )

    def download_launcher_update(self, update, dialog, button):
        button.configure(state="disabled", text="Downloading…")
        updates_root = self.store.root / "updates" / update.version

        def progress(percent, message):
            self.post_ui(
                lambda: (
                    button.configure(text=f"{message} {percent}%"),
                    self.status.set(f"{message} {percent}%"),
                )
            )

        def worker():
            try:
                archive = self.update_client.download(update, updates_root, progress)
                if self.update_install_type == launcher_update.INSTALL_LINUX_DEB:
                    progress(100, "Waiting for administrator approval")
                    launcher_update.install_debian_update(archive)
                    self.post_ui(lambda: self.finish_debian_update(update, dialog, button))
                    return
                staged = self.update_client.stage(archive, updates_root / "staged")
                install_root = launcher_update.detect_install_root(APP_DIR)
                self.post_ui(
                    lambda: self.finish_update_download(
                        update,
                        staged,
                        install_root,
                        dialog,
                        button,
                    )
                )
            except Exception as error:
                self.post_ui(
                    lambda detail=str(error): self.fail_update_download(detail, dialog, button)
                )

        threading.Thread(target=worker, daemon=True, name="launcher-update-download").start()

    def finish_debian_update(self, update, dialog, button):
        del button
        if dialog.winfo_exists():
            dialog.destroy()
        self.status.set(f"Installed {update.display_version} — restarting…")
        try:
            launcher_update.restart_debian_launcher()
        except Exception as error:
            self.status.set(f"Installed {update.display_version}")
            self.show_notice(
                "Update installed",
                f"The update was installed, but the launcher could not restart automatically. "
                f"Reopen it from your applications menu.\n\n{error}",
            )
            return
        self.after(150, self.close_launcher)

    def finish_update_download(self, update, staged, install_root, dialog, button):
        if install_root is None:
            button.configure(state="normal", text="Open release page")
            button.configure(
                command=lambda: self.open_external_url(update.release_url, "launcher release")
            )
            self.status.set("Update verified — source mode requires a manual install")
            self.show_notice(
                "Update verified",
                "This copy is running from source, so it cannot replace itself. "
                "Use the release page to install the packaged update.",
            )
            return
        try:
            launcher_update.start_self_update(staged, install_root)
        except Exception as error:
            self.fail_update_download(str(error), dialog, button)
            return
        if dialog.winfo_exists():
            dialog.destroy()
        self.status.set("Restarting to install the update…")
        self.after(100, self.close_launcher)

    def fail_update_download(self, detail, dialog, button):
        if dialog.winfo_exists():
            button.configure(state="normal", text="Try again")
        self.status.set("Launcher update failed")
        self.show_notice("Update failed", detail, danger=True)

    def show_install_progress(self, ident):
        self.active_installs.add(ident)
        dashboard = getattr(self, "launch_dashboard", None)
        if dashboard is not None:
            dashboard.set_progress(value=0, message="Preparing download…", visible=True)
            return
        self.progress.set(0)
        self.progress_percent.configure(text="0%")
        self.progress_text.set("Preparing download…")
        self.progress_area.grid()

    def finish_install_progress(self, ident):
        self.active_installs.discard(ident)
        if not self.active_installs:
            dashboard = getattr(self, "launch_dashboard", None)
            if dashboard is not None:
                dashboard.set_progress(value=0, message="", visible=False)
                return
            self.progress_area.grid_remove()
            self.progress.set(0)
            self.progress_percent.configure(text="")
            self.progress_text.set("")

    def start_install(
        self,
        ident,
        version,
        loader,
        essentials=None,
        rollback=None,
        success_message=None,
        failure_title="Installation failed",
    ):
        self.show_install_progress(ident)
        self.refresh_instances()

        def update(percent, text):
            def apply():
                value = max(0, min(100, percent)) / 100
                dashboard = getattr(self, "launch_dashboard", None)
                if dashboard is not None:
                    dashboard.set_progress(value=value, message=text, visible=True)
                else:
                    self.progress.set(value)
                    self.progress_percent.configure(text=f"{percent}%")
                    self.progress_text.set(text)

            self.post_ui(apply)

        def worker():
            try:
                minecraft_backend.Installer(
                    self.store.root,
                    update,
                    self.store.data["settings"].get("java", "auto"),
                ).install(self.store.instances / ident, version, loader)
                essential_results = []
                if loader == "Fabric" and essentials:
                    manager = modrinth_client.ModManager(
                        self.store.instances / ident,
                        version,
                        loader,
                        progress=update,
                    )
                    essential_results = manager.install_essentials(essentials)
                with self.store_lock:
                    for item in self.store.data["instances"]:
                        if item["id"] == ident:
                            item["installed"] = True
                    self.store.save()
                installed_count = sum(item["status"] == "installed" for item in essential_results)
                skipped = [item for item in essential_results if item["status"] != "installed"]

                def complete():
                    self.finish_install_progress(ident)
                    self.refresh_instances()
                    suffix = (
                        f" with {installed_count} BreakBlocks Essential{'s' if installed_count != 1 else ''}"
                        if essentials
                        else ""
                    )
                    self.status.set(success_message or ("Instance installed" + suffix))
                    if skipped:
                        details = "\n".join(
                            f"• {item['title']}: {item.get('error', 'No compatible build')}"
                            for item in skipped
                        )
                        self.show_notice(
                            "Instance installed — some Essentials skipped",
                            "Minecraft is ready. These optional mods could not be installed:\n\n"
                            + details,
                            danger=True,
                        )

                self.post_ui(complete)
            except Exception as error:
                if rollback:
                    with self.store_lock:
                        for item in self.store.data["instances"]:
                            if item["id"] == ident:
                                item.update(rollback)
                        self.store.save()

                def failed(detail=str(error)):
                    self.finish_install_progress(ident)
                    self.refresh_instances()
                    self.show_notice(failure_title, detail, danger=True)

                self.post_ui(failed)

        threading.Thread(target=worker, daemon=True).start()

    def launch(self):
        instance = next(
            (
                item
                for item in self.store.data["instances"]
                if item["id"] == self.selected_instance_id
            ),
            None,
        )
        active = self.store.data["settings"].get("active_account", "")
        account = next((item for item in self.store.data["accounts"] if item["id"] == active), None)
        if not instance:
            self.show_notice("Select an instance", "Choose a Minecraft instance first.")
            return
        if not account:
            self.show_notice(
                "Select a launch profile",
                "Choose the profile Minecraft should launch with in the Profiles panel.",
            )
            return
        if account.get("type") != "Microsoft" and not has_verified_minecraft_ownership(
            self.store.data["accounts"]
        ):
            self.show_notice(
                "Minecraft ownership required",
                "This Offline profile cannot launch until a Microsoft account that owns "
                "Minecraft: Java Edition has been verified on this installation.",
                danger=True,
            )
            return
        if not instance.get("installed"):
            self.show_notice("Instance not installed", "This instance has not finished installing.")
            return
        ident = instance["id"]
        if ident in self.running_instances or ident in self.launching_instances:
            self.show_notice(
                "Instance already running",
                "Close this Minecraft session before launching the same instance again.",
            )
            return

        launch_memory = int(instance.get("memory", self.store.data["settings"].get("memory", 4096)))
        self.launching_instances.add(ident)
        self.refresh_instances()

        def worker():
            try:
                if account["type"] == "Microsoft":
                    self.post_ui(lambda: self.status.set("Checking Microsoft session…"))
                    self.ensure_microsoft_session(account)
                launch_account = dict(account, memory=launch_memory)
                launched_at = time.time()
                started = time.monotonic()
                process = minecraft_backend.launch(self.store.instances / ident, launch_account)
                self.post_ui(
                    lambda: (
                        self.mark_instance_running(ident, started, process.pid),
                        self.status.set("Minecraft launched with " + account["name"]),
                    )
                )
                exit_code = process.wait()
                elapsed = max(0.0, time.monotonic() - started)
                self.record_instance_playtime(ident, elapsed, launched_at)
                crash_report = minecraft_backend.newest_crash_report(
                    self.store.instances / ident, launched_at
                )
                if not self.closing:
                    self.post_ui(
                        lambda code=exit_code, report=crash_report: self.finish_instance_session(
                            ident, elapsed, code, report
                        )
                    )
            except Exception as error:
                if not self.closing:
                    self.post_ui(
                        lambda detail=str(error): self.cancel_instance_launch(ident, detail)
                    )

        # This watcher intentionally outlives the window so playtime is saved
        # when someone closes the launcher while Minecraft is still running.
        threading.Thread(target=worker, daemon=False, name=f"playtime-{ident}").start()

    def http_form(self, url, data, stage=None):
        body = urllib.parse.urlencode(data).encode()
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": APP_USER_AGENT,
        }
        request = urllib.request.Request(url, data=body, headers=headers)
        hostname = urllib.parse.urlparse(url).hostname
        try:
            return json.load(open_online_request(request, timeout=20))
        except urllib.error.HTTPError as error:
            if stage:
                raise self.http_failure(stage, error) from None
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as primary_error:
            if (
                sys.platform.startswith("linux")
                and hostname == "login.microsoftonline.com"
                and shutil.which("curl")
            ):
                try:
                    return curl_form_json(url, body, headers, timeout=20)
                except urllib.error.HTTPError as error:
                    if stage:
                        raise self.http_failure(stage, error) from None
                    raise
                except (OSError, RuntimeError, TimeoutError) as fallback_error:
                    reason = fallback_error
            else:
                reason = getattr(primary_error, "reason", primary_error)
            label = stage or "Online request"
            raise RuntimeError(
                f"{label} could not reach Microsoft ({reason}). "
                "Check the internet connection, VPN or firewall, then try again."
            ) from None

    def http_json(self, url, data, token=None, extra_headers=None, stage="Online service"):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": APP_USER_AGENT,
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
            message = (
                detail.get("error_description")
                or detail.get("errorMessage")
                or detail.get("Message")
                or detail.get("message")
            )
        if not message:
            message = raw.strip() or getattr(error, "reason", "Request rejected")
        message = " ".join(str(message).split())[:500]
        if error.code == 429:
            retry_after = error.headers.get("Retry-After") if error.headers else None
            retry_note = (
                f" Try again in about {retry_after} seconds."
                if retry_after
                else " Please wait a few minutes and try again."
            )
            return ServiceRateLimitError(
                f"{stage} was temporarily rate-limited by Microsoft.{retry_note}"
            )
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
            {
                "Properties": {
                    "AuthMethod": "RPS",
                    "SiteName": "user.auth.xboxlive.com",
                    "RpsTicket": "d=" + msa,
                },
                "RelyingParty": "http://auth.xboxlive.com",
                "TokenType": "JWT",
            },
            extra_headers=contract_headers,
            stage="Xbox user authentication",
        )
        xsts = self.http_json(
            "https://xsts.auth.xboxlive.com/xsts/authorize",
            {
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl["Token"]]},
                "RelyingParty": "rp://api.minecraftservices.com/",
                "TokenType": "JWT",
            },
            extra_headers=contract_headers,
            stage="Minecraft authorization",
        )
        try:
            uhs = xsts["DisplayClaims"]["xui"][0]["uhs"]
            xsts_token = xsts["Token"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError(
                "Minecraft authorization returned an incomplete Xbox token"
            ) from None
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
            raise RuntimeError(
                "This Microsoft account does not currently own Minecraft: Java Edition"
            )
        profile = self.http_json(
            "https://api.minecraftservices.com/minecraft/profile",
            None,
            minecraft_token,
            stage="Minecraft profile lookup",
        )
        profile["minecraft_token"] = minecraft_token
        profile["entitlement_verified_at"] = int(time.time())
        try:
            expires_in = max(60, int(mc.get("expires_in", 0)))
        except (TypeError, ValueError):
            expires_in = 0
        profile["minecraft_token_expires_at"] = (
            time.time() + expires_in if expires_in else self.jwt_expiry(minecraft_token)
        )
        return profile

    @staticmethod
    def jwt_expiry(token):
        """Read the expiry claim from a Minecraft JWT without treating it as validation."""
        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            expiry = float(json.loads(base64.urlsafe_b64decode(payload.encode()))["exp"])
            return expiry if expiry > 0 else 0
        except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return 0

    def ensure_microsoft_session(self, account):
        """Reuse a valid Minecraft token and refresh only when it is close to expiry."""
        minecraft_token = account.get("minecraft_token", "")
        try:
            expires_at = float(account.get("minecraft_token_expires_at", 0))
        except (TypeError, ValueError):
            expires_at = 0

        if minecraft_token and not expires_at:
            expires_at = self.jwt_expiry(minecraft_token)
            if not expires_at:
                # 0.4.2 did not save expiry metadata. Its freshly issued token is
                # still preferable to an immediate duplicate exchange.
                expires_at = time.time() + 15 * 60
            account["minecraft_token_expires_at"] = expires_at
            self.store.save()

        if minecraft_token and expires_at > time.time() + MINECRAFT_TOKEN_REFRESH_MARGIN:
            return account

        try:
            return self.refresh_microsoft(account)
        except ServiceRateLimitError:
            # A token inside the refresh margin remains usable until its expiry.
            if minecraft_token and expires_at > time.time() + 30:
                return account
            raise

    def refresh_microsoft(self, account):
        refresh = account.get("refresh_token")
        if not refresh:
            raise RuntimeError("This Microsoft account must be signed in again")
        token = self.http_form(
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
            {
                "client_id": MICROSOFT_CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "scope": "XboxLive.SignIn XboxLive.offline_access",
            },
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
            minecraft_token_expires_at=profile["minecraft_token_expires_at"],
            entitlement_verified_at=profile["entitlement_verified_at"],
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
        request = urllib.request.Request(skins[0]["url"], headers={"User-Agent": APP_USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as source, open(path, "wb") as target:
            target.write(source.read())
        return str(path)

    def skin_head(self, path, size=42):
        try:
            skin = Image.open(path).convert("RGBA")
            head = skin.crop((8, 8, 16, 16)).resize((size, size), Image.Resampling.NEAREST)
            if skin.width >= 48:
                overlay = skin.crop((40, 8, 48, 16)).resize((size, size), Image.Resampling.NEAREST)
                head.alpha_composite(overlay)
            return ctk.CTkImage(light_image=head, dark_image=head, size=(size, size))
        except Exception:
            return None

    def load_asset(self, name, size, crop_transparent=False):
        try:
            image = Image.open(APP_DIR / "assets" / name).convert("RGBA")
            if crop_transparent:
                image = trim_transparent_square(image)
            return ctk.CTkImage(light_image=image, dark_image=image, size=size)
        except Exception:
            return None

    def make_dialog(self, title, width, height):
        window = ctk.CTkToplevel(self, fg_color=BG)
        self._modal_windows.add(window)
        window.title(title)
        window.resizable(False, False)
        x = self.winfo_x() + max(20, (self.winfo_width() - width) // 2)
        y = self.winfo_y() + max(20, (self.winfo_height() - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.transient(self)
        body = ctk.CTkFrame(
            window, fg_color=SURFACE, corner_radius=18, border_width=1, border_color=BORDER
        )
        body.pack(fill="both", expand=True, padx=14, pady=14)

        def dialog_closed(event):
            if event.widget is not window:
                return
            self._modal_windows.discard(window)
            # Some desktops can deliver the mouse release that closed a native
            # toplevel to the dashboard beneath it. Briefly suppress dashboard
            # actions so that release cannot open Create instance.
            self._modal_input_block_until = max(
                self._modal_input_block_until,
                time.monotonic() + 0.30,
            )

        def activate_dialog():
            try:
                if window.winfo_exists():
                    window.grab_set()
                    window.lift()
                    window.focus_set()
            except tk.TclError:
                pass

        window.bind("<Destroy>", dialog_closed, add="+")
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.after_idle(activate_dialog)
        return window, body

    def modal_action_blocked(self):
        if time.monotonic() < self._modal_input_block_until:
            return True
        for window in tuple(self._modal_windows):
            try:
                if window.winfo_exists():
                    return True
            except tk.TclError:
                continue
        return False

    def show_notice(self, title, message, danger=False):
        window, body = self.make_dialog(title, 470, 245)
        ctk.CTkLabel(
            body,
            text="!" if danger else "✓",
            width=45,
            height=45,
            corner_radius=22,
            fg_color="#4a2328" if danger else GREEN_BG,
            text_color=RED if danger else GREEN,
            font=ctk.CTkFont(self.ui_font, 20, "bold"),
        ).pack(pady=(23, 10))
        ctk.CTkLabel(body, text=title, text_color=TEXT, font=self.font_heading).pack()
        ctk.CTkLabel(
            body,
            text=message,
            text_color=MUTED,
            font=self.font_small,
            wraplength=400,
            justify="center",
        ).pack(padx=25, pady=(7, 14))
        ctk.CTkButton(
            body,
            text="Close",
            command=window.destroy,
            width=105,
            height=38,
            corner_radius=9,
            fg_color=RED if danger else ACCENT,
            hover_color=RED_HOVER if danger else ACCENT_HOVER,
            font=self.font_button,
        ).pack()

    def confirm_action(self, title, message, action):
        window, body = self.make_dialog(title, 490, 260)
        ctk.CTkLabel(
            body,
            text="!",
            width=45,
            height=45,
            corner_radius=22,
            fg_color="#4a2328",
            text_color=RED,
            font=ctk.CTkFont(self.ui_font, 20, "bold"),
        ).pack(pady=(24, 10))
        ctk.CTkLabel(body, text=title, text_color=TEXT, font=self.font_heading).pack()
        ctk.CTkLabel(
            body,
            text=message,
            text_color=MUTED,
            font=self.font_small,
            wraplength=420,
            justify="center",
        ).pack(padx=25, pady=(7, 15))
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack()
        ctk.CTkButton(
            buttons,
            text="Cancel",
            command=window.destroy,
            width=105,
            height=38,
            corner_radius=9,
            fg_color=SURFACE_ALT,
            hover_color=SURFACE_HOVER,
            font=self.font_button,
        ).pack(side="left", padx=5)

        def accept():
            window.destroy()
            action()

        ctk.CTkButton(
            buttons,
            text="Remove",
            command=accept,
            width=105,
            height=38,
            corner_radius=9,
            fg_color=RED,
            hover_color=RED_HOVER,
            font=self.font_button,
        ).pack(side="left", padx=5)


if __name__ == "__main__":
    if "--chat-browser" in sys.argv:
        import chat_browser as chat_browser_process

        raise SystemExit(chat_browser_process.main(sys.argv[1:]))
    Launcher().mainloop()
