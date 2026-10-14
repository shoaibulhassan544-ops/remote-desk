"""tkinter UI — VIP professional design (v1.0.2).

Layout: left sidebar navigation + main content area + top header with
product mark, version and status pill. Dark premium theme by default.

Rules (unchanged from v1.0.0):
- Every button is wired to real code, or explicitly disabled with a reason.
- The UI never claims "connected" unless a real session exists.
- Incoming requests pop a modal dialog: Accept/Reject + permission checkboxes.
- Update popup: in-app download with progress (v1.0.2); browser fallback
  ONLY when no installer asset exists or the download fails.
"""

import io
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import config, storage, update_checker
from .client import RemoteClient
from .device_id import format_device_id, get_device_name, load_or_create_device_id
from .discovery import DiscoveryListener
from .host import HostServer
from .security import PairingCodeStore, validate_unattended_password, hash_password
from .version import VERSION

# VIP premium themes. Dark is the default.
VIP_DARK = {
    "bg": "#0B1220", "sidebar": "#0E1628", "header": "#0E1628",
    "card": "#16203A", "fg": "#F1F5F9", "muted": "#94A3B8",
    "accent": "#E8B84B", "accent_fg": "#1A1405",
    "teal": "#14B8A6", "teal_fg": "#062A26",
    "danger": "#EF4444", "entry": "#0B1220", "border": "#24314F",
    "sidebar_active": "#E8B84B", "sidebar_active_fg": "#1A1405",
    "sidebar_fg": "#CBD5E1",
}
VIP_LIGHT = {
    "bg": "#EEF1F6", "sidebar": "#1B2A4A", "header": "#FFFFFF",
    "card": "#FFFFFF", "fg": "#0F172A", "muted": "#64748B",
    "accent": "#B8860B", "accent_fg": "#FFFFFF",
    "teal": "#0F766E", "teal_fg": "#FFFFFF",
    "danger": "#DC2626", "entry": "#FFFFFF", "border": "#D8DEE9",
    "sidebar_active": "#E8B84B", "sidebar_active_fg": "#1A1405",
    "sidebar_fg": "#D7DEEB",
}


class RemoteDeskApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{config.PRODUCT_NAME} v{VERSION}")
        self.root.geometry("1000x680")
        self.root.minsize(860, 600)
        self.settings = storage.load_settings()
        self.theme = VIP_LIGHT if self.settings.get("theme") == "light" else VIP_DARK
        self.device_id = load_or_create_device_id()
        self.device_name = get_device_name()
        self.msg_queue: queue.Queue = queue.Queue()
        self.host: HostServer | None = None
        self.client = RemoteClient(self.device_id, self.device_name,
                                   on_frame=self._on_frame,
                                   on_status=self._log,
                                   on_disconnect=self._on_client_disconnect)
        self.pairing = PairingCodeStore()
        self.viewer_photo = None
        self._current_page = "Dashboard"
        self._nav_btns: dict[str, tk.Button] = {}
        self.pages: dict[str, tk.Frame] = {}
        self._download_cancel: threading.Event | None = None
        self._downloaded_path: str | None = None
        self._build()
        self._apply_theme()
        self._show_page("Dashboard")
        self.root.after(200, self._pump_queue)
        if self.settings.get("auto_update_check", True):
            threading.Thread(target=self._background_update_check, daemon=True).start()

    # ------------------------------------------------------------- theming helpers
    def _role(self, widget, role: str):
        widget._theme_role = role  # type: ignore[attr-defined]
        return widget

    def _apply_theme(self):
        t = self.theme
        self.root.configure(bg=t["bg"])
        try:
            style = ttk.Style(self.root)
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass
            style.configure("VIP.Horizontal.TProgressbar",
                            troughcolor=t["entry"], background=t["accent"],
                            bordercolor=t["border"], lightcolor=t["accent"],
                            darkcolor=t["accent"])
        except Exception:
            pass

        def _apply(w):
            role = getattr(w, "_theme_role", None)
            if role == "bg":
                w.configure(bg=t["bg"])
            elif role == "sidebar":
                w.configure(bg=t["sidebar"])
            elif role == "header":
                w.configure(bg=t["header"])
            elif role == "card":
                w.configure(bg=t["card"])
            elif role == "label_bg":
                w.configure(bg=t["bg"], fg=t["fg"])
            elif role == "label_card":
                w.configure(bg=t["card"], fg=t["fg"])
            elif role == "accent_card":
                w.configure(bg=t["card"], fg=t["accent"])
            elif role == "label_sidebar":
                w.configure(bg=t["sidebar"], fg=t["sidebar_fg"])
            elif role == "label_header":
                w.configure(bg=t["header"], fg=t["fg"])
            elif role == "muted_bg":
                w.configure(bg=t["bg"], fg=t["muted"])
            elif role == "muted_card":
                w.configure(bg=t["card"], fg=t["muted"])
            elif role == "muted_sidebar":
                w.configure(bg=t["sidebar"], fg=t["muted"])
            elif role == "gold_btn":
                w.configure(bg=t["accent"], fg=t["accent_fg"],
                            activebackground=t["accent"], activeforeground=t["accent_fg"],
                            highlightbackground=t["accent"])
            elif role == "teal_btn":
                w.configure(bg=t["teal"], fg=t["teal_fg"],
                            activebackground=t["teal"], activeforeground=t["teal_fg"],
                            highlightbackground=t["teal"])
            elif role == "ghost_btn":
                w.configure(bg=t["card"], fg=t["fg"],
                            activebackground=t["border"], activeforeground=t["fg"],
                            highlightbackground=t["border"])
            elif role == "danger_btn":
                w.configure(bg=t["danger"], fg="#FFFFFF",
                            activebackground=t["danger"], activeforeground="#FFFFFF")
            elif role == "entry":
                w.configure(bg=t["entry"], fg=t["fg"], insertbackground=t["fg"],
                            highlightbackground=t["border"], highlightcolor=t["accent"])
            elif role == "text":
                w.configure(bg=t["entry"], fg=t["fg"], insertbackground=t["fg"],
                            highlightbackground=t["border"])
            elif role == "listbox":
                w.configure(bg=t["entry"], fg=t["fg"],
                            selectbackground=t["accent"], selectforeground=t["accent_fg"],
                            highlightbackground=t["border"])
            elif role == "check_card":
                w.configure(bg=t["card"], fg=t["fg"], activebackground=t["card"],
                            selectcolor=t["card"])
            elif role == "check_bg":
                w.configure(bg=t["bg"], fg=t["fg"], activebackground=t["bg"],
                            selectcolor=t["bg"])
            elif role == "nav":
                pass  # nav buttons styled by _refresh_nav()
            for child in w.winfo_children():
                _apply(child)

        _apply(self.root)
        if hasattr(self, "theme_btn"):
            self.theme_btn.configure(
                text="☀  Light mode" if self.theme is VIP_DARK else "🌙  Dark mode")
        self._refresh_nav()
        self._refresh_pill()

    def _refresh_nav(self):
        t = self.theme
        for name, btn in self._nav_btns.items():
            if name == self._current_page:
                btn.configure(bg=t["sidebar_active"], fg=t["sidebar_active_fg"],
                              activebackground=t["sidebar_active"],
                              activeforeground=t["sidebar_active_fg"])
            else:
                btn.configure(bg=t["sidebar"], fg=t["sidebar_fg"],
                              activebackground=t["border"],
                              activeforeground=t["fg"])

    def _refresh_pill(self):
        if not hasattr(self, "status_pill"):
            return
        t = self.theme
        hosting = self.host is not None
        connected = bool(getattr(self.client, "connected", False))
        session_active = bool(self.host and self.host.sessions.active)
        if connected or session_active:
            self.status_pill.configure(text="●  Connected", bg=t["teal"], fg=t["teal_fg"])
        elif hosting:
            self.status_pill.configure(text="●  Hosting ON", bg=t["accent"], fg=t["accent_fg"])
        else:
            self.status_pill.configure(text="○  Idle", bg=t["border"], fg=t["fg"])

    # ------------------------------------------------------------- building
    def _build(self):
        t = self.theme
        # ---- header ----
        header = self._role(tk.Frame(self.root, bg=t["header"]), "header")
        header.pack(fill="x", side="top")
        brand = self._role(tk.Frame(header, bg=t["header"]), "header")
        brand.pack(side="left", padx=16, pady=10)
        mark = tk.Label(brand, text="◆", font=("Segoe UI", 20, "bold"),
                        bg=t["header"], fg=t["accent"])
        self._role(mark, "label_header")
        mark.pack(side="left")
        title = tk.Label(brand, text=config.PRODUCT_NAME,
                         font=("Segoe UI", 18, "bold"), bg=t["header"], fg=t["fg"])
        self._role(title, "label_header")
        title.pack(side="left", padx=(8, 4))
        ver = tk.Label(brand, text=f"v{VERSION}  •  VIP",
                       font=("Segoe UI", 10), bg=t["header"], fg=t["muted"])
        self._role(ver, "label_header")
        ver.pack(side="left", pady=(4, 0))
        right = self._role(tk.Frame(header, bg=t["header"]), "header")
        right.pack(side="right", padx=16, pady=10)
        self.status_pill = tk.Label(right, text="○  Idle", font=("Segoe UI", 10, "bold"),
                                    padx=12, pady=4, relief="flat")
        self.status_pill.pack(side="left", padx=(0, 10))
        self.theme_btn = tk.Button(right, text="", command=self._toggle_theme,
                                   relief="flat", padx=12, pady=4,
                                   font=("Segoe UI", 10))
        self._role(self.theme_btn, "ghost_btn")
        self.theme_btn.pack(side="left")
        self.status_var = tk.StringVar(value="Idle — not hosting, not connected.")

        # ---- body: sidebar + content ----
        body = self._role(tk.Frame(self.root, bg=t["bg"]), "bg")
        body.pack(fill="both", expand=True)
        sidebar = self._role(tk.Frame(body, bg=t["sidebar"], width=210), "sidebar")
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        nav_title = tk.Label(sidebar, text="REMOTE DESK", font=("Segoe UI", 9, "bold"),
                             bg=t["sidebar"], fg=t["muted"])
        self._role(nav_title, "muted_sidebar")
        nav_title.pack(anchor="w", padx=14, pady=(14, 8))
        for name in ["Dashboard", "Viewer", "File Transfer", "Trusted Devices",
                     "History", "Security", "Diagnostics", "Settings & About"]:
            btn = tk.Button(sidebar, text=name, anchor="w", relief="flat",
                            font=("Segoe UI", 11), padx=14, pady=9,
                            command=lambda n=name: self._show_page(n))
            self._role(btn, "nav")
            btn.pack(fill="x", padx=8, pady=2)
            self._nav_btns[name] = btn
        foot = tk.Label(sidebar, text=f"{config.DEVELOPER_CREDIT}\nLAN only • Consent-first",
                        font=("Segoe UI", 8), bg=t["sidebar"], fg=t["muted"],
                        justify="left")
        self._role(foot, "muted_sidebar")
        foot.pack(side="bottom", anchor="w", padx=14, pady=14)

        content = self._role(tk.Frame(body, bg=t["bg"]), "bg")
        content.pack(side="left", fill="both", expand=True)
        # Persistent remote-session banner (hidden unless a session is active).
        self.banner = tk.Label(content,
                               text="● REMOTE SESSION ACTIVE — someone is connected to this PC",
                               bg=self.theme["danger"], fg="white",
                               font=("Segoe UI", 10, "bold"))
        for name in ["Dashboard", "Viewer", "File Transfer", "Trusted Devices",
                     "History", "Security", "Diagnostics", "Settings & About"]:
            page = self._role(tk.Frame(content, bg=t["bg"]), "bg")
            self.pages[name] = page
        self._build_dashboard()
        self._build_viewer()
        self._build_files()
        self._build_trusted()
        self._build_history()
        self._build_security()
        self._build_diag()
        self._build_about()
        self._refresh_trusted()
        self._refresh_history()

    def _show_page(self, name: str):
        self._current_page = name
        for n, page in self.pages.items():
            page.pack_forget()
        self.pages[name].pack(fill="both", expand=True, padx=14, pady=12)
        if name == "Trusted Devices":
            self._refresh_trusted()
        if name == "History":
            self._refresh_history()
        self._refresh_nav()

    # ---- widget helpers (VIP styling) ----
    def _card(self, parent, title: str):
        t = self.theme
        frame = self._role(tk.Frame(parent, bg=t["card"], padx=16, pady=12), "card")
        frame.pack(fill="x", pady=(0, 12))
        head = self._role(tk.Frame(frame, bg=t["card"]), "card")
        head.pack(fill="x")
        title_lbl = tk.Label(head, text=title.upper(), font=("Segoe UI", 9, "bold"),
                           bg=t["card"], fg=t["accent"])
        title_lbl.pack(anchor="w")
        self._role(title_lbl, "accent_card")
        tk.Frame(frame, bg=t["border"], height=1).pack(fill="x", pady=(6, 10))
        return frame

    def _lbl(self, parent, text, muted=False, bold=False, size=10, wrap=None):
        t = self.theme
        # Parent bg decides the label role: card frames vs page bg.
        bg = parent.cget("bg") if "bg" in parent.keys() else t["bg"]
        role = "label_card" if bg == t["card"] else "label_bg"
        if muted:
            role = "muted_card" if bg == t["card"] else "muted_bg"
        lbl = tk.Label(parent, text=text, bg=bg,
                       fg=t["muted"] if muted else t["fg"],
                       font=("Segoe UI", size, "bold" if bold else "normal"),
                       wraplength=wrap or 0, justify="left")
        self._role(lbl, role)
        return lbl

    def _btn(self, parent, text, command, style="gold"):
        role = {"gold": "gold_btn", "teal": "teal_btn",
                "ghost": "ghost_btn", "danger": "danger_btn"}[style]
        btn = tk.Button(parent, text=text, command=command, relief="flat",
                        font=("Segoe UI", 10, "bold"), padx=14, pady=6,
                        cursor="hand2")
        self._role(btn, role)
        return btn

    def _entry(self, parent, width=24, show=None):
        t = self.theme
        e = tk.Entry(parent, width=width, show=show or "",
                     relief="flat", font=("Segoe UI", 10),
                     highlightthickness=1)
        self._role(e, "entry")
        return e

    def _scrollable(self, parent):
        """Return an inner frame with a vertical scrollbar."""
        t = self.theme
        canvas = tk.Canvas(parent, bg=t["bg"], highlightthickness=0)
        self._role(canvas, "bg")
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = self._role(tk.Frame(canvas, bg=t["bg"]), "bg")
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return inner

    # ------------------------------------------------------------- dashboard
    def _build_dashboard(self):
        page = self.pages["Dashboard"]
        body = self._scrollable(page)
        card = self._card(body, "This device")
        self._lbl(card, f"Your ID:  {format_device_id(self.device_id)}",
                  bold=True, size=14).pack(anchor="w")
        self._lbl(card, f"Device name: {self.device_name}", muted=True).pack(anchor="w")
        self._lbl(card, f"Status: {self.status_var.get()}", muted=True).pack(anchor="w", pady=(2, 0))
        row = self._role(tk.Frame(card, bg=self.theme["card"]), "card")
        row.pack(fill="x", pady=(10, 2))
        self.host_btn = self._btn(row, "▶  Start Hosting — allow connections",
                                  self._toggle_hosting, "gold")
        self.host_btn.pack(side="left")
        self.pairing_var = tk.StringVar(value="Pairing code: — (start hosting to generate)")
        self._lbl(card, "", muted=True)  # spacing placeholder (kept minimal)
        tk.Label(card, textvariable=self.pairing_var, bg=self.theme["card"],
                 fg=self.theme["fg"], font=("Segoe UI", 12)).pack(anchor="w")
        self._btn(card, "Generate new pairing code", self._new_pairing_code,
                  "teal").pack(anchor="w", pady=(6, 2))
        self._lbl(card, "Share this code ONLY with the person you want to let in. "
                  "It expires in 5 minutes and works once.", muted=True,
                  wrap=640).pack(anchor="w")

        card2 = self._card(body, "Connect to a remote device")
        row = self._role(tk.Frame(card2, bg=self.theme["card"]), "card")
        row.pack(fill="x")
        self._lbl(row, "Host IP / address:").pack(side="left")
        self.connect_host = self._entry(row, width=24)
        self.connect_host.pack(side="left", padx=6)
        self.connect_host.insert(0, "192.168.1.100")
        self._lbl(row, "Port:").pack(side="left")
        self.connect_port = self._entry(row, width=7)
        self.connect_port.pack(side="left", padx=6)
        self.connect_port.insert(0, str(self.settings.get("port", config.DEFAULT_PORT)))
        row2 = self._role(tk.Frame(card2, bg=self.theme["card"]), "card")
        row2.pack(fill="x", pady=8)
        self._lbl(row2, "Pairing code (or unattended password):").pack(side="left")
        self.connect_code = self._entry(row2, width=24, show="•")
        self.connect_code.pack(side="left", padx=6)
        self.use_unattended = tk.BooleanVar(value=False)
        cb = tk.Checkbutton(row2, text="Use unattended password",
                            variable=self.use_unattended, font=("Segoe UI", 10))
        self._role(cb, "check_card")
        cb.pack(side="left")
        btns = self._role(tk.Frame(card2, bg=self.theme["card"]), "card")
        btns.pack(fill="x")
        self._btn(btns, "Connect", self._connect, "gold").pack(side="left", padx=(0, 6))
        self._btn(btns, "Disconnect", self._disconnect, "ghost").pack(side="left", padx=6)
        self._btn(btns, "Scan LAN for devices", self._scan_lan, "teal").pack(side="left", padx=6)

        howto = self._card(body, "How to connect — 4 steps")
        steps = (
            "1) On the laptop you want to CONTROL (the host): click "
            "“Start Hosting”, then “Generate new pairing code”.\n"
            "2) Note that laptop’s IP (Diagnostics shows it, or run ipconfig on it) "
            "and the pairing code.\n"
            "3) On YOUR laptop: enter that IP + port 47900 + pairing code → Connect.\n"
            "4) The host clicks Accept (and ticks Control if you need mouse/keyboard).\n"
            "No username needed. Both laptops must be on the same Wi-Fi. "
            "For your own laptop, enable Unattended access in Security so no "
            "Accept click is needed."
        )
        self._lbl(howto, steps, wrap=640).pack(anchor="w")

        card3 = self._card(body, "Activity log")
        self.log_box = tk.Text(card3, height=7, relief="flat", font=("Consolas", 9))
        self._role(self.log_box, "text")
        self.log_box.pack(fill="both", expand=True)
        self.log_box.configure(state="disabled")
        self._log("RemoteDesk started. Hosting is OFF until you start it.")

    # ------------------------------------------------------------- viewer
    def _build_viewer(self):
        page = self.pages["Viewer"]
        info = self._role(tk.Frame(page, bg=self.theme["bg"]), "bg")
        info.pack(fill="x", pady=(0, 8))
        self.viewer_status = tk.StringVar(value="Not connected — connect from Dashboard.")
        self._lbl(info, "", muted=True)  # keep layout stable
        tk.Label(info, textvariable=self.viewer_status, bg=self.theme["bg"],
                 fg=self.theme["muted"], font=("Segoe UI", 10)).pack(side="left")
        self._btn(info, "Request control (host must allow)",
                  self._request_control_note, "ghost").pack(side="right")
        self.canvas = tk.Canvas(page, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Button-1>", lambda e: self._send_click(e, True))
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._send_click(e, False))
        self.canvas.bind("<MouseWheel>", self._on_scroll)

    def _build_files(self):
        page = self.pages["File Transfer"]
        card = self._card(page, "File transfer (permission-gated)")
        self._lbl(card, "File transfer is available only while a session is active AND "
                  "the host allowed file transfer for that session.\n"
                  "Received files are NEVER executed automatically. They land in your "
                  "download folder (see Settings).", muted=True, wrap=660).pack(anchor="w")
        self.file_status = tk.StringVar(value="No active session.")
        tk.Label(card, textvariable=self.file_status, bg=self.theme["card"],
                 fg=self.theme["fg"], font=("Segoe UI", 10)).pack(anchor="w", pady=6)
        self._btn(card, "Send a file… (requires active session)",
                  self._send_file_note, "teal").pack(anchor="w")

    def _build_trusted(self):
        page = self.pages["Trusted Devices"]
        self.trusted_list = tk.Listbox(page, relief="flat", font=("Segoe UI", 10))
        self._role(self.trusted_list, "listbox")
        self.trusted_list.pack(fill="both", expand=True, pady=(0, 8))
        row = self._role(tk.Frame(page, bg=self.theme["bg"]), "bg")
        row.pack(fill="x")
        self._btn(row, "Remove selected (revoke)", self._remove_trusted,
                  "danger").pack(side="left")

    def _build_history(self):
        page = self.pages["History"]
        self.history_box = tk.Text(page, relief="flat", font=("Consolas", 9))
        self._role(self.history_box, "text")
        self.history_box.pack(fill="both", expand=True)
        self.history_box.configure(state="disabled")

    def _build_security(self):
        page = self.pages["Security"]
        body = self._scrollable(page)
        card = self._card(body, "Unattended access (opt-in)")
        self._lbl(card, "Unattended access lets YOU connect to this PC without "
                  "someone clicking Accept. It is OFF by default.\n"
                  "Enable it only on your own devices. You can disable or change the "
                  "password at any time.", muted=True, wrap=660).pack(anchor="w")
        self.unattended_var = tk.BooleanVar(value=bool(self.settings.get("unattended_enabled")))
        cb = tk.Checkbutton(card, text="Enable unattended access on this device",
                            variable=self.unattended_var, font=("Segoe UI", 10))
        self._role(cb, "check_card")
        cb.pack(anchor="w", pady=6)
        row = self._role(tk.Frame(card, bg=self.theme["card"]), "card")
        row.pack(fill="x")
        self._lbl(row, "New unattended password (min 10 chars):").pack(side="left")
        self.unattended_pw = self._entry(row, width=28, show="•")
        self.unattended_pw.pack(side="left", padx=6)
        self.unattended_ctrl = tk.BooleanVar(value=bool(self.settings.get("unattended_allow_control")))
        cb2 = tk.Checkbutton(card, text="Allow mouse/keyboard control in unattended sessions",
                             variable=self.unattended_ctrl, font=("Segoe UI", 10))
        self._role(cb2, "check_card")
        cb2.pack(anchor="w", pady=6)
        self._btn(card, "Save unattended settings", self._save_unattended, "gold").pack(anchor="w")
        card2 = self._card(body, "Session safety")
        self._lbl(card2, "During any session, the host can end it instantly with "
                  "Disconnect. Control permission can be revoked mid-session.",
                  muted=True, wrap=660).pack(anchor="w")
        self._btn(card2, "End active session now", self._disconnect, "danger").pack(anchor="w", pady=6)

    def _build_diag(self):
        page = self.pages["Diagnostics"]
        card = self._card(page, "Network diagnostics")
        self.diag_box = tk.Text(card, height=12, relief="flat", font=("Consolas", 9))
        self._role(self.diag_box, "text")
        self.diag_box.pack(fill="both", expand=True)
        self.diag_box.configure(state="disabled")
        self._btn(card, "Run diagnostics", self._run_diag, "teal").pack(anchor="w", pady=6)

    def _build_about(self):
        page = self.pages["Settings & About"]
        body = self._scrollable(page)
        card = self._card(body, "Settings")
        row = self._role(tk.Frame(card, bg=self.theme["card"]), "card")
        row.pack(fill="x")
        self._lbl(row, "Download folder for received files:").pack(side="left")
        self.download_dir_var = tk.StringVar(value=self.settings.get("download_dir", ""))
        dl = self._entry(row, width=40)
        dl.configure(textvariable=self.download_dir_var)
        dl.pack(side="left", padx=6)
        self._btn(row, "Browse…", self._pick_download_dir, "ghost").pack(side="left")
        self.clipboard_var = tk.BooleanVar(value=bool(self.settings.get("clipboard_sync")))
        cb = tk.Checkbutton(card, text="Enable clipboard sync (optional, off by default)",
                            variable=self.clipboard_var, font=("Segoe UI", 10))
        self._role(cb, "check_card")
        cb.pack(anchor="w", pady=8)
        self._btn(card, "Save settings", self._save_general, "gold").pack(anchor="w")
        card2 = self._card(body, "Updates")
        self._lbl(card2, "Updates come from GitHub Releases — no server needed. "
                  "When a new version is published, this app shows a popup and "
                  "downloads the installer inside the app (no browser redirect).",
                  muted=True, wrap=660).pack(anchor="w")
        self._btn(card2, "Check for Updates now", self._manual_update_check,
                  "teal").pack(anchor="w", pady=6)
        card3 = self._card(body, "About")
        self._lbl(card3, f"{config.PRODUCT_NAME} v{VERSION}\n{config.DEVELOPER_CREDIT}\n\n{config.ABOUT_TEXT}",
                  wrap=660).pack(anchor="w")

    # ------------------------------------------------------------- actions
    def _log(self, msg: str):
        self.msg_queue.put(("log", msg))

    def _pump_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self.log_box.configure(state="normal")
                    self.log_box.insert("end", payload + "\n")
                    self.log_box.see("end")
                    self.log_box.configure(state="disabled")
                elif kind == "banner":
                    if payload:
                        self.banner.pack(fill="x", padx=0, pady=(0, 8),
                                         before=self.pages[self._current_page])
                    else:
                        self.banner.pack_forget()
                    self._refresh_pill()
                elif kind == "status":
                    self.status_var.set(payload)
                    self._refresh_pill()
                elif kind == "request":
                    self._show_request_dialog(payload)
                elif kind == "update":
                    self._show_update_popup(payload)
                elif kind == "viewer_status":
                    self.viewer_status.set(payload)
                elif kind == "update_progress":
                    self._on_update_progress(*payload)
                elif kind == "update_done":
                    self._on_update_done(*payload)
                elif kind == "show_page":
                    self._show_page(payload)
        except queue.Empty:
            pass
        self.root.after(200, self._pump_queue)

    def _toggle_theme(self):
        # Immediate switch — no restart needed.
        self.settings["theme"] = "light" if self.settings.get("theme") != "light" else "dark"
        self.theme = VIP_LIGHT if self.settings["theme"] == "light" else VIP_DARK
        storage.save_settings(self.settings)
        self._apply_theme()

    def _toggle_hosting(self):
        if self.host is not None:
            self.host.stop()
            self.host = None
            self.host_btn.configure(text="▶  Start Hosting — allow connections")
            self.msg_queue.put(("status", "Hosting stopped."))
            self.msg_queue.put(("banner", False))
            self._log("Hosting stopped.")
            self._refresh_pill()
            return
        self.host = HostServer(self.device_id, self.device_name,
                               int(self.settings.get("port", config.DEFAULT_PORT)),
                               self.settings, on_request=self._queue_request,
                               on_log=self._log)
        self.host.start()
        self._new_pairing_code()
        self.host_btn.configure(text="■  Stop Hosting")
        self.msg_queue.put(("status", "Hosting ON — waiting for connection requests."))
        self._refresh_pill()

    def _new_pairing_code(self):
        if self.host is None:
            messagebox.showinfo("Pairing code", "Start hosting first.")
            return
        code = self.host.pairing.issue()
        self.pairing_var.set(f"Pairing code: {code}  (expires in 5 minutes, single use)")
        self._log("New pairing code generated (code itself is never logged).")

    def _queue_request(self, peer: dict):
        """Called from host thread — hand the decision to the UI thread."""
        result: dict = {}
        self.msg_queue.put(("request", (peer, result)))
        while "accept" not in result:
            threading.Event().wait(0.1)
        return result["accept"], result["control"], result["files"]

    def _show_request_dialog(self, data):
        peer, result = data
        t = self.theme
        dlg = tk.Toplevel(self.root)
        dlg.title("Incoming connection request")
        dlg.geometry("480x300")
        dlg.configure(bg=t["card"])
        dlg.transient(self.root)
        dlg.grab_set()
        tk.Label(dlg, text="Incoming remote connection request",
                 font=("Segoe UI", 13, "bold"), bg=t["card"], fg=t["fg"]).pack(
                     padx=18, pady=(14, 4), anchor="w")
        tk.Label(dlg, text=f"Device: {peer.get('device_name')}  (ID {peer.get('device_id')})\n"
                 f"IP: {peer.get('ip')}\n\n"
                 "Only accept if you know and trust this person.",
                 bg=t["card"], fg=t["muted"], font=("Segoe UI", 10),
                 wraplength=430, justify="left").pack(padx=18, anchor="w")
        ctrl = tk.BooleanVar(value=False)
        files = tk.BooleanVar(value=False)
        tk.Checkbutton(dlg, text="Allow mouse/keyboard control", variable=ctrl,
                       bg=t["card"], fg=t["fg"], selectcolor=t["card"],
                       activebackground=t["card"], font=("Segoe UI", 10)).pack(
                           anchor="w", padx=18, pady=(10, 0))
        tk.Checkbutton(dlg, text="Allow file transfer", variable=files,
                       bg=t["card"], fg=t["fg"], selectcolor=t["card"],
                       activebackground=t["card"], font=("Segoe UI", 10)).pack(
                           anchor="w", padx=18)
        btns = tk.Frame(dlg, bg=t["card"])
        btns.pack(pady=16)

        def answer(accept):
            result["accept"] = accept
            result["control"] = bool(ctrl.get()) if accept else False
            result["files"] = bool(files.get()) if accept else False
            dlg.destroy()
            if accept:
                self.msg_queue.put(("banner", True))
                self.msg_queue.put(("status", f"Session active with {peer.get('device_name')}."))
                self._log(f"Accepted session from {peer.get('device_name')}.")
            else:
                self._log("Rejected incoming connection request.")

        tk.Button(btns, text="✓  Accept", bg=t["accent"], fg=t["accent_fg"],
                  relief="flat", font=("Segoe UI", 10, "bold"), padx=16, pady=6,
                  command=lambda: answer(True)).pack(side="left", padx=6)
        tk.Button(btns, text="✕  Reject", bg=t["danger"], fg="#FFFFFF",
                  relief="flat", font=("Segoe UI", 10, "bold"), padx=16, pady=6,
                  command=lambda: answer(False)).pack(side="left", padx=6)
        self.root.wait_window(dlg)

    def _connect(self):
        host = self.connect_host.get().strip()
        try:
            port = int(self.connect_port.get().strip())
        except ValueError:
            messagebox.showerror("Connect", "Port must be a number.")
            return
        code = self.connect_code.get().strip()
        if not host:
            messagebox.showerror("Connect", "Enter the host IP / address.")
            return
        self._log(f"Connecting to {host}:{port} …")
        threading.Thread(target=self._connect_thread,
                         args=(host, port, code), daemon=True).start()

    def _connect_thread(self, host, port, code):
        if self.use_unattended.get():
            ok, msg = self.client.connect(host, port, unattended_password=code)
        else:
            ok, msg = self.client.connect(host, port, pairing_code=code)
        if ok:
            self.msg_queue.put(("viewer_status", f"Connected to {host}:{port}."))
            self.msg_queue.put(("status", f"Connected to {host}:{port}."))
            self.msg_queue.put(("show_page", "Viewer"))
        else:
            self.msg_queue.put(("viewer_status", f"Connection failed: {msg}"))
            self.msg_queue.put(("status", f"Connection failed: {msg}"))
            self._log(f"Connection failed: {msg}")

    def _disconnect(self):
        if self.client.connected:
            self.client.disconnect()
        if self.host is not None:
            self.host.sessions.end_active("ended")
            self.msg_queue.put(("banner", False))
        self.msg_queue.put(("status", "Disconnected."))
        self.msg_queue.put(("viewer_status", "Not connected."))
        self._refresh_pill()

    def _on_client_disconnect(self, reason: str):
        self.msg_queue.put(("viewer_status", f"Disconnected: {reason}"))
        self.msg_queue.put(("status", f"Disconnected: {reason}"))

    def _on_frame(self, jpeg: bytes):
        try:
            from PIL import Image, ImageTk
            img = Image.open(io.BytesIO(jpeg))
            w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
            if w > 10 and h > 10:
                img.thumbnail((w, h))
            self.viewer_photo = ImageTk.PhotoImage(img)
            self.canvas.delete("all")
            self.canvas.create_image(w // 2, h // 2, image=self.viewer_photo, anchor="center")
        except Exception:
            pass

    def _on_mouse_move(self, event):
        if self.client.connected and self.client.sessions.active.can_control:
            self.client.send_input({"kind": "move", "x": event.x, "y": event.y})

    def _send_click(self, event, pressed: bool):
        if self.client.connected and self.client.sessions.active.can_control:
            self.client.send_input({"kind": "click", "button": "left", "pressed": pressed,
                                    "x": event.x, "y": event.y})

    def _on_scroll(self, event):
        if self.client.connected and self.client.sessions.active.can_control:
            self.client.send_input({"kind": "scroll", "dx": 0,
                                    "dy": 1 if event.delta > 0 else -1})

    def _request_control_note(self):
        messagebox.showinfo("Control",
                            "Control permission is granted by the HOST when they "
                            "accept your request (or via unattended settings). "
                            "There is no way to take control without host permission.")

    def _send_file_note(self):
        messagebox.showinfo("File transfer",
                            "File transfer runs over the active session and requires "
                            "host permission. Connect first, then use this tab.")

    def _scan_lan(self):
        self._log("Scanning LAN for devices (5 seconds)…")
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        found = DiscoveryListener(duration_s=5.0).scan()
        if not found:
            self._log("LAN scan: no devices found. (Hosts must have hosting ON; "
                      "some Wi-Fi networks block broadcasts.)")
            return
        for did, info in found.items():
            self._log(f"Found: {info.get('device_name')} (ID {did}) at {info.get('address')}")
            self.msg_queue.put(("status", f"Found {info.get('device_name')} at {info.get('address')}."))

    def _refresh_trusted(self):
        self.trusted_list.delete(0, "end")
        for d in storage.load_trusted():
            self.trusted_list.insert("end", f"{d.get('device_name')} — ID {d.get('device_id')}")

    def _remove_trusted(self):
        sel = self.trusted_list.curselection()
        if not sel:
            return
        text = self.trusted_list.get(sel[0])
        did = text.rsplit("ID ", 1)[-1].strip()
        storage.remove_trusted(did)
        self._refresh_trusted()
        self._log(f"Revoked trusted device {did}.")

    def _refresh_history(self):
        self.history_box.configure(state="normal")
        self.history_box.delete("1.0", "end")
        for entry in storage.load_history():
            self.history_box.insert("end", str(entry) + "\n")
        if not storage.load_history():
            self.history_box.insert("end", "No sessions recorded yet.\n")
        self.history_box.configure(state="disabled")

    def _save_unattended(self):
        pw = self.unattended_pw.get()
        enabled = self.unattended_var.get()
        if enabled:
            if not pw:
                messagebox.showerror("Unattended", "Enter a new password to enable unattended access.")
                return
            ok, reason = validate_unattended_password(pw)
            if not ok:
                messagebox.showerror("Unattended", reason)
                return
            self.settings["unattended_password_hash"] = hash_password(pw)
        self.settings["unattended_enabled"] = enabled
        self.settings["unattended_allow_control"] = self.unattended_ctrl.get()
        storage.save_settings(self.settings)
        self.unattended_pw.delete(0, "end")
        messagebox.showinfo("Unattended", "Unattended settings saved. Password is stored as a hash only.")
        self._log("Unattended settings updated.")

    def _pick_download_dir(self):
        folder = filedialog.askdirectory()
        if folder:
            self.download_dir_var.set(folder)

    def _save_general(self):
        self.settings["download_dir"] = self.download_dir_var.get().strip() or config.default_download_dir()
        self.settings["clipboard_sync"] = self.clipboard_var.get()
        storage.save_settings(self.settings)
        messagebox.showinfo("Settings", "Settings saved.")
        self._log("General settings saved.")

    def _run_diag(self):
        self.diag_box.configure(state="normal")
        self.diag_box.delete("1.0", "end")
        from .screen import capture_available
        from .input_control import input_available
        lines = [
            f"Product: {config.PRODUCT_NAME} v{VERSION}",
            f"Device ID: {self.device_id} ({self.device_name})",
            f"Port: {self.settings.get('port', config.DEFAULT_PORT)}",
            f"Screen capture available: {capture_available()}",
            f"Input control available: {input_available()}",
            f"Hosting: {'ON' if self.host else 'OFF'}",
            f"Session active: {bool(self.client.connected or (self.host and self.host.sessions.active))}",
            "Internet relay: NOT included in this build (LAN direct only).",
            "See docs/TROUBLESHOOTING.md if a connection fails.",
        ]
        self.diag_box.insert("end", "\n".join(lines) + "\n")
        self.diag_box.configure(state="disabled")

    # ------------------------------------------------------------- updates (in-app download)
    def _background_update_check(self):
        release = update_checker.check_for_update()
        if release:
            self.msg_queue.put(("update", release))

    def _manual_update_check(self):
        release = update_checker.check_for_update()
        if release:
            self._show_update_popup(release)
        else:
            messagebox.showinfo("Updates", "You are on the latest version (or update checks "
                                "are not configured yet — see docs/SETUP_UPDATE.md).")

    def _show_update_popup(self, release: dict):
        t = self.theme
        self._download_cancel = threading.Event()
        self._downloaded_path = None
        dlg = tk.Toplevel(self.root)
        dlg.title("Update available")
        dlg.geometry("560x430")
        dlg.configure(bg=t["card"])
        dlg.transient(self.root)
        dlg.grab_set()
        tk.Label(dlg, text=f"✦  New update available: {release['tag']}",
                 font=("Segoe UI", 14, "bold"), bg=t["card"], fg=t["fg"]).pack(
                     padx=18, pady=(14, 4), anchor="w")
        tk.Label(dlg, text=f"You are on v{VERSION}. The installer downloads inside this app — no browser redirect.",
                 bg=t["card"], fg=t["muted"], font=("Segoe UI", 10),
                 wraplength=510, justify="left").pack(padx=18, anchor="w")
        notes = tk.Text(dlg, height=7, relief="flat", font=("Segoe UI", 10),
                        bg=t["entry"], fg=t["fg"])
        notes.pack(padx=18, pady=10, fill="both", expand=True)
        notes.insert("1.0", release.get("notes", "(No changelog provided.)"))
        notes.configure(state="disabled")

        self._upd_progress = ttk.Progressbar(dlg, mode="determinate",
                                             style="VIP.Horizontal.TProgressbar")
        self._upd_progress.pack(padx=18, fill="x", pady=(0, 4))
        self._upd_status = tk.StringVar(value="Ready to download.")
        tk.Label(dlg, textvariable=self._upd_status, bg=t["card"], fg=t["muted"],
                 font=("Segoe UI", 10)).pack(padx=18, anchor="w")
        btns = tk.Frame(dlg, bg=t["card"])
        btns.pack(pady=12)
        self._upd_download_btn = tk.Button(
            btns, text="⬇  Download Update", bg=t["accent"], fg=t["accent_fg"],
            relief="flat", font=("Segoe UI", 10, "bold"), padx=16, pady=6,
            command=lambda: self._start_update_download(release, dlg))
        self._upd_download_btn.pack(side="left", padx=6)
        self._upd_run_btn = tk.Button(
            btns, text="▶  Run Installer", bg=t["teal"], fg=t["teal_fg"],
            relief="flat", font=("Segoe UI", 10, "bold"), padx=16, pady=6,
            state="disabled", command=self._run_downloaded_installer)
        self._upd_run_btn.pack(side="left", padx=6)
        self._upd_fallback_btn = tk.Button(
            btns, text="Open release page", bg=t["card"], fg=t["fg"],
            relief="flat", font=("Segoe UI", 10), padx=12, pady=6,
            command=lambda: webbrowser.open(release["url"]))
        self._upd_fallback_btn.pack(side="left", padx=6)
        self._upd_later_btn = tk.Button(
            btns, text="Later", bg=t["card"], fg=t["fg"],
            relief="flat", font=("Segoe UI", 10), padx=12, pady=6,
            command=lambda: self._close_update_popup(dlg))
        self._upd_later_btn.pack(side="left", padx=6)
        dlg.protocol("WM_DELETE_WINDOW", lambda: self._close_update_popup(dlg))
        self._upd_dialog = dlg
        self._upd_release = release

    def _close_update_popup(self, dlg):
        if self._download_cancel is not None:
            self._download_cancel.set()
        try:
            dlg.destroy()
        except tk.TclError:
            pass

    def _start_update_download(self, release: dict, dlg):
        asset = update_checker.select_setup_asset(release.get("assets"))
        if asset is None:
            self._upd_status.set("No installer file in this release — use the release page instead.")
            return
        self._download_cancel = threading.Event()
        self._upd_download_btn.configure(state="disabled", text="Downloading…")
        self._upd_status.set(f"Downloading {asset['name']} …")
        self._upd_progress.configure(value=0)
        url = asset["download_url"]

        def _thread():
            def _progress(done, total):
                self.msg_queue.put(("update_progress", (done, total)))
            path, error = update_checker.download_update(
                url, progress_callback=_progress,
                cancel_event=self._download_cancel)
            self.msg_queue.put(("update_done", (path, error)))

        threading.Thread(target=_thread, daemon=True).start()

    def _on_update_progress(self, done: int, total: int):
        if not hasattr(self, "_upd_progress"):
            return
        try:
            if total > 0:
                self._upd_progress.configure(maximum=total, value=done)
                pct = int(done * 100 / total)
                mb_done = done / (1024 * 1024)
                mb_total = total / (1024 * 1024)
                self._upd_status.set(f"Downloading… {pct}% ({mb_done:.1f} / {mb_total:.1f} MB)")
            else:
                self._upd_progress.configure(mode="indeterminate")
                try:
                    self._upd_progress.start(10)
                except tk.TclError:
                    pass
                self._upd_status.set(f"Downloading… {done / (1024 * 1024):.1f} MB")
        except tk.TclError:
            pass

    def _on_update_done(self, path, error):
        if not hasattr(self, "_upd_progress"):
            return
        try:
            try:
                self._upd_progress.stop()
            except tk.TclError:
                pass
            self._upd_progress.configure(mode="determinate")
            if error:
                if error == "Download cancelled.":
                    self._upd_status.set("Download cancelled.")
                else:
                    self._upd_status.set(f"{error} — use the release page instead.")
                self._upd_download_btn.configure(state="normal", text="⬇  Retry Download")
                return
            self._downloaded_path = path
            self._upd_progress.configure(value=self._upd_progress.cget("maximum"))
            self._upd_status.set(f"Downloaded: {os.path.basename(path)} — click Run Installer when ready.")
            self._upd_run_btn.configure(state="normal")
            self._upd_download_btn.configure(state="disabled", text="✓  Downloaded")
        except tk.TclError:
            pass

    def _run_downloaded_installer(self):
        """Run the downloaded installer ONLY after the user clicks Run."""
        path = self._downloaded_path
        if not path or not os.path.exists(path):
            messagebox.showerror("Run Installer", "Downloaded installer not found. Download again.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa: S606 — user-clicked, file we just downloaded
            else:
                subprocess.Popen(["xdg-open", path])  # noqa: S603,S607
        except Exception as exc:
            messagebox.showerror("Run Installer", f"Could not launch installer: {exc}")


def run():
    root = tk.Tk()
    RemoteDeskApp(root)
    root.mainloop()
