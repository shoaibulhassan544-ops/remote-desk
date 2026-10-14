"""tkinter UI — blue reference design (v1.0.3).

Layout: left sidebar navigation (Home / Remote Control / Viewer /
File Transfer / Trusted Devices / Session History / Settings) + main
content area with stacked pages. Deep navy dark theme by default,
bright blue (#2E7DFF) primary buttons + active nav. Working Light theme
toggle (instant re-skin, no restart).

Honesty rules (unchanged, enforced):
- Every button is wired to real code, or explicitly disabled with a reason.
- The UI never claims "connected" unless a real session exists.
- Latency shows "—" (the protocol has no round-trip measurement).
- Quality shows real measured frame size + fps from received frames, else "—".
- File SEND is NOT wired in this build: the chooser works, but the Send
  button says so plainly and sends nothing. Receive lists the real
  download folder. No drag-and-drop claim unless tkinterdnd2 imports.
- Two-factor auth: DISABLED toggle with "not implemented in this build".
- Internet mode is direct TCP to a public IP (UPnP / manual port
  forwarding), OR via an optional signaling server (Settings) that
  maps a Device ID to an IP. The signaling server is a directory
  ONLY — no relay, no screen/password ever passes through it.
- A bare 9-digit Device ID in the IP field is BLOCKED, never
  attempted: an ID alone cannot resolve without the signaling
  server (v1.0.4 fix for the "not found on this LAN" bug).
- Incoming requests pop a modal dialog: Accept/Reject + permission
  checkboxes, auto-reject after 60 s of no answer.
- Update popup: in-app download with progress (v1.0.2); browser fallback
  ONLY when no installer asset exists or the download fails.
"""

import io
import os
import platform
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from collections import deque
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import config, connect_target, internet, signaling, storage, update_checker
from .client import RemoteClient
from .device_id import format_device_id, get_device_name, load_or_create_device_id
from .discovery import DiscoveryListener
from .host import HostServer
from .security import PairingCodeStore, hash_password, validate_unattended_password
from .version import VERSION

# Blue reference theme. Dark is the default. NO gold.
BLUE_DARK = {
    "bg": "#0B1220", "sidebar": "#0F1A2E", "header": "#0F1A2E",
    "card": "#13203A", "fg": "#FFFFFF", "muted": "#8CA3C0",
    "accent": "#2E7DFF", "accent_hover": "#2563EB", "accent_fg": "#FFFFFF",
    "success": "#22C55E", "success_fg": "#FFFFFF",
    "danger": "#EF4444", "entry": "#0B1220", "border": "#1E3A5F",
    "sidebar_active": "#2E7DFF", "sidebar_active_fg": "#FFFFFF",
    "sidebar_fg": "#B9C7DD",
}
BLUE_LIGHT = {
    "bg": "#EDF2F9", "sidebar": "#0F1A2E", "header": "#FFFFFF",
    "card": "#FFFFFF", "fg": "#0F172A", "muted": "#5B6B84",
    "accent": "#2563EB", "accent_hover": "#1D4ED8", "accent_fg": "#FFFFFF",
    "success": "#16A34A", "success_fg": "#FFFFFF",
    "danger": "#DC2626", "entry": "#FFFFFF", "border": "#C9D6E8",
    "sidebar_active": "#2E7DFF", "sidebar_active_fg": "#FFFFFF",
    "sidebar_fg": "#C7D2E3",
}

REQUEST_TIMEOUT_S = 60  # incoming-request dialog auto-rejects after this
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-.]*$")


class RemoteDeskApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{config.PRODUCT_NAME} v{VERSION}")
        self.root.geometry("1000x680")
        self.root.minsize(860, 600)
        self.settings = storage.load_settings()
        self.theme = BLUE_LIGHT if self.settings.get("theme") == "light" else BLUE_DARK
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
        self._current_page = "Home"
        self._nav_btns: dict[str, tk.Button] = {}
        self.pages: dict[str, tk.Frame] = {}
        self._download_cancel: threading.Event | None = None
        self._downloaded_path: str | None = None
        self._current_pairing_code: str | None = None
        self._session_start: float | None = None
        self._session_peer = ""
        self._session_host = ""
        self._fullscreen = False
        # Viewer quality: real measured frames only.
        self._frame_times: deque = deque(maxlen=30)
        self._last_frame_size: tuple[int, int] | None = None
        # Shared state vars (one var, labels on several pages).
        self.conn_type_var = tk.StringVar(
            value=self.settings.get("connection_type", "lan"))
        # Signaling server (AnyDesk-style ID lookup). Empty = OFF.
        self.signaling_url_var = tk.StringVar(
            value=self.settings.get("signaling_url", ""))
        self.signaling_auto_var = tk.BooleanVar(
            value=bool(self.settings.get("signaling_auto_register", False)))
        self.signaling_status_var = tk.StringVar(value="Signaling server: OFF (no URL set).")
        self.public_ip_var = tk.StringVar(value="—")
        self.lan_ip_var = tk.StringVar(value="—")
        self.upnp_var = tk.StringVar(value="—")
        self.port_reachable_var = tk.StringVar(value="Not tested yet.")
        self.connect_status_var = tk.StringVar(value="Idle — not connected.")
        self.home_status_var = tk.StringVar(value="Idle")
        self.viewer_status_var = tk.StringVar(
            value="Not connected — connect from Remote Control.")
        self.viewer_quality_var = tk.StringVar(value="Quality: —")
        self._internet_last_fetch = 0.0
        self._set_window_icon()
        self._build()
        self._apply_theme()
        self._show_page("Home")
        self.conn_type_var.trace_add("write", self._on_conn_type_change)
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
            style.configure("Blue.Horizontal.TProgressbar",
                            troughcolor=t["entry"], background=t["accent"],
                            bordercolor=t["border"], lightcolor=t["accent"],
                            darkcolor=t["accent"])
            style.configure("Treeview", background=t["entry"], foreground=t["fg"],
                            fieldbackground=t["entry"], rowheight=24,
                            bordercolor=t["border"])
            style.configure("Treeview.Heading", background=t["card"],
                            foreground=t["fg"], bordercolor=t["border"])
            style.map("Treeview", background=[("selected", t["accent"])],
                      foreground=[("selected", t["accent_fg"])])
            style.configure("TCombobox", fieldbackground=t["entry"],
                            background=t["card"], foreground=t["fg"],
                            arrowcolor=t["fg"], bordercolor=t["border"])
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
            elif role == "primary_btn":
                w.configure(bg=t["accent"], fg=t["accent_fg"],
                            activebackground=t["accent_hover"],
                            activeforeground=t["accent_fg"],
                            highlightbackground=t["accent"])
            elif role == "success_btn":
                w.configure(bg=t["success"], fg=t["success_fg"],
                            activebackground=t["success"],
                            activeforeground=t["success_fg"])
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
                text="☀  Light mode" if self.theme is BLUE_DARK else "🌙  Dark mode")
        if hasattr(self, "theme_toggle_btn"):
            self.theme_toggle_btn.configure(
                text="Switch to Dark mode" if self.theme is BLUE_LIGHT else "Switch to Light mode")
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
            self.status_pill.configure(text="●  Connected", bg=t["success"], fg="#FFFFFF")
            self.home_status_var.set("Connected")
        elif hosting:
            self.status_pill.configure(text="●  Hosting ON", bg=t["accent"], fg=t["accent_fg"])
            self.home_status_var.set("Hosting ON — waiting for connections")
        else:
            self.status_pill.configure(text="○  Idle", bg=t["border"], fg=t["fg"])
            self.home_status_var.set("Idle")

    def _asset_path(self, name: str) -> str:
        """Path to a bundled asset (works from source and from a frozen EXE)."""
        if getattr(sys, "frozen", False):
            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            return os.path.join(base, "assets", name)
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "assets", name)

    def _set_window_icon(self):
        """Window + taskbar icon. Guarded: a missing icon must never break startup."""
        try:
            from PIL import Image, ImageTk
            png = self._asset_path("icon.png")
            if os.path.exists(png):
                img = Image.open(png)
                img.thumbnail((64, 64))
                self._icon_photo = ImageTk.PhotoImage(img)
                self.root.iconphoto(True, self._icon_photo)
            if sys.platform.startswith("win"):
                ico = self._asset_path("icon.ico")
                if os.path.exists(ico):
                    try:
                        self.root.iconbitmap(ico)
                    except tk.TclError:
                        pass
        except Exception:
            pass

    # ------------------------------------------------------------- building
    def _build(self):
        t = self.theme
        body = self._role(tk.Frame(self.root, bg=t["bg"]), "bg")
        body.pack(fill="both", expand=True)
        # ---- sidebar ----
        sidebar = self._role(tk.Frame(body, bg=t["sidebar"], width=200), "sidebar")
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = self._role(tk.Frame(sidebar, bg=t["sidebar"]), "sidebar")
        brand.pack(fill="x", padx=14, pady=(16, 10))
        mark = tk.Label(brand, text="◆", font=("Segoe UI", 20, "bold"),
                        bg=t["sidebar"], fg=t["accent"])
        self._role(mark, "label_sidebar")
        mark.pack(side="left")
        title = tk.Label(brand, text=config.PRODUCT_NAME,
                         font=("Segoe UI", 17, "bold"), bg=t["sidebar"], fg="#FFFFFF")
        title.pack(side="left", padx=(8, 0))
        ver = tk.Label(sidebar, text=f"Version {VERSION}",
                       font=("Segoe UI", 9), bg=t["sidebar"], fg=t["muted"])
        self._role(ver, "muted_sidebar")
        ver.pack(anchor="w", padx=14)
        tk.Frame(sidebar, bg=t["border"], height=1).pack(fill="x", padx=14, pady=10)
        nav_items = [("🏠  Home", "Home"), ("🖥  Remote Control", "Remote Control"),
                     ("👁  Viewer", "Viewer"), ("📁  File Transfer", "File Transfer"),
                     ("✓  Trusted Devices", "Trusted Devices"),
                     ("🕘  Session History", "Session History"),
                     ("⚙  Settings", "Settings")]
        for label, name in nav_items:
            btn = tk.Button(sidebar, text=label, anchor="w", relief="flat",
                            font=("Segoe UI", 11), padx=14, pady=9,
                            command=lambda n=name: self._show_page(n))
            self._role(btn, "nav")
            btn.pack(fill="x", padx=8, pady=2)
            self._nav_btns[name] = btn
        side_bottom = self._role(tk.Frame(sidebar, bg=t["sidebar"]), "sidebar")
        side_bottom.pack(side="bottom", fill="x", padx=14, pady=14)
        self.status_pill = tk.Label(side_bottom, text="○  Idle",
                                    font=("Segoe UI", 10, "bold"), padx=12, pady=4)
        self.status_pill.pack(anchor="w", pady=(0, 8))
        self.theme_btn = tk.Button(side_bottom, text="", command=self._toggle_theme,
                                   relief="flat", padx=12, pady=4, font=("Segoe UI", 10))
        self._role(self.theme_btn, "ghost_btn")
        self.theme_btn.pack(anchor="w")
        foot = tk.Label(side_bottom, text=config.DEVELOPER_CREDIT,
                        font=("Segoe UI", 8), bg=t["sidebar"], fg=t["muted"],
                        justify="left")
        self._role(foot, "muted_sidebar")
        foot.pack(anchor="w", pady=(8, 0))

        content = self._role(tk.Frame(body, bg=t["bg"]), "bg")
        content.pack(side="left", fill="both", expand=True)
        # Persistent remote-session banner (hidden unless a session is active).
        self.banner = tk.Label(content,
                               text="● REMOTE SESSION ACTIVE — someone is connected to this PC",
                               bg=self.theme["danger"], fg="white",
                               font=("Segoe UI", 10, "bold"))
        for name in ["Home", "Remote Control", "Viewer", "File Transfer",
                     "Trusted Devices", "Session History", "Settings"]:
            page = self._role(tk.Frame(content, bg=t["bg"]), "bg")
            self.pages[name] = page
        self._build_home()
        self._build_remote_control()
        self._build_viewer()
        self._build_files()
        self._build_trusted()
        self._build_history()
        self._build_settings()
        self._refresh_trusted()
        self._refresh_history()
        self._refresh_home_history()
        self._refresh_received_files()

    def _show_page(self, name: str):
        self._current_page = name
        for n, page in self.pages.items():
            page.pack_forget()
        self.pages[name].pack(fill="both", expand=True, padx=14, pady=12)
        if name == "Trusted Devices":
            self._refresh_trusted()
        if name == "Session History":
            self._refresh_history()
        if name == "File Transfer":
            self._refresh_received_files()
            self._refresh_file_dest()
        if name == "Home":
            self._refresh_home_history()
        if name in ("Home", "Remote Control") and self.conn_type_var.get() == "internet":
            self._refresh_internet_info()
        if name in ("Home", "Remote Control") and self.conn_type_var.get() == "signaling":
            self._update_signaling_status()
        self._refresh_signaling_blocks()
        self._refresh_nav()

    # ---- widget helpers ----
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

    def _btn(self, parent, text, command, style="primary"):
        role = {"primary": "primary_btn", "success": "success_btn",
                "ghost": "ghost_btn", "danger": "danger_btn"}[style]
        btn = tk.Button(parent, text=text, command=command, relief="flat",
                        font=("Segoe UI", 10, "bold"), padx=14, pady=6,
                        cursor="hand2")
        self._role(btn, role)
        return btn

    def _entry(self, parent, width=24, show=None, textvariable=None):
        t = self.theme
        e = tk.Entry(parent, width=width, show=show or "",
                     textvariable=textvariable,
                     relief="flat", font=("Segoe UI", 10),
                     highlightthickness=1)
        self._role(e, "entry")
        return e

    def _scrollable(self, parent):
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

    # Connection-type options (dropdown — never clipped, wraps at any width).
    CONN_TYPE_LABELS = {
        "lan": "Direct (LAN / Same Network)",
        "internet": "Internet (Direct via Public IP + UPnP)",
        "signaling": "Internet (via Signaling Server — needs server URL)",
    }
    CONN_TYPE_VALUES = ["lan", "internet", "signaling"]

    def _conn_type_combo(self, parent):
        """Full-width dropdown. v1.0.4: radios clipped the 3rd option off-screen."""
        row = self._role(tk.Frame(parent, bg=self.theme["card"]), "card")
        row.pack(fill="x", pady=(0, 6))
        self._lbl(row, "Connection type:").pack(side="left")
        self.conn_type_label_var = tk.StringVar(
            value=self.CONN_TYPE_LABELS.get(self.conn_type_var.get(), "Direct (LAN / Same Network)"))
        combo = ttk.Combobox(row, textvariable=self.conn_type_label_var,
                             state="readonly", width=42,
                             values=[self.CONN_TYPE_LABELS[v] for v in self.CONN_TYPE_VALUES])
        combo.pack(side="left", fill="x", expand=True, padx=(6, 0))

        def _on_select(_event=None):
            label = self.conn_type_label_var.get()
            for value, lbl in self.CONN_TYPE_LABELS.items():
                if lbl == label:
                    self.conn_type_var.set(value)
                    break

        combo.bind("<<ComboboxSelected>>", _on_select)
        return row

    def _conn_type_radios(self, parent):
        # Back-compat alias: old call sites now get the dropdown.
        return self._conn_type_combo(parent)

    def _signaling_block(self, parent):
        """Signaling-server info block; visible only in Signaling mode."""
        t = self.theme
        frame = self._role(tk.Frame(parent, bg=t["card"]), "card")
        self._lbl(frame, "Signaling server — Device ID lookup (AnyDesk-style)",
                  bold=True, size=11).pack(anchor="w")
        tk.Label(frame, textvariable=self.signaling_status_var, bg=t["card"],
                 fg=t["fg"], font=("Segoe UI", 10), wraplength=560,
                 justify="left").pack(anchor="w", pady=(4, 0))
        self._lbl(frame, "Directory ONLY — it maps your Device ID to your IP. "
                  "Screen, input and passwords NEVER pass through it. "
                  "Pairing code + host Accept are still required.",
                  muted=True, wrap=600).pack(anchor="w", pady=(4, 0))
        btns = self._role(tk.Frame(frame, bg=t["card"]), "card")
        btns.pack(fill="x", pady=(8, 2))
        self._btn(btns, "Register this device", self._signaling_register_now,
                  "primary").pack(side="left", padx=(0, 6))
        self._btn(btns, "Settings", lambda: self._show_page("Settings"),
                  "ghost").pack(side="left", padx=6)
        return frame

    def _internet_block(self, parent):
        """Internet-mode info block; visible only when Internet is selected."""
        t = self.theme
        frame = self._role(tk.Frame(parent, bg=t["card"]), "card")
        self._lbl(frame, "Internet mode — direct connection (no relay server)",
                  bold=True, size=11).pack(anchor="w")
        self._lbl(frame, "Public IP:", muted=True).pack(anchor="w", pady=(6, 0))
        tk.Label(frame, textvariable=self.public_ip_var, bg=t["card"],
                 fg=t["fg"], font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self._lbl(frame, "LAN IP (port-forward target):", muted=True).pack(anchor="w", pady=(4, 0))
        tk.Label(frame, textvariable=self.lan_ip_var, bg=t["card"],
                 fg=t["fg"], font=("Segoe UI", 11)).pack(anchor="w")
        self._lbl(frame, "UPnP status:", muted=True).pack(anchor="w", pady=(4, 0))
        tk.Label(frame, textvariable=self.upnp_var, bg=t["card"],
                 fg=t["fg"], font=("Segoe UI", 10), wraplength=560,
                 justify="left").pack(anchor="w")
        btns = self._role(tk.Frame(frame, bg=t["card"]), "card")
        btns.pack(fill="x", pady=(8, 2))
        self._btn(btns, "Open port (UPnP)", self._open_port_upnp, "primary").pack(side="left", padx=(0, 6))
        self._btn(btns, "Refresh", self._refresh_internet_info, "ghost").pack(side="left", padx=6)
        self._btn(btns, "Copy connection details", self._copy_connection_details,
                  "ghost").pack(side="left", padx=6)
        self._lbl(frame, "Give this to the controller: Public IP + Port + Pairing code.",
                  muted=True, wrap=600).pack(anchor="w", pady=(4, 0))
        self._lbl(frame, "Port-forward guide: router → Port Forwarding → TCP "
                  f"{self.settings.get('port', config.DEFAULT_PORT)} → this PC's LAN IP "
                  "(shown above). If UPnP fails and your router is strict / CGNAT, "
                  "a relay server would be needed — not included in this build.",
                  muted=True, wrap=600).pack(anchor="w", pady=(4, 0))
        return frame

    # ------------------------------------------------------------- Home
    def _build_home(self):
        page = self.pages["Home"]
        body = self._scrollable(page)
        self._lbl(body, "Welcome Back!", bold=True, size=20).pack(anchor="w")
        self._lbl(body, "Control your devices from anywhere — securely.",
                  muted=True, size=11).pack(anchor="w", pady=(0, 12))

        top = self._role(tk.Frame(body, bg=self.theme["bg"]), "bg")
        top.pack(fill="x")
        # --- Your Device ID card ---
        id_card = self._role(tk.Frame(top, bg=self.theme["card"], padx=16, pady=12), "card")
        id_card.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self._lbl(id_card, "YOUR DEVICE ID", muted=True, bold=True, size=9).pack(anchor="w")
        id_row = self._role(tk.Frame(id_card, bg=self.theme["card"]), "card")
        id_row.pack(fill="x", pady=(6, 2))
        tk.Label(id_row, text=format_device_id(self.device_id),
                 bg=self.theme["card"], fg=self.theme["fg"],
                 font=("Segoe UI", 20, "bold")).pack(side="left")
        self._btn(id_row, "Copy", self._copy_device_id, "ghost").pack(side="left", padx=10)
        self._lbl(id_card, f"Device: {self.device_name}", muted=True).pack(anchor="w")
        os_label = f"{platform.system()} {platform.release()}"
        self._lbl(id_card, f"OS: {os_label}", muted=True).pack(anchor="w")
        status_row = self._role(tk.Frame(id_card, bg=self.theme["card"]), "card")
        status_row.pack(fill="x", pady=(6, 0))
        self._lbl(status_row, "Status:", muted=True).pack(side="left")
        tk.Label(status_row, textvariable=self.home_status_var,
                 bg=self.theme["card"], fg=self.theme["fg"],
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=6)
        # --- Host this PC card ---
        host_card = self._role(tk.Frame(top, bg=self.theme["card"], padx=16, pady=12), "card")
        host_card.pack(side="left", fill="both", expand=True, padx=(6, 0))
        self._lbl(host_card, "HOST THIS PC", muted=True, bold=True, size=9).pack(anchor="w")
        self.host_btn = self._btn(host_card, "▶  Start Hosting — allow connections",
                                  self._toggle_hosting, "primary")
        self.host_btn.pack(anchor="w", pady=(8, 4))
        self.pairing_var = tk.StringVar(value="Pairing code: — (start hosting to generate)")
        tk.Label(host_card, textvariable=self.pairing_var, bg=self.theme["card"],
                 fg=self.theme["fg"], font=("Segoe UI", 11, "bold"),
                 wraplength=300, justify="left").pack(anchor="w")
        self._btn(host_card, "Generate new pairing code", self._new_pairing_code,
                  "ghost").pack(anchor="w", pady=(6, 2))
        self._lbl(host_card, "Share this code ONLY with the person you want to let in. "
                  "It expires in 5 minutes and works once.", muted=True, wrap=320).pack(anchor="w")
        self._conn_type_radios(host_card)
        self.home_internet = self._internet_block(host_card)
        self.home_signaling = self._signaling_block(host_card)

        # --- Connect to remote (v1.0.4: IP and Device ID are SEPARATE fields.
        # A Device ID alone cannot connect without the signaling server —
        # the old single "Device ID or IP" box lied about that.) ---
        card = self._card(body, "Connect to a remote device")
        grid = self._role(tk.Frame(card, bg=self.theme["card"]), "card")
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)
        self._lbl(grid, "Remote IP address:").grid(row=0, column=0, sticky="w", pady=3)
        self.home_ip = self._entry(grid, width=22)
        self.home_ip.grid(row=0, column=1, sticky="ew", padx=(6, 12), pady=3)
        self._lbl(grid, "Remote Device ID:").grid(row=0, column=2, sticky="w", pady=3)
        self.home_device_id = self._entry(grid, width=16)
        self.home_device_id.grid(row=0, column=3, sticky="ew", padx=(6, 0), pady=3)
        self._lbl(grid, "Pairing code:").grid(row=1, column=0, sticky="w", pady=3)
        self.home_code = self._entry(grid, width=14, show="•")
        self.home_code.grid(row=1, column=1, sticky="ew", padx=(6, 12), pady=3)
        self.home_unattended = tk.BooleanVar(value=False)
        cb = tk.Checkbutton(grid, text="Use unattended", variable=self.home_unattended,
                            font=("Segoe UI", 10))
        self._role(cb, "check_card")
        cb.grid(row=1, column=2, columnspan=2, sticky="w", pady=3)
        self._lbl(grid, "IP required. Device ID is reference-only — it connects "
                  "ONLY via Signaling Server mode (or LAN scan).",
                  muted=True, wrap=640).grid(row=2, column=0, columnspan=4,
                                             sticky="w", pady=(2, 0))
        row2 = self._role(tk.Frame(card, bg=self.theme["card"]), "card")
        row2.pack(fill="x", pady=(8, 0))
        self._btn(row2, "Connect", self._connect_from_home, "primary").pack(side="left", padx=(0, 6))
        self._btn(row2, "Disconnect", self._disconnect, "ghost").pack(side="left", padx=6)
        self._btn(row2, "Find on LAN", self._find_on_lan_home, "ghost").pack(side="left", padx=6)
        tk.Label(card, textvariable=self.connect_status_var, bg=self.theme["card"],
                 fg=self.theme["muted"], font=("Segoe UI", 10),
                 wraplength=640, justify="left").pack(anchor="w", pady=(6, 0))

        # --- Recent sessions ---
        card2 = self._card(body, "Recent sessions")
        self.home_history_box = tk.Text(card2, height=5, relief="flat", font=("Consolas", 9))
        self._role(self.home_history_box, "text")
        self.home_history_box.pack(fill="both", expand=True)
        self.home_history_box.configure(state="disabled")

        # --- Quick actions ---
        card3 = self._card(body, "Quick actions")
        row3 = self._role(tk.Frame(card3, bg=self.theme["card"]), "card")
        row3.pack(fill="x")
        self._btn(row3, "File Transfer", lambda: self._show_page("File Transfer"),
                  "ghost").pack(side="left", padx=(0, 6))
        self._btn(row3, "Trusted Devices", lambda: self._show_page("Trusted Devices"),
                  "ghost").pack(side="left", padx=6)
        self._btn(row3, "Settings", lambda: self._show_page("Settings"),
                  "ghost").pack(side="left", padx=6)

        # --- Activity log ---
        card4 = self._card(body, "Activity log")
        self.log_box = tk.Text(card4, height=7, relief="flat", font=("Consolas", 9))
        self._role(self.log_box, "text")
        self.log_box.pack(fill="both", expand=True)
        self.log_box.configure(state="disabled")
        self._lbl(body, config.DEVELOPER_CREDIT, muted=True).pack(anchor="w")
        self._log("RemoteDesk started. Hosting is OFF until you start it.")

    # ------------------------------------------------------------- Remote Control
    def _build_remote_control(self):
        page = self.pages["Remote Control"]
        body = self._scrollable(page)
        self._lbl(body, "Remote Control", bold=True, size=18).pack(anchor="w")
        self._lbl(body, "Connect to another PC you are allowed to control.",
                  muted=True).pack(anchor="w", pady=(0, 12))

        # Tab row: Quick Connect / Saved Devices
        tab_row = self._role(tk.Frame(body, bg=self.theme["bg"]), "bg")
        tab_row.pack(fill="x", pady=(0, 8))
        self.rc_tab_btns: dict[str, tk.Button] = {}
        for name in ("Quick Connect", "Saved Devices"):
            btn = tk.Button(tab_row, text=name, relief="flat",
                            font=("Segoe UI", 10, "bold"), padx=16, pady=6,
                            command=lambda n=name: self._show_rc_tab(n))
            self._role(btn, "ghost_btn")
            btn.pack(side="left", padx=(0, 6))
            self.rc_tab_btns[name] = btn
        self.rc_tabs: dict[str, tk.Frame] = {}
        for name in ("Quick Connect", "Saved Devices"):
            frame = self._role(tk.Frame(body, bg=self.theme["bg"]), "bg")
            self.rc_tabs[name] = frame

        # --- Quick Connect tab (v1.0.4: split IP + Device ID fields) ---
        quick = self.rc_tabs["Quick Connect"]
        card = self._card(quick, "Quick connect")
        grid = self._role(tk.Frame(card, bg=self.theme["card"]), "card")
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)
        self._lbl(grid, "Remote IP address:").grid(row=0, column=0, sticky="w", pady=3)
        self.connect_host = self._entry(grid, width=22)
        self.connect_host.grid(row=0, column=1, sticky="ew", padx=(6, 12), pady=3)
        self._lbl(grid, "Port:").grid(row=0, column=2, sticky="w", pady=3)
        self.connect_port = self._entry(grid, width=7)
        self.connect_port.grid(row=0, column=3, sticky="w", padx=(6, 0), pady=3)
        self.connect_port.insert(0, str(self.settings.get("port", config.DEFAULT_PORT)))
        self._lbl(grid, "Remote Device ID:").grid(row=1, column=0, sticky="w", pady=3)
        self.connect_device_id = self._entry(grid, width=22)
        self.connect_device_id.grid(row=1, column=1, sticky="ew", padx=(6, 12), pady=3)
        self._lbl(grid, "Pairing code:").grid(row=1, column=2, sticky="w", pady=3)
        self.connect_code = self._entry(grid, width=16, show="•")
        self.connect_code.grid(row=1, column=3, sticky="ew", padx=(6, 0), pady=3)
        row2 = self._role(tk.Frame(card, bg=self.theme["card"]), "card")
        row2.pack(fill="x", pady=8)
        self._lbl(row2, "Pairing code (or unattended password):").pack(side="left")
        self.use_unattended = tk.BooleanVar(value=False)
        cb = tk.Checkbutton(row2, text="Use unattended password",
                            variable=self.use_unattended, font=("Segoe UI", 10))
        self._role(cb, "check_card")
        cb.pack(side="left")
        self._lbl(row2, "IP required. Device ID connects ONLY via Signaling "
                  "Server mode (or LAN scan).",
                  muted=True, wrap=640).pack(side="left", padx=(12, 0))
        self._conn_type_radios(card)
        btns = self._role(tk.Frame(card, bg=self.theme["card"]), "card")
        btns.pack(fill="x")
        self._btn(btns, "Connect", self._connect, "primary").pack(side="left", padx=(0, 6))
        self._btn(btns, "Disconnect", self._disconnect, "ghost").pack(side="left", padx=6)
        self._btn(btns, "Scan LAN for devices", self._scan_lan, "ghost").pack(side="left", padx=6)
        self._btn(btns, "Find on LAN", self._find_on_lan_rc, "ghost").pack(side="left", padx=6)
        tk.Label(card, textvariable=self.connect_status_var, bg=self.theme["card"],
                 fg=self.theme["muted"], font=("Segoe UI", 10),
                 wraplength=640, justify="left").pack(anchor="w", pady=(6, 0))
        self.rc_internet = self._internet_block(quick)
        self.rc_signaling = self._signaling_block(quick)

        # --- Saved Devices tab ---
        saved = self.rc_tabs["Saved Devices"]
        card2 = self._card(saved, "Saved devices (trusted)")
        self._lbl(card2, "Click a saved device to fill the Device ID entry, "
                  "then switch to Quick Connect.", muted=True, wrap=640).pack(anchor="w")
        self.saved_listbox = tk.Listbox(card2, relief="flat", font=("Segoe UI", 10),
                                        height=6)
        self._role(self.saved_listbox, "listbox")
        self.saved_listbox.pack(fill="x", pady=(6, 2))
        self.saved_listbox.bind("<<ListboxSelect>>", self._on_saved_select)
        self._lbl(card2, "Discovered on LAN:", muted=True).pack(anchor="w", pady=(6, 0))
        self.discovered_listbox = tk.Listbox(card2, relief="flat", font=("Segoe UI", 10),
                                             height=4)
        self._role(self.discovered_listbox, "listbox")
        self.discovered_listbox.pack(fill="x", pady=(4, 2))
        self.discovered_listbox.bind("<<ListboxSelect>>", self._on_discovered_select)
        self._btn(card2, "Scan LAN for devices", self._scan_lan, "ghost").pack(anchor="w", pady=(4, 0))
        self._show_rc_tab("Quick Connect")
        self._refresh_internet_blocks()
        self._refresh_signaling_blocks()
        self._update_signaling_status()

    def _show_rc_tab(self, name: str):
        t = self.theme
        for n, frame in self.rc_tabs.items():
            frame.pack_forget()
        self.rc_tabs[name].pack(fill="x")
        for n, btn in self.rc_tab_btns.items():
            if n == name:
                btn.configure(bg=t["accent"], fg=t["accent_fg"],
                              activebackground=t["accent_hover"])
            else:
                btn.configure(bg=t["card"], fg=t["fg"],
                              activebackground=t["border"])

    def _on_saved_select(self, _event=None):
        sel = self.saved_listbox.curselection()
        if not sel:
            return
        text = self.saved_listbox.get(sel[0])
        m = re.search(r"ID\s+([\d ]+)", text)
        if m:
            # Saved devices carry an ID, not an IP — fill the Device ID
            # field (it only connects via Signaling Server / LAN scan).
            self.connect_device_id.delete(0, "end")
            self.connect_device_id.insert(0, m.group(1).strip())
            self._show_rc_tab("Quick Connect")

    def _on_discovered_select(self, _event=None):
        sel = self.discovered_listbox.curselection()
        if not sel:
            return
        text = self.discovered_listbox.get(sel[0])
        m_ip = re.search(r"(\d+\.\d+\.\d+\.\d+)\s*$", text)
        m_id = re.search(r"ID\s+([\d ]+)", text)
        if m_ip:
            self.connect_host.delete(0, "end")
            self.connect_host.insert(0, m_ip.group(1))
        if m_id:
            self.connect_device_id.delete(0, "end")
            self.connect_device_id.insert(0, m_id.group(1).strip())
        self._show_rc_tab("Quick Connect")

    # ------------------------------------------------------------- Viewer
    def _build_viewer(self):
        page = self.pages["Viewer"]
        toolbar = self._role(tk.Frame(page, bg=self.theme["bg"]), "bg")
        toolbar.pack(fill="x", pady=(0, 8))
        tk.Label(toolbar, textvariable=self.viewer_status_var, bg=self.theme["bg"],
                 fg=self.theme["muted"], font=("Segoe UI", 10)).pack(side="left")
        tk.Label(toolbar, textvariable=self.viewer_quality_var, bg=self.theme["bg"],
                 fg=self.theme["muted"], font=("Segoe UI", 10)).pack(side="left", padx=16)
        tk.Label(toolbar, text="Latency: —", bg=self.theme["bg"],
                 fg=self.theme["muted"], font=("Segoe UI", 10)).pack(side="left")
        self._btn(toolbar, "Full-screen", self._toggle_fullscreen, "ghost").pack(side="right", padx=6)
        self._btn(toolbar, "Disconnect", self._disconnect, "danger").pack(side="right", padx=6)
        self._btn(toolbar, "Request control (host must allow)",
                  self._request_control_note, "ghost").pack(side="right", padx=6)
        self.canvas = tk.Canvas(page, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Button-1>", lambda e: self._send_click(e, True))
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._send_click(e, False))
        self.canvas.bind("<MouseWheel>", self._on_scroll)

    def _toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen
        try:
            self.root.attributes("-fullscreen", self._fullscreen)
        except tk.TclError:
            self._fullscreen = False
        if self._fullscreen:
            self.root.bind("<Escape>", lambda _e: self._toggle_fullscreen())

    # ------------------------------------------------------------- File Transfer
    def _build_files(self):
        page = self.pages["File Transfer"]
        self._lbl(page, "File Transfer", bold=True, size=18).pack(anchor="w")
        self._lbl(page, "File transfer needs an active session AND host permission. "
                  "Received files are NEVER executed automatically.",
                  muted=True, wrap=640).pack(anchor="w", pady=(0, 12))
        tab_row = self._role(tk.Frame(page, bg=self.theme["bg"]), "bg")
        tab_row.pack(fill="x", pady=(0, 8))
        self.ft_tab_btns: dict[str, tk.Button] = {}
        for name in ("Send Files", "Receive Files"):
            btn = tk.Button(tab_row, text=name, relief="flat",
                            font=("Segoe UI", 10, "bold"), padx=16, pady=6,
                            command=lambda n=name: self._show_ft_tab(n))
            self._role(btn, "ghost_btn")
            btn.pack(side="left", padx=(0, 6))
            self.ft_tab_btns[name] = btn
        self.ft_tabs: dict[str, tk.Frame] = {}
        for name in ("Send Files", "Receive Files"):
            frame = self._role(tk.Frame(page, bg=self.theme["bg"]), "bg")
            self.ft_tabs[name] = frame

        # --- Send tab ---
        send = self.ft_tabs["Send Files"]
        card = self._card(send, "Send files")
        self._lbl(card, "Drop files here or use Choose Files. Drag-and-drop works "
                  "only if tkinterdnd2 is installed; the chooser always works.",
                  muted=True, wrap=640).pack(anchor="w")
        drop = tk.Label(card, text="Drop files here or use Choose Files",
                        bg=self.theme["entry"], fg=self.theme["muted"],
                        font=("Segoe UI", 11), padx=12, pady=24, relief="flat")
        drop.pack(fill="x", pady=(8, 6))
        self._ft_drop_label = drop
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD  # noqa: F401
            drop.configure(text="Drop files here or use Choose Files (drag & drop available)")
        except ImportError:
            pass  # chooser still works; never claim DnD works
        row = self._role(tk.Frame(card, bg=self.theme["card"]), "card")
        row.pack(fill="x")
        self._btn(row, "Choose Files…", self._choose_send_files, "primary").pack(side="left", padx=(0, 6))
        self._lbl(row, "Destination device:").pack(side="left")
        self.ft_dest = ttk.Combobox(row, state="readonly", width=30)
        self.ft_dest.pack(side="left", padx=6)
        self._btn(row, "Send selected", self._send_files_honest, "ghost").pack(side="left", padx=6)
        self._lbl(card, "Transfer queue:", muted=True).pack(anchor="w", pady=(10, 0))
        self.ft_queue = tk.Listbox(card, relief="flat", font=("Segoe UI", 10), height=5)
        self._role(self.ft_queue, "listbox")
        self.ft_queue.pack(fill="x", pady=(4, 2))
        self._lbl(card, "File send over session is not wired in this build — "
                  "files are not sent. The chooser above only selects files; "
                  "Send reports this honestly and sends nothing.",
                  muted=True, wrap=640).pack(anchor="w")
        self.file_status = tk.StringVar(value="No active session.")
        tk.Label(card, textvariable=self.file_status, bg=self.theme["card"],
                 fg=self.theme["fg"], font=("Segoe UI", 10)).pack(anchor="w", pady=(6, 0))

        # --- Receive tab ---
        recv = self.ft_tabs["Receive Files"]
        card2 = self._card(recv, "Receive files")
        self._lbl(card2, "Received files land here, never auto-executed:",
                  muted=True).pack(anchor="w")
        self.recv_dir_var = tk.StringVar(
            value=self.settings.get("download_dir", config.default_download_dir()))
        tk.Label(card2, textvariable=self.recv_dir_var, bg=self.theme["card"],
                 fg=self.theme["fg"], font=("Segoe UI", 10),
                 wraplength=640, justify="left").pack(anchor="w", pady=(4, 6))
        self._btn(card2, "Open folder", self._open_download_dir, "ghost").pack(anchor="w")
        self._lbl(card2, "Files in this folder:", muted=True).pack(anchor="w", pady=(10, 0))
        self.recv_list = tk.Listbox(card2, relief="flat", font=("Segoe UI", 10), height=6)
        self._role(self.recv_list, "listbox")
        self.recv_list.pack(fill="x", pady=(4, 2))
        self._lbl(card2, "Recent transfers:", muted=True).pack(anchor="w", pady=(8, 0))
        self.transfers_box = tk.Text(card2, height=3, relief="flat", font=("Consolas", 9))
        self._role(self.transfers_box, "text")
        self.transfers_box.pack(fill="x")
        self.transfers_box.configure(state="disabled")
        self._show_ft_tab("Send Files")

    def _show_ft_tab(self, name: str):
        t = self.theme
        for n, frame in self.ft_tabs.items():
            frame.pack_forget()
        self.ft_tabs[name].pack(fill="x")
        for n, btn in self.ft_tab_btns.items():
            if n == name:
                btn.configure(bg=t["accent"], fg=t["accent_fg"],
                              activebackground=t["accent_hover"])
            else:
                btn.configure(bg=t["card"], fg=t["fg"],
                              activebackground=t["border"])

    def _choose_send_files(self):
        paths = filedialog.askopenfilenames(title="Choose files to send")
        for p in paths:
            self.ft_queue.insert("end", f"{os.path.basename(p)} — selected (not sent)")

    def _send_files_honest(self):
        if self.ft_queue.size() == 0:
            messagebox.showinfo("File transfer", "Choose files first.")
            return
        if not self.client.connected:
            messagebox.showinfo("File transfer",
                                "Connect to a device first. File transfer also "
                                "requires the host to allow it for the session.")
            return
        messagebox.showinfo(
            "File transfer",
            "File send over session is not wired in this build — "
            "files are not sent. The file-transfer protocol exists at module "
            "level, but the UI send path is not connected to a live session.")
        for i in range(self.ft_queue.size()):
            text = self.ft_queue.get(i)
            base = text.split(" — ")[0]
            self.ft_queue.delete(i)
            self.ft_queue.insert(i, f"{base} — Not sent (not wired in this build)")

    def _open_download_dir(self):
        folder = self.settings.get("download_dir", config.default_download_dir())
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # noqa: S606 — user-clicked, own folder
            else:
                subprocess.Popen(["xdg-open", folder])  # noqa: S603,S607
        except Exception as exc:
            messagebox.showerror("Open folder", f"Could not open folder: {exc}")

    def _refresh_received_files(self):
        if not hasattr(self, "recv_list"):
            return
        self.recv_list.delete(0, "end")
        folder = self.settings.get("download_dir", config.default_download_dir())
        try:
            entries = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
        except OSError:
            entries = []
        if not entries:
            self.recv_list.insert("end", "(Empty — no received files in this folder.)")
            return
        for name in entries:
            path = os.path.join(folder, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            self.recv_list.insert("end", f"{name} — {size:,} bytes")

    def _refresh_file_dest(self):
        if not hasattr(self, "ft_dest"):
            return
        names = [d.get("device_name", "") for d in storage.load_trusted()
                 if d.get("device_name")]
        for entry in storage.load_history():
            if isinstance(entry, dict) and entry.get("device_name"):
                if entry["device_name"] not in names:
                    names.append(entry["device_name"])
        self.ft_dest["values"] = names or ["(No saved devices yet)"]
        if names:
            self.ft_dest.set(names[0])

    # ------------------------------------------------------------- Trusted Devices
    def _build_trusted(self):
        page = self.pages["Trusted Devices"]
        self._lbl(page, "Trusted Devices", bold=True, size=18).pack(anchor="w")
        self._lbl(page, "Devices allowed to connect without a new pairing code "
                  "(unattended access still needs its password).",
                  muted=True, wrap=640).pack(anchor="w", pady=(0, 12))
        self.trusted_list = tk.Listbox(page, relief="flat", font=("Segoe UI", 10), height=8)
        self._role(self.trusted_list, "listbox")
        self.trusted_list.pack(fill="x", pady=(0, 8))
        row = self._role(tk.Frame(page, bg=self.theme["bg"]), "bg")
        row.pack(fill="x")
        self._btn(row, "Add Device", self._add_trusted_dialog, "primary").pack(side="left", padx=(0, 6))
        self._btn(row, "Rename", self._rename_trusted, "ghost").pack(side="left", padx=6)
        self._btn(row, "Remove (revoke)", self._remove_trusted, "danger").pack(side="left", padx=6)
        card = self._card(page, "Unattended access (opt-in)")
        self._lbl(card, "Unattended access lets YOU connect to this PC without "
                  "someone clicking Accept. It is OFF by default.\n"
                  "Enable it only on your own devices. You can disable or change the "
                  "password at any time.", muted=True, wrap=640).pack(anchor="w")
        self.unattended_var = tk.BooleanVar(value=bool(self.settings.get("unattended_enabled")))
        cb = tk.Checkbutton(card, text="Enable unattended access on this device",
                            variable=self.unattended_var, font=("Segoe UI", 10))
        self._role(cb, "check_card")
        cb.pack(anchor="w", pady=6)
        row2 = self._role(tk.Frame(card, bg=self.theme["card"]), "card")
        row2.pack(fill="x")
        self._lbl(row2, "New unattended password (min 10 chars):").pack(side="left")
        self.unattended_pw = self._entry(row2, width=28, show="•")
        self.unattended_pw.pack(side="left", padx=6)
        self.unattended_ctrl = tk.BooleanVar(value=bool(self.settings.get("unattended_allow_control")))
        cb2 = tk.Checkbutton(card, text="Allow mouse/keyboard control in unattended sessions",
                             variable=self.unattended_ctrl, font=("Segoe UI", 10))
        self._role(cb2, "check_card")
        cb2.pack(anchor="w", pady=6)
        self._btn(card, "Save unattended settings", self._save_unattended, "primary").pack(anchor="w")

    def _add_trusted_dialog(self):
        t = self.theme
        dlg = tk.Toplevel(self.root)
        dlg.title("Add trusted device")
        dlg.geometry("420x220")
        dlg.configure(bg=t["card"])
        dlg.transient(self.root)
        dlg.grab_set()
        tk.Label(dlg, text="Add trusted device", font=("Segoe UI", 13, "bold"),
                 bg=t["card"], fg=t["fg"]).pack(padx=18, pady=(14, 8), anchor="w")
        tk.Label(dlg, text="Device ID (9 digits):", bg=t["card"], fg=t["fg"],
                 font=("Segoe UI", 10)).pack(padx=18, anchor="w")
        id_entry = self._entry(dlg, width=30)
        id_entry.pack(padx=18, anchor="w", pady=(2, 8))
        tk.Label(dlg, text="Device name:", bg=t["card"], fg=t["fg"],
                 font=("Segoe UI", 10)).pack(padx=18, anchor="w")
        name_entry = self._entry(dlg, width=30)
        name_entry.pack(padx=18, anchor="w", pady=(2, 12))

        def _save():
            did = re.sub(r"\D", "", id_entry.get())
            name = name_entry.get().strip()
            if len(did) != 9:
                messagebox.showerror("Add device", "Device ID must be 9 digits.", parent=dlg)
                return
            if not name:
                messagebox.showerror("Add device", "Enter a device name.", parent=dlg)
                return
            storage.add_trusted(did, name)
            self._refresh_trusted()
            self._log(f"Added trusted device {name} (ID {did}).")
            dlg.destroy()

        self._btn(dlg, "Save", _save, "primary").pack(padx=18, anchor="w")

    def _rename_trusted(self):
        sel = self.trusted_list.curselection()
        if not sel:
            messagebox.showinfo("Rename", "Select a device first.")
            return
        text = self.trusted_list.get(sel[0])
        m = re.search(r"ID\s+([\d ]+)", text)
        if not m:
            return
        did = re.sub(r"\D", "", m.group(1))
        old = next((d for d in storage.load_trusted()
                    if re.sub(r"\D", "", d.get("device_id", "")) == did), None)
        if old is None:
            return
        new_name = simpledialog.askstring("Rename device", "New name:",
                                          initialvalue=old.get("device_name", ""))
        if not new_name or not new_name.strip():
            return
        storage.remove_trusted(did)
        storage.add_trusted(did, new_name.strip(), note=old.get("note", ""))
        self._refresh_trusted()
        self._log(f"Renamed trusted device {did} to {new_name.strip()}.")

    # ------------------------------------------------------------- Session History
    def _build_history(self):
        page = self.pages["Session History"]
        self._lbl(page, "Session History", bold=True, size=18).pack(anchor="w")
        self._lbl(page, "Every recorded session on this PC.",
                  muted=True).pack(anchor="w", pady=(0, 12))
        row = self._role(tk.Frame(page, bg=self.theme["bg"]), "bg")
        row.pack(fill="x", pady=(0, 8))
        self._lbl(row, "Search:").pack(side="left")
        self.hist_search_var = tk.StringVar()
        self.hist_search_var.trace_add("write", lambda *_: self._refresh_history())
        search = self._entry(row, width=30, textvariable=self.hist_search_var)
        search.pack(side="left", padx=6)
        self._lbl(row, "Filter:").pack(side="left", padx=(12, 0))
        self.hist_filter_var = tk.StringVar(value="All")
        filt = ttk.Combobox(row, textvariable=self.hist_filter_var, state="readonly",
                            width=18,
                            values=["All", "Remote Control", "File Transfer"])
        filt.pack(side="left", padx=6)
        filt.bind("<<ComboboxSelected>>", lambda _e: self._refresh_history())
        cols = ("Device", "Type", "Duration", "Status", "Date & Time")
        self.history_tree = ttk.Treeview(page, columns=cols, show="headings", height=12)
        for c in cols:
            self.history_tree.heading(c, text=c)
        self.history_tree.column("Device", width=180)
        self.history_tree.column("Type", width=120)
        self.history_tree.column("Duration", width=90)
        self.history_tree.column("Status", width=110)
        self.history_tree.column("Date & Time", width=170)
        self.history_tree.pack(fill="both", expand=True)

    # ------------------------------------------------------------- Settings
    def _build_settings(self):
        page = self.pages["Settings"]
        self._lbl(page, "Settings", bold=True, size=18).pack(anchor="w")
        self._lbl(page, "Security, network, general and about.",
                  muted=True).pack(anchor="w", pady=(0, 12))
        tab_row = self._role(tk.Frame(page, bg=self.theme["bg"]), "bg")
        tab_row.pack(fill="x", pady=(0, 8))
        self.settings_tab_btns: dict[str, tk.Button] = {}
        for name in ("Security", "Network", "General", "About"):
            btn = tk.Button(tab_row, text=name, relief="flat",
                            font=("Segoe UI", 10, "bold"), padx=16, pady=6,
                            command=lambda n=name: self._show_settings_tab(n))
            self._role(btn, "ghost_btn")
            btn.pack(side="left", padx=(0, 6))
            self.settings_tab_btns[name] = btn
        self.settings_tabs: dict[str, tk.Frame] = {}
        for name in ("Security", "Network", "General", "About"):
            frame = self._role(tk.Frame(page, bg=self.theme["bg"]), "bg")
            self.settings_tabs[name] = frame
        self._build_settings_security()
        self._build_settings_network()
        self._build_settings_general()
        self._build_settings_about()
        self._show_settings_tab("Security")

    def _show_settings_tab(self, name: str):
        t = self.theme
        for n, frame in self.settings_tabs.items():
            frame.pack_forget()
        self.settings_tabs[name].pack(fill="both", expand=True)
        for n, btn in self.settings_tab_btns.items():
            if n == name:
                btn.configure(bg=t["accent"], fg=t["accent_fg"],
                              activebackground=t["accent_hover"])
            else:
                btn.configure(bg=t["card"], fg=t["fg"],
                              activebackground=t["border"])

    def _build_settings_security(self):
        tab = self.settings_tabs["Security"]
        body = self._scrollable(tab)
        card = self._card(body, "Access password")
        self._lbl(card, "Change the unattended access password. Stored as a "
                  "salted hash only — never in plain text.", muted=True,
                  wrap=640).pack(anchor="w")
        row = self._role(tk.Frame(card, bg=self.theme["card"]), "card")
        row.pack(fill="x", pady=(8, 0))
        self._lbl(row, "New password (min 10 chars):").pack(side="left")
        self.sec_pw = self._entry(row, width=28, show="•")
        self.sec_pw.pack(side="left", padx=6)
        self._btn(row, "Change Access Password", self._change_access_password,
                  "primary").pack(side="left", padx=6)
        card2 = self._card(body, "Two-factor authentication")
        self.tfa_var = tk.BooleanVar(value=False)
        cb = tk.Checkbutton(card2, text="Enable two-factor authentication",
                            variable=self.tfa_var, state="disabled",
                            font=("Segoe UI", 10))
        self._role(cb, "check_card")
        cb.pack(anchor="w")
        self._lbl(card2, "Two-factor authentication is not implemented in this build. "
                  "The toggle is disabled on purpose — it does not protect "
                  "anything until a real 2FA flow ships.", muted=True,
                  wrap=640).pack(anchor="w", pady=(4, 0))
        card3 = self._card(body, "Session options")
        self.clipboard_var = tk.BooleanVar(value=bool(self.settings.get("clipboard_sync")))
        cb2 = tk.Checkbutton(card3, text="Allow Clipboard Sync",
                             variable=self.clipboard_var, font=("Segoe UI", 10))
        self._role(cb2, "check_card")
        cb2.pack(anchor="w")
        self.ft_enabled_var = tk.BooleanVar(
            value=bool(self.settings.get("file_transfer_enabled", True)))
        cb3 = tk.Checkbutton(card3, text="Enable File Transfer",
                             variable=self.ft_enabled_var, font=("Segoe UI", 10))
        self._role(cb3, "check_card")
        cb3.pack(anchor="w", pady=(4, 0))
        self._lbl(card3, "Disabling File Transfer also disables the file-transfer "
                  "checkbox on incoming requests. Per-session host permission "
                  "is still required when it is enabled.", muted=True,
                  wrap=640).pack(anchor="w", pady=(4, 0))
        self._btn(card3, "Save session options", self._save_security_toggles,
                  "primary").pack(anchor="w", pady=(8, 0))
        card4 = self._card(body, "Session safety")
        self._lbl(card4, "During any session, the host can end it instantly with "
                  "Disconnect. Control permission can be revoked mid-session.",
                  muted=True, wrap=640).pack(anchor="w")
        self._btn(card4, "End active session now", self._disconnect, "danger").pack(anchor="w", pady=6)

    def _build_settings_network(self):
        tab = self.settings_tabs["Network"]
        body = self._scrollable(tab)
        card = self._card(body, "Connection defaults")
        self._conn_type_radios(card)
        row = self._role(tk.Frame(card, bg=self.theme["card"]), "card")
        row.pack(fill="x")
        self._lbl(row, "Port:").pack(side="left")
        self.net_port = self._entry(row, width=8)
        self.net_port.pack(side="left", padx=6)
        self.net_port.insert(0, str(self.settings.get("port", config.DEFAULT_PORT)))
        self._btn(row, "Save network settings", self._save_network, "primary").pack(side="left", padx=6)
        card2 = self._card(body, "Internet (direct) status")
        self._lbl(card2, "Public IP:", muted=True).pack(anchor="w")
        tk.Label(card2, textvariable=self.public_ip_var, bg=self.theme["card"],
                 fg=self.theme["fg"], font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self._lbl(card2, "LAN IP:", muted=True).pack(anchor="w", pady=(4, 0))
        tk.Label(card2, textvariable=self.lan_ip_var, bg=self.theme["card"],
                 fg=self.theme["fg"], font=("Segoe UI", 11)).pack(anchor="w")
        self._lbl(card2, "UPnP status:", muted=True).pack(anchor="w", pady=(4, 0))
        tk.Label(card2, textvariable=self.upnp_var, bg=self.theme["card"],
                 fg=self.theme["fg"], font=("Segoe UI", 10), wraplength=600,
                 justify="left").pack(anchor="w")
        btns = self._role(tk.Frame(card2, bg=self.theme["card"]), "card")
        btns.pack(fill="x", pady=(8, 0))
        self._btn(btns, "Open port (UPnP)", self._open_port_upnp, "primary").pack(side="left", padx=(0, 6))
        self._btn(btns, "Refresh", self._refresh_internet_info, "ghost").pack(side="left", padx=6)
        self._btn(btns, "Test port reachable", self._test_port_reachable, "ghost").pack(side="left", padx=6)
        tk.Label(card2, textvariable=self.port_reachable_var, bg=self.theme["card"],
                 fg=self.theme["muted"], font=("Segoe UI", 10), wraplength=600,
                 justify="left").pack(anchor="w", pady=(6, 0))
        self._lbl(card2, "Internet mode is a direct TCP connection to the host's "
                  "public IP. It works when UPnP succeeds or port forwarding is set; "
                  "strict / CGNAT routers need a relay server (not included).",
                  muted=True, wrap=640).pack(anchor="w", pady=(6, 0))
        card_sig = self._card(body, "Signaling server (Device ID lookup)")
        self._lbl(card_sig, "AnyDesk-style: with a signaling server, controllers "
                  "connect with your Device ID instead of your IP. The server is "
                  "a directory ONLY — screen and passwords never pass through it. "
                  "Without a server, Device IDs cannot resolve; use Direct IP. "
                  "See docs/SIGNALING_DEPLOY.md for free hosting.",
                  muted=True, wrap=640).pack(anchor="w")
        row_sig = self._role(tk.Frame(card_sig, bg=self.theme["card"]), "card")
        row_sig.pack(fill="x", pady=(8, 0))
        self._lbl(row_sig, "Server URL:").pack(side="left")
        self.sig_url_entry = self._entry(row_sig, width=38,
                                         textvariable=self.signaling_url_var)
        self.sig_url_entry.pack(side="left", padx=6)
        cb_sig = tk.Checkbutton(card_sig, text="Register this device when hosting starts",
                                variable=self.signaling_auto_var,
                                font=("Segoe UI", 10))
        self._role(cb_sig, "check_card")
        cb_sig.pack(anchor="w", pady=(8, 0))
        btns_sig = self._role(tk.Frame(card_sig, bg=self.theme["card"]), "card")
        btns_sig.pack(fill="x", pady=(8, 0))
        self._btn(btns_sig, "Save signaling settings", self._save_signaling,
                  "primary").pack(side="left", padx=(0, 6))
        self._btn(btns_sig, "Register now", self._signaling_register_now,
                  "ghost").pack(side="left", padx=6)
        tk.Label(card_sig, textvariable=self.signaling_status_var,
                 bg=self.theme["card"], fg=self.theme["muted"],
                 font=("Segoe UI", 10), wraplength=600,
                 justify="left").pack(anchor="w", pady=(6, 0))
        card3 = self._card(body, "Network diagnostics")
        self.diag_box = tk.Text(card3, height=10, relief="flat", font=("Consolas", 9))
        self._role(self.diag_box, "text")
        self.diag_box.pack(fill="both", expand=True)
        self.diag_box.configure(state="disabled")
        self._btn(card3, "Run diagnostics", self._run_diag, "ghost").pack(anchor="w", pady=6)

    def _build_settings_general(self):
        tab = self.settings_tabs["General"]
        body = self._scrollable(tab)
        card = self._card(body, "General")
        row = self._role(tk.Frame(card, bg=self.theme["card"]), "card")
        row.pack(fill="x")
        self._lbl(row, "Download folder for received files:").pack(side="left")
        self.download_dir_var = tk.StringVar(value=self.settings.get("download_dir", ""))
        dl = self._entry(row, width=40, textvariable=self.download_dir_var)
        dl.pack(side="left", padx=6)
        self._btn(row, "Browse…", self._pick_download_dir, "ghost").pack(side="left")
        self.auto_update_var = tk.BooleanVar(value=bool(self.settings.get("auto_update_check", True)))
        cb = tk.Checkbutton(card, text="Check for updates automatically",
                            variable=self.auto_update_var, font=("Segoe UI", 10))
        self._role(cb, "check_card")
        cb.pack(anchor="w", pady=10)
        self._btn(card, "Save settings", self._save_general, "primary").pack(anchor="w")
        card2 = self._card(body, "Theme")
        self._lbl(card2, "Switch instantly — no restart needed.", muted=True).pack(anchor="w")
        self.theme_toggle_btn = self._btn(card2, "Switch to Light mode",
                                          self._toggle_theme, "ghost")
        self.theme_toggle_btn.pack(anchor="w", pady=(6, 0))

    def _build_settings_about(self):
        tab = self.settings_tabs["About"]
        body = self._scrollable(tab)
        card = self._card(body, "About")
        self._lbl(card, "◆  RemoteDesk", bold=True, size=18).pack(anchor="w")
        self._lbl(card, f"Version {VERSION}", muted=True).pack(anchor="w")
        self._lbl(card, "Connect. Control. Work Anywhere.", bold=True, size=12).pack(anchor="w", pady=(8, 0))
        self._lbl(card, config.DEVELOPER_CREDIT, muted=True).pack(anchor="w", pady=(4, 0))
        self._lbl(card, "Windows 10/11 • Secure & Encrypted", muted=True).pack(anchor="w")
        self._lbl(card, config.ABOUT_TEXT, wrap=640).pack(anchor="w", pady=(8, 0))
        card2 = self._card(body, "Updates")
        self._lbl(card2, "Updates come from GitHub Releases — no server needed. "
                  "When a new version is published, this app shows a popup and "
                  "downloads the installer inside the app (no browser redirect).",
                  muted=True, wrap=640).pack(anchor="w")
        self._btn(card2, "Check for Updates now", self._manual_update_check,
                  "primary").pack(anchor="w", pady=6)

    # ------------------------------------------------------------- actions
    def _log(self, msg: str):
        self.msg_queue.put(("log", msg))

    def _pump_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    if hasattr(self, "log_box"):
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
                    self._refresh_pill()
                elif kind == "connect_status":
                    self.connect_status_var.set(payload)
                elif kind == "request":
                    self._show_request_dialog(payload)
                elif kind == "update":
                    self._show_update_popup(payload)
                elif kind == "viewer_status":
                    self.viewer_status_var.set(payload)
                elif kind == "update_progress":
                    self._on_update_progress(*payload)
                elif kind == "update_done":
                    self._on_update_done(*payload)
                elif kind == "show_page":
                    self._show_page(payload)
                elif kind == "discovered":
                    self._show_discovered(payload)
                elif kind == "file_status":
                    self.file_status.set(payload)
        except queue.Empty:
            pass
        self.root.after(200, self._pump_queue)

    def _toggle_theme(self):
        # Immediate switch — no restart needed.
        self.settings["theme"] = "light" if self.settings.get("theme") != "light" else "dark"
        self.theme = BLUE_LIGHT if self.settings["theme"] == "light" else BLUE_DARK
        storage.save_settings(self.settings)
        self._apply_theme()
        if hasattr(self, "theme_toggle_btn"):
            self.theme_toggle_btn.configure(
                text="Switch to Dark mode" if self.theme is BLUE_LIGHT else "Switch to Light mode")

    def _on_conn_type_change(self, *_args):
        value = self.conn_type_var.get()
        if value not in ("lan", "internet", "signaling"):
            return
        self.settings["connection_type"] = value
        storage.save_settings(self.settings)
        self._refresh_internet_blocks()
        self._refresh_signaling_blocks()
        if value == "internet":
            self._refresh_internet_info()
        if value == "signaling":
            self._update_signaling_status()

    def _refresh_internet_blocks(self):
        show = self.conn_type_var.get() == "internet"
        for frame in (getattr(self, "home_internet", None),
                      getattr(self, "rc_internet", None)):
            if frame is None:
                continue
            if show:
                frame.pack(fill="x", pady=(8, 0))
            else:
                frame.pack_forget()

    def _refresh_signaling_blocks(self):
        show = self.conn_type_var.get() == "signaling"
        for frame in (getattr(self, "home_signaling", None),
                      getattr(self, "rc_signaling", None)):
            if frame is None:
                continue
            if show:
                frame.pack(fill="x", pady=(8, 0))
            else:
                frame.pack_forget()

    def _update_signaling_status(self):
        url = (self.settings.get("signaling_url", "") or "").strip()
        if not url:
            self.signaling_status_var.set(
                "Signaling server: OFF (no URL set). Set it in Settings → Network, "
                "or use Direct IP.")
        else:
            self.signaling_status_var.set(
                f"Signaling server: {signaling.normalize_server_url(url)}")

    def _signaling_register_now(self):
        url = (self.settings.get("signaling_url", "") or "").strip()
        if not url:
            messagebox.showinfo(
                "Signaling server",
                "Signaling server URL set nahi hai — Settings → Network me daalo "
                "ya Direct IP use karo.")
            return
        self.signaling_status_var.set("Registering…")

        def _thread():
            ok, msg = signaling.register_device(
                url, self.device_id, self.device_name,
                int(self.settings.get("port", config.DEFAULT_PORT)))
            self.root.after(0, lambda: self._after_signaling_register(ok, msg))

        threading.Thread(target=_thread, daemon=True).start()

    def _after_signaling_register(self, ok, msg):
        try:
            self.signaling_status_var.set(f"Signaling: {msg}")
        except tk.TclError:
            pass
        self._log(f"Signaling register: {msg}")
        if ok:
            messagebox.showinfo("Signaling server", msg)
        else:
            messagebox.showwarning("Signaling server", msg)

    def _refresh_internet_info(self):
        now = time.time()
        if now - self._internet_last_fetch < 5:
            return
        self._internet_last_fetch = now
        self.upnp_var.set("Checking…")

        def _thread():
            public = internet.get_public_ip()
            lan = internet.get_lan_ip()
            upnp = ("miniupnpc available — click “Open port (UPnP)” to map the port."
                    if internet.upnp_available() else
                    "miniupnpc not installed — use manual port forwarding (see guide below).")
            self.root.after(0, lambda: self._set_internet_info(public, lan, upnp))

        threading.Thread(target=_thread, daemon=True).start()

    def _set_internet_info(self, public, lan, upnp):
        try:
            self.public_ip_var.set(public or "— (could not reach ipify)")
            self.lan_ip_var.set(lan or "—")
            self.upnp_var.set(upnp)
        except tk.TclError:
            pass

    def _open_port_upnp(self):
        try:
            port = int(self.settings.get("port", config.DEFAULT_PORT))
        except (TypeError, ValueError):
            port = config.DEFAULT_PORT
        self.upnp_var.set("Trying UPnP…")

        def _thread():
            ok, msg = internet.try_upnp_mapping(port)
            self.root.after(0, lambda: self._after_upnp(ok, msg))

        threading.Thread(target=_thread, daemon=True).start()

    def _after_upnp(self, ok, msg):
        try:
            self.upnp_var.set(msg)
        except tk.TclError:
            pass
        self._log(f"UPnP: {msg}")
        if ok:
            messagebox.showinfo("UPnP", msg)
        else:
            messagebox.showwarning("UPnP", msg)

    def _copy_connection_details(self):
        public = self.public_ip_var.get()
        port = self.settings.get("port", config.DEFAULT_PORT)
        code = self._current_pairing_code or "— (generate a pairing code on the host first)"
        text = f"RemoteDesk — connect with: {public}:{port} + pairing code {code}"
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except tk.TclError:
            pass
        messagebox.showinfo("Connection details", f"Copied:\n{text}")

    def _copy_device_id(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(format_device_id(self.device_id))
        except tk.TclError:
            pass
        self._log("Device ID copied to clipboard.")

    def _test_port_reachable(self):
        self.port_reachable_var.set("Testing…")

        def _thread():
            public = internet.get_public_ip()
            port = self.settings.get("port", config.DEFAULT_PORT)
            ok = internet.check_port_reachable(public, port) if public else False
            if public and ok:
                msg = (f"Port reachable: {public}:{port} answered this self-test.")
            elif public:
                msg = (f"Port NOT proven reachable: {public}:{port} did not answer "
                       "this self-test. Check hosting ON, UPnP / port forwarding, "
                       "and firewall. Note: some routers fail a self-test even "
                       "when forwarding works for outside callers.")
            else:
                msg = "Could not determine public IP — port test not possible."
            self.root.after(0, lambda: self.port_reachable_var.set(msg))

        threading.Thread(target=_thread, daemon=True).start()

    def _toggle_hosting(self):
        if self.host is not None:
            self.host.stop()
            self.host = None
            self.host_btn.configure(text="▶  Start Hosting — allow connections")
            self.msg_queue.put(("banner", False))
            self._log("Hosting stopped.")
            self._refresh_pill()
            # Best-effort unregister from the signaling directory.
            url = (self.settings.get("signaling_url", "") or "").strip()
            if url:
                threading.Thread(target=signaling.unregister_device,
                                 args=(url, self.device_id), daemon=True).start()
            return
        self.host = HostServer(self.device_id, self.device_name,
                               int(self.settings.get("port", config.DEFAULT_PORT)),
                               self.settings, on_request=self._queue_request,
                               on_log=self._log)
        self.host.start()
        self._new_pairing_code()
        self.host_btn.configure(text="■  Stop Hosting")
        self._refresh_pill()
        # Auto-register on the signaling server if the user enabled it.
        if self.settings.get("signaling_auto_register") and \
                (self.settings.get("signaling_url", "") or "").strip():
            self._signaling_register_now()

    def _new_pairing_code(self):
        if self.host is None:
            messagebox.showinfo("Pairing code", "Start hosting first.")
            return
        code = self.host.pairing.issue()
        self._current_pairing_code = code
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
        dlg.geometry("480x340")
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
        view = tk.BooleanVar(value=True)
        ctrl = tk.BooleanVar(value=False)
        files = tk.BooleanVar(value=False)
        tk.Checkbutton(dlg, text="View Screen", variable=view,
                       bg=t["card"], fg=t["fg"], selectcolor=t["card"],
                       activebackground=t["card"], font=("Segoe UI", 10)).pack(
                           anchor="w", padx=18, pady=(10, 0))
        tk.Checkbutton(dlg, text="Control (Mouse & Keyboard)", variable=ctrl,
                       bg=t["card"], fg=t["fg"], selectcolor=t["card"],
                       activebackground=t["card"], font=("Segoe UI", 10)).pack(
                           anchor="w", padx=18)
        files_cb = tk.Checkbutton(dlg, text="File Transfer", variable=files,
                                  bg=t["card"], fg=t["fg"], selectcolor=t["card"],
                                  activebackground=t["card"], font=("Segoe UI", 10))
        files_cb.pack(anchor="w", padx=18)
        if not self.settings.get("file_transfer_enabled", True):
            files_cb.configure(state="disabled")
            tk.Label(dlg, text="File Transfer is disabled in Settings → Security.",
                     bg=t["card"], fg=t["muted"], font=("Segoe UI", 9)).pack(
                         anchor="w", padx=18)
        tk.Label(dlg, text=f"No answer in {REQUEST_TIMEOUT_S}s = auto-reject.",
                 bg=t["card"], fg=t["muted"], font=("Segoe UI", 9)).pack(
                     anchor="w", padx=18, pady=(8, 0))
        btns = tk.Frame(dlg, bg=t["card"])
        btns.pack(pady=16)
        state = {"answered": False}

        def answer(accept):
            if state["answered"]:
                return
            state["answered"] = True
            if accept and not view.get():
                # A session without screen sharing is meaningless — treat
                # an unchecked View Screen as a decline, and say so.
                result["accept"] = False
                result["control"] = False
                result["files"] = False
                self._log("Incoming request declined: host unchecked View Screen.")
            else:
                result["accept"] = accept
                result["control"] = bool(ctrl.get()) if accept else False
                result["files"] = bool(files.get()) if accept else False
            try:
                dlg.destroy()
            except tk.TclError:
                pass
            if accept and view.get():
                self.msg_queue.put(("banner", True))
                self._log(f"Accepted session from {peer.get('device_name')}.")
                self._record_history(str(peer.get("device_name", "")),
                                     str(peer.get("ip", "")), "Remote Control", "Accepted")
            elif not result.get("timeout"):
                self._log("Rejected incoming connection request.")

        def _timeout():
            if state["answered"]:
                return
            state["answered"] = True
            result["accept"] = False
            result["control"] = False
            result["files"] = False
            result["timeout"] = True
            try:
                dlg.destroy()
            except tk.TclError:
                pass
            self._log("Incoming request auto-rejected: no answer within 60 seconds.")

        dlg.after(REQUEST_TIMEOUT_S * 1000, _timeout)
        tk.Button(btns, text="✓  Accept", bg=t["success"], fg="#FFFFFF",
                  relief="flat", font=("Segoe UI", 10, "bold"), padx=16, pady=6,
                  command=lambda: answer(True)).pack(side="left", padx=6)
        tk.Button(btns, text="✕  Decline", bg=t["danger"], fg="#FFFFFF",
                  relief="flat", font=("Segoe UI", 10, "bold"), padx=16, pady=6,
                  command=lambda: answer(False)).pack(side="left", padx=6)
        dlg.protocol("WM_DELETE_WINDOW", lambda: answer(False))
        self.root.wait_window(dlg)
        if "accept" not in result:
            # Dialog closed without an answer (e.g. destroyed externally).
            result["accept"] = False
            result["control"] = False
            result["files"] = False
            self._log("Incoming request closed without an answer — treated as rejected.")

    # ------------------------------------------------------------- connect
    # v1.0.4: IP and Device ID are separate inputs. A bare 9-digit ID in
    # the IP field is BLOCKED (connect_target), never attempted.
    def _connect_from_home(self):
        ip_text = self.home_ip.get().strip()
        did_text = self.home_device_id.get().strip()
        code = self.home_code.get().strip()
        self._start_connect(ip_text, did_text,
                            int(self.settings.get("port", config.DEFAULT_PORT)),
                            code, self.home_unattended.get())

    def _connect(self):
        ip_text = self.connect_host.get().strip()
        did_text = self.connect_device_id.get().strip()
        try:
            port = int(self.connect_port.get().strip())
        except ValueError:
            messagebox.showerror("Connect", "Port must be a number.")
            return
        code = self.connect_code.get().strip()
        self._start_connect(ip_text, did_text, port, code, self.use_unattended.get())

    def _start_connect(self, ip_text: str, device_id_text: str, port: int,
                       code: str, unattended: bool):
        mode = self.conn_type_var.get()
        decision = connect_target.validate_connect_input(
            ip_text, device_id_text, mode,
            self.settings.get("signaling_url", ""))
        if decision["action"] == "error":
            self.connect_status_var.set(decision["error"])
            self._log(f"Connect blocked: {decision['error']}")
            return
        label = ip_text or format_device_id(decision["device_id"])
        self.connect_status_var.set(f"Resolving {label} …")
        self._log(f"Connecting ({mode}) to {label} …")
        threading.Thread(target=self._connect_thread,
                         args=(decision, port, code, unattended, label),
                         daemon=True).start()

    def _resolve_target(self, decision: dict, default_port: int) -> tuple[str, int, str | None]:
        """Resolve a validated decision to (host, port, error).

        - direct: use the IP/hostname as-is.
        - lan_scan: short LAN discovery scan for the Device ID.
        - signaling_lookup: ask the signaling server for the IP.
        Never raises; failures return (\"\", port, error).
        """
        action = decision["action"]
        if action == "direct":
            return decision["host"], decision["port"] or default_port, None
        if action == "lan_scan":
            did = decision["device_id"]
            self.msg_queue.put(("connect_status", f"Resolving {format_device_id(did)} on LAN …"))
            self._log(f"Looking up device {format_device_id(did)} on LAN…")
            found = DiscoveryListener(duration_s=3.0).scan()
            info = found.get(did)
            if info and info.get("address"):
                return info["address"], default_port, None
            return "", default_port, (
                f"Device {format_device_id(did)} not found on this LAN — check hosting "
                "is ON on that PC and both PCs are on the same Wi-Fi, or enter its IP "
                "directly, or use Signaling Server mode (Settings → Network).")
        if action == "signaling_lookup":
            did = decision["device_id"]
            self.msg_queue.put(("connect_status",
                                f"Resolving {format_device_id(did)} via signaling server …"))
            peer, error = signaling.lookup_device(
                self.settings.get("signaling_url", ""), did)
            if error:
                return "", default_port, error
            return peer["ip"], int(peer.get("port", default_port)), None
        return "", default_port, "Connect input samajh nahi aaya."

    def _connect_thread(self, decision, port, code, unattended, label):
        host, resolved_port, error = self._resolve_target(decision, port)
        if error is not None:
            self.msg_queue.put(("connect_status", error))
            self.msg_queue.put(("viewer_status", f"Connection failed: {error}"))
            self._log(f"Connection failed: {error}")
            return
        self.msg_queue.put(("connect_status", f"Connecting to {host}:{resolved_port} …"))
        self.msg_queue.put(("viewer_status", f"Connecting to {host}:{resolved_port} …"))
        self._log(f"Connecting to {host}:{resolved_port} …")
        if unattended:
            ok, msg = self.client.connect(host, resolved_port, unattended_password=code)
        else:
            ok, msg = self.client.connect(host, resolved_port, pairing_code=code)
        if ok:
            self.msg_queue.put(("connect_status", "Waiting for host…"))
            self._session_start = time.time()
            self._session_peer = label
            self._session_host = host
            self._record_history(label, host, "Remote Control", "Connected")
            self.msg_queue.put(("viewer_status", f"Connected to {host}:{resolved_port}."))
            self.msg_queue.put(("connect_status", f"Connected to {host}:{resolved_port}."))
            self.msg_queue.put(("file_status", "Session active."))
            self.msg_queue.put(("show_page", "Viewer"))
        else:
            if "Could not connect" in msg:
                detail = (f"Host not reachable at {host}:{resolved_port} — check hosting ON, "
                          "same Wi-Fi for LAN, Public IP + port mapping for Internet, "
                          f"or signaling registration. ({msg})")
            else:
                detail = msg
            self.msg_queue.put(("viewer_status", f"Connection failed: {detail}"))
            self.msg_queue.put(("connect_status", f"Connection failed: {detail}"))
            self._log(f"Connection failed: {detail}")

    # ------------------------------------------------------------- Find on LAN
    def _find_on_lan_home(self):
        self._find_on_lan_fill(self.home_ip, self.home_device_id)

    def _find_on_lan_rc(self):
        self._find_on_lan_fill(self.connect_host, self.connect_device_id)

    def _find_on_lan_fill(self, ip_entry, id_entry):
        """Scan the LAN, then fill the IP field (chooser if several found)."""
        self.connect_status_var.set("Scanning LAN for devices (5 seconds)…")
        self._log("Find on LAN: scanning (5 seconds)…")

        def _thread():
            found = DiscoveryListener(duration_s=5.0).scan()
            self.root.after(0, lambda: self._after_find_on_lan(found, ip_entry, id_entry))

        threading.Thread(target=_thread, daemon=True).start()

    def _after_find_on_lan(self, found, ip_entry, id_entry):
        if not found:
            self.connect_status_var.set(
                "LAN pe koi device nahi mila — check karo host pe hosting ON hai "
                "aur dono PCs ek hi Wi-Fi pe hain.")
            return
        items = list(found.items())
        if len(items) == 1:
            did, info = items[0]
            self._fill_ip_id(ip_entry, id_entry, info.get("address", ""), did)
            return
        # Several found — let the user pick one.
        dlg = tk.Toplevel(self.root)
        dlg.title("Found on LAN — pick a device")
        dlg.geometry("440x260")
        dlg.configure(bg=self.theme["card"])
        dlg.transient(self.root)
        dlg.grab_set()
        tk.Label(dlg, text="Found on LAN — pick a device",
                 font=("Segoe UI", 12, "bold"), bg=self.theme["card"],
                 fg=self.theme["fg"]).pack(padx=16, pady=(12, 6), anchor="w")
        box = tk.Listbox(dlg, relief="flat", font=("Segoe UI", 10), height=6)
        self._role(box, "listbox")
        box.pack(fill="both", expand=True, padx=16)
        for did, info in items:
            box.insert("end", f"{info.get('device_name')} (ID {format_device_id(did)}) — {info.get('address')}")

        def _pick():
            sel = box.curselection()
            if not sel:
                return
            did, info = items[sel[0]]
            self._fill_ip_id(ip_entry, id_entry, info.get("address", ""), did)
            dlg.destroy()

        self._btn(dlg, "Use this device", _pick, "primary").pack(padx=16, pady=10, anchor="w")

    def _fill_ip_id(self, ip_entry, id_entry, ip, did):
        try:
            ip_entry.delete(0, "end")
            ip_entry.insert(0, ip)
            id_entry.delete(0, "end")
            id_entry.insert(0, format_device_id(did))
        except tk.TclError:
            pass
        self.connect_status_var.set(f"Found device {format_device_id(did)} at {ip} — IP filled in.")
        self._log(f"Find on LAN: filled {format_device_id(did)} at {ip}.")

    def _disconnect(self):
        was_connected = bool(self.client.connected)
        if self.client.connected:
            self.client.disconnect()
        if self.host is not None:
            self.host.sessions.end_active("ended")
            self.msg_queue.put(("banner", False))
        if was_connected and self._session_start is not None:
            duration = time.time() - self._session_start
            self._record_history(self._session_peer, self._session_host,
                                 "Remote Control", "Ended", duration_s=duration)
        self._session_start = None
        self._session_peer = ""
        self._session_host = ""
        self.msg_queue.put(("connect_status", "Disconnected."))
        self.msg_queue.put(("viewer_status", "Not connected — connect from Remote Control."))
        self.msg_queue.put(("file_status", "No active session."))
        self.viewer_quality_var.set("Quality: —")
        self._refresh_pill()

    def _on_client_disconnect(self, reason: str):
        if self._session_start is not None:
            duration = time.time() - self._session_start
            self._record_history(self._session_peer, self._session_host,
                                 "Remote Control", "Ended", duration_s=duration)
            self._session_start = None
        self.msg_queue.put(("viewer_status", f"Disconnected: {reason}"))
        self.msg_queue.put(("connect_status", f"Disconnected: {reason}"))
        self.msg_queue.put(("file_status", "No active session."))
        self.viewer_quality_var.set("Quality: —")

    def _record_history(self, device_name, ip, stype, status, duration_s=None):
        try:
            storage.append_history({
                "device_name": device_name, "ip": ip, "type": stype,
                "status": status, "duration_s": duration_s,
                "timestamp": time.time()})
        except Exception:
            pass
        try:
            self.root.after(0, self._refresh_history)
            self.root.after(0, self._refresh_home_history)
        except tk.TclError:
            pass

    def _on_frame(self, jpeg: bytes):
        try:
            from PIL import Image, ImageTk
            img = Image.open(io.BytesIO(jpeg))
            now = time.time()
            self._frame_times.append(now)
            self._last_frame_size = img.size
            if len(self._frame_times) >= 2:
                span = self._frame_times[-1] - self._frame_times[0]
                fps = (len(self._frame_times) - 1) / span if span > 0 else 0.0
                w, h = img.size
                self.viewer_quality_var.set(f"Quality: {w}×{h} • {fps:.0f} fps")
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

    # ------------------------------------------------------------- scan / lists
    def _scan_lan(self):
        self._log("Scanning LAN for devices (5 seconds)…")
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        found = DiscoveryListener(duration_s=5.0).scan()
        if not found:
            self._log("LAN scan: no devices found. (Hosts must have hosting ON; "
                      "some Wi-Fi networks block broadcasts.)")
            self.msg_queue.put(("discovered", []))
            return
        for did, info in found.items():
            self._log(f"Found: {info.get('device_name')} (ID {did}) at {info.get('address')}")
            self.msg_queue.put(("status", ""))
        self.msg_queue.put(("discovered", found))

    def _show_discovered(self, found):
        if not hasattr(self, "discovered_listbox"):
            return
        self.discovered_listbox.delete(0, "end")
        if not found:
            return
        for did, info in found.items():
            self.discovered_listbox.insert(
                "end", f"{info.get('device_name')} (ID {format_device_id(did)}) — {info.get('address')}")

    def _refresh_trusted(self):
        for lst in (getattr(self, "trusted_list", None),
                    getattr(self, "saved_listbox", None)):
            if lst is None:
                continue
            lst.delete(0, "end")
            for d in storage.load_trusted():
                lst.insert("end", f"● {d.get('device_name')} — ID {format_device_id(d.get('device_id', ''))}")

    def _remove_trusted(self):
        sel = self.trusted_list.curselection()
        if not sel:
            return
        text = self.trusted_list.get(sel[0])
        m = re.search(r"ID\s+([\d ]+)", text)
        if not m:
            return
        did = re.sub(r"\D", "", m.group(1))
        storage.remove_trusted(did)
        self._refresh_trusted()
        self._log(f"Revoked trusted device {did}.")

    # ------------------------------------------------------------- history
    def _format_duration(self, seconds):
        if seconds is None:
            return "—"
        try:
            s = float(seconds)
        except (TypeError, ValueError):
            return "—"
        if s < 60:
            return f"{s:.0f}s"
        return f"{int(s // 60)}m {int(s % 60):02d}s"

    def _history_rows(self):
        rows = []
        for entry in storage.load_history():
            if isinstance(entry, str):
                rows.append({"device_name": entry, "type": "—", "status": "—",
                             "duration_s": None, "timestamp": 0})
                continue
            if not isinstance(entry, dict):
                continue
            rows.append(entry)
        query = self.hist_search_var.get().strip().lower() if hasattr(self, "hist_search_var") else ""
        filt = self.hist_filter_var.get() if hasattr(self, "hist_filter_var") else "All"
        out = []
        for r in rows:
            if query and query not in str(r.get("device_name", "")).lower():
                continue
            if filt != "All" and r.get("type") != filt:
                continue
            out.append(r)
        return out

    def _refresh_history(self):
        if not hasattr(self, "history_tree"):
            return
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        for r in self._history_rows():
            ts = r.get("timestamp") or 0
            when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "—"
            self.history_tree.insert("", "end", values=(
                r.get("device_name", "—"), r.get("type", "—"),
                self._format_duration(r.get("duration_s")),
                r.get("status", "—"), when))
        if not self._history_rows():
            self.history_tree.insert("", "end", values=(
                "No sessions recorded yet.", "", "", "", ""))

    def _refresh_home_history(self):
        if not hasattr(self, "home_history_box"):
            return
        self.home_history_box.configure(state="normal")
        self.home_history_box.delete("1.0", "end")
        rows = list(storage.load_history())[-8:]
        if not rows:
            self.home_history_box.insert("end", "No sessions yet.\n")
        for entry in reversed(rows):
            if isinstance(entry, dict):
                ts = entry.get("timestamp") or 0
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "—"
                self.home_history_box.insert(
                    "end",
                    f"● {entry.get('device_name', '—')} — {entry.get('ip', '—')} — "
                    f"{when} — {entry.get('status', '—')}\n")
            else:
                self.home_history_box.insert("end", str(entry) + "\n")
        self.home_history_box.configure(state="disabled")

    # ------------------------------------------------------------- settings actions
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

    def _change_access_password(self):
        pw = self.sec_pw.get()
        if not pw:
            messagebox.showerror("Access password", "Enter a new password.")
            return
        ok, reason = validate_unattended_password(pw)
        if not ok:
            messagebox.showerror("Access password", reason)
            return
        self.settings["unattended_password_hash"] = hash_password(pw)
        storage.save_settings(self.settings)
        self.sec_pw.delete(0, "end")
        messagebox.showinfo("Access password",
                            "Access password changed. Stored as a hash only.")
        self._log("Access password changed (hash only).")

    def _save_security_toggles(self):
        self.settings["clipboard_sync"] = self.clipboard_var.get()
        self.settings["file_transfer_enabled"] = self.ft_enabled_var.get()
        storage.save_settings(self.settings)
        messagebox.showinfo("Settings", "Session options saved.")
        self._log("Session options saved.")

    def _save_signaling(self):
        url = signaling.normalize_server_url(self.signaling_url_var.get())
        self.settings["signaling_url"] = url
        self.settings["signaling_auto_register"] = bool(self.signaling_auto_var.get())
        storage.save_settings(self.settings)
        self.signaling_url_var.set(url)
        self._update_signaling_status()
        messagebox.showinfo("Signaling server",
                            "Signaling settings saved. Both PCs must use the "
                            "same server URL for Device ID lookup.")
        self._log("Signaling settings saved.")

    def _save_network(self):
        try:
            port = int(self.net_port.get().strip())
        except ValueError:
            messagebox.showerror("Network", "Port must be a number.")
            return
        if not 1 <= port <= 65535:
            messagebox.showerror("Network", "Port must be 1–65535.")
            return
        self.settings["port"] = port
        self.settings["connection_type"] = self.conn_type_var.get()
        storage.save_settings(self.settings)
        messagebox.showinfo("Network", "Network settings saved.")
        self._log(f"Network settings saved (port {port}).")

    def _pick_download_dir(self):
        folder = filedialog.askdirectory()
        if folder:
            self.download_dir_var.set(folder)

    def _save_general(self):
        self.settings["download_dir"] = self.download_dir_var.get().strip() or config.default_download_dir()
        self.settings["auto_update_check"] = self.auto_update_var.get()
        storage.save_settings(self.settings)
        self.recv_dir_var.set(self.settings["download_dir"])
        messagebox.showinfo("Settings", "Settings saved.")
        self._log("General settings saved.")

    def _run_diag(self):
        self.diag_box.configure(state="normal")
        self.diag_box.delete("1.0", "end")
        self.diag_box.insert("end", "Running diagnostics…\n")
        self.diag_box.configure(state="disabled")

        def _thread():
            from .input_control import input_available
            from .screen import capture_available
            lines = [
                f"Product: {config.PRODUCT_NAME} v{VERSION}",
                f"Device ID: {self.device_id} ({self.device_name})",
                f"Port: {self.settings.get('port', config.DEFAULT_PORT)}",
                f"Screen capture available: {capture_available()}",
                f"Input control available: {input_available()}",
                f"Hosting: {'ON' if self.host else 'OFF'}",
                f"Session active: {bool(self.client.connected or (self.host and self.host.sessions.active))}",
                f"Connection type: {self.settings.get('connection_type', 'lan')}",
                f"Public IP: {internet.get_public_ip() or '— (lookup failed)'}",
                f"LAN IP: {internet.get_lan_ip()}",
                f"UPnP: {'miniupnpc available' if internet.upnp_available() else 'miniupnpc not installed'}",
            ]
            public = internet.get_public_ip()
            if public:
                reachable = internet.check_port_reachable(
                    public, self.settings.get("port", config.DEFAULT_PORT))
                lines.append(
                    f"Port reachable self-test ({public}:{self.settings.get('port', config.DEFAULT_PORT)}): "
                    f"{'reachable' if reachable else 'not reachable from this PC'}")
                lines.append("Note: a failed self-test can still mean forwarding works for "
                             "outside callers (some routers block self-tests).")
            lines.append("Internet relay: NOT included in this build (direct TCP only).")
            lines.append("See docs/TROUBLESHOOTING.md if a connection fails.")
            text = "\n".join(lines) + "\n"

            def _show():
                try:
                    self.diag_box.configure(state="normal")
                    self.diag_box.delete("1.0", "end")
                    self.diag_box.insert("end", text)
                    self.diag_box.configure(state="disabled")
                except tk.TclError:
                    pass

            self.root.after(0, _show)

        threading.Thread(target=_thread, daemon=True).start()

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
                                             style="Blue.Horizontal.TProgressbar")
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
            btns, text="▶  Run Installer", bg=t["success"], fg=t["success_fg"],
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
