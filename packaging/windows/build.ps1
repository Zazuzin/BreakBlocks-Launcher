param(
    [string]$PythonExecutable
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = $PythonExecutable
if (-not $Python) {
    $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Create .venv with Python 3.12 and install requirements-dev.txt first."
}

Set-Location $ProjectRoot
& $Python -m black --check --line-length 100 *.py tests tools
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $Python -m ruff check *.py tests tools
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$env:PYTHONPATH = $ProjectRoot
@(
    "tests/test_chat_browser.py",
    "tests/test_windows_chat_overlay.py",
    "tests/test_instance_archives.py",
    "tests/test_instance_recovery_flow.py",
    "tests/test_launch_diagnostics.py",
    "tests/test_launcher_paths.py",
    "tests/test_minecraft_launch.py"
) | ForEach-Object {
    & $Python $_
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
}

$Licences = Join-Path $ProjectRoot "third-party-licenses"
& $Python tools/collect_dependency_licenses.py --output $Licences
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $Python -m PyInstaller --noconfirm --clean BreakBlocksLauncher.spec
if ($LASTEXITCODE) { exit $LASTEXITCODE }

$PackageRoot = Join-Path $ProjectRoot "dist\BreakBlocks Launcher"
Copy-Item README-Windows.txt (Join-Path $PackageRoot "README.txt") -Force
Copy-Item LICENSE, PRIVACY.md, TERMS.md, THIRD-PARTY-NOTICES.md $PackageRoot -Force
Copy-Item $Licences (Join-Path $PackageRoot "third-party-licenses") -Recurse -Force

$Output = Join-Path $ProjectRoot "dist-release"
New-Item -ItemType Directory -Path $Output -Force | Out-Null
$Version = & $Python -c "from app_config import APP_VERSION_NUMBER; print(APP_VERSION_NUMBER)"
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$Archive = Join-Path $Output "BreakBlocks-Launcher-$Version-Windows-x86_64.zip"
if (Test-Path -LiteralPath $Archive) { Remove-Item -LiteralPath $Archive -Force }
Compress-Archive -Path $PackageRoot -DestinationPath $Archive -CompressionLevel Optimal
Write-Host "Created $Archive"
