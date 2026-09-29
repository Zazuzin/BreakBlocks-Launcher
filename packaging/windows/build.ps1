$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Create .venv with Python 3.12 and install requirements-dev.txt first."
}

Set-Location $ProjectRoot
& $Python -m black --check --line-length 100 *.py tests tools
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $Python -m ruff check *.py tests tools
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$env:PYTHONPATH = $ProjectRoot
Get-ChildItem tests/test_*.py | ForEach-Object {
    & $Python $_.FullName
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
$Archive = Join-Path $Output "BreakBlocks-Launcher-0.9.12-Windows-x86_64.zip"
if (Test-Path -LiteralPath $Archive) { Remove-Item -LiteralPath $Archive -Force }
Compress-Archive -Path $PackageRoot -DestinationPath $Archive -CompressionLevel Optimal
Write-Host "Created $Archive"
