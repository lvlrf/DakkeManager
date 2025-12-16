@echo off
title Holoo API - Service Uninstaller

:: Section 1: Administrator Access Check
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator access...
    powershell -Command "Start-Process -FilePath '%~s0' -Verb RunAs"
    exit /b
)

:: If we are here, we have admin rights.
cls
echo =====================================================
echo  Holoo API Service Uninstaller
echo =====================================================
echo.
echo Administrator access: OK.

:: Section 2: Setup
cd /d "%~dp0"

:: Section 3: Check if service exists
echo Searching for service...
sc query "HolooAPIService" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo Service 'HolooAPIService' not found.
    echo.
    pause
    exit /b 0
)
echo Service found.
echo.

:: Section 4: Stop and Remove
echo Stopping service...
nssm.exe stop "HolooAPIService" >nul 2>&1
timeout /t 1 >nul
echo.

echo Removing service...
nssm.exe remove "HolooAPIService" confirm
echo.
echo =====================================================
echo  Process finished.
echo =====================================================
echo.
pause
