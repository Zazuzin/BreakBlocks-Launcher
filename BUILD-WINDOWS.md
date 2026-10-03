# Build the Windows package

The Windows release is built on 64-bit Windows with Python 3.12. Run these
commands from PowerShell in the source directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\packaging\windows\build.ps1
```

The finished ZIP is written to `dist-release`. Windows builds are unsigned and
may trigger browser or Windows warnings; see `PUBLISHING.md`.

The build script runs the formatter check, static checks, and every regression
test before packaging. It also includes the GPL licence, launcher policies, and
third-party licence files.
