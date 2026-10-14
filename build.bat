@echo off
REM RemoteDesk — Windows build script.
REM Requires Python 3.11 on PATH. Builds RemoteDesk.exe via PyInstaller.
REM For a full installer (Setup-RemoteDesk-*.exe), install Inno Setup 6 and run:
REM   iscc setup.iss
REM Or push a tag — GitHub Actions builds both automatically (see BUILD_EXE.md).
setlocal
cd /d "%~dp0"
python --version || (echo Python 3.11 is required. && exit /b 1)
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller pytest
python -m pytest -q || (echo TESTS FAILED — fix before building. && exit /b 1)
pyinstaller remote_desk.spec
echo.
echo Build done. EXE: dist\RemoteDesk.exe
endlocal
