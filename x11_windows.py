"""Small X11 window operations for embedded chat and its Linux overlay."""

from __future__ import annotations

import ctypes as C
from contextlib import contextmanager


class XError(C.Structure):
    _fields_ = [
        ("type", C.c_int),
        ("display", C.c_void_p),
        ("resource", C.c_ulong),
        ("serial", C.c_ulong),
        ("code", C.c_ubyte),
        ("request", C.c_ubyte),
        ("minor", C.c_ubyte),
    ]


class XKeyEvent(C.Structure):
    _fields_ = [
        ("type", C.c_int),
        ("serial", C.c_ulong),
        ("send_event", C.c_int),
        ("display", C.c_void_p),
        ("window", C.c_ulong),
        ("root", C.c_ulong),
        ("subwindow", C.c_ulong),
        ("time", C.c_ulong),
        ("x", C.c_int),
        ("y", C.c_int),
        ("x_root", C.c_int),
        ("y_root", C.c_int),
        ("state", C.c_uint),
        ("keycode", C.c_uint),
        ("same_screen", C.c_int),
    ]


class XEvent(C.Union):
    _fields_ = [("type", C.c_int), ("key", XKeyEvent), ("pad", C.c_long * 24)]


class ModifierMap(C.Structure):
    _fields_ = [("count", C.c_int), ("keys", C.POINTER(C.c_ubyte))]


class X11Windows:
    def __init__(self):
        self.lib = C.cdll.LoadLibrary("libX11.so.6")
        signatures = {
            "XOpenDisplay": (C.c_void_p, [C.c_char_p]),
            "XCloseDisplay": (C.c_int, [C.c_void_p]),
            "XDefaultRootWindow": (C.c_ulong, [C.c_void_p]),
            "XSetErrorHandler": (C.c_void_p, [C.c_void_p]),
            "XSync": (C.c_int, [C.c_void_p, C.c_int]),
            "XFlush": (C.c_int, [C.c_void_p]),
            "XFree": (C.c_int, [C.c_void_p]),
            "XQueryTree": (
                C.c_int,
                [
                    C.c_void_p,
                    C.c_ulong,
                    C.POINTER(C.c_ulong),
                    C.POINTER(C.c_ulong),
                    C.POINTER(C.POINTER(C.c_ulong)),
                    C.POINTER(C.c_uint),
                ],
            ),
            "XGetGeometry": (
                C.c_int,
                [
                    C.c_void_p,
                    C.c_ulong,
                    C.POINTER(C.c_ulong),
                    C.POINTER(C.c_int),
                    C.POINTER(C.c_int),
                    C.POINTER(C.c_uint),
                    C.POINTER(C.c_uint),
                    C.POINTER(C.c_uint),
                    C.POINTER(C.c_uint),
                ],
            ),
            "XTranslateCoordinates": (
                C.c_int,
                [
                    C.c_void_p,
                    C.c_ulong,
                    C.c_ulong,
                    C.c_int,
                    C.c_int,
                    C.POINTER(C.c_int),
                    C.POINTER(C.c_int),
                    C.POINTER(C.c_ulong),
                ],
            ),
            "XReparentWindow": (C.c_int, [C.c_void_p, C.c_ulong, C.c_ulong, C.c_int, C.c_int]),
            "XMapRaised": (C.c_int, [C.c_void_p, C.c_ulong]),
            "XMoveResizeWindow": (
                C.c_int,
                [C.c_void_p, C.c_ulong, C.c_int, C.c_int, C.c_uint, C.c_uint],
            ),
            "XGetInputFocus": (C.c_int, [C.c_void_p, C.POINTER(C.c_ulong), C.POINTER(C.c_int)]),
            "XSetInputFocus": (C.c_int, [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]),
            "XInternAtom": (C.c_ulong, [C.c_void_p, C.c_char_p, C.c_int]),
            "XGetWindowProperty": (
                C.c_int,
                [
                    C.c_void_p,
                    C.c_ulong,
                    C.c_ulong,
                    C.c_long,
                    C.c_long,
                    C.c_int,
                    C.c_ulong,
                    C.POINTER(C.c_ulong),
                    C.POINTER(C.c_int),
                    C.POINTER(C.c_ulong),
                    C.POINTER(C.c_ulong),
                    C.POINTER(C.POINTER(C.c_ubyte)),
                ],
            ),
            "XStringToKeysym": (C.c_ulong, [C.c_char_p]),
            "XKeysymToKeycode": (C.c_ubyte, [C.c_void_p, C.c_ulong]),
            "XGrabKey": (
                C.c_int,
                [C.c_void_p, C.c_int, C.c_uint, C.c_ulong, C.c_int, C.c_int, C.c_int],
            ),
            "XUngrabKey": (C.c_int, [C.c_void_p, C.c_int, C.c_uint, C.c_ulong]),
            "XPending": (C.c_int, [C.c_void_p]),
            "XNextEvent": (C.c_int, [C.c_void_p, C.POINTER(XEvent)]),
            "XGetModifierMapping": (C.POINTER(ModifierMap), [C.c_void_p]),
            "XFreeModifiermap": (C.c_int, [C.POINTER(ModifierMap)]),
            "XkbSetDetectableAutoRepeat": (C.c_int, [C.c_void_p, C.c_int, C.POINTER(C.c_int)]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self.lib, name)
            function.restype, function.argtypes = result, arguments
        self.display = self.lib.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError("Could not open the X11 display for BreakBlocks chat")
        self.root = self.lib.XDefaultRootWindow(self.display)
        self.grab = None
        self.hotkey_down = False
        supported = C.c_int()
        self.lib.XkbSetDetectableAutoRepeat(self.display, 1, C.byref(supported))

    @contextmanager
    def checked(self):
        """A disappearing foreign window must not invoke Xlib's fatal handler."""
        errors = []
        callback_type = C.CFUNCTYPE(C.c_int, C.c_void_p, C.POINTER(XError))
        previous = None

        @callback_type
        def handler(display, event):
            if display == self.display:
                errors.append(event.contents.code)
                return 0
            return callback_type(previous)(display, event) if previous else 0

        previous = self.lib.XSetErrorHandler(C.cast(handler, C.c_void_p))
        try:
            yield errors
        finally:
            self.lib.XSync(self.display, 0)
            self.lib.XSetErrorHandler(previous)

    def tree(self, window):
        root, parent, count = C.c_ulong(), C.c_ulong(), C.c_uint()
        children = C.POINTER(C.c_ulong)()
        with self.checked() as errors:
            valid = self.lib.XQueryTree(
                self.display,
                window,
                C.byref(root),
                C.byref(parent),
                C.byref(children),
                C.byref(count),
            )
            values = [children[index] for index in range(count.value)] if children else []
            if children:
                self.lib.XFree(children)
        return (parent.value, values) if valid and not errors else (0, [])

    def parent(self, window):
        return self.tree(window)[0]

    def children(self, window):
        return self.tree(window)[1]

    def bounds(self, window):
        root, child = C.c_ulong(), C.c_ulong()
        x, y = C.c_int(), C.c_int()
        width, height, border, depth = (C.c_uint() for _ in range(4))
        with self.checked() as errors:
            valid = self.lib.XGetGeometry(
                self.display,
                window,
                C.byref(root),
                C.byref(x),
                C.byref(y),
                C.byref(width),
                C.byref(height),
                C.byref(border),
                C.byref(depth),
            )
            if valid:
                valid = self.lib.XTranslateCoordinates(
                    self.display, window, self.root, 0, 0, C.byref(x), C.byref(y), C.byref(child)
                )
        return (x.value, y.value, width.value, height.value) if valid and not errors else None

    def property(self, window, name):
        atom = self.lib.XInternAtom(self.display, name.encode("ascii"), 0)
        kind, count, remaining = C.c_ulong(), C.c_ulong(), C.c_ulong()
        form = C.c_int()
        data = C.POINTER(C.c_ubyte)()
        value = 0
        with self.checked() as errors:
            self.lib.XGetWindowProperty(
                self.display,
                window,
                atom,
                0,
                1,
                0,
                0,
                C.byref(kind),
                C.byref(form),
                C.byref(count),
                C.byref(remaining),
                C.byref(data),
            )
            if data:
                if form.value == 32 and count.value:
                    value = C.cast(data, C.POINTER(C.c_ulong))[0]
                self.lib.XFree(data)
        return value if not errors else 0

    def foreground(self):
        focus, revert = C.c_ulong(), C.c_int()
        self.lib.XGetInputFocus(self.display, C.byref(focus), C.byref(revert))
        window = focus.value
        for _ in range(64):
            if window <= 1 or window == self.root:
                break
            pid = self.property(window, "_NET_WM_PID")
            if pid:
                return window, pid
            window = self.parent(window)
        return 0, 0

    def reparent(self, child, parent):
        with self.checked() as errors:
            self.lib.XReparentWindow(self.display, child, parent, 0, 0)
        return not errors and self.parent(child) == parent

    def show_and_resize(self, window, width, height):
        with self.checked() as errors:
            self.lib.XMoveResizeWindow(self.display, window, 0, 0, width, height)
            self.lib.XMapRaised(self.display, window)
        return not errors

    def focus(self, window):
        with self.checked():
            self.lib.XMapRaised(self.display, window)
            self.lib.XSetInputFocus(self.display, window, 2, 0)

    def grab_hotkey(self, window, shortcut):
        self.ungrab_hotkey()
        parts = shortcut.split("+")
        modifiers = sum({"Ctrl": 4, "Shift": 1, "Alt": 8}[part] for part in parts[:-1])
        name = parts[-1] if parts[-1].startswith("F") else parts[-1].lower()
        keycode = self.lib.XKeysymToKeycode(self.display, self.lib.XStringToKeysym(name.encode()))
        if not keycode:
            return False
        # Read Num Lock's actual modifier slot rather than assuming Mod2.
        num_key = self.lib.XKeysymToKeycode(self.display, self.lib.XStringToKeysym(b"Num_Lock"))
        mapping = self.lib.XGetModifierMapping(self.display)
        num_mask = 0
        if mapping:
            for index in range(8 * mapping.contents.count):
                if num_key and mapping.contents.keys[index] == num_key:
                    num_mask |= 1 << (index // mapping.contents.count)
            self.lib.XFreeModifiermap(mapping)
        variants = tuple(sorted({modifiers | locks for locks in (0, 2, num_mask, 2 | num_mask)}))
        self.grab = (window, keycode, variants)
        with self.checked() as errors:
            for mask in variants:
                self.lib.XGrabKey(self.display, keycode, mask, window, 0, 1, 1)
        if errors:
            self.ungrab_hotkey()
            return False
        return True

    def ungrab_hotkey(self):
        if self.grab:
            window, keycode, variants = self.grab
            with self.checked():
                for mask in variants:
                    self.lib.XUngrabKey(self.display, keycode, mask, window)
            self.grab = None
        self.hotkey_down = False

    def hotkey_pressed(self):
        pressed = False
        while self.lib.XPending(self.display):
            event = XEvent()
            self.lib.XNextEvent(self.display, C.byref(event))
            if self.grab and event.key.keycode == self.grab[1]:
                if event.type == 2 and not self.hotkey_down:
                    pressed = True
                    self.hotkey_down = True
                elif event.type == 3:
                    self.hotkey_down = False
        return pressed

    def close(self):
        if self.display:
            self.ungrab_hotkey()
            self.lib.XCloseDisplay(self.display)
            self.display = None
