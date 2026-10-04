# Build the Linux packages

The tested target is 64-bit Ubuntu 24.04 with Python 3.12. Ubuntu's system
Python and Tk are used by the `.deb`; application dependencies are installed
into the package's vendor directory.

Install the build and desktop dependencies:

```bash
sudo apt install python3 python3-pip python3-venv python3-tk curl dpkg-dev \
  libegl1 libopengl0 libpulse0 libxkbcommon-x11-0 libxcb-cursor0 \
  libxcb-icccm4 libxcb-keysyms1 libxcb-shape0
```

## Ubuntu package

From the source directory:

```bash
bash packaging/linux/build-deb.sh
```

The script creates its own temporary build environment, checks formatting,
runs the complete test suite and collects dependency licences. The finished
`.deb` is written to `dist-release`. Install it with:

```bash
sudo apt install ./dist-release/BreakBlocks-Launcher-0.9.28-Ubuntu-amd64.deb
```

The package includes launcher and Minecraft desktop identities and dock icons.
For the additional X11 focus check, install `xvfb` and `xauth` and use the
command in `README-SOURCE.txt`.

## Portable Linux / Steam Deck package

Build this on Ubuntu, then run it in Steam Deck Desktop Mode. The commands
below match the portable packaging steps in the test workflow:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python tools/collect_dependency_licenses.py --output third-party-licenses
.venv/bin/python -m PyInstaller --noconfirm --clean BreakBlocksLauncher.spec
cp README.txt "dist/BreakBlocks Launcher/README.txt"
cp README-SteamDeck.txt "dist/BreakBlocks Launcher/README-SteamDeck.txt"
cp LICENSE PRIVACY.md TERMS.md THIRD-PARTY-NOTICES.md "dist/BreakBlocks Launcher/"
cp -R fonts third-party-licenses "dist/BreakBlocks Launcher/"
mv "dist/BreakBlocks Launcher" dist/BreakBlocks-Launcher
chmod +x "dist/BreakBlocks-Launcher/BreakBlocks Launcher"
mkdir -p dist-release
tar -C dist -czf dist-release/BreakBlocks-Launcher-0.9.28-SteamDeck-x86_64.tar.gz \
  BreakBlocks-Launcher
```

Run the development checks in `README-SOURCE.txt` before packaging. GitHub
Actions runs them and the X11 focus check before producing its downloads.
