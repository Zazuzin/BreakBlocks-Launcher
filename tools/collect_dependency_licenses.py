#!/usr/bin/env python3
"""Collect licence files for components shipped in launcher binaries."""

from __future__ import annotations

import argparse
import importlib.metadata
import pathlib
import shutil
import sys
import sysconfig
import tempfile

PACKAGES = {
    "customtkinter": "5.2.2",
    "darkdetect": "0.8.0",
    "Pillow": "12.3.0",
    "packaging": "25.0",
    "PySide6": "6.8.3",
    "PyInstaller": "6.16.0",
}
LICENCE_NAMES = ("license", "licence", "copying", "notice")
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


def licence_files(distribution: importlib.metadata.Distribution) -> list[pathlib.Path]:
    matches = []
    for item in distribution.files or ():
        if not any(name in item.name.lower() for name in LICENCE_NAMES):
            continue
        path = pathlib.Path(distribution.locate_file(item))
        if path.is_file():
            matches.append(path)
    return matches


def first_existing(candidates: list[pathlib.Path]) -> pathlib.Path | None:
    return next((path for path in candidates if path.is_file()), None)


def python_licence() -> pathlib.Path | None:
    roots = {
        pathlib.Path(sys.base_prefix),
        pathlib.Path(sys.prefix),
        pathlib.Path(sys.executable).resolve().parent,
        pathlib.Path(sysconfig.get_paths()["data"]),
    }
    candidates = []
    for root in roots:
        candidates.extend(
            (
                root / "LICENSE.txt",
                root / "LICENSE",
                root
                / "lib"
                / f"python{sys.version_info.major}.{sys.version_info.minor}"
                / "LICENSE.txt",
            )
        )
    return first_existing(candidates)


def tcl_tk_licences() -> list[pathlib.Path]:
    roots = {pathlib.Path(sys.base_prefix), pathlib.Path(sys.prefix)}
    candidates = [
        pathlib.Path("/usr/share/doc/tcl8.6/copyright"),
        pathlib.Path("/usr/share/doc/tk8.6/copyright"),
        PROJECT_ROOT / "legal" / "TCL-TK-LICENSE.txt",
    ]
    for root in roots:
        candidates.extend(
            (
                root / "tcl" / "tcl8.6" / "license.terms",
                root / "tcl" / "tk8.6" / "license.terms",
            )
        )
    matches = [path for path in candidates if path.is_file()]
    if matches:
        return list(dict.fromkeys(matches))
    for root in roots:
        try:
            matches.extend(root.glob("**/license.terms"))
        except OSError:
            pass
    return [path for path in dict.fromkeys(matches) if path.is_file()]


def collect(output: pathlib.Path) -> None:
    output = output.resolve()
    if output == output.parent or len(output.parts) < 3:
        raise ValueError("Refusing to use a broad output directory")

    with tempfile.TemporaryDirectory(prefix="breakblocks-licences-") as temporary:
        staging = pathlib.Path(temporary)
        index = ["BreakBlocks Launcher third-party licence files", ""]

        for package, required_version in PACKAGES.items():
            distribution = importlib.metadata.distribution(package)
            if distribution.version != required_version:
                raise RuntimeError(
                    f"{package} {distribution.version} is installed; expected {required_version}"
                )
            files = licence_files(distribution)
            if not files:
                raise RuntimeError(f"No licence file found for {package} {required_version}")
            package_directory = staging / f"{package.lower()}-{required_version}"
            package_directory.mkdir()
            for source in files:
                target = package_directory / source.name
                if target.exists():
                    target = package_directory / f"{source.parent.name}-{source.name}"
                shutil.copy2(source, target)
            index.append(f"- {package} {required_version}: {package_directory.name}/")

        python_source = python_licence()
        if python_source is None:
            raise RuntimeError("The bundled Python licence file could not be located")
        shutil.copy2(python_source, staging / "PYTHON-LICENSE.txt")
        index.append("- Python runtime: PYTHON-LICENSE.txt")

        tk_sources = tcl_tk_licences()
        if not tk_sources:
            raise RuntimeError("The bundled Tcl/Tk licence files could not be located")
        for index_number, source in enumerate(tk_sources, start=1):
            suffix = "" if len(tk_sources) == 1 else f"-{index_number}"
            shutil.copy2(source, staging / f"TCL-TK-LICENSE{suffix}.txt")
        index.append("- Tcl/Tk runtime: TCL-TK-LICENSE*.txt")

        inter_licence = PROJECT_ROOT / "legal" / "INTER-OFL.txt"
        if not inter_licence.is_file():
            raise RuntimeError("The Inter font licence file could not be located")
        inter_directory = staging / "inter-4.1"
        inter_directory.mkdir()
        shutil.copy2(inter_licence, inter_directory / "OFL.txt")
        index.append("- Inter 4.1: inter-4.1/OFL.txt")

        (staging / "README.txt").write_text("\n".join(index) + "\n", encoding="utf-8")
        if output.exists():
            shutil.rmtree(output)
        shutil.copytree(staging, output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=pathlib.Path)
    arguments = parser.parse_args()
    collect(arguments.output)


if __name__ == "__main__":
    main()
