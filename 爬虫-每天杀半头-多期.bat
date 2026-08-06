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
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo Input periods, for example 187 188 189 190
set /p PERIODS=

if "%PERIODS%"=="" (
  echo Periods are required.
  pause
  exit /b 1
)

%PY_CMD% "%~dp0bantou_multi_period.py" %PERIODS%
if errorlevel 1 (
  echo.
  echo Multi-period crawl failed.
  echo.
  pause
  exit /b 1
)

echo.
pause
