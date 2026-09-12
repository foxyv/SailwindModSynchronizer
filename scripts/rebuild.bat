@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
title Rebuild Sailwind Mod Synchronizer

echo.
echo Rebuilding Sailwind Mod Synchronizer...
echo Working folder: %CD%
echo Incremental freeze (cache reused). For a GitHub zip: rebuild.bat release
echo.

taskkill /IM SailwindModSynchronizer.exe /F >nul 2>&1
if not errorlevel 1 (
    echo Closed the running app so files can be replaced.
    timeout /t 2 /nobreak >nul
)

set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo Virtualenv python not found:
    echo   %PY%
    echo Create it with: py -3 -m venv .venv
    set "ERR=1"
    goto :end
)

if /I "%~1"=="release" (
    echo Release freeze: clean PyInstaller cache and write a GitHub zip.
    "%PY%" scripts\build.py --skip-shortcut --release
) else (
    "%PY%" scripts\build.py --skip-shortcut
)
set "ERR=%ERRORLEVEL%"
echo.
if not "%ERR%"=="0" (
    echo Build failed with exit code %ERR%.
) else (
    echo Build succeeded.
    echo %CD%\dist\SailwindModSynchronizer\SailwindModSynchronizer.exe
)

:end
echo.
pause
exit /b %ERR%
