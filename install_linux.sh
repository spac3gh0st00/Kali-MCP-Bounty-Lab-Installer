#!/usr/bin/env bash
# =============================================================================
# Kali MCP Bounty Lab — Linux Installer  (hardened)
# Usage:  bash install_linux.sh --phase <phase> [OPTIONS]
#
# Phases:   prereqs | docker | kali | mcp | discord | health | tailscale | firewall
# Options:
#   --repo-url    <url>       repo to clone  (default: https://github.com/k3nn3dy-ai/kali-mcp)
#   --install-dir <path>      clone location (default: ~/kali-mcp)
#   --mcp-port    <port>      MCP port       (default: 8000)
#   --host-ip     <ip>        Windows host IP for UFW rule
#   --ssh-port    <port>      SSH port       (default: 22)
#   --discord     true|false  (default: true)
#   --health      true|false  (default: true)
#   --tailscale   true|false  (default: true)
#   --vm-subnet   <cidr>      UFW subnet fallback (default: 192.168.91.0/24)
# =============================================================================

# ── No set -e. Every command is checked individually. ─────────────────────────
set -uo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
PHASE=""
REPO_URL="https://github.com/k3nn3dy-ai/kali-mcp"
INSTALL_DIR="${HOME}/kali-mcp"
MCP_PORT="8000"
HOST_IP=""
SSH_PORT="22"
DISCORD="true"
HEALTH="true"
TAILSCALE_INSTALL="true"
VM_SUBNET="192.168.91.0/24"

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --phase)        PHASE="$2";             shift 2 ;;
    --repo-url)     REPO_URL="$2";          shift 2 ;;
    --install-dir)  INSTALL_DIR="$2";       shift 2 ;;
    --mcp-port)     MCP_PORT="$2";          shift 2 ;;
    --host-ip)      HOST_IP="$2";           shift 2 ;;
    --ssh-port)     SSH_PORT="$2";          shift 2 ;;
    --discord)      DISCORD="$2";           shift 2 ;;
    --health)       HEALTH="$2";            shift 2 ;;
    --tailscale)    TAILSCALE_INSTALL="$2"; shift 2 ;;
    --vm-subnet)    VM_SUBNET="$2";         shift 2 ;;
    *) echo "  ✗  Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "$PHASE" ]]; then
  echo "  ✗  --phase is required"
  echo "     Valid phases: prereqs docker kali mcp discord health tailscale firewall"
  exit 1
fi

# Expand ~ in INSTALL_DIR now so every phase uses the real path
INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"

# ── Colour helpers ────────────────────────────────────────────────────────────
info()    { echo "  ✓  $*"; }
warn()    { echo "  ⚠  $*"; }
err()     { echo "  ✗  $*"; }
section() { echo ""; echo "━━━  $*  ━━━"; }

# ── docker compose shim ───────────────────────────────────────────────────────
# Supports both the v2 plugin (docker compose) and the v1 standalone binary
docker_compose() {
  if docker compose version &>/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose &>/dev/null; then
    docker-compose "$@"
  else
    err "Neither 'docker compose' (v2) nor 'docker-compose' (v1) found."
    err "Run the docker phase first to install Docker Engine."
    return 1
  fi
}

# ── Find the running kali container name ─────────────────────────────────────
# docker-compose.yml might name it anything; we grep for 'kali' in the names
get_container_name() {
  docker ps --format '{{.Names}}' 2>/dev/null | grep -i kali | head -1
}

# ── Idempotent sudo apt-get install ──────────────────────────────────────────
apt_install() {
  sudo apt-get install -y "$@" 2>&1 || {
    warn "apt-get install failed for: $*"
    warn "Try: sudo apt-get update -y && sudo apt-get install -y $*"
  }
}

# =============================================================================
# PHASE: prereqs
# =============================================================================
phase_prereqs() {
  section "Checking prerequisites"

  check_cmd() {
    local label="$1" cmd="$2" ver_flag="${3:---version}"
    if command -v "$cmd" &>/dev/null; then
      local ver
      ver=$("$cmd" "$ver_flag" 2>&1 | head -1) || ver="(version flag failed)"
      info "$label: $ver"
      return 0
    else
      warn "$label: NOT FOUND"
      return 1
    fi
  }

  check_cmd "git"     "git"
  check_cmd "curl"    "curl"
  check_cmd "python3" "python3"
  check_cmd "ufw"     "ufw"

  # Docker — check both binary and daemon
  if command -v docker &>/dev/null; then
    info "docker binary: $(docker --version 2>&1)"
    if docker ps &>/dev/null 2>&1; then
      info "docker daemon: running"
    else
      warn "docker daemon: not running (will be started in the Docker phase)"
    fi
  else
    warn "docker: NOT FOUND (will be installed in the Docker phase)"
  fi

  # docker compose v2 or v1
  if docker compose version &>/dev/null 2>&1; then
    info "docker compose: v2 plugin — $(docker compose version 2>&1 | head -1)"
  elif command -v docker-compose &>/dev/null; then
    warn "docker compose: v1 standalone found — $(docker-compose --version 2>&1 | head -1)"
    warn "  v2 will be installed in the Docker phase"
  else
    warn "docker compose: not found (will be installed in the Docker phase)"
  fi

  # python3-tk (needed for the GUI)
  if python3 -c "import tkinter" &>/dev/null 2>&1; then
    info "python3-tk: OK"
  else
    warn "python3-tk: NOT FOUND — install with: sudo apt-get install python3-tk"
  fi

  # customtkinter (needed for the GUI)
  if python3 -c "import customtkinter" &>/dev/null 2>&1; then
    info "customtkinter: OK"
  else
    warn "customtkinter: NOT FOUND — install with: pip install customtkinter"
  fi

  echo ""
  info "Prereq scan complete.  Fix any warning items before proceeding."
}

# =============================================================================
# PHASE: prereqs-install
# Installs anything missing. Safe to re-run.
# =============================================================================
phase_prereqs_install() {
  section "Installing missing prerequisites"

  sudo apt-get update -y 2>&1 || warn "apt-get update had errors — continuing anyway"

  # git
  if ! command -v git &>/dev/null; then
    info "Installing git..."
    apt_install git
    command -v git &>/dev/null && info "git: installed" || warn "git install may have failed"
  else
    info "git: already present"
  fi

  # curl
  if ! command -v curl &>/dev/null; then
    info "Installing curl..."
    apt_install curl
    command -v curl &>/dev/null && info "curl: installed" || warn "curl install may have failed"
  else
    info "curl: already present"
  fi

  # python3
  if ! command -v python3 &>/dev/null; then
    info "Installing python3..."
    apt_install python3
    command -v python3 &>/dev/null && info "python3: installed" || warn "python3 install may have failed"
  else
    info "python3: already present"
  fi

  # python3-tk
  if ! python3 -c "import tkinter" &>/dev/null 2>&1; then
    info "Installing python3-tk..."
    apt_install python3-tk
    python3 -c "import tkinter" &>/dev/null 2>&1 \
      && info "python3-tk: installed" \
      || warn "python3-tk install may have failed"
  else
    info "python3-tk: already present"
  fi

  # pip
  if ! python3 -m pip --version &>/dev/null 2>&1; then
    info "Installing python3-pip..."
    apt_install python3-pip
  else
    info "python3-pip: already present"
  fi

  # customtkinter
  if ! python3 -c "import customtkinter" &>/dev/null 2>&1; then
    info "Installing customtkinter..."
    python3 -m pip install customtkinter --break-system-packages -q 2>&1 \
      || python3 -m pip install customtkinter --user -q 2>&1 \
      || python3 -m pip install customtkinter -q 2>&1 \
      || true
    python3 -c "import customtkinter" &>/dev/null 2>&1 \
      && info "customtkinter: installed" \
      || warn "customtkinter install failed — try: python3 -m pip install customtkinter --break-system-packages"
  else
    info "customtkinter: already present"
  fi

  # ufw
  if ! command -v ufw &>/dev/null; then
    info "Installing ufw..."
    apt_install ufw
    command -v ufw &>/dev/null && info "ufw: installed" || warn "ufw install may have failed"
  else
    info "ufw: already present"
  fi

  # Docker is handled in its own step
  if ! command -v docker &>/dev/null; then
    warn "docker: not installed here — use the Docker step for that"
  else
    info "docker: already present"
  fi

  echo ""
  info "Done. Click Run Checks again to verify everything is green."
}

# =============================================================================
# PHASE: docker
# =============================================================================
phase_docker() {
  section "Docker setup"

  if command -v docker &>/dev/null; then
    info "Docker already installed: $(docker --version 2>&1)"
  else
    info "Installing Docker Engine (official method)..."

    sudo apt-get update -y 2>&1 || warn "apt-get update had errors — continuing"

    apt_install ca-certificates curl gnupg lsb-release

    sudo install -m 0755 -d /etc/apt/keyrings

    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>&1 \
      || { err "Failed to download Docker GPG key — check your internet connection"; return 1; }

    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    ARCH=$(dpkg --print-architecture 2>/dev/null || echo "amd64")
    CODENAME=$(lsb_release -cs 2>/dev/null || echo "jammy")

    echo \
      "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu ${CODENAME} stable" \
      | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -y 2>&1 || warn "apt-get update had errors"

    apt_install docker-ce docker-ce-cli containerd.io \
                docker-buildx-plugin docker-compose-plugin

    if command -v docker &>/dev/null; then
      info "Docker installed: $(docker --version 2>&1)"
    else
      err "Docker installation failed — check the output above"
      return 1
    fi
  fi

  # docker group
  if groups "$USER" 2>/dev/null | grep -q docker; then
    info "User '$USER' is already in the docker group"
  else
    sudo usermod -aG docker "$USER" 2>&1 \
      && info "Added '$USER' to the docker group" \
      || warn "Could not add user to docker group (non-fatal if running as root)"
    warn "You may need to log out and back in (or run: newgrp docker)"
    warn "for docker to work without sudo in this session."
  fi

  # Enable and start daemon
  if sudo systemctl enable docker --now 2>&1; then
    info "Docker daemon: $(sudo systemctl is-active docker 2>&1)"
  else
    warn "systemctl enable docker failed — trying to start directly"
    sudo service docker start 2>&1 || warn "Could not start Docker daemon"
  fi

  # Sanity check — use sudo in case group change hasn't taken effect yet
  if sudo docker ps &>/dev/null 2>&1; then
    info "Docker is working correctly"
  else
    err "Docker is installed but 'docker ps' failed"
    err "Try: sudo docker ps  OR log out/in and try again"
  fi
}

# =============================================================================
# PHASE: kali
# =============================================================================
phase_kali() {
  section "Kali MCP container setup"

  # Ensure git is available
  if ! command -v git &>/dev/null; then
    info "Installing git..."
    apt_install git
  fi

  # Clone or update
  if [[ -d "${INSTALL_DIR}/.git" ]]; then
    info "Repo already cloned at ${INSTALL_DIR} — pulling latest..."
    cd "${INSTALL_DIR}" && git pull 2>&1 \
      || warn "git pull failed — continuing with existing files"
  elif [[ -d "${INSTALL_DIR}" ]]; then
    warn "Directory ${INSTALL_DIR} exists but is not a git repo."
    warn "Skipping clone — continuing with existing files."
    cd "${INSTALL_DIR}"
  else
    info "Cloning ${REPO_URL} → ${INSTALL_DIR} ..."
    git clone "${REPO_URL}" "${INSTALL_DIR}" 2>&1 \
      || { err "git clone failed — check the repo URL and your internet connection"; return 1; }
    cd "${INSTALL_DIR}"
  fi

  cd "${INSTALL_DIR}" || { err "Cannot cd into ${INSTALL_DIR}"; return 1; }

  # Check docker-compose.yml exists
  if [[ ! -f "docker-compose.yml" ]] && [[ ! -f "compose.yml" ]]; then
    err "No docker-compose.yml found in ${INSTALL_DIR}"
    err "The clone may be incomplete. Try deleting the folder and re-running."
    return 1
  fi

  info "Building Docker image — first run pulls ~3 GB, takes 10–20 min..."
  docker_compose build 2>&1 \
    || { err "docker compose build failed — check output above"; return 1; }

  info "Starting container..."
  docker_compose up -d 2>&1 \
    || { err "docker compose up -d failed"; return 1; }

  # Wait for container to appear
  local attempts=0
  local container=""
  while [[ $attempts -lt 10 ]]; do
    container=$(get_container_name)
    if [[ -n "$container" ]]; then
      info "Container running: $container"
      break
    fi
    attempts=$((attempts + 1))
    warn "Waiting for container to start... ($attempts/10)"
    sleep 3
  done

  if [[ -z "$container" ]]; then
    warn "No kali container found after 30 s — check: docker ps -a"
  else
    info "Last 10 log lines from $container:"
    docker logs "$container" 2>&1 | tail -10 || true
  fi
}

# =============================================================================
# PHASE: mcp
# =============================================================================
phase_mcp() {
  section "MCP server verification"

  cd "${INSTALL_DIR}" 2>/dev/null || {
    err "${INSTALL_DIR} not found — run the kali phase first"
    return 1
  }

  # Start container if not running
  local container
  container=$(get_container_name)
  if [[ -z "$container" ]]; then
    warn "No kali container found — starting..."
    docker_compose up -d 2>&1 || { err "Could not start container"; return 1; }
    sleep 5
    container=$(get_container_name)
  fi

  if [[ -n "$container" ]]; then
    info "Container: $container"
  else
    err "Container still not found after start attempt"
    err "Check: docker ps -a"
    return 1
  fi

  # Health check with retry
  info "Polling http://localhost:${MCP_PORT}/health (up to 30 s)..."
  local ok=0
  for i in $(seq 1 10); do
    local body
    body=$(curl -sf --max-time 3 "http://localhost:${MCP_PORT}/health" 2>/dev/null) && {
      info "Health endpoint OK: $body"
      ok=1
      break
    }
    warn "Attempt $i/10 — server not ready yet, waiting 3 s..."
    sleep 3
  done

  if [[ $ok -eq 0 ]]; then
    err "Health endpoint did not respond after 30 s"
    err "Check container logs: docker logs $container"
    warn "If /health returns 404, the endpoint may not be added yet."
    warn "See README Step 30 to add it to server.py, then rebuild: docker compose build && docker compose up -d"
  fi

  # SSE endpoint hint
  info "SSE endpoint: http://localhost:${MCP_PORT}/sse"
  info "Test in a browser — you should see: event: endpoint"
}

# =============================================================================
# PHASE: discord
# =============================================================================
phase_discord() {
  if [[ "$DISCORD" == "false" ]]; then
    info "Discord Bot: skipped"
    return 0
  fi

  section "Discord Bot setup"

  # ── .env validation ──────────────────────────────────────────────────────
  local env_file="${INSTALL_DIR}/.env"
  local env_ok=1

  if [[ ! -f "$env_file" ]]; then
    # Try to copy .env.example if it exists
    if [[ -f "${INSTALL_DIR}/.env.example" ]]; then
      cp "${INSTALL_DIR}/.env.example" "$env_file"
      warn ".env not found — copied .env.example to .env"
      warn "You still need to fill in the real values before the bot will work."
    else
      err ".env not found at $env_file"
      err "Create it with these keys:"
      err "  DISCORD_TOKEN=<your bot token>"
      err "  ALLOWED_USER_ID=<your Discord user ID>"
      err "  ANTHROPIC_API_KEY=<your Anthropic key>"
      err "  DISCORD_WEBHOOK_URL=<your Discord webhook URL>"
      return 1
    fi
  fi

  # Check each required key
  for key in DISCORD_TOKEN ALLOWED_USER_ID ANTHROPIC_API_KEY DISCORD_WEBHOOK_URL; do
    local val
    val=$(grep "^${key}=" "$env_file" 2>/dev/null | cut -d'=' -f2-)
    if [[ -z "$val" ]] || [[ "$val" == "your_"* ]] || [[ "$val" == "<"* ]]; then
      warn "  ${key} is not set in .env — bot will not work until this is filled in"
      env_ok=0
    else
      info "  ${key}: set"
    fi
  done

  if [[ $env_ok -eq 0 ]]; then
    warn "Some .env values are missing or look like placeholders."
    warn "Edit ${env_file} and re-run this phase."
    warn "Continuing with service setup anyway so you can fill it in later."
  fi

  # Lock .env permissions
  chmod 600 "$env_file" 2>/dev/null && info ".env permissions: 600" \
    || warn "Could not set .env permissions"

  # .gitignore
  if ! grep -qxF ".env" "${INSTALL_DIR}/.gitignore" 2>/dev/null; then
    echo ".env" >> "${INSTALL_DIR}/.gitignore" 2>/dev/null \
      && info ".env added to .gitignore" \
      || warn "Could not update .gitignore"
  else
    info ".env already in .gitignore"
  fi

  # ── Python venv ──────────────────────────────────────────────────────────
  if [[ ! -d "${INSTALL_DIR}/venv" ]]; then
    info "Creating Python virtual environment..."
    # Try python3.12-venv, fall back to python3-venv
    if python3 -m venv "${INSTALL_DIR}/venv" 2>/dev/null; then
      info "venv created with system python3-venv"
    else
      warn "python3 -m venv failed — trying to install venv package..."
      # Try version-specific first, then generic
      local pyver
      pyver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "")
      if [[ -n "$pyver" ]]; then
        apt_install "python${pyver}-venv" python3-pip 2>/dev/null \
          || apt_install python3-venv python3-pip
      else
        apt_install python3-venv python3-pip
      fi
      python3 -m venv "${INSTALL_DIR}/venv" 2>&1 \
        || { err "Could not create virtual environment"; return 1; }
      info "venv created"
    fi
  else
    info "venv already exists"
  fi

  # ── Install Python deps ──────────────────────────────────────────────────
  info "Installing Python dependencies..."
  "${INSTALL_DIR}/venv/bin/pip" install -q --upgrade pip 2>&1 || true
  "${INSTALL_DIR}/venv/bin/pip" install -q \
    discord.py httpx python-dotenv anthropic requests 2>&1 \
    || { err "pip install failed — check network and try again"; return 1; }
  info "Python deps installed"

  # ── Copy / fetch bot script ──────────────────────────────────────────────
  if [[ ! -f "${INSTALL_DIR}/discord_kali_bot.py" ]]; then
    # Preferred: bundled alongside the installer scripts
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ -f "${SCRIPT_DIR}/discord_kali_bot.py" ]]; then
      cp "${SCRIPT_DIR}/discord_kali_bot.py" "${INSTALL_DIR}/discord_kali_bot.py" \
        && info "discord_kali_bot.py copied from installer directory" \
        || { err "Could not copy discord_kali_bot.py to ${INSTALL_DIR}"; return 1; }
    else
      # Fallback: download from the lab repo
      warn "discord_kali_bot.py not found in installer directory — downloading from lab repo..."
      curl -fsSL \
        "https://raw.githubusercontent.com/spac3gh0st00/Kali-MCP-Bounty-Lab/main/discord_kali_bot.py" \
        -o "${INSTALL_DIR}/discord_kali_bot.py" \
        || { err "Could not download discord_kali_bot.py — add it to the installer folder or check your internet connection"; return 1; }
      info "discord_kali_bot.py downloaded from lab repo"
    fi
    chmod +x "${INSTALL_DIR}/discord_kali_bot.py"
  else
    info "discord_kali_bot.py already present"
  fi

  # ── Systemd service ──────────────────────────────────────────────────────
  local svc_file="/tmp/discord-kali-bot.service"
  cat > "$svc_file" <<SERVICE
[Unit]
Description=Discord Kali MCP Bot
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=${USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/discord_kali_bot.py
Restart=on-failure
RestartSec=10
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
SERVICE

  sudo cp "$svc_file" /etc/systemd/system/discord-kali-bot.service 2>&1 \
    || { err "Could not copy service file (need sudo)"; return 1; }
  sudo systemctl daemon-reload 2>&1 || warn "systemctl daemon-reload failed"
  sudo systemctl enable discord-kali-bot 2>&1 || warn "Could not enable service"
  sudo systemctl restart discord-kali-bot 2>&1 || warn "Could not start service"

  sleep 2
  sudo systemctl status discord-kali-bot --no-pager -l 2>&1 || true
  info "Discord bot service installed"
}

# =============================================================================
# PHASE: health
# =============================================================================
phase_health() {
  if [[ "$HEALTH" == "false" ]]; then
    info "Health Monitor: skipped"
    return 0
  fi

  section "Health Monitor setup"

  # Ensure venv exists (created by discord phase or standalone)
  if [[ ! -d "${INSTALL_DIR}/venv" ]]; then
    info "Creating Python venv for health monitor..."
    local pyver
    pyver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "")
    if [[ -n "$pyver" ]]; then
      apt_install "python${pyver}-venv" 2>/dev/null || apt_install python3-venv
    else
      apt_install python3-venv
    fi
    python3 -m venv "${INSTALL_DIR}/venv" 2>&1 \
      || { err "Could not create venv"; return 1; }
  fi

  "${INSTALL_DIR}/venv/bin/pip" install -q requests python-dotenv 2>&1 || true

  # Write health_monitor.py — uses INSTALL_DIR for .env path, not hardcoded
  info "Writing health_monitor.py..."
  cat > "${INSTALL_DIR}/health_monitor.py" <<PYEOF
#!/usr/bin/env python3
import os
import time
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the same directory as this script
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

WEBHOOK_URL   = os.getenv("DISCORD_WEBHOOK_URL", "")
HEALTH_URL    = os.getenv("HEALTH_URL", "http://localhost:${MCP_PORT}/health")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))

def send_discord(status):
    if not WEBHOOK_URL:
        print("[Monitor] DISCORD_WEBHOOK_URL not set in .env — skipping Discord alert")
        return
    colors = {"UP": 0x00FF00, "DOWN": 0xFF0000, "DEGRADED": 0xFFA500}
    payload = {
        "embeds": [{
            "title": f"KaliBot MCP — {status}",
            "description": f"Status changed at {datetime.now().strftime('%H:%M:%S')}",
            "color": colors.get(status, 0x888888),
        }]
    }
    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=5)
        if r.status_code in (200, 204):
            print(f"[Monitor] Discord alert sent: {status}")
        else:
            print(f"[Monitor] Discord webhook returned {r.status_code}")
    except Exception as exc:
        print(f"[Monitor] Discord error: {exc}")

def check_health():
    try:
        r = requests.get(HEALTH_URL, timeout=3)
        return "up" if r.status_code == 200 else "degraded"
    except requests.exceptions.ConnectionError:
        return "down"
    except requests.exceptions.Timeout:
        return "degraded"
    except Exception:
        return "degraded"

def run():
    last_status = None
    print(f"[Monitor] Watching {HEALTH_URL} every {POLL_INTERVAL}s")
    print(f"[Monitor] Discord webhook: {'configured' if WEBHOOK_URL else 'NOT configured'}")
    while True:
        current = check_health()
        if current != last_status:
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[Monitor] {ts} — status changed: {last_status} → {current.upper()}")
            send_discord(current.upper())
            last_status = current
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run()
PYEOF
  chmod +x "${INSTALL_DIR}/health_monitor.py"
  info "health_monitor.py written"

  # Ensure .env exists (at minimum an empty file so the service starts)
  if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
    touch "${INSTALL_DIR}/.env"
    chmod 600 "${INSTALL_DIR}/.env"
    warn ".env not found — created empty file. Fill in DISCORD_WEBHOOK_URL for alerts."
  fi

  # Systemd service
  local svc_file="/tmp/kalibot-monitor.service"
  cat > "$svc_file" <<SERVICE
[Unit]
Description=KaliBot Health Monitor
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=${USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/health_monitor.py
Restart=always
RestartSec=10
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
SERVICE

  sudo cp "$svc_file" /etc/systemd/system/kalibot-monitor.service 2>&1 \
    || { err "Could not copy service file"; return 1; }
  sudo systemctl daemon-reload 2>&1 || warn "daemon-reload failed"
  sudo systemctl enable kalibot-monitor 2>&1 || warn "Could not enable service"
  sudo systemctl restart kalibot-monitor 2>&1 || warn "Could not start service"

  sleep 2
  sudo systemctl status kalibot-monitor --no-pager -l 2>&1 || true
  info "Health monitor service installed"
}

# =============================================================================
# PHASE: tailscale
# =============================================================================
phase_tailscale() {
  if [[ "$TAILSCALE_INSTALL" == "false" ]]; then
    info "Tailscale: skipped"
    return 0
  fi

  section "Tailscale setup"

  if command -v tailscale &>/dev/null; then
    info "Tailscale already installed: $(tailscale version 2>&1 | head -1)"
  else
    info "Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh 2>&1 \
      || { err "Tailscale install script failed — check your internet connection"; return 1; }

    if command -v tailscale &>/dev/null; then
      info "Tailscale installed: $(tailscale version 2>&1 | head -1)"
    else
      err "Tailscale binary not found after install"
      return 1
    fi
  fi

  # Enable + start daemon
  sudo systemctl enable tailscaled --now 2>&1 || \
    sudo service tailscaled start 2>&1 || \
    warn "Could not start tailscaled via systemctl or service"

  # SSH server
  info "Installing OpenSSH server (for phone access via Termius)..."
  apt_install openssh-server
  sudo systemctl enable ssh --now 2>&1 || sudo service ssh start 2>&1 || \
    warn "Could not start SSH"
  info "SSH: $(sudo systemctl is-active ssh 2>/dev/null || echo 'unknown')"

  # Bring Tailscale up — this shows a URL if not authenticated
  info "Running 'tailscale up' — if not yet authenticated, visit the URL shown below..."
  sudo tailscale up 2>&1 || warn "'tailscale up' returned non-zero (this is normal if already connected)"

  info "Your Tailscale IPs:"
  tailscale ip 2>/dev/null || warn "Run 'tailscale ip' after authentication to get your IP"
}

# =============================================================================
# PHASE: firewall
# =============================================================================
phase_firewall() {
  section "UFW firewall configuration"

  # Install ufw if missing
  if ! command -v ufw &>/dev/null; then
    info "Installing ufw..."
    apt_install ufw
  fi

  # Enable
  info "Enabling UFW..."
  echo "y" | sudo ufw enable 2>&1 || sudo ufw --force enable 2>&1 \
    || warn "ufw enable failed — check output"

  # Default policies
  sudo ufw default deny incoming 2>&1  && info "Default: deny incoming"
  sudo ufw default allow outgoing 2>&1 && info "Default: allow outgoing"

  # SSH — must come before any deny rules
  sudo ufw allow "${SSH_PORT}/tcp" comment "SSH" 2>&1 \
    && info "Allowed SSH on port $SSH_PORT" \
    || warn "Could not add SSH rule"

  # MCP port
  if [[ -n "$HOST_IP" ]]; then
    sudo ufw allow from "$HOST_IP" to any port "$MCP_PORT" comment "Kali MCP" 2>&1 \
      && info "Allowed port $MCP_PORT from $HOST_IP" \
      || warn "Could not add MCP rule from host IP"
  else
    warn "--host-ip not provided."
    info "Allowing MCP port $MCP_PORT from subnet $VM_SUBNET as fallback..."
    sudo ufw allow from "$VM_SUBNET" to any port "$MCP_PORT" comment "Kali MCP subnet" 2>&1 \
      && info "Allowed port $MCP_PORT from $VM_SUBNET" \
      || warn "Could not add subnet MCP rule"
    warn "For tighter security, re-run with --host-ip set to your Windows machine's IP."
  fi

  info "Current UFW status:"
  sudo ufw status verbose 2>&1
}

# =============================================================================
# Dispatch
# =============================================================================
case "$PHASE" in
  prereqs)         phase_prereqs         ;;
  prereqs-install) phase_prereqs_install ;;
  docker)          phase_docker          ;;
  kali)      phase_kali      ;;
  mcp)       phase_mcp       ;;
  discord)   phase_discord   ;;
  health)    phase_health    ;;
  tailscale) phase_tailscale ;;
  firewall)  phase_firewall  ;;
  *)
    err "Unknown phase: $PHASE"
    err "Valid phases: prereqs docker kali mcp discord health tailscale firewall"
    exit 1
    ;;
esac
