"""
Kali MCP Bounty Lab — GUI Installer Wizard
Calls install_linux.sh or install_windows.ps1 with --phase arguments.

Requirements: pip install customtkinter
              sudo apt install python3-tk   (Linux)
Run:          python kali_lab_installer.py
"""

# ── Dependency check BEFORE importing customtkinter ──────────────────────────
import sys
import subprocess
import platform

def _check_deps():
    """
    Verify tkinter and customtkinter are available.
    Print clear instructions and exit if they're not.
    Returns True if all good.
    """
    missing = []

    # tkinter is part of the stdlib but needs a system package on Linux
    try:
        import tkinter  # noqa: F401
    except ImportError:
        missing.append("tkinter")

    # customtkinter is a pip package
    try:
        import customtkinter  # noqa: F401
    except ImportError:
        missing.append("customtkinter")

    if not missing:
        return True

    print("\n" + "="*60)
    print("  Kali MCP Bounty Lab — Missing Dependencies")
    print("="*60)

    if "tkinter" in missing:
        if platform.system() == "Linux":
            print("\n  python3-tk is not installed.")
            print("  Fix:  sudo apt-get install python3-tk\n")
        else:
            print("\n  tkinter is missing. Reinstall Python from python.org")
            print("  and make sure 'tcl/tk and IDLE' is checked.\n")

    if "customtkinter" in missing:
        print("  customtkinter is not installed.")
        print("  Fix:  pip install customtkinter\n")

    print("  After fixing the above, re-run:")
    print("    python kali_lab_installer.py\n")
    print("="*60 + "\n")
    sys.exit(1)

_check_deps()

# ── Safe to import now ────────────────────────────────────────────────────────
import customtkinter as ctk
import threading
import os
from pathlib import Path

# ──────────────────────────────────────────────
# Theme
# ──────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

ACCENT     = "#00ff88"
ACCENT_DIM = "#00cc6a"
BG_BASE    = "#0b0b0b"
BG_PANEL   = "#141414"
BG_CARD    = "#1c1c1c"
BG_FIELD   = "#111111"
BORDER     = "#2a2a2a"
TXT_BRIGHT = "#f0f0f0"
TXT_MID    = "#888888"
TXT_DIM    = "#444444"
CLR_OK     = "#00ff88"
CLR_WARN   = "#ffaa00"
CLR_ERR    = "#ff4455"
TERM_FG    = "#c8ffc8"

CURRENT_OS = platform.system()   # "Linux" or "Windows"

# ──────────────────────────────────────────────
# Script paths (sit next to this file)
# ──────────────────────────────────────────────
SCRIPT_DIR     = Path(__file__).parent.resolve()
LINUX_SCRIPT   = SCRIPT_DIR / "install_linux.sh"
WINDOWS_SCRIPT = SCRIPT_DIR / "install_windows.ps1"

# ──────────────────────────────────────────────
# Wizard step definitions
# ──────────────────────────────────────────────
LINUX_STEPS = [
    ("Welcome",        "welcome"),
    ("Prerequisites",  "prereqs"),
    ("Docker",         "docker"),
    ("Kali Container", "kali"),
    ("MCP Server",     "mcp"),
    ("Discord Bot",    "discord"),
    ("Health Monitor", "health"),
    ("Tailscale",      "tailscale"),
    ("Firewall",       "firewall"),
    ("Done",           "summary"),
]

WINDOWS_STEPS = [
    ("Welcome",        "welcome"),
    ("Prerequisites",  "prereqs"),
    ("Claude Desktop", "claude"),
    ("Port Proxy",     "portproxy"),
    ("Done",           "summary"),
]


# ──────────────────────────────────────────────
# Widget helpers
# ──────────────────────────────────────────────
def lbl(parent, text, size=12, weight="normal", color=TXT_BRIGHT, **kw):
    return ctk.CTkLabel(parent, text=text,
                        font=ctk.CTkFont(size=size, weight=weight),
                        text_color=color, **kw)


def mk_entry(parent, placeholder="", width=280, show="", textvariable=None):
    e = ctk.CTkEntry(parent, placeholder_text=placeholder, width=width,
                     fg_color=BG_FIELD, border_color=BORDER,
                     text_color=TXT_BRIGHT, placeholder_text_color=TXT_DIM,
                     show=show)
    if textvariable is not None:
        e.configure(textvariable=textvariable)
    return e


def card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8, **kw)


def divider(parent):
    ctk.CTkFrame(parent, height=1, fg_color=BORDER).pack(fill="x")


def terminal(parent, height=200):
    t = ctk.CTkTextbox(parent, height=height,
                       fg_color="#050505", text_color=TERM_FG,
                       font=ctk.CTkFont(family="Courier New", size=11),
                       corner_radius=6, border_width=1, border_color=BORDER,
                       wrap="none")
    t.pack(fill="x", pady=(8, 0))
    t.configure(state="disabled")
    return t


def twrite(t, text):
    """Thread-safe terminal write — silently ignores destroyed-widget errors."""
    try:
        t.configure(state="normal")
        t.insert("end", text)
        t.see("end")
        t.configure(state="disabled")
    except Exception:
        pass  # widget was destroyed (user navigated away while script ran)


# ──────────────────────────────────────────────
# Script runner
# ──────────────────────────────────────────────
def run_script(app, term, phase, extra_args=None, run_btn=None):
    """
    Builds the command, disables run_btn while running, streams output.
    Linux:   bash install_linux.sh  --phase <phase> [extra_args]
    Windows: powershell -ExecutionPolicy Bypass -File install_windows.ps1 -Phase <phase> [extra_args]
    """
    extra = extra_args or []

    if CURRENT_OS == "Linux":
        if not LINUX_SCRIPT.exists():
            twrite(term, f"\n✗  install_linux.sh not found:\n   {SCRIPT_DIR}\n")
            twrite(term, "   All three files must be in the same folder.\n")
            return
        cmd = ["bash", str(LINUX_SCRIPT), "--phase", phase] + extra

    else:  # Windows
        if not WINDOWS_SCRIPT.exists():
            twrite(term, f"\n✗  install_windows.ps1 not found:\n   {SCRIPT_DIR}\n")
            twrite(term, "   All three files must be in the same folder.\n")
            return
        cmd = [
            "powershell", "-ExecutionPolicy", "Bypass",
            "-File", str(WINDOWS_SCRIPT),
            "-Phase", phase,
        ] + extra

    def worker():
        if run_btn:
            try:
                app.after(0, lambda: run_btn.configure(state="disabled",
                                                        text="⏳ Running..."))
            except Exception:
                pass

        twrite(term, f"\n$ {' '.join(cmd)}\n{'─'*60}\n")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in proc.stdout:
                twrite(term, line)
            proc.wait()
            sep = "─" * 60
            if proc.returncode == 0:
                twrite(term, f"\n{sep}\n✓  Phase '{phase}' complete.\n")
            else:
                twrite(term, f"\n{sep}\n⚠  Exited with code {proc.returncode}. "
                             f"Check output above.\n")
        except FileNotFoundError as exc:
            twrite(term, f"\n✗  Could not launch: {exc}\n")
            if CURRENT_OS == "Linux":
                twrite(term, "   Is 'bash' installed?\n")
            else:
                twrite(term, "   Is PowerShell installed and in PATH?\n")
        except Exception as exc:
            twrite(term, f"\n✗  Unexpected error: {exc}\n")
        finally:
            if run_btn:
                try:
                    def _restore():
                        try:
                            run_btn.configure(state="normal", text=run_btn._original_text)
                        except Exception:
                            pass
                    app.after(0, _restore)
                except Exception:
                    pass

    threading.Thread(target=worker, daemon=True).start()


# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────
class KaliLabInstaller(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Kali MCP Bounty Lab  ─  Installer")
        self.geometry("1040x700")
        self.resizable(False, False)
        self.configure(fg_color=BG_BASE)

        self.steps = LINUX_STEPS if CURRENT_OS == "Linux" else WINDOWS_STEPS
        self.current_step = 0

        # Shared config — persists as the user moves between steps
        self.v_install_dir = ctk.StringVar(value="~/kali-mcp")
        self.v_mcp_port    = ctk.StringVar(value="8000")
        self.v_vm_ip       = ctk.StringVar(value="")

        # Optional toggles
        self.opt_discord   = ctk.BooleanVar(value=True)
        self.opt_health    = ctk.BooleanVar(value=True)
        self.opt_tailscale = ctk.BooleanVar(value=True)

        self._build_shell()
        self._show_step(0)

    # ── Shell ─────────────────────────────────────
    def _build_shell(self):
        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=230, fg_color=BG_PANEL, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        logo = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo.pack(fill="x", padx=20, pady=(28, 16))
        ctk.CTkLabel(logo, text="⚡ KALI MCP",
                     font=ctk.CTkFont(family="Courier New", size=15, weight="bold"),
                     text_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(logo, text="Bounty Lab Installer",
                     font=ctk.CTkFont(size=11), text_color=TXT_MID).pack(anchor="w")
        badge = ctk.CTkFrame(logo, fg_color=BG_CARD, corner_radius=4)
        badge.pack(anchor="w", pady=(8, 0))
        icon = "🐧" if CURRENT_OS == "Linux" else "🪟"
        ctk.CTkLabel(badge, text=f"{icon}  {CURRENT_OS}",
                     font=ctk.CTkFont(size=10), text_color=TXT_MID,
                     padx=8, pady=3).pack()

        divider(self.sidebar)

        steps_wrap = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        steps_wrap.pack(fill="x", pady=10)
        self._step_rows = []
        for name, _ in self.steps:
            row = ctk.CTkFrame(steps_wrap, fg_color="transparent", height=38)
            row.pack(fill="x")
            row.pack_propagate(False)
            dot = ctk.CTkLabel(row, text="○", width=28,
                               font=ctk.CTkFont(size=13), text_color=TXT_DIM)
            dot.pack(side="left", padx=(18, 4))
            lbl_w = ctk.CTkLabel(row, text=name, font=ctk.CTkFont(size=12),
                                  text_color=TXT_DIM, anchor="w")
            lbl_w.pack(side="left", fill="x")
            self._step_rows.append((row, dot, lbl_w))

        ctk.CTkLabel(self.sidebar, text="v1.0  •  github.com/spac3gh0st00",
                     font=ctk.CTkFont(size=9), text_color=TXT_DIM).pack(
                         side="bottom", pady=14)

        # Main content
        self.main = ctk.CTkFrame(self, fg_color=BG_BASE, corner_radius=0)
        self.main.pack(side="left", fill="both", expand=True)

        self.content = ctk.CTkScrollableFrame(
            self.main, fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=TXT_DIM)
        self.content.pack(fill="both", expand=True, padx=44, pady=(34, 0))

        # Nav bar
        nav = ctk.CTkFrame(self.main, height=66, fg_color=BG_PANEL, corner_radius=0)
        nav.pack(fill="x", side="bottom")
        nav.pack_propagate(False)

        self.back_btn = ctk.CTkButton(
            nav, text="← Back", width=100, height=38,
            fg_color=BG_CARD, hover_color=BORDER, text_color=TXT_MID,
            font=ctk.CTkFont(size=12), command=self._prev_step)
        self.back_btn.pack(side="left", padx=22, pady=14)

        self.step_lbl = ctk.CTkLabel(nav, text="",
                                     font=ctk.CTkFont(size=11), text_color=TXT_DIM)
        self.step_lbl.pack(side="left")

        self.next_btn = ctk.CTkButton(
            nav, text="Next  →", width=130, height=38,
            fg_color=ACCENT, hover_color=ACCENT_DIM, text_color="#000000",
            font=ctk.CTkFont(size=13, weight="bold"), command=self._next_step)
        self.next_btn.pack(side="right", padx=22, pady=14)

    def _update_sidebar(self):
        for i, (row, dot, lbl_w) in enumerate(self._step_rows):
            if i < self.current_step:
                dot.configure(text="✓", text_color=CLR_OK)
                lbl_w.configure(text_color=TXT_MID, font=ctk.CTkFont(size=12))
                row.configure(fg_color="transparent")
            elif i == self.current_step:
                dot.configure(text="●", text_color=ACCENT)
                lbl_w.configure(text_color=TXT_BRIGHT,
                                font=ctk.CTkFont(size=12, weight="bold"))
                row.configure(fg_color=BG_CARD)
            else:
                dot.configure(text="○", text_color=TXT_DIM)
                lbl_w.configure(text_color=TXT_DIM, font=ctk.CTkFont(size=12))
                row.configure(fg_color="transparent")

    def _show_step(self, idx):
        for w in self.content.winfo_children():
            w.destroy()
        self.current_step = idx
        self._update_sidebar()
        total = len(self.steps)
        self.step_lbl.configure(text=f"Step {idx + 1} / {total}")
        self.back_btn.configure(state="normal" if idx > 0 else "disabled")
        self.next_btn.configure(text="Close" if idx == total - 1 else "Next  →")
        _, key = self.steps[idx]
        getattr(self, f"_step_{key}", self._step_generic)()

    def _next_step(self):
        if self.current_step < len(self.steps) - 1:
            self._show_step(self.current_step + 1)
        else:
            self.destroy()

    def _prev_step(self):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    # ── Shared builders ───────────────────────────
    def _header(self, title, subtitle=""):
        lbl(self.content, title, size=22, weight="bold").pack(anchor="w")
        if subtitle:
            lbl(self.content, subtitle, size=12, color=TXT_MID,
                wraplength=700, justify="left").pack(anchor="w", pady=(4, 18))
        else:
            ctk.CTkFrame(self.content, height=18, fg_color="transparent").pack()

    def _field_row(self, parent, label_text, var=None, placeholder="",
                   width=280, show=""):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=5)
        lbl(row, label_text, size=12, color=TXT_MID,
            width=160, anchor="w").pack(side="left")
        e = mk_entry(row, placeholder=placeholder, width=width,
                     show=show, textvariable=var)
        e.pack(side="left")
        return e

    def _run_btn(self, parent, label_text, callback):
        """Returns the button so callers can pass it to run_script for disabling."""
        btn = ctk.CTkButton(
            parent, text=f"▶  {label_text}",
            width=190, height=36,
            fg_color=ACCENT, hover_color=ACCENT_DIM,
            text_color="#000000",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=callback)
        btn.pack(anchor="w", pady=(10, 0))
        btn._original_text = f"▶  {label_text}"
        return btn

    def _toggle_row(self, parent, label_text, var):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=10)
        lbl(row, label_text, size=13).pack(side="left")
        ctk.CTkSwitch(row, variable=var, text="",
                      onvalue=True, offvalue=False,
                      progress_color=ACCENT,
                      button_color=ACCENT).pack(side="right")

    def _notice(self, text, color=TXT_MID):
        c = card(self.content)
        c.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(c, text=text, font=ctk.CTkFont(size=11),
                     text_color=color, wraplength=660,
                     justify="left").pack(padx=16, pady=10, anchor="w")

    # ── Common arg builders ───────────────────────
    def _linux_args(self, extra=None):
        args = [
            "--install-dir", self.v_install_dir.get().strip() or "~/kali-mcp",
            "--mcp-port",    self.v_mcp_port.get().strip()    or "8000",
            "--discord",     "true" if self.opt_discord.get()   else "false",
            "--health",      "true" if self.opt_health.get()    else "false",
            "--tailscale",   "true" if self.opt_tailscale.get() else "false",
        ]
        if extra:
            args += extra
        return args

    def _windows_args(self, extra=None):
        args = ["-McpPort", self.v_mcp_port.get().strip() or "8000"]
        ip = self.v_vm_ip.get().strip()
        if ip:
            args += ["-VmIp", ip]
        if extra:
            args += extra
        return args

    # ══════════════════════════════════════════════
    # STEPS
    # ══════════════════════════════════════════════

    def _step_generic(self):
        self._header("Step not implemented")

    # ── Welcome ──────────────────────────────────
    def _step_welcome(self):
        banner = (
            " ██╗  ██╗ █████╗ ██╗     ██╗\n"
            " ██║ ██╔╝██╔══██╗██║     ██║\n"
            " █████╔╝ ███████║██║     ██║\n"
            " ██╔═██╗ ██╔══██║██║     ██║\n"
            " ██║  ██╗██║  ██║███████╗██║\n"
            " ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  MCP Bounty Lab"
        )
        ctk.CTkLabel(self.content, text=banner,
                     font=ctk.CTkFont(family="Courier New", size=9),
                     text_color=ACCENT, justify="left").pack(anchor="w", pady=(0, 14))

        platform_label = "Linux (Ubuntu VM)" if CURRENT_OS == "Linux" else "Windows Host"
        self._header("Welcome",
                     f"Platform detected: {platform_label}.  "
                     "Each step runs a phase of the installer script and streams "
                     "the output live. You can go back and re-run any step.")

        # Script presence check
        script = LINUX_SCRIPT if CURRENT_OS == "Linux" else WINDOWS_SCRIPT
        c = card(self.content)
        c.pack(fill="x", pady=4)
        if script.exists():
            lbl(c, f"✓  {script.name}  found", size=12, color=CLR_OK).pack(
                padx=16, pady=(10, 2), anchor="w")
        else:
            lbl(c, f"✗  {script.name}  NOT FOUND  ← fix this before proceeding",
                size=12, color=CLR_ERR).pack(padx=16, pady=(10, 2), anchor="w")
            lbl(c, "All three files must be in the same folder as this GUI.",
                size=11, color=CLR_WARN).pack(padx=16, pady=(0, 2), anchor="w")
        lbl(c, f"📁  {SCRIPT_DIR}", size=11, color=TXT_DIM).pack(
            padx=16, pady=(0, 10), anchor="w")

        items = ([
            ("🔍", "Prerequisites Check"),
            ("🐳", "Docker setup"),
            ("💀", "Kali container clone + build  (10–20 min first time)"),
            ("🔗", "MCP server start + health check"),
            ("💬", "Discord Bot  (optional)"),
            ("📡", "Health Monitor  (optional)"),
            ("🔒", "Tailscale  (optional)"),
            ("🛡️", "UFW Firewall rules"),
        ] if CURRENT_OS == "Linux" else [
            ("🔍", "Prerequisites Check"),
            ("🖥️", "Claude Desktop config writer"),
            ("🌐", "netsh Port Proxy + firewall rule"),
        ])
        for icon, desc in items:
            ci = card(self.content)
            ci.pack(fill="x", pady=2)
            lbl(ci, icon, size=16, width=40).pack(side="left", padx=10, pady=8)
            lbl(ci, desc, size=12).pack(side="left", anchor="w")

    # ── Prerequisites ─────────────────────────────
    def _step_prereqs(self):
        self._header("Prerequisites Check",
                     "Scan first to see what\'s missing, then install it all "
                     "with one click. Run checks again to confirm.")

        t = terminal(self.content, 280)
        twrite(t, "# Click \'Run Checks\' to scan your system\n")

        args = self._linux_args() if CURRENT_OS == "Linux" else self._windows_args()

        # Button row
        btn_row = ctk.CTkFrame(self.content, fg_color="transparent")
        btn_row.pack(anchor="w", pady=(10, 0))

        check_btn = ctk.CTkButton(
            btn_row, text="\u25b6  Run Checks",
            width=170, height=36,
            fg_color=ACCENT, hover_color=ACCENT_DIM,
            text_color="#000000",
            font=ctk.CTkFont(size=12, weight="bold"))
        check_btn.pack(side="left", padx=(0, 12))
        check_btn._original_text = "\u25b6  Run Checks"

        # Install Missing button — works on both Linux and Windows
        install_btn = ctk.CTkButton(
            btn_row, text="\u2b07  Install Missing",
            width=185, height=36,
            fg_color=BG_CARD, hover_color=BORDER,
            text_color=TXT_BRIGHT,
            border_width=1, border_color=BORDER,
            font=ctk.CTkFont(size=12, weight="bold"))
        install_btn.pack(side="left")
        install_btn._original_text = "\u2b07  Install Missing"

        if CURRENT_OS == "Linux":
            self._notice(
                "\u2139  Installs: git, curl, python3-tk, pip, customtkinter, ufw.\n"
                "   Docker is handled separately in the Docker step.",
                color=TXT_MID)
        else:
            self._notice(
                "\u2139  Installs: git, Node.js, mcp-remote, Claude Desktop.\n"
                "   Administrator privileges cannot be auto-granted — right-click\n"
                "   run.bat and choose Run as administrator for the Port Proxy step.",
                color=TXT_MID)

        install_btn.configure(
            command=lambda: run_script(
                self, t, "prereqs-install", args, install_btn))

        check_btn.configure(
            command=lambda: run_script(self, t, "prereqs", args, check_btn))

    # ── Docker (Linux) ────────────────────────────
    def _step_docker(self):
        self._header("Docker Setup",
                     "Installs Docker Engine (if missing), adds you to the docker "
                     "group, and starts the daemon.")
        self._notice(
            "ℹ  If Docker is already installed, this phase just verifies "
            "the daemon is running and skips the install.", color=TXT_MID)
        self._notice(
            "⚠  After this phase, if your user was just added to the docker group, "
            "you may need to log out and back in (or run 'newgrp docker' in the "
            "terminal) before docker works without sudo.", color=CLR_WARN)
        t = terminal(self.content, 260)
        twrite(t, "# Click 'Run Docker Setup' to begin\n")
        btn = self._run_btn(self.content, "Run Docker Setup", None)
        btn.configure(command=lambda: run_script(
            self, t, "docker", self._linux_args(), btn))

    # ── Kali Container (Linux) ────────────────────
    def _step_kali(self):
        self._header("Kali Container",
                     "Clone the kali-mcp repo and docker compose build. "
                     "First run pulls ~3 GB — takes 10–20 minutes.")

        c = card(self.content)
        c.pack(fill="x", pady=(0, 10))
        repo_e = self._field_row(c, "Repo URL:",
                                  placeholder="https://github.com/k3nn3dy-ai/kali-mcp",
                                  width=380)
        self._field_row(c, "Install directory:",
                        var=self.v_install_dir, width=260)
        ctk.CTkFrame(c, height=8, fg_color="transparent").pack()

        t = terminal(self.content, 240)
        twrite(t, "# Click 'Clone & Build' to proceed\n")

        btn = self._run_btn(self.content, "Clone & Build", None)

        def _do():
            repo = repo_e.get().strip() or "https://github.com/k3nn3dy-ai/kali-mcp"
            run_script(self, t, "kali", self._linux_args(["--repo-url", repo]), btn)

        btn.configure(command=_do)

    # ── MCP Server (Linux) ────────────────────────
    def _step_mcp(self):
        self._header("MCP Server",
                     "Starts the container (if not running) and polls /health "
                     "until it responds or times out.")
        c = card(self.content)
        c.pack(fill="x", pady=(0, 10))
        self._field_row(c, "MCP Port:", var=self.v_mcp_port,
                        placeholder="8000", width=120)
        ctk.CTkFrame(c, height=8, fg_color="transparent").pack()

        t = terminal(self.content, 220)
        twrite(t, "# Click 'Start & Verify' to bring up the server\n")
        btn = self._run_btn(self.content, "Start & Verify", None)
        btn.configure(command=lambda: run_script(
            self, t, "mcp", self._linux_args(), btn))

    # ── Discord Bot (Linux) ───────────────────────
    def _step_discord(self):
        self._header("Discord Bot  (Optional)",
                     "Creates a Python venv, installs discord.py, and runs "
                     "the bot as a systemd service.")

        c1 = card(self.content)
        c1.pack(fill="x", pady=(0, 10))
        self._toggle_row(c1, "Enable Discord Bot", self.opt_discord)

        # ── Credential fields ─────────────────────────────────────────────
        creds = card(self.content)
        creds.pack(fill="x", pady=(0, 6))

        lbl(creds, "Discord credentials", size=12, weight="bold",
            color=TXT_BRIGHT).pack(anchor="w", padx=16, pady=(12, 4))
        lbl(creds,
            "Fill these in now and the installer writes your .env automatically.",
            size=11, color=TXT_MID).pack(anchor="w", padx=16, pady=(0, 8))

        self.v_discord_token   = ctk.StringVar()
        self.v_discord_guild   = ctk.StringVar()
        self.v_discord_user_id = ctk.StringVar()
        self.v_anthropic_key   = ctk.StringVar()
        self.v_webhook_url     = ctk.StringVar()

        self._field_row(creds, "Bot Token:",
                        var=self.v_discord_token,
                        placeholder="Paste bot token from Discord Developer Portal  (starts with MT... or OT...)",
                        width=340, show="*")
        self._field_row(creds, "Guild (Server) ID:",
                        var=self.v_discord_guild,
                        placeholder="Numbers only — right-click server name → Copy Server ID",
                        width=240)
        self._field_row(creds, "Your User ID:",
                        var=self.v_discord_user_id,
                        placeholder="Numbers only — right-click your name → Copy User ID",
                        width=240)
        self._field_row(creds, "Anthropic API Key:",
                        var=self.v_anthropic_key,
                        placeholder="Paste API key from console.anthropic.com  (starts with sk-ant-...)",
                        width=340, show="*")
        self._field_row(creds, "Discord Webhook URL:",
                        var=self.v_webhook_url,
                        placeholder="Paste webhook URL  (starts with https://discord.com/api/webhooks/...)",
                        width=340)

        ctk.CTkFrame(creds, height=10, fg_color="transparent").pack()

        self._notice(
            "ℹ  Leave any field blank to skip it — the installer will warn "
            "you but still set up the service.\n"
            "   You can fill in blanks later by editing .env and running:\n"
            "   sudo systemctl restart discord-kali-bot",
            color=TXT_MID)

        t = terminal(self.content, 180)
        twrite(t, "# Fill in your credentials above, then click Install\n")
        btn = self._run_btn(self.content, "Install Discord Bot", None)

        def _do_discord():
            # Write .env before calling the script
            idir = self.v_install_dir.get().strip() or "~/kali-mcp"
            import os
            idir_real = os.path.expanduser(idir)
            env_path = os.path.join(idir_real, ".env")

            token   = self.v_discord_token.get().strip()
            guild   = self.v_discord_guild.get().strip()
            user_id = self.v_discord_user_id.get().strip()
            ant_key = self.v_anthropic_key.get().strip()
            webhook = self.v_webhook_url.get().strip()

            # ── Validate field formats before writing anything ────────────
            errors = []

            if guild and not guild.isdigit():
                errors.append(
                    f"  ✗  Guild (Server) ID must be numbers only.\n"
                    f"     Got: {guild[:30]}...\n"
                    f"     Tip: right-click your server name → Copy Server ID\n"
                )

            if user_id and not user_id.isdigit():
                errors.append(
                    f"  ✗  Your User ID must be numbers only.\n"
                    f"     Got: {user_id[:30]}...\n"
                    f"     Tip: Settings → Advanced → enable Developer Mode,\n"
                    f"          then right-click your username → Copy User ID\n"
                )

            if ant_key and not ant_key.startswith("sk-ant-"):
                errors.append(
                    f"  ✗  Anthropic API Key should start with 'sk-ant-'.\n"
                    f"     Got: {ant_key[:20]}...\n"
                    f"     Tip: get it from console.anthropic.com → API Keys\n"
                )

            if webhook and not webhook.startswith("https://discord.com/api/webhooks/"):
                errors.append(
                    f"  ✗  Webhook URL should start with 'https://discord.com/api/webhooks/'.\n"
                    f"     Got: {webhook[:40]}...\n"
                    f"     Tip: channel settings → Integrations → Webhooks → Copy URL\n"
                )

            if errors:
                twrite(t, "\n─── Credential errors — fix these before installing ───\n")
                for e in errors:
                    twrite(t, e)
                twrite(t, "──────────────────────────────────────────────────────\n")
                return   # stop here — do not write .env or run the script

            # Only write fields that were actually filled in
            lines_out = []
            if token:   lines_out.append(f"DISCORD_TOKEN={token}")
            if guild:   lines_out.append(f"DISCORD_GUILD_ID={guild}")
            if user_id: lines_out.append(f"ALLOWED_USER_ID={user_id}")
            if ant_key: lines_out.append(f"ANTHROPIC_API_KEY={ant_key}")
            if webhook: lines_out.append(f"DISCORD_WEBHOOK_URL={webhook}")
            lines_out.append(f"MCP_URL=http://localhost:{self.v_mcp_port.get().strip() or '8000'}")

            if lines_out:
                try:
                    os.makedirs(idir_real, exist_ok=True)
                    # Merge with existing .env if present
                    existing = {}
                    if os.path.exists(env_path):
                        with open(env_path) as ef:
                            for line in ef:
                                line = line.strip()
                                if "=" in line and not line.startswith("#"):
                                    k, v = line.split("=", 1)
                                    existing[k.strip()] = v.strip()
                    # New values override existing
                    for entry in lines_out:
                        k, v = entry.split("=", 1)
                        existing[k] = v
                    with open(env_path, "w") as ef:
                        for k, v in existing.items():
                            ef.write(f"{k}={v}\n")
                    os.chmod(env_path, 0o600)
                    twrite(t, f"\n  Wrote credentials to {env_path}\n")
                except Exception as exc:
                    twrite(t, f"\n  Could not write .env: {exc}\n")
                    twrite(t, "  You may need to create it manually.\n")
            else:
                twrite(t, "\n  No credentials entered — skipping .env write\n")

            run_script(self, t, "discord", self._linux_args(), btn)

        btn.configure(command=_do_discord)

        # ── Health Monitor (Linux) ────────────────────
    def _step_health(self):
        self._header("Health Monitor  (Optional)",
                     "Writes health_monitor.py and installs it as a systemd "
                     "service that polls /health every 10 s.")
        c = card(self.content)
        c.pack(fill="x", pady=(0, 10))
        self._toggle_row(c, "Enable Health Monitor", self.opt_health)

        t = terminal(self.content, 220)
        twrite(t, "# Click 'Install Monitor' to set up the service\n")
        btn = self._run_btn(self.content, "Install Monitor", None)
        btn.configure(command=lambda: run_script(
            self, t, "health", self._linux_args(), btn))

    # ── Tailscale (Linux) ─────────────────────────
    def _step_tailscale(self):
        self._header("Tailscale  (Optional)",
                     "Installs Tailscale and OpenSSH for encrypted "
                     "phone/remote access.")
        c = card(self.content)
        c.pack(fill="x", pady=(0, 10))
        self._toggle_row(c, "Enable Tailscale", self.opt_tailscale)
        divider(c)
        self._notice(
            "ℹ  'tailscale up' will print a URL in the terminal below.\n"
            "   Open that URL in a browser to authenticate your device.",
            color=TXT_MID)

        t = terminal(self.content, 220)
        twrite(t, "# Click 'Install Tailscale' to begin\n")
        btn = self._run_btn(self.content, "Install Tailscale", None)
        btn.configure(command=lambda: run_script(
            self, t, "tailscale", self._linux_args(), btn))

    # ── Firewall (Linux) ─────────────────────────
    def _step_firewall(self):
        self._header("Firewall Rules  (UFW)",
                     "Deny all inbound by default. Allow SSH and "
                     "MCP port only from your Windows host.")
        c = card(self.content)
        c.pack(fill="x", pady=(0, 10))
        host_e = self._field_row(
            c, "Windows Host IP:",
            placeholder="run 'hostname -I' on Ubuntu → use that IP on Windows",
            width=320)
        self._field_row(c, "MCP Port:", var=self.v_mcp_port,
                        placeholder="8000", width=120)
        ssh_e  = self._field_row(c, "SSH Port:", placeholder="22", width=120)
        ctk.CTkFrame(c, height=8, fg_color="transparent").pack()

        self._notice(
            "⚠  If you leave 'Windows Host IP' blank the script will use the "
            "whole VM subnet (192.168.x.0/24) as a fallback. That's less "
            "restrictive but still safe for a home lab.",
            color=CLR_WARN)

        t = terminal(self.content, 200)
        twrite(t, "# Fill in the Windows Host IP then click 'Apply Rules'\n")
        btn = self._run_btn(self.content, "Apply Rules", None)

        def _do():
            host = host_e.get().strip()
            ssh  = ssh_e.get().strip() or "22"
            extra = ["--ssh-port", ssh]
            if host:
                extra += ["--host-ip", host]
            run_script(self, t, "firewall", self._linux_args(extra), btn)

        btn.configure(command=_do)

    # ── Claude Desktop (Windows) ──────────────────
    def _step_claude(self):
        self._header("Claude Desktop Config",
                     "Writes the kali MCP entry into claude_desktop_config.json. "
                     "Installs mcp-remote if it's missing.")
        self._notice(
            "ℹ  Use the DIRECT installer from claude.ai/download — not the "
            "Microsoft Store version. The Store version does not support "
            "remote MCP connections.", color=TXT_MID)
        c = card(self.content)
        c.pack(fill="x", pady=(0, 10))
        self._field_row(c, "Ubuntu VM IP:", var=self.v_vm_ip,
                        placeholder="192.168.91.x", width=220)
        self._field_row(c, "MCP Port:", var=self.v_mcp_port,
                        placeholder="8000", width=120)
        ctk.CTkFrame(c, height=8, fg_color="transparent").pack()

        t = terminal(self.content, 260)
        twrite(t, "# Fill in the Ubuntu VM IP, then click 'Write Config'\n")
        btn = self._run_btn(self.content, "Write Config", None)
        btn.configure(command=lambda: run_script(
            self, t, "claude", self._windows_args(), btn))

    # ── Port Proxy (Windows) ──────────────────────
    def _step_portproxy(self):
        self._header("Port Proxy Setup",
                     "Adds a netsh portproxy rule and Windows Firewall rule "
                     "so Claude Desktop can reach the MCP server.")
        self._notice(
            "⚠  This step requires Administrator privileges.\n"
            "   The script will exit with a clear error message if it's not "
            "running as admin — right-click the installer and choose "
            "'Run as administrator', then come back to this step.",
            color=CLR_WARN)
        c = card(self.content)
        c.pack(fill="x", pady=(0, 10))
        self._field_row(c, "Ubuntu VM IP:", var=self.v_vm_ip,
                        placeholder="192.168.91.x", width=220)
        self._field_row(c, "MCP Port:", var=self.v_mcp_port,
                        placeholder="8000", width=120)
        ctk.CTkFrame(c, height=8, fg_color="transparent").pack()

        t = terminal(self.content, 260)
        twrite(t, "# Click 'Apply Port Proxy' to run\n")
        btn = self._run_btn(self.content, "Apply Port Proxy", None)
        btn.configure(command=lambda: run_script(
            self, t, "portproxy", self._windows_args(), btn))

    # ── Summary ───────────────────────────────────
    def _step_summary(self):
        self._header("All done  🎉", "Your lab is configured.")

        if CURRENT_OS == "Linux":
            rows = [
                ("🐳", "Docker + Kali Container", "Running · port 8000"),
                ("🔗", "MCP Server", "Listening on /sse"),
                ("💬", "Discord Bot",
                 "Installed" if self.opt_discord.get() else "Skipped"),
                ("📡", "Health Monitor",
                 "Installed" if self.opt_health.get() else "Skipped"),
                ("🔒", "Tailscale",
                 "Connected" if self.opt_tailscale.get() else "Skipped"),
                ("🛡️", "UFW Firewall", "Rules applied"),
            ]
            next_steps = (
                "Daily startup:\n"
                "  cd ~/kali-mcp && docker compose up -d\n\n"
                "Check services:\n"
                "  sudo systemctl status discord-kali-bot\n"
                "  sudo systemctl status kalibot-monitor\n\n"
                "Test MCP:\n"
                "  curl http://localhost:8000/health"
            )
        else:
            rows = [
                ("🖥️", "Claude Desktop Config", "MCP server registered"),
                ("🌐", "Port Proxy", "netsh rule created"),
            ]
            next_steps = (
                "1. Restart Claude Desktop (system tray → Quit, relaunch)\n"
                "2. Click + in chat → Connectors → verify 'kali' is listed\n"
                "3. Ask Claude: 'Run a quick nmap scan on 127.0.0.1'"
            )

        for icon, title, status in rows:
            c = card(self.content)
            c.pack(fill="x", pady=3)
            lbl(c, icon, size=18, width=44).pack(side="left", padx=10, pady=10)
            inner = ctk.CTkFrame(c, fg_color="transparent")
            inner.pack(side="left", fill="x", expand=True, pady=8)
            lbl(inner, title, size=13, weight="bold").pack(anchor="w")
            lbl(inner, status, size=11,
                color=TXT_DIM if status == "Skipped" else CLR_OK).pack(anchor="w")

        c2 = card(self.content)
        c2.pack(fill="x", pady=(12, 0))
        lbl(c2, "Next steps:", size=12, weight="bold").pack(
            anchor="w", padx=16, pady=(12, 4))
        tb = ctk.CTkTextbox(c2, height=110, fg_color="#050505",
                            text_color=TERM_FG,
                            font=ctk.CTkFont(family="Courier New", size=11),
                            corner_radius=4, border_width=0)
        tb.pack(fill="x", padx=14, pady=(0, 12))
        tb.insert("end", next_steps)
        tb.configure(state="disabled")

        self._notice(
            "🔒  Authorised testing only — bug bounty programs you're enrolled in, "
            "CTFs, and systems you own.", color=CLR_WARN)


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────
if __name__ == "__main__":
    app = KaliLabInstaller()
    app.mainloop()
