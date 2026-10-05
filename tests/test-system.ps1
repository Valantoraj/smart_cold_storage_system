# Smart Cold Storage Digital Twin - System Test Script (PowerShell)
# Tests all components of the system

param(
    [switch]$Quick,
    [switch]$Verbose
)

$ErrorActionPreference = "Continue"

# Colors for output
function Write-Success { Write-Host "✓ $args" -ForegroundColor Green }
function Write-Failure { Write-Host "✗ $args" -ForegroundColor Red }
function Write-Info { Write-Host "ℹ $args" -ForegroundColor Cyan }
function Write-Section { Write-Host "`n=== $args ===" -ForegroundColor Yellow }

$TestResults = @{
    Passed = 0
    Failed = 0
    Skipped = 0
}

function Test-Service {
    param($Name, $Command)
    try {
        $result = Invoke-Expression $Command 2>$null
        if ($LASTEXITCODE -eq 0 -or $result) {
            Write-Success "$Name is accessible"
            $TestResults.Passed++
            return $true
        } else {
            Write-Failure "$Name is not accessible"
            $TestResults.Failed++
            return $false
        }
    } catch {
        Write-Failure "$Name check failed: $($_.Exception.Message)"
        $TestResults.Failed++
        return $false
    }
}

function Test-HttpEndpoint {
    param($Name, $Url, $ExpectedStatus = 200)
    try {
        $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 10 -ErrorAction Stop
        if ($response.StatusCode -eq $ExpectedStatus) {
            Write-Success "$Name responded with status $($response.StatusCode)"
            $TestResults.Passed++
            return $true
        } else {
            Write-Failure "$Name responded with unexpected status $($response.StatusCode)"
            $TestResults.Failed++
            return $false
        }
    } catch {
        Write-Failure "$Name is not responding: $($_.Exception.Message)"
        $TestResults.Failed++
        return $false
    }
}

# =============================================================================
# Main Test Execution
# =============================================================================

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  Smart Cold Storage Digital Twin - System Validation" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# =============================================================================
# 1. Docker Environment Check
# =============================================================================

Write-Section "Docker Environment"

Write-Info "Checking Docker installation..."
if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Success "Docker is installed"
    $TestResults.Passed++
    
    $dockerVersion = docker --version
    Write-Info "Version: $dockerVersion"
} else {
    Write-Failure "Docker is not installed or not in PATH"
    $TestResults.Failed++
}

Write-Info "Checking Docker Compose..."
if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    Write-Success "Docker Compose is installed"
    $TestResults.Passed++
    
    $composeVersion = docker-compose --version
    Write-Info "Version: $composeVersion"
} else {
    Write-Failure "Docker Compose is not installed or not in PATH"
    $TestResults.Failed++
}

# =============================================================================
# 2. Container Status Check
# =============================================================================

Write-Section "Container Status"

$containers = @(
    "smart_cooling_mosquitto",
    "smart_cooling_influxdb",
    "smart_cooling_mongodb",
    "smart_cooling_ditto_gateway",
    "smart_cooling_nodered",
    "smart_cooling_grafana",
    "smart_cooling_api"
)

foreach ($container in $containers) {
    $status = docker ps --filter "name=$container" --format "{{.Status}}" 2>$null
    if ($status -like "*Up*") {
        Write-Success "$container is running"
        $TestResults.Passed++
    } else {
        Write-Failure "$container is not running"
        $TestResults.Failed++
    }
}

# =============================================================================
# 3. Service Accessibility Check
# =============================================================================

Write-Section "Service Accessibility"

Test-HttpEndpoint "Mosquitto (HTTP)" "http://localhost:1883" -ExpectedStatus 0
Test-HttpEndpoint "InfluxDB" "http://localhost:8086/health"
Test-HttpEndpoint "Eclipse Ditto" "http://localhost:8080/health"
Test-HttpEndpoint "Node-RED" "http://localhost:1880"
Test-HttpEndpoint "Grafana" "http://localhost:3000/api/health"
Test-HttpEndpoint "REST API" "http://localhost:3001/api/health"

# =============================================================================
# 4. REST API Endpoints Test
# =============================================================================

Write-Section "REST API Endpoints"

$apiTests = @(
    @{ Name = "Health Check"; Url = "http://localhost:3001/api/health" },
    @{ Name = "List Storage Units"; Url = "http://localhost:3001/api/storage" },
    @{ Name = "Get Unit CS-01"; Url = "http://localhost:3001/api/storage/CS-01" },
    @{ Name = "Get Current Data"; Url = "http://localhost:3001/api/storage/CS-01/current" },
    @{ Name = "Get Alerts"; Url = "http://localhost:3001/api/alerts" },
    @{ Name = "Get Maintenance Scores"; Url = "http://localhost:3001/api/maintenance/scores" }
)

foreach ($test in $apiTests) {
    Test-HttpEndpoint $test.Name $test.Url
}

# =============================================================================
# 5. InfluxDB Data Check
# =============================================================================

Write-Section "InfluxDB Data Validation"

try {
    $influxQuery = 'from(bucket:"cold_storage") |> range(start: -1h) |> limit(n: 1)'
    $response = Invoke-WebRequest -Uri "http://localhost:8086/api/v2/query?org=smart_cooling" `
        -Method Post `
        -Headers @{
            "Authorization" = "Token smart-cooling-super-secret-token"
            "Content-Type" = "application/vnd.flux"
        } `
        -Body $influxQuery `
        -TimeoutSec 10 `
        -ErrorAction Stop
    
    if ($response.StatusCode -eq 200 -and $response.Content.Length -gt 0) {
        Write-Success "InfluxDB contains sensor data"
        $TestResults.Passed++
    } else {
        Write-Failure "InfluxDB has no sensor data"
        $TestResults.Failed++
    }
} catch {
    Write-Failure "Could not query InfluxDB: $($_.Exception.Message)"
    $TestResults.Failed++
}

# =============================================================================
# 6. Eclipse Ditto Digital Twins Check
# =============================================================================

Write-Section "Eclipse Ditto Digital Twins"

$things = @("CS-01", "CS-02", "CS-03")

foreach ($thing in $things) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8080/api/2/things/org.eclipse.ditto:$thing" `
            -Method Get `
            -TimeoutSec 10 `
            -ErrorAction Stop
        
        if ($response.StatusCode -eq 200) {
            Write-Success "Digital twin $thing exists"
            $TestResults.Passed++
        } else {
            Write-Failure "Digital twin $thing not found"
            $TestResults.Failed++
        }
    } catch {
        Write-Failure "Could not access digital twin $thing"
        $TestResults.Failed++
    }
}

# =============================================================================
# 7. MQTT Connectivity Check
# =============================================================================

Write-Section "MQTT Connectivity"

Write-Info "Testing MQTT publish/subscribe (requires mosquitto_pub/sub)..."
if (Get-Command mosquitto_pub -ErrorAction SilentlyContinue) {
    try {
        # Publish test message
        $testMessage = @{
            unitId = "TEST-01"
            temperature = 4.0
            humidity = 65
            compressorStatus = "OFF"
            energyConsumption = 0.5
            timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        } | ConvertTo-Json -Compress
        
        mosquitto_pub -h localhost -p 1883 -t "coldstorage/TEST-01/data" -m $testMessage
        
        Write-Success "MQTT publish successful"
        $TestResults.Passed++
    } catch {
        Write-Failure "MQTT publish failed"
        $TestResults.Failed++
    }
} else {
    Write-Info "Mosquitto clients not installed - skipping MQTT test"
    $TestResults.Skipped++
}

# =============================================================================
# 8. Data Flow Validation (if not Quick mode)
# =============================================================================

if (-not $Quick) {
    Write-Section "Data Flow Validation"
    
    Write-Info "Running sensor simulator for 60 seconds..."
    
    # Check if Python is available
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $simulatorPath = Join-Path $PSScriptRoot "..\simulator\sensor_simulator.py"
        
        if (Test-Path $simulatorPath) {
            Write-Info "Starting simulator..."
            
            $simProcess = Start-Process python `
                -ArgumentList "$simulatorPath --units CS-01:normal --interval 10 --duration 60" `
                -NoNewWindow `
                -PassThru
            
            Start-Sleep -Seconds 15
            
            # Check if data appeared in InfluxDB
            try {
                $influxQuery = 'from(bucket:"cold_storage") |> range(start: -1m) |> filter(fn: (r) => r["unitId"] == "CS-01") |> count()'
                $response = Invoke-WebRequest -Uri "http://localhost:8086/api/v2/query?org=smart_cooling" `
                    -Method Post `
                    -Headers @{
                        "Authorization" = "Token smart-cooling-super-secret-token"
                        "Content-Type" = "application/vnd.flux"
                    } `
                    -Body $influxQuery `
                    -TimeoutSec 10
                
                if ($response.Content -match "\d+") {
                    Write-Success "Data flow verified - sensor data reaching InfluxDB"
                    $TestResults.Passed++
                } else {
                    Write-Failure "No data flow detected"
                    $TestResults.Failed++
                }
            } catch {
                Write-Failure "Could not verify data flow"
                $TestResults.Failed++
            }
            
            # Wait for simulator to complete
            Wait-Process -Id $simProcess.Id -ErrorAction SilentlyContinue
        } else {
            Write-Info "Simulator not found - skipping data flow test"
            $TestResults.Skipped++
        }
    } else {
        Write-Info "Python not installed - skipping data flow test"
        $TestResults.Skipped++
    }
}

# =============================================================================
# Test Summary
# =============================================================================

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  Test Summary" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

$total = $TestResults.Passed + $TestResults.Failed + $TestResults.Skipped
$passRate = if ($total -gt 0) { [math]::Round(($TestResults.Passed / $total) * 100, 1) } else { 0 }

Write-Host "Total Tests:    $total"
Write-Host "Passed:         $($TestResults.Passed) " -NoNewline
Write-Host "($passRate%)" -ForegroundColor Green
Write-Host "Failed:         $($TestResults.Failed)" -ForegroundColor $(if ($TestResults.Failed -gt 0) { "Red" } else { "White" })
Write-Host "Skipped:        $($TestResults.Skipped)" -ForegroundColor Yellow

Write-Host ""

if ($TestResults.Failed -eq 0) {
    Write-Host "✓ All tests passed!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "✗ Some tests failed. Please review the output above." -ForegroundColor Red
    exit 1
}
