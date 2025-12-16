@echo off
title Holoo API - Service Installer

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
echo  Holoo API Service Installer
echo =====================================================
echo.
echo Administrator access: OK.

:: Section 2: Setup
cd /d "%~dp0"
echo Current directory: %CD%
echo.

:: Section 3: Find Python
echo Searching for Python...
set "PYTHON_PATH="
for /f "delims=" %%i in ('where python') do (
    set "PYTHON_PATH=%%i"
    goto :found_python
)

:not_found_python
echo ERROR: Python not found. Please install Python.
pause
exit /b

:found_python
echo Python found: %PYTHON_PATH%
echo.

:: Section 4: Install Process
echo Removing old service (if any)...
nssm.exe remove "HolooAPIService" confirm >nul 2>&1
echo.

echo Installing new service...
nssm.exe install "HolooAPIService" "%PYTHON_PATH%" "holoo_api.py"
echo.

echo Configuring service...
nssm.exe set "HolooAPIService" AppDirectory "%CD%"
nssm.exe set "HolooAPIService" DisplayName "Holoo API Service"
nssm.exe set "HolooAPIService" Description "API server for Holoo Branch Management System."
nssm.exe set "HolooAPIService" Start SERVICE_AUTO_START
nssm.exe set "HolooAPIService" AppStdout "%CD%\holoo_api_stdout.log"
nssm.exe set "HolooAPIService" AppStderr "%CD%\holoo_api_stderr.log"
echo.

:: Section 5: Start and Check
echo Starting service...
nssm.exe start "HolooAPIService"
timeout /t 2 >nul
echo.

echo Final status:
nssm.exe status "HolooAPIService"
echo.
echo =====================================================
echo  Process finished.
echo  API URL: http://localhost:7480
echo =====================================================
echo.
pause
