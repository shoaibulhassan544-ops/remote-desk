"""CustomTkinter UI — FRESH REBUILD v1.0.8 (Option 1 "AnyDesk Blue").

v1.0.7 changed the FLOW but still LOOKED like old flat tkinter (the user
was right — his screenshot proved it: flat rectangles, no card contrast,
no rounded corners, no depth). Root cause: tkinter's native widgets
cannot look modern no matter the colors. This file rebuilds the SAME
app on CustomTkinter: rounded cards, rounded buttons/entries, real
visual separation, CTk dialogs — with ALL v1.0.7 logic/flows intact.

Public entry points (unchanged): RemoteDeskApp(root), run().
Pure helpers kept for tests: format_update_status, scale_coords.

CTk has no equivalent for: tk.Canvas (viewer drawing surface),
ttk.Treeview (history table), tkinter file/message dialogs — those
stay, and are justified here. Everything else is CustomTkinter.

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
- Assisted sessions ALWAYS need host Accept (Accept popup, Control
  defaults ON since v1.0.7). Unattended (password, opt-in) is the only
  no-Accept path.
- Update popup: SMALL, centered, only [Download Update] [Later].
  Download starts immediately in-thread with live progress; on success
  the button becomes [Run Installer] (click-only). The release-page
  link appears ONLY if the download fails.
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

import customtkinter as ctk

from . import config, connect_target, internet, signaling, storage, update_checker
from .client import RemoteClient
from .device_id import format_device_id, get_device_name, load_or_create_device_id
from .discovery import DiscoveryListener
from .host import HostServer
from .security import PairingCodeStore, hash_password, validate_unattended_password
from .version import VERSION

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BLUE_DARK = {
    "bg": "#0B1220", "sidebar": "#0A0F1E", "header": "#0F1A2E",
    "card": "#16263F", "fg": "#FFFFFF", "muted": "#8CA3C0",
    "accent": "#2E7DFF", "accent_hover": "#1D6FE0", "accent_fg": "#FFFFFF",
    "success": "#22C55E", "success_fg": "#FFFFFF",
    "danger": "#EF4444", "entry": "#0B1220", "border": "#22365C",
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


def format_update_status(done: int, total: int, elapsed_s: float) -> str:
    """'Downloading… 4.2 / 21.3 MB (20%) • 1.1 MB/s' (pure, testable)."""
    mb_done = max(done, 0) / (1024 * 1024)
    speed = (done / elapsed_s) if elapsed_s > 0 else 0.0
    speed_txt = f" • {speed / (1024 * 1024):.1f} MB/s" if speed > 0 else ""
    if total > 0:
        pct = int(done * 100 / total) if total else 0
        return (f"Downloading… {mb_done:.1f} / {total / (1024 * 1024):.1f} MB "
                f"({pct}%){speed_txt}")
    return f"Downloading… {mb_done:.1f} MB{speed_txt}"


def scale_coords(x: float, y: float, canvas_w: float, canvas_h: float,
                 host_w: float, host_h: float) -> tuple[int, int]:
    """Map a point on the viewer canvas to host-screen coordinates.

    The viewer shows a thumbnail-scaled image, but old code sent RAW
    canvas x,y as absolute host coords — clicks landed in the wrong
    place whenever canvas size != host screen size. Now the host sends
    its real size with every frame and the UI scales into it.
    Falls back to raw coords when the host size is unknown (0).
    Results are clamped to the host screen bounds. Pure, testable.
    """
    try:
        x, y = float(x), float(y)
        canvas_w, canvas_h = float(canvas_w), float(canvas_h)
        host_w, host_h = float(host_w), float(host_h)
    except (TypeError, ValueError):
        return 0, 0
    if host_w <= 0 or host_h <= 0 or canvas_w <= 0 or canvas_h <= 0:
        return int(x), int(y)
    sx = x * host_w / canvas_w
    sy = y * host_h / canvas_h
    sx = min(max(sx, 0), host_w - 1)
    sy = min(max(sy, 0), host_h - 1)
    return int(sx), int(sy)


def _font(size: int, bold: bool = False):
    return ctk.CTkFont(family="Segoe UI", size=size, weight="bold" if bold else "normal")


class _CTkList(ctk.CTkScrollableFrame):
    """Listbox-like adapter on a CTkScrollableFrame (CTk has no Listbox).

    Exposes the small Listbox API the app uses: insert/delete/get/size/
    curselection/bind("<<ListboxSelect>>"). Rows are clickable buttons;
    clicking selects the row and fires the bound callback.
    """

    def __init__(self, master, height: int = 120, **kwargs):
        super().__init__(master, height=height, corner_radius=10, **kwargs)
        self._rows: list[tuple[ctk.CTkButton, str]] = []
        self._selected: int | None = None
        self._callback = None
        self._fg = kwargs.get("fg_color", "#0B1220")

    def _refresh(self):
        for i, (btn, _text) in enumerate(self._rows):
            if i == self._selected:
                btn.configure(fg_color="#2E7DFF", text_color="#FFFFFF")
            else:
                btn.configure(fg_color="transparent", text_color="#FFFFFF")

    def _click(self, idx: int):
        self._selected = idx
        self._refresh()
        if self._callback is not None:
            try:
                self._callback(None)
            except TypeError:
                self._callback()

    def insert(self, index, text: str):
        btn = ctk.CTkButton(self, text=str(text), anchor="w",
                            fg_color="transparent", text_color="#FFFFFF",
                            hover_color="#22365C", corner_radius=8,
                            font=_font(11))
        if index == "end" or (isinstance(index, int) and index >= len(self._rows)):
            idx = len(self._rows)
            self._rows.append((btn, str(text)))
            btn.configure(command=lambda i=idx: self._click(i))
            btn.pack(fill="x", padx=4, pady=2)
        else:
            idx = int(index)
            self._rows.insert(idx, (btn, str(text)))
            btn.configure(command=lambda i=idx: self._click(i))
            btn.pack(fill="x", padx=4, pady=2)
            for j, (b, _t) in enumerate(self._rows):
                b.configure(command=lambda i=j: self._click(i))
        self._refresh()

    def delete(self, first, last=None):
        if last is None:
            last = first
        if last == "end":
            last = len(self._rows) - 1
        first, last = int(first), int(last)
        for idx in range(last, first - 1, -1):
            if 0 <= idx < len(self._rows):
                self._rows[idx][0].destroy()
                del self._rows[idx]
        if self._selected is not None and self._selected > last:
            self._selected = None
        elif self._selected is not None and first <= self._selected <= last:
            self._selected = None
        for j, (b, _t) in enumerate(self._rows):
            b.configure(command=lambda i=j: self._click(i))
        self._refresh()

    def get(self, index):
        return self._rows[int(index)][1]

    def size(self) -> int:
        return len(self._rows)

    def curselection(self):
        return (self._selected,) if self._selected is not None else ()

    def bind(self, event, callback=None):  # noqa: A003 — Listbox-compatible name
        if event == "<<ListboxSelect>>":
            self._callback = callback
        return None


class RemoteDeskApp:
    def __init__(self, root: ctk.CTk):
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
        self._nav_btns: dict[str, ctk.CTkButton] = {}
        self.pages: dict[str, ctk.CTkFrame] = {}
        self._download_cancel: threading.Event | None = None
        self._downloaded_path: str | None = None
        self._session_start: float | None = None
        self._session_peer = ""
        self._session_host = ""
        self._fullscreen = False
        self._frame_times: deque = deque(maxlen=30)
        self._last_frame_size: tuple[int, int] | None = None
        self._host_screen_size: tuple[int, int] = (0, 0)
        self._got_first_frame = False
        # Shared state vars.
        self.conn_type_var = tk.StringVar(
            value=self.settings.get("connection_type", "lan"))
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
        self.viewer_control_var = tk.StringVar(value="Control: —")
        self._internet_last_fetch = 0.0
        self._set_window_icon()
        self._build()
        self._apply_theme()
        self._show_page("Home")
        self.conn_type_var.trace_add("write", self._on_conn_type_change)
        self.root.after(200, self._pump_queue)
        if self.settings.get("auto_update_check", True):
            threading.Thread(target=self._background_update_check, daemon=True).start()

    # ------------------------------------------------------------- theming
    def _role(self, widget, role: str):
        widget._theme_role = role  # type: ignore[attr-defined]
        return widget

    def _apply_theme(self):
        """Re-skin every CTk widget from the active token set."""
        t = self.theme
        ctk.set_appearance_mode("light" if self.theme is BLUE_LIGHT else "dark")
        try:
            style = ttk.Style(self.root)
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass
            style.configure("Treeview", background=t["entry"], foreground=t["fg"],
                            fieldbackground=t["entry"], rowheight=26,
                            bordercolor=t["border"], font=("Segoe UI", 10))
            style.configure("Treeview.Heading", background=t["card"],
                            foreground=t["fg"], bordercolor=t["border"],
                            font=("Segoe UI", 10, "bold"))
            style.map("Treeview", background=[("selected", t["accent"])],
                      foreground=[("selected", t["accent_fg"])])
        except Exception:
            pass

        def _apply(w):
            role = getattr(w, "_theme_role", None)
            try:
                if isinstance(w, ctk.CTkFrame) or isinstance(w, ctk.CTkScrollableFrame):
                    if role in ("bg", "header"):
                        w.configure(fg_color=t["header"] if role == "header" else t["bg"])
                    elif role == "sidebar":
                        w.configure(fg_color=t["sidebar"])
                    elif role == "card":
                        w.configure(fg_color=t["card"])
                elif isinstance(w, ctk.CTkLabel):
                    if role in ("label_bg", "label_card", "label_sidebar", "label_header"):
                        w.configure(text_color=t["fg"])
                    elif role in ("muted_bg", "muted_card", "muted_sidebar"):
                        w.configure(text_color=t["muted"])
                    elif role == "accent_card":
                        w.configure(text_color=t["accent"])
                elif isinstance(w, ctk.CTkButton):
                    if role == "primary_btn":
                        w.configure(fg_color=t["accent"], hover_color=t["accent_hover"],
                                    text_color=t["accent_fg"])
                    elif role == "success_btn":
                        w.configure(fg_color=t["success"], hover_color=t["success"],
                                    text_color=t["success_fg"])
                    elif role == "ghost_btn":
                        w.configure(fg_color=t["border"], hover_color=t["accent"],
                                    text_color=t["fg"])
                    elif role == "danger_btn":
                        w.configure(fg_color=t["danger"], hover_color=t["danger"],
                                    text_color="#FFFFFF")
                    elif role == "nav":
                        pass
                elif isinstance(w, ctk.CTkEntry):
                    w.configure(fg_color=t["entry"], border_color=t["border"],
                                text_color=t["fg"])
                elif isinstance(w, ctk.CTkTextbox):
                    w.configure(fg_color=t["entry"], border_color=t["border"],
                                text_color=t["fg"])
                elif isinstance(w, (ctk.CTkCheckBox, ctk.CTkSwitch)):
                    w.configure(text_color=t["fg"], fg_color=t["accent"],
                                border_color=t["border"])
                elif isinstance(w, ctk.CTkComboBox):
                    w.configure(fg_color=t["entry"], button_color=t["card"],
                                border_color=t["border"], text_color=t["fg"],
                                dropdown_fg_color=t["card"],
                                dropdown_text_color=t["fg"])
                elif isinstance(w, ctk.CTkProgressBar):
                    w.configure(fg_color=t["entry"], progress_color=t["accent"])
                elif isinstance(w, tk.Canvas):
                    # Only the viewer drawing surface — never CTkScrollableFrame
                    # internals (their canvas is part of the scroll widget).
                    if w is getattr(self, "canvas", None):
                        w.configure(bg="#000000")
            except Exception:
                pass
            try:
                for child in w.winfo_children():
                    _apply(child)
            except Exception:
                pass

        try:
            self.root.configure(fg_color=t["bg"])
        except Exception:
            pass
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
                btn.configure(fg_color=t["sidebar_active"], text_color=t["sidebar_active_fg"],
                              hover_color=t["sidebar_active"])
            else:
                btn.configure(fg_color="transparent", text_color=t["sidebar_fg"],
                              hover_color=t["border"])

    def _refresh_pill(self):
        if not hasattr(self, "status_pill"):
            return
        t = self.theme
        hosting = self.host is not None
        connected = bool(getattr(self.client, "connected", False))
        session_active = bool(self.host and self.host.sessions.active)
        if connected or session_active:
            self.status_pill.configure(text="●  Connected", fg_color=t["success"],
                                       text_color="#FFFFFF")
            self.home_status_var.set("Connected")
        elif hosting:
            self.status_pill.configure(text="●  Hosting ON", fg_color=t["accent"],
                                       text_color=t["accent_fg"])
            self.home_status_var.set("Hosting ON — waiting for connections")
        else:
            self.status_pill.configure(text="○  Idle", fg_color=t["border"],
                                       text_color=t["fg"])
            self.home_status_var.set("Idle")

    def _asset_path(self, name: str) -> str:
        if getattr(sys, "frozen", False):
            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            return os.path.join(base, "assets", name)
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "assets", name)

    def _set_window_icon(self):
        source = "none"
        try:
            from PIL import Image, ImageTk
            img = None
            try:
                import base64
                from .icon_data import ICON_PNG_B64
                img = Image.open(io.BytesIO(base64.b64decode(ICON_PNG_B64)))
                source = "embedded"
            except Exception:
                img = None
            if img is None:
                png = self._asset_path("icon.png")
                if os.path.exists(png):
                    img = Image.open(png)
                    source = "file"
            if img is not None:
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
            source = "none"
        self._log(f"App icon loaded: {source} (if Windows still shows the old icon, "
                  "uninstall the old version + clear the icon cache — see Troubleshooting).")

    # ------------------------------------------------------------- building
    def _build(self):
        t = self.theme
        body = self._role(ctk.CTkFrame(self.root, fg_color=t["bg"], corner_radius=0), "bg")
        body.pack(fill="both", expand=True)
        sidebar = self._role(ctk.CTkFrame(body, fg_color=t["sidebar"], corner_radius=0,
                                          width=210), "sidebar")
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = self._role(ctk.CTkFrame(sidebar, fg_color="transparent"), "sidebar")
        brand.pack(fill="x", padx=16, pady=(18, 6))
        mark = self._role(ctk.CTkLabel(brand, text="◆", font=_font(22, True),
                                       text_color=t["accent"]), "accent_card")
        mark.pack(side="left")
        title = self._role(ctk.CTkLabel(brand, text=config.PRODUCT_NAME,
                                        font=_font(18, True), text_color="#FFFFFF"), "label_sidebar")
        title.pack(side="left", padx=(8, 0))
        ver = self._role(ctk.CTkLabel(sidebar, text=f"Version {VERSION}",
                                      font=_font(10), text_color=t["muted"]), "muted_sidebar")
        ver.pack(anchor="w", padx=16)
        sep = ctk.CTkFrame(sidebar, fg_color=t["border"], height=1, corner_radius=0)
        sep.pack(fill="x", padx=16, pady=12)
        nav_items = [("🏠  Home", "Home"), ("🖥  Remote Control", "Remote Control"),
                     ("👁  Viewer", "Viewer"), ("📁  File Transfer", "File Transfer"),
                     ("✓  Trusted Devices", "Trusted Devices"),
                     ("🕘  Session History", "Session History"),
                     ("⚙  Settings", "Settings")]
        for label, name in nav_items:
            btn = ctk.CTkButton(sidebar, text=label, anchor="w",
                                font=_font(12), corner_radius=10,
                                height=38, fg_color="transparent",
                                text_color=t["sidebar_fg"], hover_color=t["border"],
                                command=lambda n=name: self._show_page(n))
            self._role(btn, "nav")
            btn.pack(fill="x", padx=10, pady=3)
            self._nav_btns[name] = btn
        side_bottom = self._role(ctk.CTkFrame(sidebar, fg_color="transparent"), "sidebar")
        side_bottom.pack(side="bottom", fill="x", padx=16, pady=16)
        self.status_pill = ctk.CTkLabel(side_bottom, text="○  Idle",
                                        font=_font(11, True), corner_radius=10,
                                        fg_color=t["border"], text_color=t["fg"])
        self.status_pill.pack(anchor="w", pady=(0, 10), ipadx=10, ipady=4)
        self.theme_btn = ctk.CTkButton(side_bottom, text="", command=self._toggle_theme,
                                       font=_font(11), corner_radius=10,
                                       fg_color=t["card"], hover_color=t["border"],
                                       text_color=t["fg"])
        self._role(self.theme_btn, "ghost_btn")
        self.theme_btn.pack(anchor="w", fill="x")
        foot = self._role(ctk.CTkLabel(side_bottom, text=config.DEVELOPER_CREDIT,
                                       font=_font(9), text_color=t["muted"]), "muted_sidebar")
        foot.pack(anchor="w", pady=(10, 0))

        content = self._role(ctk.CTkFrame(body, fg_color=t["bg"], corner_radius=0), "bg")
        content.pack(side="left", fill="both", expand=True)
        self.banner = ctk.CTkLabel(content,
                                   text="● REMOTE SESSION ACTIVE — someone is connected to this PC",
                                   fg_color=self.theme["danger"], text_color="white",
                                   font=_font(11, True), corner_radius=0)
        for name in ["Home", "Remote Control", "Viewer", "File Transfer",
                     "Trusted Devices", "Session History", "Settings"]:
            self.pages[name] = self._role(ctk.CTkFrame(content, fg_color=t["bg"],
                                                       corner_radius=0), "bg")
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
        self.pages[name].pack(fill="both", expand=True, padx=20, pady=16)
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

    # ---- widget helpers (all CustomTkinter) ----
    def _card(self, parent, title: str):
        t = self.theme
        frame = self._role(ctk.CTkFrame(parent, fg_color=t["card"], corner_radius=14,
                                        border_width=1, border_color=t["border"]), "card")
        frame.pack(fill="x", pady=(0, 14))
        head = self._role(ctk.CTkFrame(frame, fg_color="transparent"), "card")
        head.pack(fill="x", padx=18, pady=(14, 0))
        title_lbl = self._role(ctk.CTkLabel(head, text=title.upper(), font=_font(11, True),
                                            text_color=t["accent"]), "accent_card")
        title_lbl.pack(anchor="w")
        sep = ctk.CTkFrame(frame, fg_color=t["border"], height=1, corner_radius=0)
        sep.pack(fill="x", padx=18, pady=(8, 12))
        body = self._role(ctk.CTkFrame(frame, fg_color="transparent"), "card")
        body.pack(fill="x", padx=18, pady=(0, 16))
        return body

    def _lbl(self, parent, text, muted=False, bold=False, size=11, wrap=None):
        t = self.theme
        lbl = self._role(ctk.CTkLabel(parent, text=text,
                                      font=_font(size, bold),
                                      text_color=t["muted"] if muted else t["fg"],
                                      wraplength=wrap or 0, justify="left"), "muted_card" if muted else "label_card")
        return lbl

    def _btn(self, parent, text, command, style="primary"):
        t = self.theme
        colors = {
            "primary": (t["accent"], t["accent_hover"], t["accent_fg"]),
            "success": (t["success"], t["success"], t["success_fg"]),
            "ghost": (t["border"], t["accent"], t["fg"]),
            "danger": (t["danger"], t["danger"], "#FFFFFF"),
        }
        fg, hover, txt = colors[style]
        role = {"primary": "primary_btn", "success": "success_btn",
                "ghost": "ghost_btn", "danger": "danger_btn"}[style]
        btn = self._role(ctk.CTkButton(parent, text=text, command=command,
                                       font=_font(11, True), corner_radius=10,
                                       fg_color=fg, hover_color=hover, text_color=txt,
                                       height=34), role)
        return btn

    def _entry(self, parent, width=320, show=None, textvariable=None, placeholder=None):
        t = self.theme
        kwargs: dict = dict(width=width, font=_font(11), corner_radius=10,
                            fg_color=t["entry"], border_color=t["border"],
                            text_color=t["fg"], height=34)
        if show:
            kwargs["show"] = show
        if textvariable is not None:
            kwargs["textvariable"] = textvariable
        if placeholder:
            kwargs["placeholder_text"] = placeholder
        e = self._role(ctk.CTkEntry(parent, **kwargs), "entry")
        return e

    def _check(self, parent, text, variable, command=None, disabled=False):
        t = self.theme
        cb = self._role(ctk.CTkCheckBox(parent, text=text, variable=variable,
                                        font=_font(11), fg_color=t["accent"],
                                        text_color=t["fg"], border_color=t["border"],
                                        corner_radius=6), "check_card")
        if command is not None:
            cb.configure(command=command)
        if disabled:
            cb.configure(state="disabled")
        return cb

    def _switch(self, parent, text, variable, command=None):
        t = self.theme
        sw = self._role(ctk.CTkSwitch(parent, text=text, variable=variable,
                                      font=_font(11), fg_color=t["border"],
                                      progress_color=t["accent"],
                                      text_color=t["fg"]), "check_card")
        if command is not None:
            sw.configure(command=command)
        return sw

    def _combo(self, parent, values, variable=None, command=None, width=320):
        t = self.theme
        kwargs: dict = dict(values=values, font=_font(11), corner_radius=10,
                            fg_color=t["entry"], button_color=t["card"],
                            border_color=t["border"], text_color=t["fg"],
                            dropdown_fg_color=t["card"], dropdown_text_color=t["fg"],
                            width=width)
        if variable is not None:
            kwargs["variable"] = variable
        if command is not None:
            kwargs["command"] = command
        return self._role(ctk.CTkComboBox(parent, **kwargs), "combo")

    def _scrollable(self, parent):
        t = self.theme
        frame = self._role(ctk.CTkScrollableFrame(parent, fg_color=t["bg"],
                                                  corner_radius=0,
                                                  scrollbar_button_color=t["border"]), "bg")
        frame.pack(fill="both", expand=True)
        return frame

    CONN_TYPE_LABELS = {
        "lan": "Direct (LAN / Same Network)",
        "internet": "Internet (Direct via Public IP + UPnP)",
        "signaling": "Internet (via Signaling Server — needs server URL)",
    }
    CONN_TYPE_VALUES = ["lan", "internet", "signaling"]

    def _conn_type_combo(self, parent):
        row = self._role(ctk.CTkFrame(parent, fg_color="transparent"), "card")
        row.pack(fill="x", pady=(0, 6))
        self._lbl(row, "Connection type:").pack(side="left")
        self.conn_type_label_var = tk.StringVar(
            value=self.CONN_TYPE_LABELS.get(self.conn_type_var.get(), "Direct (LAN / Same Network)"))

        def _on_select(_value=None):
            label = self.conn_type_label_var.get()
            for value, lbl in self.CONN_TYPE_LABELS.items():
                if lbl == label:
                    self.conn_type_var.set(value)
                    break

        combo = self._combo(row, [self.CONN_TYPE_LABELS[v] for v in self.CONN_TYPE_VALUES],
                            variable=self.conn_type_label_var, command=_on_select, width=380)
        combo.pack(side="left", fill="x", expand=True, padx=(8, 0))
        return row

    def _conn_type_radios(self, parent):
        return self._conn_type_combo(parent)

    def _signaling_block(self, parent):
        frame = self._role(ctk.CTkFrame(parent, fg_color="transparent"), "card")
        self._lbl(frame, "Signaling server — Device ID lookup (AnyDesk-style)",
                  bold=True, size=12).pack(anchor="w")
        self._role(ctk.CTkLabel(frame, textvariable=self.signaling_status_var,
                                font=_font(11), text_color=self.theme["fg"],
                                wraplength=560, justify="left"), "label_card").pack(
                                    anchor="w", pady=(4, 0))
        self._lbl(frame, "Directory ONLY — it maps your Device ID to your IP. "
                  "Screen, input and passwords NEVER pass through it. "
                  "Host Accept is still required for every assisted session.",
                  muted=True, wrap=600).pack(anchor="w", pady=(4, 0))
        btns = self._role(ctk.CTkFrame(frame, fg_color="transparent"), "card")
        btns.pack(fill="x", pady=(8, 2))
        self._btn(btns, "Register this device", self._signaling_register_now,
                  "primary").pack(side="left", padx=(0, 6))
        self._btn(btns, "Settings", lambda: self._show_page("Settings"),
                  "ghost").pack(side="left", padx=6)
        return frame

    def _internet_block(self, parent):
        frame = self._role(ctk.CTkFrame(parent, fg_color="transparent"), "card")
        self._lbl(frame, "Internet mode — direct connection (no relay server)",
                  bold=True, size=12).pack(anchor="w")
        self._lbl(frame, "Public IP:", muted=True).pack(anchor="w", pady=(6, 0))
        self._role(ctk.CTkLabel(frame, textvariable=self.public_ip_var,
                                font=_font(13, True),
                                text_color=self.theme["fg"]), "label_card").pack(anchor="w")
        self._lbl(frame, "LAN IP (port-forward target):", muted=True).pack(anchor="w", pady=(4, 0))
        self._role(ctk.CTkLabel(frame, textvariable=self.lan_ip_var,
                                font=_font(11),
                                text_color=self.theme["fg"]), "label_card").pack(anchor="w")
        self._lbl(frame, "UPnP status:", muted=True).pack(anchor="w", pady=(4, 0))
        self._role(ctk.CTkLabel(frame, textvariable=self.upnp_var,
                                font=_font(11), wraplength=560,
                                justify="left",
                                text_color=self.theme["fg"]), "label_card").pack(anchor="w")
        btns = self._role(ctk.CTkFrame(frame, fg_color="transparent"), "card")
        btns.pack(fill="x", pady=(8, 2))
        self._btn(btns, "Open port (UPnP)", self._open_port_upnp, "primary").pack(side="left", padx=(0, 6))
        self._btn(btns, "Refresh", self._refresh_internet_info, "ghost").pack(side="left", padx=6)
        self._btn(btns, "Copy connection details", self._copy_connection_details,
                  "ghost").pack(side="left", padx=6)
        self._lbl(frame, "Give this to the controller: Public IP + Port + your Address.",
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
        self._lbl(body, "Welcome Back!", bold=True, size=26).pack(anchor="w")
        self._lbl(body, "Ready to connect or host a remote session — securely.",
                  muted=True, size=12).pack(anchor="w", pady=(0, 16))

        top = self._role(ctk.CTkFrame(body, fg_color="transparent"), "bg")
        top.pack(fill="x")
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)
        id_card = self._role(ctk.CTkFrame(top, fg_color=self.theme["card"], corner_radius=14,
                                          border_width=1, border_color=self.theme["border"]), "card")
        id_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        inner = self._role(ctk.CTkFrame(id_card, fg_color="transparent"), "card")
        inner.pack(fill="both", expand=True, padx=18, pady=16)
        self._lbl(inner, "YOUR ADDRESS", muted=True, bold=True, size=11).pack(anchor="w")
        self._lbl(inner, "Yehi address dusre PC pe likhna hai.",
                  muted=True, size=10).pack(anchor="w")
        id_row = self._role(ctk.CTkFrame(inner, fg_color="transparent"), "card")
        id_row.pack(fill="x", pady=(8, 2))
        self._role(ctk.CTkLabel(id_row, text=format_device_id(self.device_id),
                                font=_font(32, True),
                                text_color=self.theme["fg"]), "label_card").pack(side="left")
        self._btn(id_row, "Copy", self._copy_device_id, "ghost").pack(side="left", padx=12)
        self._lbl(inner, f"Device: {self.device_name}", muted=True).pack(anchor="w")
        os_label = f"{platform.system()} {platform.release()}"
        self._lbl(inner, f"OS: {os_label}", muted=True).pack(anchor="w")
        status_row = self._role(ctk.CTkFrame(inner, fg_color="transparent"), "card")
        status_row.pack(fill="x", pady=(8, 0))
        self._lbl(status_row, "Status:", muted=True).pack(side="left")
        self._role(ctk.CTkLabel(status_row, textvariable=self.home_status_var,
                                font=_font(11, True),
                                text_color=self.theme["fg"]), "label_card").pack(side="left", padx=6)
        ip_row = self._role(ctk.CTkFrame(inner, fg_color="transparent"), "card")
        ip_row.pack(fill="x", pady=(4, 0))
        self._lbl(ip_row, "IP (LAN):", muted=True, size=10).pack(side="left")
        self._role(ctk.CTkLabel(ip_row, textvariable=self.lan_ip_var,
                                font=_font(10), text_color=self.theme["muted"]), "muted_card").pack(
                                    side="left", padx=4)
        self._lbl(ip_row, "•  Public IP (Internet):", muted=True, size=10).pack(side="left")
        self._role(ctk.CTkLabel(ip_row, textvariable=self.public_ip_var,
                                font=_font(10), text_color=self.theme["muted"]), "muted_card").pack(
                                    side="left", padx=4)

        host_card = self._role(ctk.CTkFrame(top, fg_color=self.theme["card"], corner_radius=14,
                                            border_width=1, border_color=self.theme["border"]), "card")
        host_card.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        hinner = self._role(ctk.CTkFrame(host_card, fg_color="transparent"), "card")
        hinner.pack(fill="both", expand=True, padx=18, pady=16)
        self._lbl(hinner, "HOST THIS PC", muted=True, bold=True, size=11).pack(anchor="w")
        self.host_btn = self._btn(hinner, "▶  Start Hosting — allow connections",
                                  self._toggle_hosting, "primary")
        self.host_btn.pack(anchor="w", pady=(10, 6))
        self._lbl(hinner, "Hosting ON hone pe dusra PC tumhara Address likh "
                  "ke connect karega — tumhare paas Accept / Decline ka popup "
                  "aayega. Koi code nahi chahiye.",
                  muted=True, wrap=320).pack(anchor="w", pady=(8, 0))

        card = self._card(body, "Connect to a remote device")
        self._lbl(card, "Remote Address", bold=True).pack(anchor="w")
        self.home_address = self._entry(card, width=520,
                                        placeholder="739 738 074 ya 192.168.1.100")
        self.home_address.pack(anchor="w", pady=(4, 2), fill="x")
        self.home_address.bind("<Return>", lambda _e: self._connect_from_home())
        self._lbl(card, "Device ID ya IP address likho — misal 739 738 074 ya 192.168.1.100",
                  muted=True, size=10).pack(anchor="w")
        self.home_unattended = tk.BooleanVar(value=False)
        self.home_pw_frame = self._role(ctk.CTkFrame(card, fg_color="transparent"), "card")
        self._lbl(self.home_pw_frame, "Unattended password", bold=True).pack(anchor="w")
        self.home_pw = self._entry(self.home_pw_frame, width=260, show="•")
        self.home_pw.pack(anchor="w", pady=(2, 2))
        self._switch(card, "Unattended (password se)", self.home_unattended,
                     self._toggle_home_unattended).pack(anchor="w", pady=(8, 0))
        self._lbl(card, "Assisted: host ke popup pe Accept zaroori hai. "
                  "Unattended tick karne pe password se connect hoga, popup nahi aayega.",
                  muted=True, wrap=640).pack(anchor="w", pady=(4, 0))
        row2 = self._role(ctk.CTkFrame(card, fg_color="transparent"), "card")
        row2.pack(fill="x", pady=(10, 0))
        self._btn(row2, "Connect", self._connect_from_home, "primary").pack(side="left", padx=(0, 6))
        self._btn(row2, "Disconnect", self._disconnect, "ghost").pack(side="left", padx=6)
        self._btn(row2, "Find on LAN", self._find_on_lan_home, "ghost").pack(side="left", padx=6)
        self._lbl(card, "1) Dusre PC pe Start Hosting dabao, uska Address lo. "
                  "2) Yahan Address likh ke Connect dabao — dusre PC pe Accept ka popup aayega.",
                  muted=True, wrap=640).pack(anchor="w", pady=(8, 0))
        self._role(ctk.CTkLabel(card, textvariable=self.connect_status_var,
                                font=_font(11), text_color=self.theme["muted"],
                                wraplength=640, justify="left"), "muted_card").pack(
                                    anchor="w", pady=(6, 0))

        self.home_internet = self._internet_block(body)
        self.home_signaling = self._signaling_block(body)

        card2 = self._card(body, "Recent sessions")
        self.home_history_box = self._role(ctk.CTkTextbox(card2, height=110,
                                                          font=ctk.CTkFont(family="Consolas", size=11),
                                                          fg_color=self.theme["entry"],
                                                          border_color=self.theme["border"],
                                                          text_color=self.theme["fg"]), "text")
        self.home_history_box.pack(fill="both", expand=True)
        self.home_history_box.configure(state="disabled")

        card3 = self._card(body, "Quick actions")
        row3 = self._role(ctk.CTkFrame(card3, fg_color="transparent"), "card")
        row3.pack(fill="x")
        self._btn(row3, "File Transfer", lambda: self._show_page("File Transfer"),
                  "ghost").pack(side="left", padx=(0, 6))
        self._btn(row3, "Trusted Devices", lambda: self._show_page("Trusted Devices"),
                  "ghost").pack(side="left", padx=6)
        self._btn(row3, "Settings", lambda: self._show_page("Settings"),
                  "ghost").pack(side="left", padx=6)

        card4 = self._card(body, "Activity log")
        self.log_box = self._role(ctk.CTkTextbox(card4, height=130,
                                                 font=ctk.CTkFont(family="Consolas", size=11),
                                                 fg_color=self.theme["entry"],
                                                 border_color=self.theme["border"],
                                                 text_color=self.theme["fg"]), "text")
        self.log_box.pack(fill="both", expand=True)
        self.log_box.configure(state="disabled")
        self._lbl(body, config.DEVELOPER_CREDIT, muted=True).pack(anchor="w")
        self._log("RemoteDesk started. Hosting is OFF until you start it.")

    # ------------------------------------------------------------- Remote Control
    def _build_remote_control(self):
        page = self.pages["Remote Control"]
        body = self._scrollable(page)
        self._lbl(body, "Remote Control", bold=True, size=22).pack(anchor="w")
        self._lbl(body, "Connect to another PC you are allowed to control.",
                  muted=True).pack(anchor="w", pady=(0, 14))
        tab_row = self._role(ctk.CTkFrame(body, fg_color="transparent"), "bg")
        tab_row.pack(fill="x", pady=(0, 10))
        self.rc_tab_btns: dict[str, ctk.CTkButton] = {}
        for name in ("Quick Connect", "Saved Devices"):
            btn = ctk.CTkButton(tab_row, text=name, font=_font(11, True),
                                corner_radius=10, height=34,
                                fg_color=self.theme["card"], hover_color=self.theme["border"],
                                text_color=self.theme["fg"],
                                command=lambda n=name: self._show_rc_tab(n))
            self._role(btn, "ghost_btn")
            btn.pack(side="left", padx=(0, 6))
            self.rc_tab_btns[name] = btn
        self.rc_tabs: dict[str, ctk.CTkFrame] = {}
        for name in ("Quick Connect", "Saved Devices"):
            self.rc_tabs[name] = self._role(ctk.CTkFrame(body, fg_color="transparent"), "bg")

        quick = self.rc_tabs["Quick Connect"]
        card = self._card(quick, "Quick connect")
        self._lbl(card, "Remote Address", bold=True).pack(anchor="w")
        self.connect_host = self._entry(card, width=520,
                                        placeholder="739 738 074 ya 192.168.1.100")
        self.connect_host.pack(anchor="w", pady=(4, 2), fill="x")
        self._lbl(card, "Device ID ya IP address likho — misal 739 738 074 ya 192.168.1.100",
                  muted=True, size=10).pack(anchor="w")
        self._lbl(card, "Port:", bold=True).pack(anchor="w", pady=(10, 0))
        self.connect_port = self._entry(card, width=140)
        self.connect_port.pack(anchor="w", pady=(4, 2))
        self.connect_port.insert(0, str(self.settings.get("port", config.DEFAULT_PORT)))
        self.use_unattended = tk.BooleanVar(value=False)
        self._switch(card, "Unattended (password se)", self.use_unattended,
                     self._toggle_rc_unattended).pack(anchor="w", pady=(10, 0))
        self.rc_pw_frame = self._role(ctk.CTkFrame(card, fg_color="transparent"), "card")
        self._lbl(self.rc_pw_frame, "Unattended password", bold=True).pack(anchor="w")
        self.connect_code = self._entry(self.rc_pw_frame, width=260, show="•")
        self.connect_code.pack(anchor="w", pady=(2, 2))
        btns = self._role(ctk.CTkFrame(card, fg_color="transparent"), "card")
        btns.pack(fill="x", pady=(10, 0))
        self._btn(btns, "Connect", self._connect, "primary").pack(side="left", padx=(0, 6))
        self._btn(btns, "Disconnect", self._disconnect, "ghost").pack(side="left", padx=6)
        self._btn(btns, "Scan LAN for devices", self._scan_lan, "ghost").pack(side="left", padx=6)
        self._btn(btns, "Find on LAN", self._find_on_lan_rc, "ghost").pack(side="left", padx=6)
        self._role(ctk.CTkLabel(card, textvariable=self.connect_status_var,
                                font=_font(11), text_color=self.theme["muted"],
                                wraplength=640, justify="left"), "muted_card").pack(
                                    anchor="w", pady=(8, 0))

        saved = self.rc_tabs["Saved Devices"]
        card2 = self._card(saved, "Saved devices (trusted)")
        self._lbl(card2, "Click a saved device to fill the Remote Address entry, "
                  "then switch to Quick Connect.", muted=True, wrap=640).pack(anchor="w")
        self.saved_listbox = _CTkList(card2, height=150)
        self.saved_listbox.pack(fill="x", pady=(8, 2))
        self.saved_listbox.bind("<<ListboxSelect>>", self._on_saved_select)
        self._lbl(card2, "Discovered on LAN:", muted=True).pack(anchor="w", pady=(8, 0))
        self.discovered_listbox = _CTkList(card2, height=110)
        self.discovered_listbox.pack(fill="x", pady=(6, 2))
        self.discovered_listbox.bind("<<ListboxSelect>>", self._on_discovered_select)
        self._btn(card2, "Scan LAN for devices", self._scan_lan, "ghost").pack(anchor="w", pady=(6, 0))
        self._show_rc_tab("Quick Connect")
        self.rc_internet = self._internet_block(body)
        self.rc_signaling = self._signaling_block(body)
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
                btn.configure(fg_color=t["accent"], text_color=t["accent_fg"],
                              hover_color=t["accent_hover"])
            else:
                btn.configure(fg_color=t["card"], text_color=t["fg"],
                              hover_color=t["border"])

    def _on_saved_select(self, _event=None):
        sel = self.saved_listbox.curselection()
        if not sel:
            return
        text = self.saved_listbox.get(sel[0])
        m = re.search(r"ID\s+([\d ]+)", text)
        if m:
            self.connect_host.delete(0, "end")
            self.connect_host.insert(0, m.group(1).strip())
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
        elif m_id:
            self.connect_host.delete(0, "end")
            self.connect_host.insert(0, m_id.group(1).strip())
        self._show_rc_tab("Quick Connect")

    # ------------------------------------------------------------- Viewer
    def _build_viewer(self):
        page = self.pages["Viewer"]
        toolbar = self._role(ctk.CTkFrame(page, fg_color="transparent"), "bg")
        toolbar.pack(fill="x", pady=(0, 10))
        self._role(ctk.CTkLabel(toolbar, textvariable=self.viewer_status_var,
                                font=_font(11), text_color=self.theme["muted"]), "muted_bg").pack(
                                    side="left")
        self._role(ctk.CTkLabel(toolbar, textvariable=self.viewer_quality_var,
                                font=_font(11), text_color=self.theme["muted"]), "muted_bg").pack(
                                    side="left", padx=16)
        self._role(ctk.CTkLabel(toolbar, text="Latency: —", font=_font(11),
                                text_color=self.theme["muted"]), "muted_bg").pack(side="left")
        self._role(ctk.CTkLabel(toolbar, textvariable=self.viewer_control_var,
                                font=_font(11, True),
                                text_color=self.theme["muted"]), "muted_bg").pack(
                                    side="left", padx=16)
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
        self.viewer_waiting = self._role(ctk.CTkLabel(
            page, text="Waiting for screen…\n(Host ne Accept kiya to screen yahan aayegi.)",
            font=_font(13), text_color="#8CA3C0", justify="center"), "muted_bg")
        self.viewer_waiting.place(relx=0.5, rely=0.5, anchor="center")

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
        self._lbl(page, "File Transfer", bold=True, size=22).pack(anchor="w")
        self._lbl(page, "File transfer needs an active session AND host permission. "
                  "Received files are NEVER executed automatically.",
                  muted=True, wrap=640).pack(anchor="w", pady=(0, 14))
        tab_row = self._role(ctk.CTkFrame(page, fg_color="transparent"), "bg")
        tab_row.pack(fill="x", pady=(0, 10))
        self.ft_tab_btns: dict[str, ctk.CTkButton] = {}
        for name in ("Send Files", "Receive Files"):
            btn = ctk.CTkButton(tab_row, text=name, font=_font(11, True),
                                corner_radius=10, height=34,
                                fg_color=self.theme["card"], hover_color=self.theme["border"],
                                text_color=self.theme["fg"],
                                command=lambda n=name: self._show_ft_tab(n))
            self._role(btn, "ghost_btn")
            btn.pack(side="left", padx=(0, 6))
            self.ft_tab_btns[name] = btn
        self.ft_tabs: dict[str, ctk.CTkFrame] = {}
        for name in ("Send Files", "Receive Files"):
            self.ft_tabs[name] = self._role(ctk.CTkFrame(page, fg_color="transparent"), "bg")

        send = self.ft_tabs["Send Files"]
        card = self._card(send, "Send files")
        self._lbl(card, "Drop files here or use Choose Files. Drag-and-drop works "
                  "only if tkinterdnd2 is installed; the chooser always works.",
                  muted=True, wrap=640).pack(anchor="w")
        drop = self._role(ctk.CTkLabel(card, text="Drop files here or use Choose Files",
                                       font=_font(12), text_color=self.theme["muted"],
                                       fg_color=self.theme["entry"], corner_radius=10), "muted_card")
        drop.pack(fill="x", pady=(10, 8), ipady=18)
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD  # noqa: F401
            drop.configure(text="Drop files here or use Choose Files (drag & drop available)")
        except ImportError:
            pass
        row = self._role(ctk.CTkFrame(card, fg_color="transparent"), "card")
        row.pack(fill="x")
        self._btn(row, "Choose Files…", self._choose_send_files, "primary").pack(side="left", padx=(0, 6))
        self._lbl(row, "Destination device:").pack(side="left")
        self.ft_dest = self._combo(row, ["(No saved devices yet)"], width=260)
        self.ft_dest.pack(side="left", padx=6)
        self._btn(row, "Send selected", self._send_files_honest, "ghost").pack(side="left", padx=6)
        self._lbl(card, "Transfer queue:", muted=True).pack(anchor="w", pady=(12, 0))
        self.ft_queue = _CTkList(card, height=130)
        self.ft_queue.pack(fill="x", pady=(6, 2))
        self._lbl(card, "File send over session is not wired in this build — "
                  "files are not sent. The chooser above only selects files; "
                  "Send reports this honestly and sends nothing.",
                  muted=True, wrap=640).pack(anchor="w")
        self.file_status = tk.StringVar(value="No active session.")
        self._role(ctk.CTkLabel(card, textvariable=self.file_status, font=_font(11),
                                text_color=self.theme["fg"]), "label_card").pack(
                                    anchor="w", pady=(8, 0))

        recv = self.ft_tabs["Receive Files"]
        card2 = self._card(recv, "Receive files")
        self._lbl(card2, "Received files land here, never auto-executed:",
                  muted=True).pack(anchor="w")
        self.recv_dir_var = tk.StringVar(
            value=self.settings.get("download_dir", config.default_download_dir()))
        self._role(ctk.CTkLabel(card2, textvariable=self.recv_dir_var, font=_font(11),
                                text_color=self.theme["fg"], wraplength=640,
                                justify="left"), "label_card").pack(anchor="w", pady=(4, 8))
        self._btn(card2, "Open folder", self._open_download_dir, "ghost").pack(anchor="w")
        self._lbl(card2, "Files in this folder:", muted=True).pack(anchor="w", pady=(12, 0))
        self.recv_list = _CTkList(card2, height=150)
        self.recv_list.pack(fill="x", pady=(6, 2))
        self._lbl(card2, "Recent transfers:", muted=True).pack(anchor="w", pady=(10, 0))
        self.transfers_box = self._role(ctk.CTkTextbox(card2, height=70,
                                                       font=ctk.CTkFont(family="Consolas", size=11),
                                                       fg_color=self.theme["entry"],
                                                       border_color=self.theme["border"],
                                                       text_color=self.theme["fg"]), "text")
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
                btn.configure(fg_color=t["accent"], text_color=t["accent_fg"],
                              hover_color=t["accent_hover"])
            else:
                btn.configure(fg_color=t["card"], text_color=t["fg"],
                              hover_color=t["border"])

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
        self.ft_dest.configure(values=names or ["(No saved devices yet)"])
        if names:
            self.ft_dest.set(names[0])

    # ------------------------------------------------------------- Trusted Devices
    def _build_trusted(self):
        page = self.pages["Trusted Devices"]
        self._lbl(page, "Trusted Devices", bold=True, size=22).pack(anchor="w")
        self._lbl(page, "Address book: click a device to fill the Remote Address "
                  "field. Every connect STILL needs host Accept — trusted "
                  "devices do NOT auto-accept.",
                  muted=True, wrap=640).pack(anchor="w", pady=(0, 14))
        self.trusted_list = _CTkList(page, height=200)
        self.trusted_list.pack(fill="x", pady=(0, 10))
        row = self._role(ctk.CTkFrame(page, fg_color="transparent"), "bg")
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
        self._check(card, "Enable unattended access on this device",
                    self.unattended_var).pack(anchor="w", pady=8)
        row2 = self._role(ctk.CTkFrame(card, fg_color="transparent"), "card")
        row2.pack(fill="x")
        self._lbl(row2, "New unattended password (min 10 chars):").pack(side="left")
        self.unattended_pw = self._entry(row2, width=260, show="•")
        self.unattended_pw.pack(side="left", padx=6)
        self.unattended_ctrl = tk.BooleanVar(value=bool(self.settings.get("unattended_allow_control")))
        self._check(card, "Allow mouse/keyboard control in unattended sessions",
                    self.unattended_ctrl).pack(anchor="w", pady=8)
        self._btn(card, "Save unattended settings", self._save_unattended, "primary").pack(anchor="w")

    def _add_trusted_dialog(self):
        t = self.theme
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Add trusted device")
        dlg.geometry("420x260")
        dlg.configure(fg_color=t["card"])
        dlg.transient(self.root)
        dlg.grab_set()
        self._role(ctk.CTkLabel(dlg, text="Add trusted device", font=_font(14, True),
                                text_color=t["fg"]), "label_card").pack(
                                    padx=18, pady=(14, 8), anchor="w")
        self._role(ctk.CTkLabel(dlg, text="Device ID (9 digits):", font=_font(11),
                                text_color=t["fg"]), "label_card").pack(padx=18, anchor="w")
        id_entry = self._entry(dlg, width=300)
        id_entry.pack(padx=18, anchor="w", pady=(2, 8))
        self._role(ctk.CTkLabel(dlg, text="Device name:", font=_font(11),
                                text_color=t["fg"]), "label_card").pack(padx=18, anchor="w")
        name_entry = self._entry(dlg, width=300)
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
        self._lbl(page, "Session History", bold=True, size=22).pack(anchor="w")
        self._lbl(page, "Every recorded session on this PC.",
                  muted=True).pack(anchor="w", pady=(0, 14))
        row = self._role(ctk.CTkFrame(page, fg_color="transparent"), "bg")
        row.pack(fill="x", pady=(0, 10))
        self._lbl(row, "Search:").pack(side="left")
        self.hist_search_var = tk.StringVar()
        self.hist_search_var.trace_add("write", lambda *_: self._refresh_history())
        search = self._entry(row, width=260, textvariable=self.hist_search_var)
        search.pack(side="left", padx=6)
        self._lbl(row, "Filter:").pack(side="left", padx=(12, 0))
        self.hist_filter_var = tk.StringVar(value="All")
        filt = self._combo(row, ["All", "Remote Control", "File Transfer"],
                           variable=self.hist_filter_var,
                           command=lambda _v: self._refresh_history(), width=180)
        filt.pack(side="left", padx=6)
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
        self._lbl(page, "Settings", bold=True, size=22).pack(anchor="w")
        self._lbl(page, "Security, network, general and about.",
                  muted=True).pack(anchor="w", pady=(0, 14))
        tab_row = self._role(ctk.CTkFrame(page, fg_color="transparent"), "bg")
        tab_row.pack(fill="x", pady=(0, 10))
        self.settings_tab_btns: dict[str, ctk.CTkButton] = {}
        for name in ("Security", "Network", "General", "About"):
            btn = ctk.CTkButton(tab_row, text=name, font=_font(11, True),
                                corner_radius=10, height=34,
                                fg_color=self.theme["card"], hover_color=self.theme["border"],
                                text_color=self.theme["fg"],
                                command=lambda n=name: self._show_settings_tab(n))
            self._role(btn, "ghost_btn")
            btn.pack(side="left", padx=(0, 6))
            self.settings_tab_btns[name] = btn
        self.settings_tabs: dict[str, ctk.CTkFrame] = {}
        for name in ("Security", "Network", "General", "About"):
            self.settings_tabs[name] = self._role(ctk.CTkFrame(page, fg_color="transparent"), "bg")
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
                btn.configure(fg_color=t["accent"], text_color=t["accent_fg"],
                              hover_color=t["accent_hover"])
            else:
                btn.configure(fg_color=t["card"], text_color=t["fg"],
                              hover_color=t["border"])

    def _build_settings_security(self):
        tab = self.settings_tabs["Security"]
        body = self._scrollable(tab)
        card = self._card(body, "Access password")
        self._lbl(card, "Change the unattended access password. Stored as a "
                  "salted hash only — never in plain text.", muted=True,
                  wrap=640).pack(anchor="w")
        row = self._role(ctk.CTkFrame(card, fg_color="transparent"), "card")
        row.pack(fill="x", pady=(10, 0))
        self._lbl(row, "New password (min 10 chars):").pack(side="left")
        self.sec_pw = self._entry(row, width=260, show="•")
        self.sec_pw.pack(side="left", padx=6)
        self._btn(row, "Change Access Password", self._change_access_password,
                  "primary").pack(side="left", padx=6)
        card2 = self._card(body, "Two-factor authentication")
        self.tfa_var = tk.BooleanVar(value=False)
        self._check(card2, "Enable two-factor authentication",
                    self.tfa_var, disabled=True).pack(anchor="w")
        self._lbl(card2, "Two-factor authentication is not implemented in this build. "
                  "The toggle is disabled on purpose — it does not protect "
                  "anything until a real 2FA flow ships.", muted=True,
                  wrap=640).pack(anchor="w", pady=(4, 0))
        card3 = self._card(body, "Session options")
        self.clipboard_var = tk.BooleanVar(value=bool(self.settings.get("clipboard_sync")))
        self._check(card3, "Allow Clipboard Sync", self.clipboard_var).pack(anchor="w")
        self.ft_enabled_var = tk.BooleanVar(
            value=bool(self.settings.get("file_transfer_enabled", True)))
        self._check(card3, "Enable File Transfer", self.ft_enabled_var).pack(anchor="w", pady=(6, 0))
        self._lbl(card3, "Disabling File Transfer also disables the file-transfer "
                  "checkbox on incoming requests. Per-session host permission "
                  "is still required when it is enabled.", muted=True,
                  wrap=640).pack(anchor="w", pady=(6, 0))
        self._lbl(card3, "Assisted sessions ALWAYS need host Accept — there is "
                  "no auto-accept, not even for trusted devices. The only "
                  "no-Accept path is Unattended (password, opt-in, on the "
                  "Trusted Devices page).",
                  muted=True, wrap=640).pack(anchor="w", pady=(10, 0))
        self._btn(card3, "Save session options", self._save_security_toggles,
                  "primary").pack(anchor="w", pady=(10, 0))
        card4 = self._card(body, "Session safety")
        self._lbl(card4, "During any session, the host can end it instantly with "
                  "Disconnect. Control permission can be revoked mid-session.",
                  muted=True, wrap=640).pack(anchor="w")
        self._btn(card4, "End active session now", self._disconnect, "danger").pack(anchor="w", pady=8)

    def _build_settings_network(self):
        tab = self.settings_tabs["Network"]
        body = self._scrollable(tab)
        card = self._card(body, "Connection defaults")
        self._conn_type_radios(card)
        row = self._role(ctk.CTkFrame(card, fg_color="transparent"), "card")
        row.pack(fill="x")
        self._lbl(row, "Port:").pack(side="left")
        self.net_port = self._entry(row, width=120)
        self.net_port.pack(side="left", padx=6)
        self.net_port.insert(0, str(self.settings.get("port", config.DEFAULT_PORT)))
        self._btn(row, "Save network settings", self._save_network, "primary").pack(side="left", padx=6)
        card2 = self._card(body, "Internet (direct) status")
        self._lbl(card2, "Public IP:", muted=True).pack(anchor="w")
        self._role(ctk.CTkLabel(card2, textvariable=self.public_ip_var,
                                font=_font(13, True),
                                text_color=self.theme["fg"]), "label_card").pack(anchor="w")
        self._lbl(card2, "LAN IP:", muted=True).pack(anchor="w", pady=(4, 0))
        self._role(ctk.CTkLabel(card2, textvariable=self.lan_ip_var,
                                font=_font(11),
                                text_color=self.theme["fg"]), "label_card").pack(anchor="w")
        self._lbl(card2, "UPnP status:", muted=True).pack(anchor="w", pady=(4, 0))
        self._role(ctk.CTkLabel(card2, textvariable=self.upnp_var,
                                font=_font(11), wraplength=600, justify="left",
                                text_color=self.theme["fg"]), "label_card").pack(anchor="w")
        btns = self._role(ctk.CTkFrame(card2, fg_color="transparent"), "card")
        btns.pack(fill="x", pady=(10, 0))
        self._btn(btns, "Open port (UPnP)", self._open_port_upnp, "primary").pack(side="left", padx=(0, 6))
        self._btn(btns, "Refresh", self._refresh_internet_info, "ghost").pack(side="left", padx=6)
        self._btn(btns, "Test port reachable", self._test_port_reachable, "ghost").pack(side="left", padx=6)
        self._role(ctk.CTkLabel(card2, textvariable=self.port_reachable_var,
                                font=_font(11), wraplength=600, justify="left",
                                text_color=self.theme["muted"]), "muted_card").pack(
                                    anchor="w", pady=(8, 0))
        self._lbl(card2, "Internet mode is a direct TCP connection to the host's "
                  "public IP. It works when UPnP succeeds or port forwarding is set; "
                  "strict / CGNAT routers need a relay server (not included).",
                  muted=True, wrap=640).pack(anchor="w", pady=(8, 0))
        card_sig = self._card(body, "Signaling server (Device ID lookup)")
        self._lbl(card_sig, "AnyDesk-style: with a signaling server, controllers "
                  "connect with your Device ID instead of your IP. The server is "
                  "a directory ONLY — screen and passwords never pass through it. "
                  "Without a server, Device IDs cannot resolve; use Direct IP. "
                  "See docs/SIGNALING_DEPLOY.md for free hosting.",
                  muted=True, wrap=640).pack(anchor="w")
        row_sig = self._role(ctk.CTkFrame(card_sig, fg_color="transparent"), "card")
        row_sig.pack(fill="x", pady=(10, 0))
        self._lbl(row_sig, "Server URL:").pack(side="left")
        self.sig_url_entry = self._entry(row_sig, width=360,
                                         textvariable=self.signaling_url_var)
        self.sig_url_entry.pack(side="left", padx=6)
        self._check(card_sig, "Register this device when hosting starts",
                    self.signaling_auto_var).pack(anchor="w", pady=(10, 0))
        btns_sig = self._role(ctk.CTkFrame(card_sig, fg_color="transparent"), "card")
        btns_sig.pack(fill="x", pady=(10, 0))
        self._btn(btns_sig, "Save signaling settings", self._save_signaling,
                  "primary").pack(side="left", padx=(0, 6))
        self._btn(btns_sig, "Register now", self._signaling_register_now,
                  "ghost").pack(side="left", padx=6)
        self._role(ctk.CTkLabel(card_sig, textvariable=self.signaling_status_var,
                                font=_font(11), wraplength=600, justify="left",
                                text_color=self.theme["muted"]), "muted_card").pack(
                                    anchor="w", pady=(8, 0))
        card3 = self._card(body, "Network diagnostics")
        self.diag_box = self._role(ctk.CTkTextbox(card3, height=190,
                                                  font=ctk.CTkFont(family="Consolas", size=11),
                                                  fg_color=self.theme["entry"],
                                                  border_color=self.theme["border"],
                                                  text_color=self.theme["fg"]), "text")
        self.diag_box.pack(fill="both", expand=True)
        self.diag_box.configure(state="disabled")
        self._btn(card3, "Run diagnostics", self._run_diag, "ghost").pack(anchor="w", pady=8)

    def _build_settings_general(self):
        tab = self.settings_tabs["General"]
        body = self._scrollable(tab)
        card = self._card(body, "General")
        row = self._role(ctk.CTkFrame(card, fg_color="transparent"), "card")
        row.pack(fill="x")
        self._lbl(row, "Download folder for received files:").pack(side="left")
        self.download_dir_var = tk.StringVar(value=self.settings.get("download_dir", ""))
        dl = self._entry(row, width=340, textvariable=self.download_dir_var)
        dl.pack(side="left", padx=6)
        self._btn(row, "Browse…", self._pick_download_dir, "ghost").pack(side="left")
        self.auto_update_var = tk.BooleanVar(value=bool(self.settings.get("auto_update_check", True)))
        self._check(card, "Check for updates automatically",
                    self.auto_update_var).pack(anchor="w", pady=12)
        self._btn(card, "Save settings", self._save_general, "primary").pack(anchor="w")
        card2 = self._card(body, "Theme")
        self._lbl(card2, "Switch instantly — no restart needed.", muted=True).pack(anchor="w")
        self.theme_toggle_btn = self._btn(card2, "Switch to Light mode",
                                          self._toggle_theme, "ghost")
        self.theme_toggle_btn.pack(anchor="w", pady=(8, 0))

    def _build_settings_about(self):
        tab = self.settings_tabs["About"]
        body = self._scrollable(tab)
        card = self._card(body, "About")
        self._lbl(card, "◆  RemoteDesk", bold=True, size=20).pack(anchor="w")
        self._lbl(card, f"Version {VERSION}", muted=True).pack(anchor="w")
        self._lbl(card, "Connect. Control. Work Anywhere.", bold=True, size=13).pack(anchor="w", pady=(10, 0))
        self._lbl(card, config.DEVELOPER_CREDIT, muted=True).pack(anchor="w", pady=(4, 0))
        self._lbl(card, "Windows 10/11 • Secure & Encrypted", muted=True).pack(anchor="w")
        self._lbl(card, config.ABOUT_TEXT, wrap=640).pack(anchor="w", pady=(10, 0))
        card2 = self._card(body, "Updates")
        self._lbl(card2, "Updates come from GitHub Releases — no server needed. "
                  "When a new version is published, this app shows a popup and "
                  "downloads the installer inside the app (no browser redirect).",
                  muted=True, wrap=640).pack(anchor="w")
        self._btn(card2, "Check for Updates now", self._manual_update_check,
                  "primary").pack(anchor="w", pady=8)

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
                elif kind == "show_code_prompt":
                    self.connect_status_var.set(payload)
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
        text = (f"RemoteDesk — connect with: Address {format_device_id(self.device_id)} "
                f"ya IP {public}:{port} (host pe Accept ka popup aayega)")
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
                msg = f"Port reachable: {public}:{port} answered this self-test."
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
        self.host_btn.configure(text="■  Stop Hosting")
        self._refresh_pill()
        if self.settings.get("signaling_auto_register") and \
                (self.settings.get("signaling_url", "") or "").strip():
            self._signaling_register_now()

    def _new_pairing_code(self):
        # Kept for compatibility: pairing codes were removed from the
        # assisted flow in v1.0.5 (host Accept popup decides). No-op.
        self._log("Pairing codes are not used in the v1.0.5 assisted flow.")

    def _queue_request(self, peer: dict):
        """Called from host thread — hand the decision to the UI thread.

        Returns (accept, control, files). Assisted sessions ALWAYS need
        this Accept — there is no auto-accept, not even for trusted devices.
        """
        result: dict = {}
        self.msg_queue.put(("request", (peer, result)))
        while "accept" not in result:
            threading.Event().wait(0.1)
        return result["accept"], result["control"], result["files"]

    def _show_request_dialog(self, data):
        peer, result = data
        t = self.theme
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Incoming connection request")
        dlg.geometry("480x400")
        dlg.configure(fg_color=t["card"])
        dlg.transient(self.root)
        dlg.grab_set()
        self._role(ctk.CTkLabel(dlg, text="Incoming remote connection request",
                                font=_font(14, True), text_color=t["fg"]), "label_card").pack(
                                    padx=18, pady=(16, 4), anchor="w")
        self._role(ctk.CTkLabel(dlg, text=f"Device: {peer.get('device_name')}  (ID {peer.get('device_id')})\n"
                 f"IP: {peer.get('ip')}\n\n"
                 "Only accept if you know and trust this person.",
                 font=_font(11), text_color=t["muted"],
                 wraplength=430, justify="left"), "muted_card").pack(padx=18, anchor="w")
        view = tk.BooleanVar(value=True)
        ctrl = tk.BooleanVar(value=True)
        files = tk.BooleanVar(value=False)
        self._check(dlg, "View Screen", view).pack(anchor="w", padx=18, pady=(12, 0))
        self._check(dlg, "Control (Mouse & Keyboard)", ctrl).pack(anchor="w", padx=18)
        self._role(ctk.CTkLabel(dlg, text="Control ON rakhne se dusra banda mouse/keyboard use kar sakega.",
                                font=_font(10), text_color=t["muted"]), "muted_card").pack(
                                    anchor="w", padx=18)
        files_cb = self._check(dlg, "File Transfer", files)
        files_cb.pack(anchor="w", padx=18)
        if not self.settings.get("file_transfer_enabled", True):
            files_cb.configure(state="disabled")
            self._role(ctk.CTkLabel(dlg, text="File Transfer is disabled in Settings → Security.",
                                    font=_font(10), text_color=t["muted"]), "muted_card").pack(
                                        anchor="w", padx=18)
        self._role(ctk.CTkLabel(dlg, text=f"No answer in {REQUEST_TIMEOUT_S}s = auto-reject.",
                                font=_font(10), text_color=t["muted"]), "muted_card").pack(
                                    anchor="w", padx=18, pady=(10, 0))
        btns = self._role(ctk.CTkFrame(dlg, fg_color="transparent"), "card")
        btns.pack(pady=18)
        state = {"answered": False}

        def answer(accept):
            if state["answered"]:
                return
            state["answered"] = True
            if accept and not view.get():
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
                self._log(f"Accepted session from {peer.get('device_name')} "
                          f"(control={'ON' if result['control'] else 'OFF'}).")
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
        self._btn(btns, "✓  Accept", lambda: answer(True), "success").pack(side="left", padx=6)
        self._btn(btns, "✕  Decline", lambda: answer(False), "danger").pack(side="left", padx=6)
        dlg.protocol("WM_DELETE_WINDOW", lambda: answer(False))
        self.root.wait_window(dlg)
        if "accept" not in result:
            result["accept"] = False
            result["control"] = False
            result["files"] = False
            self._log("Incoming request closed without an answer — treated as rejected.")

    # ------------------------------------------------------------- connect
    def _toggle_home_unattended(self):
        if self.home_unattended.get():
            self.home_pw_frame.pack(anchor="w", fill="x", pady=(6, 0))
        else:
            self.home_pw_frame.pack_forget()

    def _toggle_rc_unattended(self):
        if self.use_unattended.get():
            self.rc_pw_frame.pack(anchor="w", fill="x", pady=(6, 0))
        else:
            self.rc_pw_frame.pack_forget()

    def _connect_from_home(self):
        address = self.home_address.get().strip()
        code = self.home_pw.get().strip() if self.home_unattended.get() else ""
        if self.home_unattended.get() and not code:
            self.connect_status_var.set("Unattended password likho (host pe Settings me set hota hai).")
            return
        self._start_connect(address, "",
                            int(self.settings.get("port", config.DEFAULT_PORT)),
                            code, self.home_unattended.get())

    def _connect(self):
        ip_text = self.connect_host.get().strip()
        try:
            port = int(self.connect_port.get().strip())
        except ValueError:
            messagebox.showerror("Connect", "Port must be a number.")
            return
        code = self.connect_code.get().strip() if self.use_unattended.get() else ""
        if self.use_unattended.get() and not code:
            messagebox.showerror("Unattended", "Unattended password likho.")
            return
        self._start_connect(ip_text, "", port, code, self.use_unattended.get())

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
        """Resolve a validated decision to (host, port, error). Never raises."""
        action = decision["action"]
        if action == "direct":
            return decision["host"], decision["port"] or default_port, None
        if action == "auto_resolve":
            did = decision["device_id"]
            self.msg_queue.put(("connect_status", f"Resolving {format_device_id(did)} …"))
            host, port, error = connect_target.resolve_device_id(
                did, self.settings.get("signaling_url", ""),
                scan_fn=lambda: DiscoveryListener(duration_s=5.0).scan(),
                lookup_fn=lambda url, d: signaling.lookup_device(url, d))
            if error is not None:
                return "", default_port, error
            return host, port or default_port, None
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
            ok, msg = self.client.connect(host, resolved_port)
        if ok:
            self._session_start = time.time()
            self._session_peer = label
            self._session_host = host
            self._got_first_frame = False
            self._host_screen_size = (0, 0)
            self._record_history(label, host, "Remote Control", "Connected")
            self.msg_queue.put(("viewer_status", f"Connected to {host}:{resolved_port}."))
            self.msg_queue.put(("connect_status", f"Connected to {host}:{resolved_port}."))
            self.msg_queue.put(("file_status", "Session active."))
            self._update_control_indicator()
            self.msg_queue.put(("show_page", "Viewer"))
        else:
            if "rejected" in msg.lower():
                detail = "Host ne request decline kar di / jawab nahi diya."
                self.msg_queue.put(("viewer_status", f"Connection failed: {detail}"))
                self.msg_queue.put(("connect_status", f"Connection failed: {detail}"))
                self._log(f"Connection failed: {detail}")
                return
            if "Could not connect" in msg:
                detail = (f"Host not reachable at {host}:{resolved_port} — check hosting ON, "
                          "same Wi-Fi for LAN, Public IP + port mapping for Internet, "
                          f"or signaling registration. ({msg})")
            else:
                detail = msg
            self.msg_queue.put(("viewer_status", f"Connection failed: {detail}"))
            self.msg_queue.put(("connect_status", f"Connection failed: {detail}"))
            self._log(f"Connection failed: {detail}")

    def _update_control_indicator(self):
        """Viewer toolbar: show whether clicks will work, from the REAL session."""
        try:
            active = self.client.sessions.active
            if active is not None and active.can_control:
                self.viewer_control_var.set("Control: ON ✓")
            elif self.client.connected:
                self.viewer_control_var.set("Control: OFF — host ne control nahi diya")
            else:
                self.viewer_control_var.set("Control: —")
        except tk.TclError:
            pass

    # ------------------------------------------------------------- Find on LAN
    def _find_on_lan_home(self):
        self._find_on_lan_fill(self.home_address, None)

    def _find_on_lan_rc(self):
        self._find_on_lan_fill(self.connect_host, None)

    def _find_on_lan_fill(self, ip_entry, id_entry):
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
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Found on LAN — pick a device")
        dlg.geometry("440x280")
        dlg.configure(fg_color=self.theme["card"])
        dlg.transient(self.root)
        dlg.grab_set()
        self._role(ctk.CTkLabel(dlg, text="Found on LAN — pick a device",
                                font=_font(13, True),
                                text_color=self.theme["fg"]), "label_card").pack(
                                    padx=16, pady=(14, 6), anchor="w")
        box = _CTkList(dlg, height=150)
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
            if id_entry is not None:
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
        self._got_first_frame = False
        self._host_screen_size = (0, 0)
        self.msg_queue.put(("connect_status", "Disconnected."))
        self.msg_queue.put(("viewer_status", "Not connected — connect from Remote Control."))
        self.msg_queue.put(("file_status", "No active session."))
        self.viewer_quality_var.set("Quality: —")
        self.viewer_control_var.set("Control: —")
        self._refresh_pill()

    def _on_client_disconnect(self, reason: str):
        if self._session_start is not None:
            duration = time.time() - self._session_start
            self._record_history(self._session_peer, self._session_host,
                                 "Remote Control", "Ended", duration_s=duration)
            self._session_start = None
        self._got_first_frame = False
        self._host_screen_size = (0, 0)
        self.msg_queue.put(("viewer_status", f"Disconnected: {reason}"))
        self.msg_queue.put(("connect_status", f"Disconnected: {reason}"))
        self.msg_queue.put(("file_status", "No active session."))
        self.viewer_quality_var.set("Quality: —")
        self.viewer_control_var.set("Control: —")

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
            if getattr(self.client, "host_screen_size", (0, 0)) != (0, 0):
                self._host_screen_size = self.client.host_screen_size
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
            if not self._got_first_frame:
                self._got_first_frame = True
                try:
                    self.viewer_waiting.place_forget()
                except tk.TclError:
                    pass
                self._update_control_indicator()
        except Exception:
            pass

    def _scale_event(self, event):
        """Canvas event → host coords (scaled; see scale_coords)."""
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        hw, hh = self._host_screen_size
        return scale_coords(event.x, event.y, cw, ch, hw, hh)

    def _on_mouse_move(self, event):
        if self.client.connected and self.client.sessions.active.can_control:
            x, y = self._scale_event(event)
            self.client.send_input({"kind": "move", "x": x, "y": y})

    def _send_click(self, event, pressed: bool):
        if self.client.connected and self.client.sessions.active.can_control:
            x, y = self._scale_event(event)
            self.client.send_input({"kind": "click", "button": "left", "pressed": pressed,
                                    "x": x, "y": y})

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
                perms = []
                if d.get("control_allowed"):
                    perms.append("control")
                if d.get("files_allowed"):
                    perms.append("files")
                perm_txt = f" ({', '.join(perms)})" if perms else " (view only)"
                lst.insert("end", f"● {d.get('device_name')} — ID {format_device_id(d.get('device_id', ''))}{perm_txt}")

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

    def _refresh_history(self):
        if not hasattr(self, "history_tree"):
            return
        for row in self.history_tree.get_children():
            self.history_tree.delete(row)
        q = self.hist_search_var.get().lower() if hasattr(self, "hist_search_var") else ""
        filt = self.hist_filter_var.get() if hasattr(self, "hist_filter_var") else "All"
        for entry in reversed(storage.load_history()):
            if not isinstance(entry, dict):
                continue
            if q and q not in str(entry.get("device_name", "")).lower() \
                    and q not in str(entry.get("ip", "")).lower():
                continue
            if filt != "All" and entry.get("type") != filt:
                continue
            ts = entry.get("timestamp", 0)
            date_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "—"
            dur = entry.get("duration_s")
            dur_txt = f"{dur:.0f}s" if isinstance(dur, (int, float)) else "—"
            self.history_tree.insert("", "end", values=(
                entry.get("device_name", ""), entry.get("type", ""),
                dur_txt, entry.get("status", ""), date_str))

    def _refresh_home_history(self):
        if not hasattr(self, "home_history_box"):
            return
        entries = [e for e in storage.load_history()
                   if isinstance(e, dict)][-5:]
        lines = []
        for e in reversed(entries):
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(e.get("timestamp", 0))) \
                if e.get("timestamp") else "—"
            lines.append(f"{ts}  •  {e.get('device_name','')}  •  {e.get('type','')}  •  {e.get('status','')}")
        self.home_history_box.configure(state="normal")
        self.home_history_box.delete("1.0", "end")
        self.home_history_box.insert("end", "\n".join(lines) or "No sessions yet.")
        self.home_history_box.configure(state="disabled")

    # ------------------------------------------------------------- settings actions
    def _save_security_toggles(self):
        self.settings["clipboard_sync"] = self.clipboard_var.get()
        self.settings["file_transfer_enabled"] = self.ft_enabled_var.get()
        storage.save_settings(self.settings)
        self._log("Saved session options.")
        messagebox.showinfo("Settings", "Saved session options.")

    def _save_unattended(self):
        enabled = self.unattended_var.get()
        if enabled and not self.settings.get("unattended_hash"):
            messagebox.showerror("Unattended", "Set a password first (Settings → Security → Access password).")
            return
        self.settings["unattended_enabled"] = enabled
        self.settings["unattended_allow_control"] = self.unattended_ctrl.get()
        storage.save_settings(self.settings)
        self._log(f"Unattended access {'enabled' if enabled else 'disabled'}.")
        messagebox.showinfo("Unattended", f"Unattended access {'enabled' if enabled else 'disabled'}.")

    def _change_access_password(self):
        pw = self.sec_pw.get()
        ok, err = validate_unattended_password(pw)
        if not ok:
            messagebox.showerror("Access password", err)
            return
        self.settings["unattended_hash"] = hash_password(pw)
        storage.save_settings(self.settings)
        self.sec_pw.delete(0, "end")
        self._log("Access password changed (stored as salted hash only).")
        messagebox.showinfo("Access password", "Access password changed.")

    def _save_network(self):
        try:
            port = int(self.net_port.get())
        except ValueError:
            messagebox.showerror("Network", "Port must be a number.")
            return
        if not (1 <= port <= 65535):
            messagebox.showerror("Network", "Port must be 1–65535.")
            return
        self.settings["port"] = port
        storage.save_settings(self.settings)
        self._log(f"Port set to {port}. Restart hosting for it to take effect.")
        messagebox.showinfo("Network", f"Port set to {port}. Restart hosting for it to take effect.")

    def _save_signaling(self):
        url = self.signaling_url_var.get().strip()
        if url:
            url = signaling.normalize_server_url(url)
        self.settings["signaling_url"] = url
        self.settings["signaling_auto_register"] = self.signaling_auto_var.get()
        storage.save_settings(self.settings)
        self._update_signaling_status()
        self._log(f"Signaling server URL saved: {url or '(none)'}")
        messagebox.showinfo("Signaling server", "Signaling settings saved.")

    def _save_general(self):
        d = self.download_dir_var.get().strip()
        if d:
            self.settings["download_dir"] = d
        self.settings["auto_update_check"] = self.auto_update_var.get()
        storage.save_settings(self.settings)
        self._log("Saved general settings.")
        messagebox.showinfo("Settings", "Saved.")

    def _pick_download_dir(self):
        d = filedialog.askdirectory(initialdir=self.settings.get(
            "download_dir", config.default_download_dir()))
        if d:
            self.download_dir_var.set(d)

    def _run_diag(self):
        out = [
            f"{config.PRODUCT_NAME} {VERSION} — Network diagnostics",
            f"Device: {self.device_name}",
            f"Device ID: {format_device_id(self.device_id)}",
            f"OS: {platform.system()} {platform.release()}",
            f"Port: {self.settings.get('port', config.DEFAULT_PORT)}",
            f"LAN IP: {internet.get_lan_ip() or '—'}",
            f"Public IP: {internet.get_public_ip() or '— (could not reach ipify)'}",
            f"miniupnpc installed: {'yes' if internet.upnp_available() else 'no'}",
            f"Signaling URL: {self.settings.get('signaling_url') or '(none)'}",
            "",
            "Hosting is ON only when you click Start Hosting. Incoming",
            "sessions always need your Accept. If LAN discovery fails,",
            "enter the host IP directly (Find on LAN scans 5 seconds).",
        ]
        self.diag_box.configure(state="normal")
        self.diag_box.delete("1.0", "end")
        self.diag_box.insert("end", "\n".join(out))
        self.diag_box.configure(state="disabled")

    # ------------------------------------------------------------- updates
    def _background_update_check(self):
        update = update_checker.check_for_update(current=VERSION)
        if update:
            self._log(f"Update available: {update.get('tag')} — popup shown.")
            self.msg_queue.put(("update", update))

    def _manual_update_check(self):
        self._log("Checking for updates…")

        def _thread():
            update = update_checker.check_for_update(current=VERSION)
            if update:
                self.msg_queue.put(("update", update))
            else:
                self.msg_queue.put(("log", "You are on the latest version."))

        threading.Thread(target=_thread, daemon=True).start()

    def _show_update_popup(self, update):
        t = self.theme
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Update available")
        dlg.geometry("520x420")
        dlg.configure(fg_color=t["card"])
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.update_idletasks()
        x = self.root.winfo_rootx() + max((self.root.winfo_width() - 520) // 2, 0)
        y = self.root.winfo_rooty() + max((self.root.winfo_height() - 420) // 2, 0)
        dlg.geometry(f"+{x}+{y}")
        tag = str(update.get("tag") or "new version")
        self._role(ctk.CTkLabel(dlg, text=f"Update available — {tag}",
                                font=_font(16, True), text_color=t["fg"]), "label_card").pack(
                                    padx=20, pady=(18, 4), anchor="w")
        self._role(ctk.CTkLabel(dlg, text=f"Current version: v{VERSION}",
                                font=_font(11), text_color=t["muted"]), "muted_card").pack(
                                    padx=20, anchor="w")
        notes = update.get("notes") or "No release notes in this build."
        self._role(ctk.CTkLabel(dlg, text="What's new:", font=_font(11, True),
                                text_color=t["fg"]), "label_card").pack(
                                    padx=20, pady=(14, 2), anchor="w")
        notes_box = self._role(ctk.CTkTextbox(dlg, height=120,
                                              font=ctk.CTkFont(family="Segoe UI", size=11),
                                              fg_color=t["entry"],
                                              border_color=t["border"],
                                              text_color=t["fg"]), "text")
        notes_box.pack(fill="x", padx=20)
        notes_box.insert("end", notes)
        notes_box.configure(state="disabled")
        progress = self._role(ctk.CTkProgressBar(dlg, fg_color=t["entry"],
                                                 progress_color=t["accent"]), "progress")
        status_var = tk.StringVar(value="Waiting…")
        btn_row = self._role(ctk.CTkFrame(dlg, fg_color="transparent"), "card")
        btn_row.pack(pady=(16, 0))
        btn_later = self._btn(btn_row, "Later", dlg.destroy, "ghost")
        btn_later.pack(side="right", padx=6)
        state = {"downloading": False, "done_path": None}

        def _start_download():
            if state["downloading"]:
                return
            state["downloading"] = True
            btn_dl.configure(text="Downloading…", state="disabled")
            progress.pack(fill="x", padx=20, pady=(12, 4))
            self._role(ctk.CTkLabel(dlg, textvariable=status_var,
                                    font=_font(11), text_color=t["muted"]), "muted_card").pack(
                                        padx=20, anchor="w")
            self._download_cancel = threading.Event()
            threading.Thread(target=self._download_update_thread,
                             args=(update,), daemon=True).start()

        btn_dl = self._btn(btn_row, "Download Update", _start_download, "primary")
        btn_dl.pack(side="left", padx=6)
        self._update_popup = {
            "dialog": dlg, "progress": progress, "status_var": status_var,
            "btn_dl": btn_dl, "state": state,
            "release_url": update.get("url") or
            f"https://github.com/{config.UPDATE_REPO}/releases",
        }

    def _on_update_progress(self, done, total, elapsed):
        popup = getattr(self, "_update_popup", None)
        if not popup:
            return
        try:
            popup["status_var"].set(format_update_status(done, total, elapsed))
            if total > 0:
                popup["progress"].set(min(done / total, 1.0))
        except tk.TclError:
            pass

    def _on_update_done(self, path, error):
        popup = getattr(self, "_update_popup", None)
        if not popup:
            return
        try:
            if error:
                popup["status_var"].set(f"Download failed: {error}")
                popup["btn_dl"].configure(text="Try again", state="normal")
                popup["state"]["downloading"] = False
                self._downloaded_path = None
                dlg = popup["dialog"]

                def _open_release():
                    webbrowser.open(popup.get("release_url") or
                                    f"https://github.com/{config.UPDATE_REPO}/releases")
                    dlg.destroy()

                self._btn(dlg, "Open release page", _open_release, "ghost").pack(pady=(6, 0))
                return
            self._downloaded_path = path
            popup["progress"].set(1.0)
            popup["status_var"].set("Download complete — click Run Installer.")
            popup["btn_dl"].configure(text="Run Installer", state="normal")
            popup["btn_dl"].configure(command=self._run_downloaded_installer)
            popup["state"]["downloading"] = False
            popup["state"]["done_path"] = path
        except tk.TclError:
            pass

    def _download_update_thread(self, update):
        """Download the release asset in a worker thread; UI updates via queue.

        Real API: download_update(asset_url, dest_dir, progress_callback
        (downloaded, total), cancel_event) -> (path, error). Never raises.
        """
        asset = update_checker.select_setup_asset(update.get("assets"))
        url = asset.get("download_url") if asset else update.get("url")
        if not url:
            self.msg_queue.put(("update_done", (None, "No download URL in this release.")))
            return
        started = time.time()

        def _progress(done, total):
            self.msg_queue.put(("update_progress", (done, total, time.time() - started)))

        path, error = update_checker.download_update(
            url, None, _progress, self._download_cancel)
        self.msg_queue.put(("update_done", (path, error)))

    def _run_downloaded_installer(self):
        if not self._downloaded_path or not os.path.exists(self._downloaded_path):
            messagebox.showerror("Installer", "Installer not found. Please download again.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(self._downloaded_path)  # noqa: S606 — user-clicked, downloaded asset
            else:
                subprocess.Popen(["xdg-open", self._downloaded_path])  # noqa: S603,S607
        except Exception as exc:
            messagebox.showerror("Installer", f"Could not start installer: {exc}")


def run():
    root = ctk.CTk()
    app = RemoteDeskApp(root)
    root.mainloop()
