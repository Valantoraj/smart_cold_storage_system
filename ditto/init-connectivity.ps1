#!/usr/bin/env pwsh
# =============================================================================
# Initialize Ditto Connectivity API — MQTT Bridge
# =============================================================================
# Run this AFTER init-ditto.ps1 to configure Ditto's direct MQTT connection.
# Ditto will subscribe to coldstorage/+/data and update twins automatically,
# removing the need for Node-RED to manually PATCH Ditto.
#
# Usage:
#   .\init-connectivity.ps1
#   .\init-connectivity.ps1 -DittoUrl "http://your-gcp-ip:8080"
# =============================================================================

param(
    [string]$DittoUrl = "http://localhost:8080"
)

$ConnectionFile = Join-Path $PSScriptRoot "connectivity\mqtt-connection.json"
$ApiUrl = "$DittoUrl/api/2/connections"
$Headers = @{
    "Content-Type"              = "application/json"
    "x-ditto-pre-authenticated" = "nginx:ditto"
}

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Ditto MQTT Connectivity API Setup"        -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Ditto URL: $DittoUrl"                     -ForegroundColor DarkGray
Write-Host ""

# Wait for Ditto to be ready
Write-Host "Waiting for Ditto gateway..." -ForegroundColor Yellow
$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "$DittoUrl/alive" -TimeoutSec 3 -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {
        Start-Sleep -Seconds 5
    }
}

if (-not $ready) {
    Write-Host "Ditto not reachable after 100s. Check containers." -ForegroundColor Red
    exit 1
}
Write-Host "Ditto is ready." -ForegroundColor Green

# Read connection definition
$connectionBody = Get-Content $ConnectionFile -Raw
$connectionId = "mqtt-cold-storage-connection"

# Check if connection already exists
try {
    $existing = Invoke-WebRequest -Uri "$ApiUrl/$connectionId" -Headers $Headers -Method Get -ErrorAction Stop
    Write-Host "Connection already exists — updating..." -ForegroundColor Yellow
    $method = "Put"
} catch {
    Write-Host "Creating new MQTT connection..." -ForegroundColor Cyan
    $method = "Post"
}

# Create or update connection
try {
    if ($method -eq "Post") {
        $resp = Invoke-RestMethod -Uri $ApiUrl -Method Post -Headers $Headers -Body $connectionBody -ErrorAction Stop
    } else {
        $resp = Invoke-RestMethod -Uri "$ApiUrl/$connectionId" -Method Put -Headers $Headers -Body $connectionBody -ErrorAction Stop
    }
    Write-Host "MQTT connection configured successfully!" -ForegroundColor Green
} catch {
    Write-Host "Failed: $($_.Exception.Message)" -ForegroundColor Red
    # Try with basic auth fallback
    $basicHeaders = @{
        "Content-Type"  = "application/json"
        "Authorization" = "Basic ZGl0dG86ZGl0dG8="  # ditto:ditto
    }
    try {
        $resp = Invoke-RestMethod -Uri $ApiUrl -Method Post -Headers $basicHeaders -Body $connectionBody -ErrorAction Stop
        Write-Host "Created with basic auth." -ForegroundColor Green
    } catch {
        Write-Host "Could not create connection. Check Ditto logs." -ForegroundColor Red
    }
}

# Verify connection status
Start-Sleep -Seconds 3
try {
    $status = Invoke-RestMethod -Uri "$ApiUrl/$connectionId/status" -Headers $Headers -ErrorAction Stop
    Write-Host "Connection status: $($status.connectionStatus)" -ForegroundColor Cyan
    Write-Host "Sources:"
    $status.sourceStatus | ForEach-Object { Write-Host "  $($_.address): $($_.status)" }
} catch {
    Write-Host "Could not fetch connection status (non-critical)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host "  Ditto MQTT Bridge Active!"                 -ForegroundColor Green
Write-Host "  Ditto now subscribes to:"                  -ForegroundColor White
Write-Host "    coldstorage/+/data"                      -ForegroundColor Cyan
Write-Host "  And updates twins automatically."          -ForegroundColor White
Write-Host "=============================================" -ForegroundColor Green
