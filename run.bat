@echo off
:: =============================================================================
:: Kali MCP Bounty Lab — Windows Launcher
:: Double-click this file to start the installer GUI.
:: =============================================================================
setlocal enabledelayedexpansion

echo.
echo   ^^ Kali MCP Bounty Lab
echo   -----------------------------------------

:: ── Python check / auto-install ──────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON=python
    goto python_ok
)
py --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON=py
    goto python_ok
)

echo   ??  Python not found - attempting automatic install via winget...
winget --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   X  winget not available.
    echo      Install Python manually from https://www.python.org/downloads/
    echo      Check "Add Python to PATH" during install, then re-run this script.
    pause
    exit /b 1
)

winget install -e --id Python.Python.3.12 --source winget --accept-source-agreements --accept-package-agreements
if %errorlevel% neq 0 (
    echo   X  winget install failed.
    echo      Install Python manually from https://www.python.org/downloads/
    echo      Check "Add Python to PATH" during install, then re-run this script.
    pause
    exit /b 1
)

echo   OK  Python installed. Please close this window and re-run run.bat
echo        (PATH needs to refresh before Python will be found)
pause
exit /b 0

:python_ok
for /f "tokens=*" %%v in ('!PYTHON! --version 2^>^&1') do echo   OK  %%v

:: ── customtkinter check / install ─────────────────────────────────────────────
!PYTHON! -c "import customtkinter" >nul 2>&1
if %errorlevel% neq 0 (
    echo   ??  customtkinter not found - installing...
    !PYTHON! -m pip install customtkinter
    if %errorlevel% neq 0 (
        echo   X  pip install customtkinter failed.
        echo      Try manually: pip install customtkinter
        pause
        exit /b 1
    )
    echo   OK  customtkinter installed
) else (
    echo   OK  customtkinter: found
)

:: ── File presence check ───────────────────────────────────────────────────────
if not exist "%~dp0kali_lab_installer.py" (
    echo   X  kali_lab_installer.py not found in %~dp0
    pause
    exit /b 1
)
if not exist "%~dp0install_windows.ps1" (
    echo   X  install_windows.ps1 not found in %~dp0
    pause
    exit /b 1
)

echo   -----------------------------------------
echo   Launching installer...
echo.

!PYTHON! "%~dp0kali_lab_installer.py"

:: If the GUI crashes show the error before the window closes
if %errorlevel% neq 0 (
    echo.
    echo   X  Installer exited with code %errorlevel%
    pause
)
