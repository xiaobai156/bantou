@echo off
chcp 65001 >nul
set "PY_CMD="
py -3 --version >nul 2>nul
if not errorlevel 1 set "PY_CMD=py -3"
if not defined PY_CMD (
  python --version >nul 2>nul
  if not errorlevel 1 set "PY_CMD=python"
)
if not defined PY_CMD (
  echo Cannot find Python. Please install Python and add it to PATH.
  pause
  exit /b 1
)
setlocal DisableDelayedExpansion
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

%PY_CMD% "%~dp0run_daily.py"
if errorlevel 1 (
  echo.
  echo Crawl or cache update failed. Check the result and cache messages above.
  echo.
  pause
  exit /b 1
)

echo.
pause
