# Google Drive OAuth Environment Variables Setup
# This script sets up Google Drive OAuth credentials for PDF Tools

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PDF Tools - Google Drive Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This will set up your Google Drive OAuth credentials."
Write-Host "Get your credentials from: https://console.cloud.google.com/apis/credentials"
Write-Host ""

$CLIENT_ID = Read-Host "Enter GOOGLE_CLIENT_ID"
$CLIENT_SECRET = Read-Host "Enter GOOGLE_CLIENT_SECRET"
$REDIRECT_URI = Read-Host "Enter GOOGLE_REDIRECT_URI (default: http://localhost:5000/drive/callback)"

if ([string]::IsNullOrWhiteSpace($REDIRECT_URI)) {
    $REDIRECT_URI = "http://localhost:5000/drive/callback"
}

# Set environment variables for current session
$env:GOOGLE_CLIENT_ID = $CLIENT_ID
$env:GOOGLE_CLIENT_SECRET = $CLIENT_SECRET
$env:GOOGLE_REDIRECT_URI = $REDIRECT_URI

# Set permanent environment variables
[System.Environment]::SetEnvironmentVariable("GOOGLE_CLIENT_ID", $CLIENT_ID, "User")
[System.Environment]::SetEnvironmentVariable("GOOGLE_CLIENT_SECRET", $CLIENT_SECRET, "User")
[System.Environment]::SetEnvironmentVariable("GOOGLE_REDIRECT_URI", $REDIRECT_URI, "User")

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Environment variables set successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "GOOGLE_CLIENT_ID: $CLIENT_ID"
Write-Host "GOOGLE_CLIENT_SECRET: ******* (hidden)"
Write-Host "GOOGLE_REDIRECT_URI: $REDIRECT_URI"
Write-Host ""
Write-Host "Note: You may need to restart your terminal for changes to take effect." -ForegroundColor Yellow
Write-Host ""
