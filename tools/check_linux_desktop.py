"""Run chat regressions under a desktop window manager, inside xvfb-run."""

import argparse
import os
import pathlib
import subprocess
import sys
import tempfile
import time


def check(executable=None, ubuntu_package=None):
    desktop = subprocess.Popen(["openbox", "--sm-disable"], stdin=subprocess.DEVNULL)
    try:
        time.sleep(0.5)
        assert desktop.poll() is None, "The test window manager could not start"
        subprocess.run([sys.executable, "tests/test_x11_chat_overlay.py"], check=True)
        environment = dict(os.environ, QT_QPA_PLATFORM="wayland")
        # A desktop Qt preference must not turn the Tk chat child into a
        # separate Wayland window. Both frozen parent and child are checked.
        if executable is not None:
            subprocess.run(
                [sys.executable, "tools/check_packaged_chat.py", str(executable)],
                env=environment,
                check=True,
            )
        if ubuntu_package is not None:
            with tempfile.TemporaryDirectory(prefix="breakblocks-deb-check-") as temporary:
                subprocess.run(
                    ["dpkg-deb", "--extract", str(ubuntu_package), temporary], check=True
                )
                script = (
                    pathlib.Path(temporary)
                    / "usr/lib/breakblocks-launcher/app/breakblocks_launcher.py"
                )
                subprocess.run(
                    [
                        sys.executable,
                        "tools/check_packaged_chat.py",
                        "--python-script",
                        str(script),
                    ],
                    env=environment,
                    check=True,
                )
                print(
                    "Ubuntu package started its vendored chat and repaired its native attachment.",
                    flush=True,
                )
    finally:
        desktop.terminate()
        desktop.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=pathlib.Path, nargs="?")
    parser.add_argument("--ubuntu-package", type=pathlib.Path)
    options = parser.parse_args()
    check(
        options.executable.resolve(strict=True) if options.executable else None,
        options.ubuntu_package,
    )
