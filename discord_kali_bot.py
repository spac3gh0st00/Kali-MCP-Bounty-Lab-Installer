#!/usr/bin/env python3
"""
discord_kali_bot.py — Secure Discord → Kali MCP bridge
-------------------------------------------------------
Architecture:
  Discord (slash commands, private server)
    → Tailscale-connected device
      → This bot on Ubuntu VM
        → MCP HTTP API on localhost:8000
          → Kali Docker container (defined tools only)

Install deps:  pip install discord.py httpx python-dotenv
Configure:     copy .env.example → .env and fill in values
Run:           python3 discord_kali_bot.py
"""

import os
import json
import asyncio
import logging
from datetime import datetime

import discord
from discord import app_commands
import httpx
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────

DISCORD_TOKEN   = os.getenv("DISCORD_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0"))
MCP_BASE        = "http://localhost:8000"
LOG_FILE        = os.path.expanduser("~/kali-mcp/bot_audit.log")

# These tools are blocked from Discord — raw shell, payloads, brute force
# are too risky to expose even to yourself remotely
BLOCKED_TOOLS = {
    "run",              # arbitrary shell — never expose this
    "payload_generate", # msfvenom payloads
    "reverse_shell",    # shell one-liners
    "hydra_attack",     # brute force (use Claude Desktop for this locally)
}

# ── Audit Logging ─────────────────────────────────────────────────────────────

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

def audit(user_id: int, username: str, tool: str, args: dict, result_len: int):
    logging.info(
        f"user={username}({user_id}) "
        f"tool={tool} "
        f"args={json.dumps(args)} "
        f"result_chars={result_len}"
    )

def audit_denied(user_id: int, username: str, reason: str):
    logging.warning(f"DENIED user={username}({user_id}) reason={reason}")

# ── MCP Streamable HTTP Client ─────────────────────────────────────────────────

async def call_mcp_tool(tool_name: str, arguments: dict, timeout: int = 90) -> str:
    """
    Talks to the Kali MCP server via the Streamable HTTP protocol.

    Flow:
      1. POST /mcp  → initialize  (get mcp-session-id from response header)
      2. POST /mcp  → notifications/initialized
      3. POST /mcp  → tools/call  (read SSE stream or JSON from response body)
    """
    if tool_name in BLOCKED_TOOLS:
        return f"❌ Tool `{tool_name}` is blocked from Discord. Use Claude Desktop locally."

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:

            # 1. Initialize
            init_resp = await client.post(f"{MCP_BASE}/mcp", headers=headers, json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "discord-kali-bot", "version": "1.0"}
                }
            })

            session_id = init_resp.headers.get("mcp-session-id")
            if not session_id:
                return "❌ MCP server did not return a session ID."

            headers["mcp-session-id"] = session_id

            # 2. Initialized notification
            await client.post(f"{MCP_BASE}/mcp", headers=headers, json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {}
            })

            # 3. Tool call — response may be SSE stream or plain JSON
            async with client.stream("POST", f"{MCP_BASE}/mcp", headers=headers, json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }) as tool_resp:
                raw_body = await tool_resp.aread()
                body_text = raw_body.decode("utf-8", errors="replace")

                # Strip SSE framing if present
                data = None
                for line in body_text.splitlines():
                    line = line.strip()
                    if line.startswith("data:"):
                        payload = line[len("data:"):].strip()
                        try:
                            data = json.loads(payload)
                            break
                        except json.JSONDecodeError:
                            continue

                # Fallback: try parsing entire body as JSON
                if data is None:
                    try:
                        data = json.loads(body_text)
                    except json.JSONDecodeError:
                        return f"❌ Unparseable response: {body_text[:200]}"

        if "result" in data:
            content = data["result"].get("content", [])
            text = "\n".join(
                c.get("text", "")
                for c in content
                if c.get("type") == "text"
            )
            return text or "✅ Tool completed with no text output."
        elif "error" in data:
            err = data["error"]
            return f"❌ MCP Error [{err.get('code', '?')}]: {err.get('message', 'Unknown error')}"
        else:
            return f"❌ Unexpected response: {data}"

    except httpx.TimeoutException:
        return f"⏱️ Command timed out after {timeout}s. Try a lighter scan type."
    except httpx.ConnectError:
        return "❌ Cannot reach MCP server at localhost:8000. Is the container running?"
    except Exception as exc:
        return f"❌ Bot error: {exc}"

# ── Discord Bot Setup ──────────────────────────────────────────────────────────

intents = discord.Intents.default()
client  = discord.Client(intents=intents)
tree    = app_commands.CommandTree(client)

# ── Auth + Common Runner ───────────────────────────────────────────────────────

def is_authorized(interaction: discord.Interaction) -> bool:
    return interaction.user.id == ALLOWED_USER_ID

async def run_tool(
    interaction: discord.Interaction,
    tool: str,
    args: dict,
    timeout: int = 90
):
    """Auth check → defer → call MCP → split output → respond → audit log."""
    if not is_authorized(interaction):
        audit_denied(interaction.user.id, str(interaction.user), f"tried /{tool}")
        await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    output = await call_mcp_tool(tool, args, timeout=timeout)
    audit(interaction.user.id, str(interaction.user), tool, args, len(output))

    # Split into 1900-char chunks to stay under Discord's 2000-char limit
    chunks = [output[i:i+1900] for i in range(0, max(len(output), 1), 1900)]
    total  = len(chunks)

    for i, chunk in enumerate(chunks):
        header = (
            f"**`/{tool}`** • {datetime.now().strftime('%H:%M:%S')}"
            + (f" • part {i+1}/{total}" if total > 1 else "")
            + "\n"
        )
        msg = f"{header}```\n{chunk}\n```"
        if i == 0:
            await interaction.followup.send(msg)
        else:
            await interaction.followup.send(msg)

# ── Slash Commands ─────────────────────────────────────────────────────────────
# Only bug-bounty-relevant tools are exposed.
# Dangerous tools (run, payload_generate, hydra_attack, reverse_shell)
# are intentionally omitted — use Claude Desktop locally for those.

# ── Recon ──────────────────────────────────────────────────────────────────────

@tree.command(name="port_scan", description="Nmap port scan with presets")
@app_commands.describe(
    target="IP address, hostname, or CIDR range",
    scan_type="quick | full | stealth | udp | service | aggressive"
)
async def cmd_port_scan(interaction, target: str, scan_type: str = "quick"):
    await run_tool(interaction, "port_scan", {"target": target, "scan_type": scan_type}, timeout=120)

@tree.command(name="dns_enum", description="DNS enumeration with zone transfer attempts")
@app_commands.describe(domain="Target domain e.g. example.com")
async def cmd_dns_enum(interaction, domain: str):
    await run_tool(interaction, "dns_enum", {"domain": domain})

@tree.command(name="subdomain_enum", description="Subdomain enumeration (subfinder + amass + waybackurls)")
@app_commands.describe(domain="Target domain e.g. example.com")
async def cmd_subdomain_enum(interaction, domain: str):
    await run_tool(interaction, "subdomain_enum", {"domain": domain}, timeout=120)

@tree.command(name="network_discovery", description="Multi-stage network recon")
@app_commands.describe(
    target="CIDR range or IP e.g. 192.168.1.0/24",
    discovery_type="quick | comprehensive | stealth"
)
async def cmd_network_discovery(interaction, target: str, discovery_type: str = "quick"):
    await run_tool(interaction, "network_discovery", {"target": target, "discovery_type": discovery_type}, timeout=120)

@tree.command(name="recon_auto", description="Automated multi-stage recon pipeline")
@app_commands.describe(
    target="Target IP or domain",
    depth="quick | standard | deep"
)
async def cmd_recon_auto(interaction, target: str, depth: str = "quick"):
    await run_tool(interaction, "recon_auto", {"target": target, "depth": depth}, timeout=180)

# ── Web App Testing ────────────────────────────────────────────────────────────

@tree.command(name="web_enum", description="Web application discovery and enumeration")
@app_commands.describe(
    target="Target URL e.g. https://example.com",
    enumeration_type="basic | full | aggressive"
)
async def cmd_web_enum(interaction, target: str, enumeration_type: str = "full"):
    await run_tool(interaction, "web_enumeration", {"target": target, "enumeration_type": enumeration_type}, timeout=120)

@tree.command(name="web_audit", description="Comprehensive web application security audit")
@app_commands.describe(target="Target URL e.g. https://example.com")
async def cmd_web_audit(interaction, target: str):
    await run_tool(interaction, "web_audit", {"target": target}, timeout=120)

@tree.command(name="header_analysis", description="HTTP security header analysis")
@app_commands.describe(target="Target URL")
async def cmd_header_analysis(interaction, target: str):
    await run_tool(interaction, "header_analysis", {"target": target})

@tree.command(name="ssl_analysis", description="SSL/TLS security assessment")
@app_commands.describe(target="Target domain or IP")
async def cmd_ssl_analysis(interaction, target: str):
    await run_tool(interaction, "ssl_analysis", {"target": target})

@tree.command(name="spider", description="Web crawling and spidering")
@app_commands.describe(target="Target URL")
async def cmd_spider(interaction, target: str):
    await run_tool(interaction, "spider_website", {"target": target}, timeout=120)

@tree.command(name="form_analysis", description="Discover and analyze web forms")
@app_commands.describe(target="Target URL")
async def cmd_form_analysis(interaction, target: str):
    await run_tool(interaction, "form_analysis", {"target": target})

# ── Vulnerability Scanning ─────────────────────────────────────────────────────

@tree.command(name="vuln_scan", description="Automated vulnerability assessment")
@app_commands.describe(
    target="Target IP or URL",
    scan_type="quick | comprehensive | web | network"
)
async def cmd_vuln_scan(interaction, target: str, scan_type: str = "quick"):
    await run_tool(interaction, "vulnerability_scan", {"target": target, "scan_type": scan_type}, timeout=180)

@tree.command(name="exploit_search", description="Search for known exploits via searchsploit")
@app_commands.describe(query="Search term e.g. 'Apache 2.4.49' or 'OpenSSH 7.4'")
async def cmd_exploit_search(interaction, query: str):
    await run_tool(interaction, "exploit_search", {"query": query})

@tree.command(name="enum_shares", description="SMB/NFS share enumeration")
@app_commands.describe(
    target="Target IP",
    enum_type="smb | nfs | all"
)
async def cmd_enum_shares(interaction, target: str, enum_type: str = "smb"):
    await run_tool(interaction, "enum_shares", {"target": target, "enum_type": enum_type})

# ── Utilities ──────────────────────────────────────────────────────────────────

@tree.command(name="hash_identify", description="Identify a hash type (MD5, SHA, bcrypt, NTLM...)")
@app_commands.describe(hash_value="The hash string to identify")
async def cmd_hash_identify(interaction, hash_value: str):
    await run_tool(interaction, "hash_identify", {"hash_value": hash_value})

@tree.command(name="encode", description="Encode or decode data (base64, URL, hex, HTML, rot13)")
@app_commands.describe(
    data="Input string",
    operation="encode or decode",
    format="base64 | url | hex | html | rot13"
)
async def cmd_encode(interaction, data: str, operation: str, format: str = "base64"):
    await run_tool(interaction, "encode_decode", {
        "data": data, "operation": operation, "format": format
    })

@tree.command(name="fetch_url", description="Fetch and analyze web content from a URL")
@app_commands.describe(url="Target URL to fetch")
async def cmd_fetch(interaction, url: str):
    await run_tool(interaction, "fetch", {"url": url})

# ── Session Management ─────────────────────────────────────────────────────────

@tree.command(name="session_create", description="Create a new pentest session")
@app_commands.describe(name="Session name e.g. 'bugbounty-target-com-2026'")
async def cmd_session_create(interaction, name: str):
    await run_tool(interaction, "session_create", {"name": name})

@tree.command(name="session_status", description="Show current active session status")
async def cmd_session_status(interaction):
    await run_tool(interaction, "session_status", {})

@tree.command(name="session_list", description="List all pentest sessions")
async def cmd_session_list(interaction):
    await run_tool(interaction, "session_list", {})

@tree.command(name="session_history", description="Show command history for current session")
async def cmd_session_history(interaction):
    await run_tool(interaction, "session_history", {})

# ── Reporting ──────────────────────────────────────────────────────────────────

@tree.command(name="create_report", description="Generate a structured pentest report")
@app_commands.describe(
    title="Report title",
    format="markdown | text | json"
)
async def cmd_report(interaction, title: str, format: str = "markdown"):
    await run_tool(interaction, "create_report", {"title": title, "format": format})

# ── AI Investigate Command ─────────────────────────────────────────────────────

from investigate import setup_investigate
setup_investigate(tree, run_tool, call_mcp_tool, is_authorized, audit, audit_denied)

# ── Bot Lifecycle ──────────────────────────────────────────────────────────────

@client.event
async def on_ready():
    guild = discord.Object(id=int(os.getenv("DISCORD_GUILD_ID")))
    tree.copy_global_to(guild=guild)
    await tree.sync(guild=guild)
    print(f"[+] Bot online as {client.user}")
    print(f"[+] Authorized user ID: {ALLOWED_USER_ID}")
    print(f"[+] Audit log: {LOG_FILE}")
    print(f"[+] Synced commands to guild {guild.id}")
    logging.info(f"Bot started | authorized_user_id={ALLOWED_USER_ID}")

client.run(DISCORD_TOKEN)
