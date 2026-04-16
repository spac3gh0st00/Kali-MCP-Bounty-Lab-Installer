#!/usr/bin/env python3
"""
investigate.py — AI-powered autonomous recon agent
---------------------------------------------------
Drop this file in ~/kali-mcp/ alongside discord_kali_bot.py
Then add this to the bottom of discord_kali_bot.py (before client.run):

    from investigate import setup_investigate
    setup_investigate(tree, run_tool, call_mcp_tool, is_authorized, audit, audit_denied)

Usage in Discord:
    /investigate target:example.com
    /investigate target:192.168.1.1 depth:thorough
"""

import os
import json
import asyncio
import logging
from datetime import datetime

import anthropic
import discord
from discord import app_commands

# ── Config ────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MAX_TOOL_CALLS    = 8   # cap per investigation to control cost
MODEL             = "claude-sonnet-4-20250514"

# Tools the AI agent is allowed to chain together
# Excludes dangerous tools (run, payload_generate, reverse_shell, hydra_attack)
AGENT_TOOLS = [
    "port_scan",
    "dns_enum",
    "subdomain_enum",
    "network_discovery",
    "recon_auto",
    "web_enumeration",
    "web_audit",
    "header_analysis",
    "ssl_analysis",
    "spider_website",
    "form_analysis",
    "vulnerability_scan",
    "exploit_search",
    "enum_shares",
    "hash_identify",
    "encode_decode",
    "fetch",
]

# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are an expert bug bounty recon agent operating a Kali Linux security toolkit.

Your job is to investigate a target systematically, chain the right tools together, and produce a clear actionable summary for a bug bounty hunter.

## Available Tools
{', '.join(AGENT_TOOLS)}

## Tool Reference
- port_scan(target, scan_type): scan_type = quick | full | stealth | service | aggressive
- dns_enum(domain, record_types): record_types = all | a,mx,ns,txt etc
- subdomain_enum(url): finds subdomains
- network_discovery(target, discovery_type): discovery_type = quick | comprehensive | stealth
- recon_auto(target, depth): depth = quick | standard | deep
- web_enumeration(target, enumeration_type): enumeration_type = basic | full | aggressive
- web_audit(url, audit_type): audit_type = comprehensive | quick
- header_analysis(url): checks HTTP security headers
- ssl_analysis(url): checks SSL/TLS config
- spider_website(url, depth): crawls website links
- form_analysis(url): finds and analyzes web forms
- vulnerability_scan(target, scan_type): scan_type = quick | comprehensive | web | network
- exploit_search(search_term): searches for known exploits
- enum_shares(target, enum_type): enum_type = smb | nfs | all
- fetch(url): fetches and analyzes web page content

## Your Workflow
1. Start broad — DNS, subdomains, port scan
2. Drill into what you find — if you see port 80/443, check web headers, audit the app
3. Follow leads — if you find an old service version, search for exploits
4. Stop when you have enough to write a solid report OR after {MAX_TOOL_CALLS} tool calls
5. Always write a final report

## Response Format
You MUST always respond with valid JSON only. No markdown, no explanation outside the JSON.

To run a tool:
{{
  "action": "run_tool",
  "tool": "tool_name",
  "arguments": {{"arg1": "value1"}},
  "reasoning": "one sentence why you're running this"
}}

To finish and write the report:
{{
  "action": "final_report",
  "report": "your full report here"
}}

## Report Format
Structure your final report like this:

# Recon Summary: [target]
## Overview
Brief summary of what was found.

## Key Findings
List the most important discoveries — open ports, services, subdomains, vulnerabilities, misconfigs.

## Potential Attack Vectors
What a bug bounty hunter should investigate further and why.

## Recommended Next Steps
Specific follow-up actions with tool suggestions.

## Risk Assessment
Overall risk level: Low / Medium / High / Critical with brief justification.
"""

# ── Agent Loop ────────────────────────────────────────────────────────────────

async def run_investigation(target: str, depth: str, call_mcp_tool_fn) -> tuple[str, list]:
    """
    Autonomous recon agent loop.
    Returns (final_report, tool_call_log)
    """
    client       = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    tool_log     = []
    call_count   = 0
    messages     = []

    # Initial user message
    messages.append({
        "role": "user",
        "content": (
            f"Investigate this target for bug bounty recon: {target}\n"
            f"Depth preference: {depth}\n"
            f"You have up to {MAX_TOOL_CALLS} tool calls. Make them count."
        )
    })

    while call_count < MAX_TOOL_CALLS:
        # Ask Claude what to do next
        response = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=messages
        )

        raw = response.content[0].text.strip()

        # Parse Claude's decision
        try:
            # Strip markdown code fences if Claude adds them
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            decision = json.loads(raw.strip())
        except json.JSONDecodeError:
            logging.error(f"Agent JSON parse error: {raw}")
            break

        # Add Claude's response to history
        messages.append({"role": "assistant", "content": response.content[0].text})

        # Final report — we're done
        if decision.get("action") == "final_report":
            return decision.get("report", "No report generated."), tool_log

        # Run tool
        if decision.get("action") == "run_tool":
            tool_name  = decision.get("tool", "")
            arguments  = decision.get("arguments", {})
            reasoning  = decision.get("reasoning", "")

            # Safety check — only allow whitelisted tools
            if tool_name not in AGENT_TOOLS:
                messages.append({
                    "role": "user",
                    "content": f"Tool '{tool_name}' is not available. Choose from: {', '.join(AGENT_TOOLS)}"
                })
                continue

            call_count += 1
            tool_log.append({
                "step": call_count,
                "tool": tool_name,
                "arguments": arguments,
                "reasoning": reasoning
            })

            logging.info(f"Agent running tool {call_count}/{MAX_TOOL_CALLS}: {tool_name} {arguments}")

            # Run the tool via MCP
            result = await call_mcp_tool_fn(tool_name, arguments, timeout=120)

            # Truncate very long results to keep token usage reasonable
            if len(result) > 3000:
                result = result[:3000] + "\n...(output truncated for context)"

            # Feed result back to Claude
            messages.append({
                "role": "user",
                "content": (
                    f"Tool result for {tool_name}:\n\n{result}\n\n"
                    f"Tool calls used: {call_count}/{MAX_TOOL_CALLS}. "
                    + ("Write your final report now." if call_count >= MAX_TOOL_CALLS else "What's next?")
                )
            })

    # If we hit the limit without a final report, ask for one explicitly
    messages.append({
        "role": "user",
        "content": "You've reached the tool call limit. Write your final_report now based on everything gathered."
    })

    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=messages
    )

    raw = response.content[0].text.strip()
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        decision = json.loads(raw.strip())
        return decision.get("report", raw), tool_log
    except json.JSONDecodeError:
        return raw, tool_log

# ── Discord Command Setup ─────────────────────────────────────────────────────

def setup_investigate(tree, run_tool_fn, call_mcp_tool_fn, is_authorized_fn, audit_fn, audit_denied_fn):
    """
    Call this from discord_kali_bot.py to register the /investigate command.
    """

    @tree.command(
        name="investigate",
        description="AI-powered autonomous recon — chains tools together and writes a full summary"
    )
    @app_commands.describe(
        target="Target domain, IP, or URL e.g. example.com or 192.168.1.1",
        depth="quick (3-4 tools) | standard (5-6 tools) | thorough (up to 8 tools)"
    )
    async def cmd_investigate(
        interaction: discord.Interaction,
        target: str,
        depth: str = "standard"
    ):
        if not is_authorized_fn(interaction):
            audit_denied_fn(
                interaction.user.id,
                str(interaction.user),
                f"tried /investigate on {target}"
            )
            await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        start_time = datetime.now()

        # Let the user know it's running
        await interaction.followup.send(
            f"🤖 **AI Recon Agent started**\n"
            f"**Target:** `{target}`\n"
            f"**Depth:** `{depth}`\n"
            f"**Max tool calls:** `{MAX_TOOL_CALLS}`\n"
            f"_Running autonomously — this may take 2–5 minutes..._"
        )

        try:
            report, tool_log = await run_investigation(target, depth, call_mcp_tool_fn)
        except Exception as e:
            logging.error(f"Investigation error: {e}")
            await interaction.followup.send(f"❌ Investigation failed: {e}")
            return

        elapsed = (datetime.now() - start_time).seconds

        # Post the tool call log first
        if tool_log:
            log_lines = "\n".join(
                f"  {t['step']}. `{t['tool']}` — {t['reasoning']}"
                for t in tool_log
            )
            await interaction.followup.send(
                f"**🔧 Tools used ({len(tool_log)}/{MAX_TOOL_CALLS}):**\n{log_lines}"
            )

        # Post the report — split into chunks if needed
        chunks = [report[i:i+1900] for i in range(0, max(len(report), 1), 1900)]
        total  = len(chunks)

        for i, chunk in enumerate(chunks):
            header = (
                f"**📋 Recon Report — `{target}`**"
                + (f" (part {i+1}/{total})" if total > 1 else "")
                + f" _{elapsed}s_\n"
            )
            await interaction.followup.send(f"{header}```markdown\n{chunk}\n```")

        # Audit log
        audit_fn(
            interaction.user.id,
            str(interaction.user),
            "investigate",
            {"target": target, "depth": depth, "tools_used": len(tool_log)},
            len(report)
        )
