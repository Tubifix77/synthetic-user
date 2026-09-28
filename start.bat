@echo off
rem Synthetic User - double-click to start. Opens in your browser; no window stays open.
rem First run installs it and puts a "Synthetic User" icon on your desktop.
cd /d "%~dp0"
where python >nul 2>nul || (echo Python is not installed. Get Python 3.11+ from https://www.python.org/downloads/ and tick "Add python.exe to PATH". & pause & exit /b 1)
python -c "import synthetic_user.ui.server" >nul 2>nul
if errorlevel 1 (
  echo First run: installing Synthetic User ^(about a minute^)...
  python -m pip install -q -e ".[dev]" || (echo Install failed - see the messages above. & pause & exit /b 1)
  python -m synthetic_user shortcut
)
where pythonw >nul 2>nul && (start "" pythonw -m synthetic_user ui) || (start "Synthetic User" /min python -m synthetic_user ui)
exit /b 0
