# =============================================================================
# Kali MCP Bounty Lab - Windows Installer
# Usage: powershell -ExecutionPolicy Bypass -File install_windows.ps1 -Phase <phase>
#
# Phases: prereqs | claude | portproxy
# Options:
#   -VmIp    <ip>    Ubuntu VM IP (required for claude + portproxy)
#   -McpPort <port>  MCP port (default: 8000)
# =============================================================================
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("prereqs","prereqs-install","claude","portproxy")]
    [string]$Phase,

    [string]$VmIp    = "",
    [string]$McpPort = "8000"
)

$ErrorActionPreference = "Continue"
Set-StrictMode -Off

# Helpers
function Write-OK($msg)  { Write-Host "  OK  $msg" -ForegroundColor Green  }
function Write-WN($msg)  { Write-Host "  ??  $msg" -ForegroundColor Yellow }
function Write-ER($msg)  { Write-Host "  XX  $msg" -ForegroundColor Red    }
function Write-SEC($msg) { Write-Host ""; Write-Host "---  $msg  ---" -ForegroundColor Cyan }

function Test-Cmd($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = [Security.Principal.WindowsPrincipal]$id
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Find-McpRemote {
    $found = Get-Command "mcp-remote" -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }

    try {
        $npmBin = (npm bin -g 2>$null).Trim()
        if ($npmBin -and (Test-Path "$npmBin\mcp-remote.cmd")) {
            return "$npmBin\mcp-remote.cmd"
        }
    } catch {}

    $candidates = @(
        "$env:APPDATA\npm\mcp-remote.cmd",
        "$env:APPDATA\npm\mcp-remote",
        "$env:ProgramFiles\nodejs\node_modules\.bin\mcp-remote.cmd",
        "$env:LOCALAPPDATA\npm\mcp-remote.cmd"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    return $null
}

function Read-ClaudeConfig($path) {
    if (-not (Test-Path $path)) { return $null }
    try {
        $raw = Get-Content $path -Raw -ErrorAction Stop
        if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
        return $raw | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-WN "Existing config could not be parsed: $_"
        return $null
    }
}

# =============================================================================
# PHASE: prereqs
# =============================================================================
function Phase-Prereqs {
    Write-SEC "Checking prerequisites"

    # Node.js - auto install if missing
    if (Test-Cmd "node") {
        $v = (node --version 2>&1)
        Write-OK "Node.js: $v"
    } else {
        Write-WN "Node.js: NOT FOUND - attempting auto-install via winget..."
        try {
            $wg = Get-Command "winget" -ErrorAction SilentlyContinue
            if ($wg) {
                winget install -e --id OpenJS.NodeJS.LTS --source winget --accept-source-agreements --accept-package-agreements 2>&1 | Write-Host
                $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" +
                            [System.Environment]::GetEnvironmentVariable("PATH","User")
                if (Test-Cmd "node") {
                    Write-OK "Node.js: installed OK - $(node --version 2>&1)"
                } else {
                    Write-WN "Node.js installed but not in PATH yet - close and reopen window then re-run"
                }
            } else {
                Write-ER "winget not available - install Node.js manually from https://nodejs.org"
            }
        } catch {
            Write-ER "Node.js auto-install failed: $_"
        }
    }

    # npm
    if (Test-Cmd "npm") {
        $v = (npm --version 2>&1)
        Write-OK "npm: $v"
    } else {
        Write-WN "npm: NOT FOUND (should come with Node.js - try re-running prereqs)"
    }

    # mcp-remote
    $mcpPath = Find-McpRemote
    if ($mcpPath) {
        Write-OK "mcp-remote: found at $mcpPath"
    } else {
        Write-WN "mcp-remote: NOT FOUND - installing now..."
        if (Test-Cmd "npm") {
            $result = npm install -g mcp-remote 2>&1
            Write-Host $result
            $mcpPath = Find-McpRemote
            if ($mcpPath) {
                Write-OK "mcp-remote: installed at $mcpPath"
            } else {
                Write-WN "mcp-remote installed but not in PATH yet - may need new window"
            }
        } else {
            Write-ER "Cannot install mcp-remote - npm is not available"
        }
    }

    # git (optional)
    if (Test-Cmd "git") {
        $v = (git --version 2>&1)
        Write-OK "git: $v"
    } else {
        Write-WN "git: NOT FOUND (optional - download from https://git-scm.com)"
    }

    # curl
    if (Test-Cmd "curl") {
        Write-OK "curl: available"
    } else {
        Write-WN "curl: NOT FOUND (usually built into Windows 10+)"
    }

    # netsh - always present
    Write-OK "netsh: built-in"

    # Admin check
    if (Test-Admin) {
        Write-OK "Administrator privileges: YES"
    } else {
        Write-WN "Administrator privileges: NO"
        Write-WN "  The portproxy phase requires admin."
        Write-WN "  Right-click run.bat and choose Run as administrator"
    }

    # Claude Desktop
    $claudeDir = "$env:APPDATA\Claude"
    $claudeExe = @(
        "$env:LOCALAPPDATA\Programs\Claude\Claude.exe",
        "$env:ProgramFiles\Claude\Claude.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1

    if ($claudeExe) {
        Write-OK "Claude Desktop: found at $claudeExe"
    } elseif (Test-Path $claudeDir) {
        Write-WN "Claude Desktop: config folder found but exe not located (this is fine)"
    } else {
        Write-ER "Claude Desktop: NOT found"
        Write-WN "  Download the DIRECT installer (not Microsoft Store) from:"
        Write-WN "  https://claude.ai/download"
    }

    Write-Host ""
    Write-OK "Prereq scan complete."
}

# =============================================================================
# PHASE: claude
# =============================================================================
function Phase-Claude {
    Write-SEC "Claude Desktop config"

    if ([string]::IsNullOrWhiteSpace($VmIp)) {
        Write-ER "-VmIp is required for this phase"
        Write-ER "Example: -VmIp 192.168.91.132"
        exit 1
    }

    if ($VmIp -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
        Write-ER "VmIp '$VmIp' does not look like a valid IP address"
        exit 1
    }

    $mcpPath = Find-McpRemote
    if (-not $mcpPath) {
        Write-WN "mcp-remote not found - installing..."
        if (-not (Test-Cmd "npm")) {
            Write-ER "npm not found - install Node.js from https://nodejs.org first"
            exit 1
        }
        npm install -g mcp-remote 2>&1 | Write-Host
        $mcpPath = Find-McpRemote
        if (-not $mcpPath) {
            Write-ER "mcp-remote still not found after install."
            Write-WN "Open a NEW terminal and re-run this phase."
            exit 1
        }
    }
    Write-OK "mcp-remote: $mcpPath"

    $cfgDir  = "$env:APPDATA\Claude"
    $cfgPath = "$cfgDir\claude_desktop_config.json"

    if (-not (Test-Path $cfgDir)) {
        New-Item -ItemType Directory -Path $cfgDir -Force | Out-Null
        Write-OK "Created Claude config directory: $cfgDir"
    }

    $cfg = Read-ClaudeConfig $cfgPath

    if ($null -eq $cfg) {
        if (Test-Path $cfgPath) {
            $backup = "$cfgPath.bak"
            Copy-Item $cfgPath $backup -Force
            Write-WN "Backed up unreadable config to: $backup"
        }
        $cfg = [PSCustomObject]@{ mcpServers = [PSCustomObject]@{} }
        Write-OK "Starting with empty config"
    } else {
        Write-OK "Loaded existing config"
    }

    if (-not ($cfg.PSObject.Properties.Name -contains "mcpServers")) {
        $cfg | Add-Member -MemberType NoteProperty -Name "mcpServers" -Value ([PSCustomObject]@{})
    }

    $kaliEntry = [PSCustomObject]@{
        command = $mcpPath
        args    = @("http://localhost:$McpPort/sse")
    }

    if ($cfg.mcpServers.PSObject.Properties.Name -contains "kali") {
        $cfg.mcpServers.kali = $kaliEntry
        Write-OK "Updated existing kali entry"
    } else {
        $cfg.mcpServers | Add-Member -MemberType NoteProperty -Name "kali" -Value $kaliEntry
        Write-OK "Added kali entry"
    }

    $json = $cfg | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($cfgPath, $json, [System.Text.UTF8Encoding]::new($false))
    Write-OK "Config written to: $cfgPath"

    Write-Host ""
    Write-Host $json -ForegroundColor DarkGray
    Write-Host ""
    Write-OK "Next: Quit Claude Desktop from system tray, then relaunch."
    Write-OK "Then click + in chat -> Connectors -> verify kali is listed."
}

# =============================================================================
# PHASE: portproxy
# =============================================================================
function Phase-Portproxy {
    Write-SEC "Port proxy setup"

    if (-not (Test-Admin)) {
        Write-ER "This phase requires Administrator privileges."
        Write-ER ""
        Write-ER "How to fix:"
        Write-ER "  1. Close this window"
        Write-ER "  2. Right-click run.bat"
        Write-ER "  3. Choose Run as administrator"
        Write-ER "  4. Navigate back to the Port Proxy step"
        exit 1
    }
    Write-OK "Running as Administrator"

    if ([string]::IsNullOrWhiteSpace($VmIp)) {
        Write-ER "-VmIp is required for this phase"
        exit 1
    }

    if ($VmIp -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
        Write-ER "VmIp '$VmIp' does not look like a valid IP address"
        exit 1
    }

    $listenAddr = "127.0.0.1"

    # Remove old rules
    Write-OK "Checking for existing portproxy rules on port $McpPort..."
    netsh interface portproxy delete v4tov4 listenaddress=$listenAddr listenport=$McpPort 2>&1 | Out-Null
    netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$McpPort 2>&1 | Out-Null

    # Add rule
    Write-OK "Adding portproxy: $listenAddr`:$McpPort -> $VmIp`:$McpPort"
    $result = netsh interface portproxy add v4tov4 `
        listenaddress=$listenAddr `
        listenport=$McpPort `
        connectaddress=$VmIp `
        connectport=$McpPort 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-ER "netsh portproxy add failed: $result"
        exit 1
    }
    Write-OK "Portproxy rule added"

    # Firewall rule
    $ruleName = "KaliMCP-Port$McpPort"
    Remove-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Out-Null

    try {
        New-NetFirewallRule `
            -DisplayName $ruleName `
            -Direction Inbound `
            -Protocol TCP `
            -LocalPort ([int]$McpPort) `
            -Action Allow `
            -ErrorAction Stop | Out-Null
        Write-OK "Firewall rule created: $ruleName"
    } catch {
        Write-WN "New-NetFirewallRule failed: $_ - trying netsh fallback..."
        netsh advfirewall firewall add rule name="$ruleName" protocol=TCP dir=in localport=$McpPort action=allow 2>&1 | Write-Host
    }

    Write-Host ""
    Write-OK "Current portproxy rules:"
    netsh interface portproxy show all 2>&1 | Write-Host

    # TCP test
    Write-Host ""
    Write-OK "Testing TCP connection to $VmIp`:$McpPort ..."
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $iar = $tcp.BeginConnect($VmIp, [int]$McpPort, $null, $null)
        $ok  = $iar.AsyncWaitHandle.WaitOne(4000, $false)
        if ($ok) {
            try { $tcp.EndConnect($iar) } catch {}
            Write-OK "Connection to $VmIp`:$McpPort succeeded"
        } else {
            Write-WN "Connection timed out - make sure the Ubuntu VM and Docker container are running"
        }
        $tcp.Close()
    } catch {
        Write-WN "TCP test error: $_"
    }

    Write-Host ""
    Write-OK "Test in browser: http://localhost:$McpPort/sse"
    Write-OK "Expected:        event: endpoint"
}


# =============================================================================
# PHASE: prereqs-install
# Installs missing prerequisites automatically. Safe to re-run.
# =============================================================================
function Phase-PrereqsInstall {
    Write-SEC "Installing missing prerequisites"

    # git
    if (-not (Test-Cmd "git")) {
        Write-OK "Installing git..."
        try {
            winget install -e --id Git.Git --source winget --accept-source-agreements --accept-package-agreements 2>&1 | Write-Host
            $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" +
                        [System.Environment]::GetEnvironmentVariable("PATH","User")
            if (Test-Cmd "git") {
                Write-OK "git: installed OK"
            } else {
                Write-WN "git installed - may need to reopen window for PATH to refresh"
            }
        } catch {
            Write-WN "git install failed: $_ - download from https://git-scm.com"
        }
    } else {
        Write-OK "git: already installed"
    }

    # Claude Desktop
    $claudeExe = @(
        "$env:LOCALAPPDATA\Programs\Claude\Claude.exe",
        "$env:ProgramFiles\Claude\Claude.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1

    if (-not $claudeExe) {
        Write-OK "Installing Claude Desktop..."
        try {
            winget install -e --id Anthropic.Claude --source winget --accept-source-agreements --accept-package-agreements 2>&1 | Write-Host
            $claudeExe = @(
                "$env:LOCALAPPDATA\Programs\Claude\Claude.exe",
                "$env:ProgramFiles\Claude\Claude.exe"
            ) | Where-Object { Test-Path $_ } | Select-Object -First 1
            if ($claudeExe) {
                Write-OK "Claude Desktop: installed at $claudeExe"
            } else {
                Write-WN "Claude Desktop install ran - if it did not appear, download manually:"
                Write-WN "  https://claude.ai/download  (use the DIRECT installer, not Microsoft Store)"
            }
        } catch {
            Write-WN "Claude Desktop auto-install failed: $_"
            Write-WN "  Download manually from https://claude.ai/download"
        }
    } else {
        Write-OK "Claude Desktop: already installed"
    }

    # Node.js
    if (-not (Test-Cmd "node")) {
        Write-OK "Installing Node.js..."
        try {
            winget install -e --id OpenJS.NodeJS.LTS --source winget --accept-source-agreements --accept-package-agreements 2>&1 | Write-Host
            $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" +
                        [System.Environment]::GetEnvironmentVariable("PATH","User")
            if (Test-Cmd "node") {
                Write-OK "Node.js: installed OK"
            } else {
                Write-WN "Node.js installed - may need to reopen window for PATH to refresh"
            }
        } catch {
            Write-WN "Node.js install failed: $_ - download from https://nodejs.org"
        }
    } else {
        Write-OK "Node.js: already installed"
    }

    # mcp-remote
    $mcpPath = Find-McpRemote
    if (-not $mcpPath) {
        if (Test-Cmd "npm") {
            Write-OK "Installing mcp-remote..."
            npm install -g mcp-remote 2>&1 | Write-Host
            $mcpPath = Find-McpRemote
            if ($mcpPath) {
                Write-OK "mcp-remote: installed at $mcpPath"
            } else {
                Write-WN "mcp-remote install ran but binary not found - try re-running checks"
            }
        } else {
            Write-WN "npm not available yet - install Node.js first then re-run"
        }
    } else {
        Write-OK "mcp-remote: already installed"
    }

    Write-Host ""
    Write-OK "Done. Click Run Checks again to verify everything is green."
    Write-WN "Note: Administrator privileges cannot be auto-granted."
    Write-WN "  Right-click run.bat and choose Run as administrator for the Port Proxy step."
}

# =============================================================================
# Dispatch
# =============================================================================
switch ($Phase) {
    "prereqs"         { Phase-Prereqs         }
    "prereqs-install" { Phase-PrereqsInstall  }
    "claude"          { Phase-Claude          }
    "portproxy"       { Phase-Portproxy       }
}
