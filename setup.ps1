#!/usr/bin/env pwsh
# =============================================================================
# Smart Cold Storage — Laptop Setup Script (Windows PowerShell)
# =============================================================================
# Run this ONCE on each laptop to configure it for its role.
#
# Usage:
#   # Laptop 1 (Warehouse Alpha):
#   .\setup.ps1 -Role alpha
#
#   # Laptop 2 (Warehouse Beta):
#   .\setup.ps1 -Role beta
#
#   # Laptop 3 (Operations Console):
#   .\setup.ps1 -Role gamma
#
#   # Single machine (current working mode, no distributed):
#   .\setup.ps1 -Role single
# =============================================================================

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("alpha", "beta", "gamma", "single")]
    [string]$Role,

    [switch]$SkipPrereqCheck,
    [switch]$SkipDockerPull,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"

# ─── Colors ──────────────────────────────────────────────────────────────────
function Write-Step  { param($msg) Write-Host "`n[$([char]0x25B6)] $msg" -ForegroundColor Cyan }
function Write-OK    { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "  [!!] $msg" -ForegroundColor Yellow }
function Write-Fail  { param($msg) Write-Host "  [X] $msg" -ForegroundColor Red }
function Write-Info  { param($msg) Write-Host "  [i] $msg" -ForegroundColor DarkGray }

# ─── Role config ─────────────────────────────────────────────────────────────
$roleConfig = @{
    alpha  = @{ units = "CS-01,CS-02"; warehouse = "alpha"; desc = "Warehouse Alpha (CS-01, CS-02)" }
    beta   = @{ units = "CS-03";       warehouse = "beta";  desc = "Warehouse Beta (CS-03)" }
    gamma  = @{ units = "";            warehouse = "gamma"; desc = "Operations Console" }
    single = @{ units = "CS-01,CS-02,CS-03"; warehouse = "local"; desc = "Single Machine (all units)" }
}
$config = $roleConfig[$Role]

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Smart Cold Storage — Setup for Role: $($Role.ToUpper())" -ForegroundColor Cyan
Write-Host "  $($config.desc)" -ForegroundColor DarkCyan
Write-Host "============================================================" -ForegroundColor Cyan

# ─── Step 1: Prerequisites check ─────────────────────────────────────────────
Write-Step "Checking prerequisites..."

if (-not $SkipPrereqCheck) {
    # Docker Desktop
    try {
        $dockerVersion = docker --version 2>&1
        Write-OK "Docker: $dockerVersion"
    } catch {
        Write-Fail "Docker not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop"
        exit 1
    }

    # Docker running
    try {
        docker ps 2>&1 | Out-Null
        Write-OK "Docker daemon is running"
    } catch {
        Write-Fail "Docker daemon is not running. Start Docker Desktop first."
        exit 1
    }

    # Docker Compose
    try {
        $composeVersion = docker compose version 2>&1
        Write-OK "Docker Compose: $composeVersion"
    } catch {
        Write-Fail "Docker Compose not found. Update Docker Desktop."
        exit 1
    }

    # Git
    try {
        $gitVersion = git --version 2>&1
        Write-OK "Git: $gitVersion"
    } catch {
        Write-Warn "Git not found. You'll need it to update the repo."
    }

    # Python (for simulator)
    try {
        $pyVersion = python --version 2>&1
        Write-OK "Python: $pyVersion"
    } catch {
        Write-Warn "Python not found. Simulator won't work without it."
    }
} else {
    Write-Info "Prerequisite check skipped."
}

# ─── Step 2: .env file setup ─────────────────────────────────────────────────
Write-Step "Configuring .env file..."

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-OK "Created .env from .env.example"
    } else {
        Write-Fail ".env.example not found. Are you in the smart_cooling directory?"
        exit 1
    }
}

# Read current .env
$envContent = Get-Content ".env" -Raw

# Update NODE_ROLE
if ($envContent -match "NODE_ROLE=") {
    $envContent = $envContent -replace "NODE_ROLE=.*", "NODE_ROLE=$Role"
} else {
    $envContent += "`nNODE_ROLE=$Role"
}

# Update UNIT_IDS
if ($config.units -ne "") {
    if ($envContent -match "UNIT_IDS=") {
        $envContent = $envContent -replace "UNIT_IDS=.*", "UNIT_IDS=$($config.units)"
    } else {
        $envContent += "`nUNIT_IDS=$($config.units)"
    }
}

# Update WAREHOUSE_ID
if ($envContent -match "WAREHOUSE_ID=") {
    $envContent = $envContent -replace "WAREHOUSE_ID=.*", "WAREHOUSE_ID=$($config.warehouse)"
} else {
    $envContent += "`nWAREHOUSE_ID=$($config.warehouse)"
}

# Set InfluxDB retention for edge nodes (7 days) vs single (90 days)
if ($Role -in @("alpha", "beta")) {
    $envContent = $envContent -replace "INFLUXDB_RETENTION=.*", "INFLUXDB_RETENTION=7d"
    $envContent = $envContent -replace "ADAPTIVE_THRESHOLDS=.*", "ADAPTIVE_THRESHOLDS=true"
    $envContent = $envContent -replace "IOFOG_BUS_ENABLED=.*", "IOFOG_BUS_ENABLED=true"
} elseif ($Role -eq "single") {
    $envContent = $envContent -replace "INFLUXDB_RETENTION=.*", "INFLUXDB_RETENTION=90d"
}

[System.IO.File]::WriteAllText((Resolve-Path ".env"), $envContent, [System.Text.UTF8Encoding]::new($false))
Write-OK ".env configured for role: $Role"

# ─── Step 3: Create host directories ─────────────────────────────────────────
Write-Step "Creating host directories..."

$dirs = @(
    "C:\smart-cooling\mosquitto\config",
    "C:\smart-cooling\mosquitto\data",
    "C:\smart-cooling\mosquitto\log",
    "C:\smart-cooling\nodered",
    "C:\smart-cooling\influxdb\data",
    "C:\smart-cooling\influxdb\config",
    "C:\smart-cooling\grafana\data",
    "C:\smart-cooling\grafana\provisioning",
    "C:\smart-cooling\grafana\dashboards",
    "C:\smart-cooling\gcp"
)

foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
Write-OK "Host directories created at C:\smart-cooling\"

# Copy mosquitto config to host dir
if (Test-Path ".\mosquitto\config\mosquitto.conf") {
    Copy-Item ".\mosquitto\config\mosquitto.conf" "C:\smart-cooling\mosquitto\config\" -Force
    Write-OK "Mosquitto config copied"
}

# Copy Node-RED files to host dir
if (Test-Path ".\nodered\flows.json") {
    Copy-Item ".\nodered\flows.json" "C:\smart-cooling\nodered\" -Force
    Copy-Item ".\nodered\settings.js" "C:\smart-cooling\nodered\" -Force
    Copy-Item ".\nodered\flows_cred.json" "C:\smart-cooling\nodered\" -Force -ErrorAction SilentlyContinue
    Copy-Item ".\nodered\package.json" "C:\smart-cooling\nodered\" -Force
    Write-OK "Node-RED files copied"
}

# Copy Grafana files
if (Test-Path ".\grafana\provisioning") {
    Copy-Item ".\grafana\provisioning" "C:\smart-cooling\grafana\" -Recurse -Force
    Copy-Item ".\grafana\dashboards" "C:\smart-cooling\grafana\" -Recurse -Force
    Write-OK "Grafana provisioning files copied"
}

# Copy GCP service account key if exists
if (Test-Path ".\gcp\service-account.json") {
    Copy-Item ".\gcp\service-account.json" "C:\smart-cooling\gcp\" -Force
    Write-OK "GCP service account key copied"
} else {
    Write-Warn "GCP service account key not found at .\gcp\service-account.json"
    Write-Info "Run gcp/setup.sh first to generate the key, then re-run this script."
}

# ─── Step 4: Pull Docker images ───────────────────────────────────────────────
Write-Step "Pulling Docker images for role: $Role..."

if (-not $SkipDockerPull) {
    $images = @("eclipse-mosquitto:2.0", "influxdb:2.7", "nodered/node-red:latest")

    if ($Role -in @("", "single")) {
        $images += @("mongo:6.0", "eclipse/ditto-policies:3.4.0", "eclipse/ditto-things:3.4.0",
                     "eclipse/ditto-things-search:3.4.0", "eclipse/ditto-connectivity:3.4.0",
                     "eclipse/ditto-gateway:3.4.0", "grafana/grafana:10.2.0")
    }
    if ($Role -eq "gamma") {
        $images = @("grafana/grafana:10.2.0", "eclipse/ditto-ui:3.4.0")
    }

    foreach ($img in $images) {
        Write-Info "Pulling $img ..."
        docker pull $img 2>&1 | Out-Null
        Write-OK "$img pulled"
    }
} else {
    Write-Info "Docker pull skipped."
}

# ─── Step 5: Install ioFog Agent (distributed mode only) ─────────────────────
if ($Role -in @("alpha", "beta", "gamma")) {
    Write-Step "Setting up ioFog Agent..."

    $controllerIp = (Get-Content ".env" | Select-String "IOFOG_CONTROLLER_IP=(.+)" | ForEach-Object { $_.Matches.Groups[1].Value })

    if (-not $controllerIp -or $controllerIp -eq "") {
        Write-Warn "IOFOG_CONTROLLER_IP not set in .env"
        Write-Info "Set IOFOG_CONTROLLER_IP=<GCP_VM_IP> in .env and re-run."
        Write-Info "Skipping ioFog Agent start for now."
    } else {
        # Check if agent container already running
        $agentRunning = docker ps --filter "name=smart_cooling_iofog_agent" --format "{{.Names}}" 2>&1
        if ($agentRunning -eq "smart_cooling_iofog_agent") {
            Write-OK "ioFog Agent already running"
        } else {
            Write-Info "Starting ioFog Agent container..."
            docker run -d `
                --name smart_cooling_iofog_agent `
                --restart unless-stopped `
                --privileged `
                -v /var/run/docker.sock:/var/run/docker.sock `
                -v smart_cooling_iofog_agent_data:/var/lib/iofog-agent `
                -v smart_cooling_iofog_agent_log:/var/log/iofog-agent `
                -e IOFOG_CONTROLLER_URL="http://${controllerIp}:51121" `
                -e IOFOG_AGENT_NAME="${Role}-agent" `
                iofog/agent:3.4.0 2>&1 | Out-Null
            Write-OK "ioFog Agent started — connecting to Controller at $controllerIp"
            Write-Info "Agent will appear in Controller within ~30 seconds"
        }
    }
}

# ─── Step 6: Start Docker Compose with profile ───────────────────────────────
Write-Step "Starting Docker Compose services..."

if ($Role -eq "single") {
    Write-Info "Starting all services (single machine mode)..."
    docker compose up -d 2>&1 | Select-String "Started|Created|Running|Error" | ForEach-Object { Write-Info $_ }
} else {
    Write-Info "Starting services for profile: $Role ..."
    docker compose --profile $Role up -d 2>&1 | Select-String "Started|Created|Running|Error" | ForEach-Object { Write-Info $_ }
}

# ─── Step 7: Wait and verify ──────────────────────────────────────────────────
Write-Step "Waiting for services to initialize (30 seconds)..."
Start-Sleep -Seconds 30

$containers = docker ps --filter "name=smart_cooling" --format "{{.Names}}`t{{.Status}}" 2>&1
Write-Host ""
Write-Host "  Container Status:" -ForegroundColor DarkGray
$containers | ForEach-Object {
    if ($_ -match "Up") { Write-Host "  $_ " -ForegroundColor Green }
    else                { Write-Host "  $_ " -ForegroundColor Yellow }
}

# ─── Step 8: Install Python simulator deps ────────────────────────────────────
if ($Role -in @("single", "alpha")) {
    Write-Step "Installing Python simulator dependencies..."
    try {
        Set-Location simulator
        python -m pip install -r requirements.txt --quiet
        Set-Location ..
        Write-OK "Python dependencies installed"
    } catch {
        Write-Warn "Could not install Python deps: $($_.Exception.Message)"
    }
}

# ─── Summary ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Setup Complete for Role: $($Role.ToUpper())" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""

switch ($Role) {
    "single" {
        Write-Host "  Access Points:" -ForegroundColor White
        Write-Host "    Web Controller : http://localhost:8088" -ForegroundColor Cyan
        Write-Host "    Grafana        : http://localhost:3000  (admin / Valan@2005)" -ForegroundColor Cyan
        Write-Host "    Node-RED       : http://localhost:1880" -ForegroundColor Cyan
        Write-Host "    InfluxDB       : http://localhost:8086" -ForegroundColor Cyan
        Write-Host "    Ditto API      : http://localhost:8080" -ForegroundColor Cyan
        Write-Host "    REST API       : http://localhost:3001/api/health" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Start simulator:" -ForegroundColor White
        Write-Host "    cd simulator" -ForegroundColor DarkGray
        Write-Host "    python sensor_simulator.py" -ForegroundColor DarkGray
    }
    "alpha" {
        Write-Host "  This laptop handles: CS-01, CS-02 (Warehouse Alpha)" -ForegroundColor White
        Write-Host "  Access Points:" -ForegroundColor White
        Write-Host "    Web Controller : http://localhost:8088" -ForegroundColor Cyan
        Write-Host "    Node-RED       : http://localhost:1880" -ForegroundColor Cyan
        Write-Host "    InfluxDB       : http://localhost:8086" -ForegroundColor Cyan
        Write-Host "    REST API       : http://localhost:3001/api/health" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Next: Set IOFOG_CONTROLLER_IP in .env then re-run:" -ForegroundColor Yellow
        Write-Host "    .\setup.ps1 -Role alpha" -ForegroundColor DarkGray
    }
    "beta" {
        Write-Host "  This laptop handles: CS-03 (Warehouse Beta)" -ForegroundColor White
        Write-Host "  Access Points:" -ForegroundColor White
        Write-Host "    Node-RED       : http://localhost:1880" -ForegroundColor Cyan
        Write-Host "    InfluxDB       : http://localhost:8086" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Next: Set IOFOG_CONTROLLER_IP in .env then re-run:" -ForegroundColor Yellow
        Write-Host "    .\setup.ps1 -Role beta" -ForegroundColor DarkGray
    }
    "gamma" {
        Write-Host "  This laptop is the Operations Console" -ForegroundColor White
        Write-Host "  Access Points:" -ForegroundColor White
        Write-Host "    Grafana        : http://localhost:3000  (admin / Valan@2005)" -ForegroundColor Cyan
        Write-Host "    Fleet Dashboard: http://localhost:8090  (after Phase 5)" -ForegroundColor Cyan
        Write-Host "    Ditto UI       : http://localhost:8091  (after Phase 5)" -ForegroundColor Cyan
    }
}

Write-Host ""
Write-Host "  Logs: docker compose logs -f" -ForegroundColor DarkGray
Write-Host "  Stop: docker compose --profile $Role down" -ForegroundColor DarkGray
Write-Host ""
