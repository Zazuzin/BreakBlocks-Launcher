@echo off
setlocal
cd /d "%~dp0"
set "ZAZU_PACKAGE_DIR=%~dp0"
set "SSL_CERT_FILE=%~dp0certs\cacert.pem"
set "TCL_LIBRARY=%~dp0runtime\tcl\tcl8.6"
set "TK_LIBRARY=%~dp0runtime\tcl\tk8.6"
set "PATH=%~dp0runtime;%~dp0runtime\bin;%PATH%"
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath $env:ZAZU_PACKAGE_DIR -Recurse -File | Unblock-File -ErrorAction SilentlyContinue" >nul 2>&1
start "Zazu Launcher" "%~dp0runtime\pythonw.exe" "%~dp0app\zazu_launcher_boot.pyw"
endlocal
