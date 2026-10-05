# Initialize Eclipse Ditto Digital Twins (PowerShell)
# This script creates the policy and things for all cold storage units

$DittoUrl = "http://localhost:8080/api/2"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "========================================"
Write-Host "Initializing Eclipse Ditto Digital Twins"
Write-Host "========================================"
Write-Host ""

# Wait for Ditto to be ready
Write-Host "Waiting for Ditto to be ready..."
$maxAttempts = 30
$attempt = 0
$ready = $false

while (-not $ready -and $attempt -lt $maxAttempts) {
    try {
        $healthUrl = $DittoUrl -replace '/api/2$', '/health'
        $response = Invoke-WebRequest -Uri $healthUrl -Method Get -TimeoutSec 2 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $ready = $true
            Write-Host "✓ Ditto is ready" -ForegroundColor Green
        }
    }
    catch {
        Write-Host "  Ditto not ready yet, waiting..."
        Start-Sleep -Seconds 5
        $attempt++
    }
}

if (-not $ready) {
    Write-Host "✗ Failed to connect to Ditto after $maxAttempts attempts" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Create policy
Write-Host "Creating cold-storage-policy..."
try {
    $policyPath = Join-Path $ScriptDir "policies\cold-storage-policy.json"
    $policyJson = Get-Content $policyPath -Raw
    
    $response = Invoke-WebRequest `
        -Uri "$DittoUrl/policies/org.eclipse.ditto:cold-storage-policy" `
        -Method Put `
        -ContentType "application/json" `
        -Body $policyJson `
        -ErrorAction Stop
    
    if ($response.StatusCode -eq 201 -or $response.StatusCode -eq 204) {
        Write-Host "✓ Policy created successfully" -ForegroundColor Green
    }
}
catch {
    Write-Host "✗ Failed to create policy" -ForegroundColor Red
    Write-Host "Error: $($_.Exception.Message)"
}
Write-Host ""

# Create things
$units = @("CS-01", "CS-02", "CS-03")

foreach ($unit in $units) {
    Write-Host "Creating thing $unit..."
    try {
        $thingPath = Join-Path $ScriptDir "things\$unit.json"
        $thingJson = Get-Content $thingPath -Raw
        
        $response = Invoke-WebRequest `
            -Uri "$DittoUrl/things/org.eclipse.ditto:$unit" `
            -Method Put `
            -ContentType "application/json" `
            -Body $thingJson `
            -ErrorAction Stop
        
        if ($response.StatusCode -eq 201 -or $response.StatusCode -eq 204) {
            Write-Host "✓ Thing $unit created successfully" -ForegroundColor Green
        }
    }
    catch {
        Write-Host "✗ Failed to create thing $unit" -ForegroundColor Red
        Write-Host "Error: $($_.Exception.Message)"
    }
    Write-Host ""
}

Write-Host "========================================"
Write-Host "Initialization complete!"
Write-Host "========================================"
Write-Host ""
Write-Host "Verify by running:"
Write-Host "  Invoke-WebRequest -Uri $DittoUrl/things"
Write-Host ""
Write-Host "Get specific thing:"
Write-Host "  Invoke-WebRequest -Uri $DittoUrl/things/org.eclipse.ditto:CS-01"
Write-Host ""
