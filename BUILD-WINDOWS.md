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

To run the launcher from source before packaging:

```powershell
.\.venv\Scripts\python.exe breakblocks_launcher_boot.pyw
```

The build script checks formatting and runs the seven Windows regression test
files before packaging. GitHub Actions calls this same script, using its Python
installation through the optional `-PythonExecutable` argument. The tests cover
chat, the Windows overlay, backups and transfers, recovery actions, diagnostics,
data migration and Minecraft launching.

The remaining test files use Linux data paths or Linux desktop behavior. Run
the complete suite on Linux as described in `README-SOURCE.txt`.

The package includes the GPL licence, launcher policies and third-party licence
files. The ZIP contains the application folder and everything needed to run it;
Python does not need to be installed on the user's computer.
