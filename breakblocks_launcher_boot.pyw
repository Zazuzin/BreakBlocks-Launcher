import os
import pathlib
import sys
import traceback

from display_environment import enable_windows_per_monitor_dpi
from launcher_paths import launcher_data_root

enable_windows_per_monitor_dpi()

APP_DIR = pathlib.Path(__file__).resolve().parent
PACKAGE_DIR = APP_DIR.parent
RUNTIME_DIR = PACKAGE_DIR / "runtime"
PACKAGED_RUNTIME = (RUNTIME_DIR / "pythonw.exe").is_file()
if sys.platform.startswith("linux"):
    font_directory = next(
        (path for path in (PACKAGE_DIR / "fonts", APP_DIR / "fonts") if path.is_dir()),
        None,
    )
    if font_directory is not None:
        os.environ.setdefault("FONTCONFIG_PATH", str(font_directory))
        os.environ.setdefault("FONTCONFIG_FILE", "fonts.conf")
DATA_DIR = launcher_data_root(state=True)
if PACKAGED_RUNTIME:
    os.environ.setdefault("SSL_CERT_FILE", str(PACKAGE_DIR / "certs" / "cacert.pem"))
    os.environ.setdefault("TCL_LIBRARY", str(RUNTIME_DIR / "tcl" / "tcl8.6"))
    os.environ.setdefault("TK_LIBRARY", str(RUNTIME_DIR / "tcl" / "tk8.6"))
    os.environ["PATH"] = (
        str(RUNTIME_DIR)
        + os.pathsep
        + str(RUNTIME_DIR / "bin")
        + os.pathsep
        + os.environ.get("PATH", "")
    )

# Python 3.8+ uses a restricted DLL search path on Windows. Keep these handles
# alive for the whole process so extension modules can resolve their bundled DLLs.
DLL_DIRECTORY_HANDLES = []
if os.name == "nt" and PACKAGED_RUNTIME and hasattr(os, "add_dll_directory"):
    DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(RUNTIME_DIR)))
    DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(RUNTIME_DIR / "bin")))

sys.path.insert(0, str(APP_DIR))

log = open(DATA_DIR / "launcher.log", "a", encoding="utf-8", buffering=1)
sys.stdout = log
sys.stderr = log

try:
    if os.name == "nt" and PACKAGED_RUNTIME:
        import ctypes

        for dll_name in ("zlib1.dll", "tcl86t.dll", "tk86t.dll"):
            ctypes.WinDLL(str(RUNTIME_DIR / dll_name))
    if "--chat-browser" in sys.argv:
        from chat_browser import main as chat_browser_main

        raise SystemExit(chat_browser_main(sys.argv[1:]))
    from breakblocks_launcher import Launcher

    Launcher().mainloop()
except Exception:
    traceback.print_exc()
    log.flush()
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            "BreakBlocks Launcher could not start.\n\nThe error was saved to:\n"
            + str(DATA_DIR / "launcher.log"),
            "BreakBlocks Launcher",
            0x10,
        )
    except Exception:
        pass
