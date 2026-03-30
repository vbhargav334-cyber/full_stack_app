@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv" (
  python -m venv .venv
)

call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller waitress

set "PLAYWRIGHT_BROWSERS_PATH=0"
python -m playwright install chromium

set "PW_LOCAL_BROWSERS=.venv\Lib\site-packages\playwright\driver\package\.local-browsers"
if not exist "%PW_LOCAL_BROWSERS%" (
  echo ERROR: Playwright local browser folder not found:
  echo %PW_LOCAL_BROWSERS%
  exit /b 1
)

pyinstaller --noconfirm --clean --onedir ^
  --name GoogleMapsScraperApp ^
  --add-data "frontend;frontend" ^
  --add-data "%PW_LOCAL_BROWSERS%;playwright\driver\package\.local-browsers" ^
  --collect-all playwright ^
  --hidden-import waitress ^
  launcher.py

echo.
echo Build completed.
echo EXE path: dist\GoogleMapsScraperApp\GoogleMapsScraperApp.exe
pause
