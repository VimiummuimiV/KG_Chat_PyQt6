@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\KG Chat.lnk"
set "INSTALL_LOG=%DESKTOP%\install_log.txt"
set "DATA_DIR=%USERPROFILE%\Documents\KG_Chat_Data"
set "AUTOSTART_KEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Run"

if not exist "%ROOT%\src\main.py" (
    echo ERROR: %ROOT% does not look like the KG Chat project folder. Nothing was removed.
    pause
    exit /b 1
)

echo This removes KG Chat: shortcut, autostart entry and the project folder:
echo   %ROOT%
choice /c YN /n /m "Continue? [Y/N] "
if errorlevel 2 exit /b 0

echo.
echo Stopping KG Chat...
set "KG_ROOT=%ROOT%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:KG_ROOT) -and $_.Name -match '^pythonw?\.exe$' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"

echo Removing shortcut and autostart entry...
if exist "%SHORTCUT%" del /f /q "%SHORTCUT%"
if exist "%INSTALL_LOG%" del /f /q "%INSTALL_LOG%"
reg delete "%AUTOSTART_KEY%" /v KG_Chat /f >nul 2>&1

if exist "%DATA_DIR%" (
    choice /c NY /n /m "Also delete your data (accounts, chat logs, settings) in %DATA_DIR%? [Y/N] "
    if not errorlevel 2 goto keep_data
    rd /s /q "%DATA_DIR%"
    echo Data deleted.
)
:keep_data

choice /c NY /n /m "Delete the project folder %ROOT% (including this file)? [Y/N] "
if not errorlevel 2 (
    echo Project folder kept.
    pause
    exit /b 0
)

echo Done. Python packages installed with pip were left in place.
echo The project folder is being removed.
cd /d "%TEMP%"
rem A separate cmd waits until this script exits, then deletes the folder
start "" /min cmd /c ping 127.0.0.1 -n 3 ^>nul ^& rd /s /q "%ROOT%"
exit
