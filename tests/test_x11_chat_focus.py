"""Exercise Linux chat foreground detection against a real X11 server."""

import os
import sys

import chat_browser


def test_chat_focus_follows_the_window_containing_the_host():
    if not sys.platform.startswith("linux") or not os.environ.get("DISPLAY"):
        return
    import tkinter as tk

    launcher = tk.Tk()
    launcher.geometry("320x200")
    host = tk.Frame(launcher, width=200, height=100)
    host.pack()
    other = tk.Toplevel(launcher)
    other.geometry("320x200+350+0")
    try:
        launcher.update()
        launcher.focus_force()
        launcher.update()
        assert chat_browser.launcher_has_foreground(host.winfo_id())

        other.focus_force()
        other.update()
        assert not chat_browser.launcher_has_foreground(host.winfo_id())
    finally:
        launcher.destroy()


if __name__ == "__main__":
    test_chat_focus_follows_the_window_containing_the_host()
    if sys.platform.startswith("linux") and os.environ.get("DISPLAY"):
        print("Passed X11 chat focus check")
    else:
        print("Skipped X11 chat focus check (no X11 display)")
