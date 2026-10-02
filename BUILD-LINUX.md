# Build the Ubuntu package

The tested Linux target is 64-bit Ubuntu with Python 3.12. Install the build
tools, then run the package script from the source directory:

```bash
sudo apt install python3 python3-pip python3-venv python3-tk curl dpkg-dev
./packaging/linux/build-deb.sh
```

The finished `.deb` is written to `dist-release`. Install it with:

```bash
sudo apt install ./dist-release/BreakBlocks-Launcher-0.9.20-Ubuntu-amd64.deb
```

This package deliberately uses Ubuntu's system Python and Tk while bundling its
other Python dependencies, including the Qt WebEngine chat surface. That is the
configuration that produced sharp native text and working Microsoft sign-in in
the tested system-Tk build. The package also installs matching desktop
identities for the launcher and Minecraft dock icons.
