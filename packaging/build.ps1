# Builds dist\DeskHub.exe (one file, no console window). Needs uv; PyInstaller is fetched for the build only.
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\companion"
uv run python ..\packaging\make_icon.py
uv run --with pyinstaller pyinstaller --noconfirm --clean --onefile --windowed --name DeskHub `
  --icon "$root\packaging\deskhub.ico" `
  --distpath "$root\dist" --workpath "$root\build" --specpath "$root\build" `
  --paths "$root\companion" `
  --add-data "$root\companion\deskhub\web;deskhub\web" `
  --add-data "$root\companion\deskhub\panel_web;deskhub\panel_web" `
  --add-data "$root\companion\config.example.toml;." `
  --collect-submodules pynput --collect-submodules keyring --collect-submodules winrt `
  --collect-submodules aiohttp --collect-data tzdata --collect-data recurring_ical_events --collect-data icalendar `
  --hidden-import pynvml --hidden-import tomlkit `
  "$root\packaging\run_app.py"
Write-Host "Built: $root\dist\DeskHub.exe"
