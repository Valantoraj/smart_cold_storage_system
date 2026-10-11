# setup-wsl.ps1 — Run in Admin PowerShell on each laptop
# Usage:
#   L1 (Edge,   8GB+):  .\setup-wsl.ps1 -Role edge
#   L2 (Fog,   12GB+):  .\setup-wsl.ps1 -Role fog
#   L3 (Core,  16GB+):  .\setup-wsl.ps1 -Role core   (already done)

param(
    [ValidateSet("edge","fog","core")]
    [string]$Role = "edge"
)

$memMap  = @{ edge = "5GB";  fog = "8GB";  core = "11GB" }
$cpuMap  = @{ edge = "4";    fog = "4";    core = "4"    }
$swapMap = @{ edge = "4GB";  fog = "4GB";  core = "4GB"  }

$mem  = $memMap[$Role]
$cpu  = $cpuMap[$Role]
$swap = $swapMap[$Role]

Write-Host "Configuring WSL2 for role: $Role (memory=$mem)" -ForegroundColor Cyan

# Write .wslconfig
$cfg = @"
[wsl2]
networkingMode=mirrored
memory=$mem
processors=$cpu
swap=$swap

[experimental]
hostAddressLoopback=true
"@
[System.IO.File]::WriteAllText("$env:USERPROFILE\.wslconfig", $cfg, [System.Text.UTF8Encoding]::new($false))
Write-Host ".wslconfig written" -ForegroundColor Green

# Power settings (prevent sleep during demo)
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0
powercfg /hibernate off
Write-Host "Sleep disabled" -ForegroundColor Green

# Firewall — allow all TCP from local subnet (lab only)
Set-NetConnectionProfile -NetworkCategory Private -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "ColdTwin LAN inbound" -Direction Inbound `
  -Action Allow -Protocol TCP -RemoteAddress LocalSubnet -Profile Any `
  -ErrorAction SilentlyContinue | Out-Null
Write-Host "Firewall rule added" -ForegroundColor Green

# Restart WSL to apply memory config
wsl --shutdown
Write-Host "WSL shutdown — reopen Ubuntu to apply new config" -ForegroundColor Yellow
Write-Host ""
Write-Host "Next steps inside Ubuntu WSL:" -ForegroundColor White
Write-Host "  1. sudo snap install tailscale" -ForegroundColor DarkGray
Write-Host "  2. sudo tailscale up --hostname=coldtwin-$Role --accept-dns=false" -ForegroundColor DarkGray
Write-Host "  3. tailscale ip -4   (paste this IP to team)" -ForegroundColor DarkGray
Write-Host "  4. curl -fsSL https://raw.githubusercontent.com/.../prep-host.sh | ROLE=$Role bash" -ForegroundColor DarkGray
