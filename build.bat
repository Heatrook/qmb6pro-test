@echo off
setlocal enabledelayedexpansion

REM ---------------------------
REM build_onedir_and_zip.bat
REM ---------------------------
REM Usage: place in project root and run
REM Creates .venv, installs deps, builds ONEDIR (no UPX), zips dist\QMB6Pro_GUI -> QMB6Pro_GUI.zip
REM ---------------------------

set APP_NAME=QMB6Pro_GUI
set DIST_FOLDER=dist\%APP_NAME%
set ZIP_NAME=%APP_NAME%.zip
set PYI_VER=6.6.0

echo ====================================================
echo BUILD (ONEDIR) + ZIP for %APP_NAME%
echo ====================================================
echo.

REM 1) Create venv if missing
if not exist .venv (
  echo [1/6] Creating virtualenv...
  python -m venv .venv || (echo ERROR: could not create venv & exit /b 1)
) else (
  echo [1/6] .venv exists — using it.
)

call .venv\Scripts\activate

echo [2/6] Upgrading pip...
python -m pip install --upgrade pip

echo [3/6] Installing requirements...
pip install -r requirements.txt || (echo ERROR: pip install -r requirements.txt failed & goto :cleanup)

echo [4/6] Installing PyInstaller %PYI_VER%...
pip install pyinstaller==%PYI_VER% || (echo ERROR: pip install pyinstaller failed & goto :cleanup)

REM 2) Try temporary Defender exclusion for dist (optional — needs admin)
echo [5/6] Trying to add temporary Defender exclusion for "%CD%\dist"
powershell -Command "Try { Add-MpPreference -ExclusionPath '%CD%\dist' -ErrorAction Stop; Write-Host '  -> Exclusion added.' } Catch { Write-Host '  -> Could not add exclusion (not admin?), continuing anyway.' }"

REM 3) Build ONEDIR (no UPX)
echo [6/6] Building ONEDIR with PyInstaller (no UPX)...
pyinstaller --noconfirm --clean --onedir --windowed --noupx ^
  --collect-data ttkbootstrap ^
  --collect-data matplotlib ^
  --add-data registers.json;. ^
  --name %APP_NAME% app_gui.py

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: PyInstaller build failed. Check output above.
  goto :cleanup
)

if not exist "%DIST_FOLDER%" (
  echo.
  echo ERROR: Expected folder %DIST_FOLDER% not found. Build likely failed.
  goto :cleanup
)

REM 4) Create ZIP immediately
echo Creating ZIP: %ZIP_NAME% (from %DIST_FOLDER%)
powershell -Command "Try { Remove-Item -Force -ErrorAction SilentlyContinue '%CD%\%ZIP_NAME%'; Compress-Archive -Path '%CD%\%DIST_FOLDER%\*' -DestinationPath '%CD%\%ZIP_NAME%' -Force; Write-Host '  -> Zip created: %ZIP_NAME%'; } Catch { Write-Host '  -> Zip creation failed'; Exit 1 }"

echo.
echo DONE. Distribution archive: %ZIP_NAME%
echo You can send this zip to client. Inside there is the onedir with exe and dependencies.
echo.

:cleanup
echo Cleaning up temporary Defender exclusion (if any)...
powershell -Command "Try { Remove-MpPreference -ExclusionPath '%CD%\dist' -ErrorAction Stop; Write-Host '  -> Exclusion removed.' } Catch { Write-Host '  -> Could not remove exclusion (not admin or not present).' }"

echo.
echo Tip: If Defender still flags files, run this script as Administrator, or use self-signed cert for internal tests, or sign with OV/EV cert for production.
pause
endlocal
