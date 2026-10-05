# Build dist\RemindersSys.exe on Windows.
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python packaging\make_icons.py
python packaging\version_info.py
python -m PyInstaller --noconfirm --clean packaging\remindersys.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Write-Host "Built dist\RemindersSys.exe"
