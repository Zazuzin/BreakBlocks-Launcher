"""Helpers for launching operating-system programs from a portable runtime."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from typing import Any

PORTABLE_RUNTIME_VARIABLES = (
    "PYTHONHOME",
    "PYTHONNOUSERSITE",
    "TCL_LIBRARY",
    "TK_LIBRARY",
    "FONTCONFIG_PATH",
    "FONTCONFIG_FILE",
    "SSL_CERT_FILE",
)


def system_process_environment(extra: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Return an environment that cannot leak bundled Ubuntu runtime settings."""
    environment = os.environ.copy()
    system_library_path = environment.pop("BREAKBLOCKS_SYSTEM_LD_LIBRARY_PATH", "")
    if system_library_path:
        environment["LD_LIBRARY_PATH"] = system_library_path
    else:
        environment.pop("LD_LIBRARY_PATH", None)
    for name in PORTABLE_RUNTIME_VARIABLES:
        environment.pop(name, None)
    if extra:
        environment.update({str(name): str(value) for name, value in extra.items()})
    return environment


def open_system_target(target: str | os.PathLike[str]) -> None:
    """Open a URL or path with the host desktop rather than the bundled runtime."""
    target_text = str(target)
    if os.name == "nt":
        os.startfile(target_text)
        return
    commands = (
        (("open", target_text),)
        if sys.platform == "darwin"
        else (
            ("xdg-open", target_text),
            ("gio", "open", target_text),
        )
    )
    failures = []
    for command in commands:
        executable = shutil.which(command[0])
        if not executable:
            continue
        try:
            process = subprocess.Popen(
                (executable, *command[1:]),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=system_process_environment(),
            )
            try:
                return_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                return
            if return_code == 0:
                return
            failures.append(f"{command[0]} exited with code {return_code}")
        except OSError as error:
            failures.append(f"{command[0]}: {error}")
    if failures:
        raise RuntimeError("; ".join(failures))
    raise RuntimeError("No desktop application opener is installed")
