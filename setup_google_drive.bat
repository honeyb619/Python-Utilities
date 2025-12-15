@echo off
REM Set Google Drive OAuth Environment Variables for PDF Tools
REM This script sets the environment variables needed for Google Drive integration

setlocal enabledelayedexpansion

echo.
echo ========================================
echo PDF Tools - Google Drive Setup
echo ========================================
echo.
echo This will set up your Google Drive OAuth credentials.
echo Get your credentials from: https://console.cloud.google.com/apis/credentials
echo.

set /p CLIENT_ID="Enter GOOGLE_CLIENT_ID: "
set /p CLIENT_SECRET="Enter GOOGLE_CLIENT_SECRET: "
set /p REDIRECT_URI="Enter GOOGLE_REDIRECT_URI (default: http://localhost:5000/drive/callback): "

if "!REDIRECT_URI!"=="" (
    set REDIRECT_URI=http://localhost:5000/drive/callback
)

REM Set the environment variables for current session
setx GOOGLE_CLIENT_ID "!CLIENT_ID!"
setx GOOGLE_CLIENT_SECRET "!CLIENT_SECRET!"
setx GOOGLE_REDIRECT_URI "!REDIRECT_URI!"

echo.
echo ========================================
echo Environment variables set successfully!
echo ========================================
echo.
echo GOOGLE_CLIENT_ID: !CLIENT_ID!
echo GOOGLE_CLIENT_SECRET: ******* (hidden)
echo GOOGLE_REDIRECT_URI: !REDIRECT_URI!
echo.
echo Note: You may need to restart your terminal for changes to take effect.
echo.
pause
