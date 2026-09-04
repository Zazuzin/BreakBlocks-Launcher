import os
import pathlib
import sys
import traceback

APP_DIR = pathlib.Path(__file__).resolve().parent
PACKAGE_DIR = APP_DIR.parent
RUNTIME_DIR = PACKAGE_DIR / "runtime"
DATA_DIR = pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home() / "AppData/Local")) / "Zazu Launcher"
DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("SSL_CERT_FILE", str(PACKAGE_DIR / "certs" / "cacert.pem"))
os.environ.setdefault("TCL_LIBRARY", str(RUNTIME_DIR / "tcl" / "tcl8.6"))
os.environ.setdefault("TK_LIBRARY", str(RUNTIME_DIR / "tcl" / "tk8.6"))
os.environ["PATH"] = str(RUNTIME_DIR) + os.pathsep + str(RUNTIME_DIR / "bin") + os.pathsep + os.environ.get("PATH", "")

# Python 3.8+ uses a restricted DLL search path on Windows. Keep these handles
# alive for the whole process so extension modules can resolve their bundled DLLs.
DLL_DIRECTORY_HANDLES = []
if os.name == "nt" and hasattr(os, "add_dll_directory"):
    DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(RUNTIME_DIR)))
    DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(RUNTIME_DIR / "bin")))

sys.path.insert(0, str(APP_DIR))

log = open(DATA_DIR / "launcher.log", "a", encoding="utf-8", buffering=1)
sys.stdout = log
sys.stderr = log

try:
    if os.name == "nt":
        import ctypes
        for dll_name in ("zlib1.dll", "tcl86t.dll", "tk86t.dll"):
            ctypes.WinDLL(str(RUNTIME_DIR / dll_name))
    from zazu_launcher import Launcher
    Launcher().mainloop()
except Exception:
    traceback.print_exc()
    log.flush()
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "Zazu Launcher could not start.\n\nThe error was saved to:\n" + str(DATA_DIR / "launcher.log"),
            "Zazu Launcher",
            0x10,
        )
    except Exception:
        pass
