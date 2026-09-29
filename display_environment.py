"""Display setup that must run before Tk creates its first window."""

from __future__ import annotations

import ctypes
import os


def enable_windows_per_monitor_dpi() -> bool:
    """Prevent Windows from bitmap-scaling the launcher on high-DPI displays."""
    if os.name != "nt":
        return False

    try:
        context = ctypes.c_void_p(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(context):
            return True
    except (AttributeError, OSError):
        pass

    try:
        # PROCESS_PER_MONITOR_DPI_AWARE for Windows 8.1 and older Python/Tk builds.
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return True
    except (AttributeError, OSError):
        pass

    try:
        return bool(ctypes.windll.user32.SetProcessDPIAware())
    except (AttributeError, OSError):
        return False
