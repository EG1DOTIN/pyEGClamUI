@echo off
setlocal
cd /d "%~dp0"

REM Check for virtual environment pythonw.exe
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m pyegclamui %*
    exit /b 0
)

REM Check for virtual environment python.exe
if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" -m pyegclamui %*
    exit /b 0
)

REM If .venv is not yet configured, run automated setup
echo ======================================================
echo    pyEGClamUI - Initializing Environment Setup
echo ======================================================
echo Local virtual environment (.venv) not found.
echo Running automated setup engine...
echo.

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    py -3 setup\setup.py --start
    exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    python setup\setup.py --start
    exit /b %ERRORLEVEL%
)

echo [ERROR] Python 3.10+ is required but was not found in PATH.
echo Please install Python from https://www.python.org or via:
echo     winget install Python.Python.3.12
echo.
pause
exit /b 1
