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
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo Input period, for example 125 or 094-125
set /p ISSUES=

if "%ISSUES%"=="" (
  echo Period is required.
  pause
  exit /b 1
) else (
  echo %ISSUES% | findstr /c:"-" >nul
  if errorlevel 1 (
    %PY_CMD% "%~dp0bantou_crawler.py" %ISSUES% --write-backup
  ) else (
    %PY_CMD% "%~dp0bantou_crawler.py" %ISSUES%
  )
)
if errorlevel 1 (
  echo.
  echo Crawl or cache update failed. Check the result and cache messages above.
  echo.
  pause
  exit /b 1
)

echo.
pause
