@echo off
setlocal
cd /d "%~dp0"
set "PLAYWRIGHT_BROWSERS_PATH=0"
if not "%~1"=="" set "SCRAPER_PORT=%~1"

call :try_venv ".venv\Scripts\python.exe" ".venv\pyvenv.cfg"
if %errorlevel%==0 exit /b 0

call :try_venv "..\.venv\Scripts\python.exe" "..\.venv\pyvenv.cfg"
if %errorlevel%==0 exit /b 0

py -3.12 -V >nul 2>nul
if %errorlevel%==0 (
  echo Using Python launcher: py -3.12
  call :run_with_pylauncher
  exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel%==0 (
  echo Using system python from PATH
  call :run_with_python python
  exit /b %errorlevel%
)

echo ERROR: No usable Python interpreter was found.
exit /b 1

:try_venv
set "VENV_PY=%~1"
set "VENV_CFG=%~2"

if not exist "%VENV_PY%" exit /b 1
if not exist "%VENV_CFG%" exit /b 1

set "VENV_TEST_LOG=%TEMP%\gmaps_venv_check_%RANDOM%_%RANDOM%.log"
"%VENV_PY%" -c "import sys" >"%VENV_TEST_LOG%" 2>&1
findstr /I /C:"did not find executable at" "%VENV_TEST_LOG%" >nul
if not errorlevel 1 (
  del "%VENV_TEST_LOG%" >nul 2>nul
  echo WARNING: Ignoring broken venv at %VENV_CFG%
  exit /b 1
)
del "%VENV_TEST_LOG%" >nul 2>nul

echo Using virtual environment: %VENV_PY%
call :run_with_python "%VENV_PY%"
exit /b %errorlevel%

:run_with_python
set "PY_BIN=%~1"
"%PY_BIN%" -m playwright install chromium
if errorlevel 1 (
  echo ERROR: Failed to install Playwright Chromium with "%PY_BIN%".
  exit /b 1
)
"%PY_BIN%" launcher.py
exit /b %errorlevel%

:run_with_pylauncher
py -3.12 -m playwright install chromium
if errorlevel 1 (
  echo ERROR: Failed to install Playwright Chromium with py -3.12.
  exit /b 1
)
py -3.12 launcher.py
exit /b %errorlevel%
