"""Run chat regressions under a desktop window manager, inside xvfb-run."""

import argparse
import os
import pathlib
import subprocess
import sys
import time


def check(executable):
    desktop = subprocess.Popen(["openbox", "--sm-disable"], stdin=subprocess.DEVNULL)
    try:
        time.sleep(0.5)
        assert desktop.poll() is None, "The test window manager could not start"
        subprocess.run([sys.executable, "tests/test_x11_chat_overlay.py"], check=True)
        environment = dict(os.environ, QT_QPA_PLATFORM="wayland")
        # A desktop Qt preference must not turn the Tk chat child into a
        # separate Wayland window. Both frozen parent and child are checked.
        subprocess.run(
            [sys.executable, "tools/check_packaged_chat.py", str(executable)],
            env=environment,
            check=True,
        )
    finally:
        desktop.terminate()
        desktop.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=pathlib.Path)
    check(parser.parse_args().executable.resolve(strict=True))
