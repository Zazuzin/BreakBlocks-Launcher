"""Run public HTTPS checks using the packaged interpreter and bundled roots."""

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile


def check(executable, python_script=False):
    with tempfile.TemporaryDirectory(prefix="breakblocks-packaged-tls-") as temporary:
        folder = pathlib.Path(temporary)
        environment = dict(
            os.environ,
            LOCALAPPDATA=str(folder / "data"),
            XDG_STATE_HOME=str(folder / "state"),
            XDG_DATA_HOME=str(folder / "data"),
            SSL_CERT_DIR=str(folder / "missing-host-certificates"),
        )
        environment.pop("SSL_CERT_FILE", None)
        command = [sys.executable, str(executable)] if python_script else [str(executable)]
        result = subprocess.run(
            [*command, "--check-network"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=100,
        )
        log = (
            folder / "data/BreakBlocks Launcher/launcher.log"
            if os.name == "nt"
            else folder / "state/breakblocks-launcher/launcher.log"
        )
        output = (
            result.stdout
            + result.stderr
            + (log.read_text(errors="replace") if log.exists() else "")
        )
        assert result.returncode == 0, output
        report = next(
            json.loads(line)
            for line in output.splitlines()
            if line.startswith("{") and '"certificate_bundle"' in line
        )
        assert (
            pathlib.Path(report["certificate_bundle"])
            .resolve()
            .is_relative_to(executable.parent.resolve())
        ), output
        assert report["trusted_roots"] > 50, output
        for service in ("Modrinth", "GitHub updates", "Minecraft metadata"):
            assert f"Verified HTTPS certificate: {service}" in output, output
        print(output, flush=True)
        print("Packaged HTTPS checks passed using bundled trusted roots.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=pathlib.Path)
    parser.add_argument("--python-script", action="store_true")
    options = parser.parse_args()
    check(options.executable.resolve(strict=True), options.python_script)
