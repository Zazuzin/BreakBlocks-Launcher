BreakBlocks Launcher 0.9.28 Alpha - complete source

Windows, Ubuntu and Steam Deck use the same launcher code. This package
includes all modules, assets, fonts, tests, build scripts and licence files.
Start with SOURCE-REVIEW.md for a map of the code.

NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH
MOJANG OR MICROSOFT.

Requirements
------------
The tested build environment is Python 3.12 on 64-bit Windows or Ubuntu 24.04.
Source requires Python 3.10 or newer and Tk support. Use the pinned versions
in requirements.txt and requirements-dev.txt.

Windows
-------
Open PowerShell in the source directory:

  py -3.12 -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
  .\.venv\Scripts\python.exe breakblocks_launcher_boot.pyw

To check and build the Windows package:

  .\packaging\windows\build.ps1

See BUILD-WINDOWS.md for output and test-suite details.

Ubuntu / Linux
--------------
Install Python, Tk and the system libraries listed in BUILD-LINUX.md, then:

  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements-dev.txt
  .venv/bin/python breakblocks_launcher_boot.pyw

To check and build the Ubuntu package:

  bash packaging/linux/build-deb.sh

BUILD-LINUX.md also describes the portable Linux / Steam Deck package.

Development checks
------------------
From the source directory, using the environment's Python:

  python -m black --check --line-length 100 *.py tests tools
  python -m ruff check *.py tests tools

On Linux, run the complete suite:

  export PYTHONPATH="$PWD"
  for test_file in tests/test_*.py; do .venv/bin/python "$test_file" || exit; done

With xvfb and xauth installed, also run the desktop-focus regression:

  xvfb-run -a .venv/bin/python tests/test_x11_chat_focus.py

The Windows build script runs the eight Windows regression files. Some of
the remaining tests exercise Linux-specific data paths or desktop behavior.
Tests use temporary fixtures and do not require a real game or account.

Existing installations
----------------------
The launcher migrates older account, instance and chat-session folders on
first run. The historical folder-name constants in launcher_paths.py must
remain available for this migration. Product labels use BreakBlocks Launcher.

Distribution
------------
PUBLISHING.md describes version tags, draft releases, update manifests and
unsigned Windows packages. Build output is written to dist and dist-release;
those directories are excluded from source archives.

Licence and credits
-------------------
The original source is licensed under the GNU General Public License version
3 only; see LICENSE. README.md lists project credits. THIRD-PARTY-NOTICES.md
indexes dependency notices, and legal/ includes the font and Tk notices.
BreakBlocks branding, community artwork and third-party trademarks retain
their owners' terms.

Project: https://github.com/Zazuzin/BreakBlocks-Launcher
Launcher privacy: PRIVACY.md
Launcher terms: TERMS.md
