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

echo Input one period to retry its failed sites, for example 251
set /p ISSUE=
if "%ISSUE%"=="" (
  echo Period is required.
  pause
  exit /b 1
)
echo %ISSUE%| findstr /r /x "[0-9][0-9]*" >nul
if errorlevel 1 (
  echo Period must contain digits only.
  pause
  exit /b 1
)

%PY_CMD% "%~dp0bantou_crawler.py" "%ISSUE%" --retry-fail --write-backup --workers 1
if errorlevel 1 (
  echo.
  echo Failed-site retry did not complete. Check the output above.
  echo.
  pause
  exit /b 1
)

echo.
echo Only sites listed in the period failure TXT were retried.
pause
