@echo off
:: =============================================================================
:: Kali MCP Bounty Lab — Windows Launcher
:: Does ALL bootstrapping in one pass, then opens the GUI.
:: Double-click to run. Right-click -> Run as administrator for Port Proxy step.
:: =============================================================================
setlocal enabledelayedexpansion

echo.
echo   ^^ Kali MCP Bounty Lab
echo   -----------------------------------------
echo   Checking dependencies...
echo.

:: ── Track whether we installed anything that needs a PATH refresh ─────────────
set NEEDS_RESTART=0

:: ═════════════════════════════════════════════════════════════════════════════
:: PYTHON
:: ═════════════════════════════════════════════════════════════════════════════
set PYTHON=
python --version >nul 2>&1
if %errorlevel% equ 0 ( set PYTHON=python & goto python_ok )
py --version >nul 2>&1
if %errorlevel% equ 0 ( set PYTHON=py & goto python_ok )

echo   ??  Python not found - installing via winget...
winget install -e --id Python.Python.3.12 --source winget --accept-source-agreements --accept-package-agreements
if %errorlevel% neq 0 (
    echo   X  winget install failed.
    echo      Install Python manually: https://www.python.org/downloads/
    echo      Check "Add Python to PATH" during install.
    pause & exit /b 1
)
:: Refresh PATH without closing window
for /f "skip=2 tokens=3*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul') do set SYS_PATH=%%a %%b
for /f "skip=2 tokens=3*" %%a in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set USR_PATH=%%a %%b
set PATH=!SYS_PATH!;!USR_PATH!;%PATH%
python --version >nul 2>&1
if %errorlevel% equ 0 ( set PYTHON=python & goto python_ok )
py --version >nul 2>&1
if %errorlevel% equ 0 ( set PYTHON=py & goto python_ok )
set NEEDS_RESTART=1
echo   OK  Python installed - will need one window restart (see end of this script)
goto python_done

:python_ok
for /f "tokens=*" %%v in ('!PYTHON! --version 2^>^&1') do echo   OK  Python: %%v
:python_done

:: ═════════════════════════════════════════════════════════════════════════════
:: NODE.JS / NPM
:: ═════════════════════════════════════════════════════════════════════════════
if "!NEEDS_RESTART!"=="1" goto skip_node_check
node --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo   OK  Node.js: %%v
    goto node_ok
)

echo   ??  Node.js not found - installing via winget...
winget install -e --id OpenJS.NodeJS.LTS --source winget --accept-source-agreements --accept-package-agreements
if %errorlevel% neq 0 (
    echo   X  winget install failed.
    echo      Install Node.js manually: https://nodejs.org
    pause & exit /b 1
)
:: Refresh PATH
for /f "skip=2 tokens=3*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul') do set SYS_PATH=%%a %%b
set PATH=!SYS_PATH!;!USR_PATH!;%PATH%
node --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo   OK  Node.js: %%v
    goto node_ok
)
echo   OK  Node.js installed - will need one window restart (see end of this script)
set NEEDS_RESTART=1
goto node_done

:node_ok
:skip_node_check
:node_done

:: ═════════════════════════════════════════════════════════════════════════════
:: MCP-REMOTE
:: ═════════════════════════════════════════════════════════════════════════════
if "!NEEDS_RESTART!"=="1" goto skip_mcp_check
where mcp-remote >nul 2>&1
if %errorlevel% equ 0 (
    echo   OK  mcp-remote: found
    goto mcp_ok
)
if exist "%APPDATA%\npm\mcp-remote.cmd" (
    echo   OK  mcp-remote: found in npm global
    goto mcp_ok
)

echo   ??  mcp-remote not found - installing via npm...
npm install -g mcp-remote
if %errorlevel% neq 0 (
    echo   X  npm install mcp-remote failed
    echo      Try manually: npm install -g mcp-remote
) else (
    echo   OK  mcp-remote installed
)

:mcp_ok
:skip_mcp_check

:: ═════════════════════════════════════════════════════════════════════════════
:: CUSTOMTKINTER
:: ═════════════════════════════════════════════════════════════════════════════
if "!NEEDS_RESTART!"=="1" goto skip_ctk_check
if not defined PYTHON goto skip_ctk_check

!PYTHON! -c "import customtkinter" >nul 2>&1
if %errorlevel% equ 0 (
    echo   OK  customtkinter: found
    goto ctk_ok
)

echo   ??  customtkinter not found - installing...
!PYTHON! -m pip install customtkinter --quiet
if %errorlevel% equ 0 (
    echo   OK  customtkinter installed
) else (
    echo   X  pip install customtkinter failed
    echo      Try manually: pip install customtkinter
    pause & exit /b 1
)

:ctk_ok
:skip_ctk_check

:: ═════════════════════════════════════════════════════════════════════════════
:: If anything was installed and PATH couldn't refresh, ask for one restart
:: ═════════════════════════════════════════════════════════════════════════════
if "!NEEDS_RESTART!"=="1" (
    echo.
    echo   -------------------------------------------------------
    echo   One or more tools were installed but need a PATH refresh
    echo   before the GUI can launch.
    echo.
    echo   Please close this window and double-click run.bat again.
    echo   This only happens once.
    echo   -------------------------------------------------------
    echo.
    pause
    exit /b 0
)

:: ═════════════════════════════════════════════════════════════════════════════
:: FILE CHECKS
:: ═════════════════════════════════════════════════════════════════════════════
if not exist "%~dp0kali_lab_installer.py" (
    echo   X  kali_lab_installer.py not found in %~dp0
    echo      Make sure all 5 files are in the same folder.
    pause & exit /b 1
)
if not exist "%~dp0install_windows.ps1" (
    echo   X  install_windows.ps1 not found in %~dp0
    echo      Make sure all 5 files are in the same folder.
    pause & exit /b 1
)

:: ═════════════════════════════════════════════════════════════════════════════
:: LAUNCH GUI
:: ═════════════════════════════════════════════════════════════════════════════
echo.
echo   -----------------------------------------
echo   All dependencies OK. Launching GUI...
echo   -----------------------------------------
echo.

!PYTHON! "%~dp0kali_lab_installer.py"

if %errorlevel% neq 0 (
    echo.
    echo   X  GUI exited with error code %errorlevel%
    pause
)
