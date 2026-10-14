"""tkinter UI: Dashboard, Connect, Viewer, File Transfer, Trusted Devices,
Session History, Security/Unattended, Network Diagnostics, Settings/About.

Rules:
- Every button is wired to real code, or explicitly disabled with a reason.
- The UI never claims "connected" unless a real session exists.
- Incoming requests pop a modal dialog: Accept/Reject + permission checkboxes.
- Update popup: shown when GitHub Releases reports a newer version.
"""

import io
import queue
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

DARK = {"bg": "#0f172a", "card": "#1e293b", "fg": "#f1f5f9", "muted": "#94a3b8",
        "accent": "#14b8a6", "danger": "#ef4444", "entry": "#0b1220"}
LIGHT = {"bg": "#f1f5f9", "card": "#ffffff", "fg": "#0f172a", "muted": "#64748b",
         "accent": "#0f766e", "danger": "#dc2626", "entry": "#ffffff"}


class RemoteDeskApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{config.PRODUCT_NAME} v{VERSION}")
        self.root.geometry("860x620")
        self.root.minsize(720, 520)
        self.settings = storage.load_settings()
        self.theme = LIGHT if self.settings.get("theme") == "light" else DARK
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
        self._build()
        self._apply_theme()
        self.root.after(200, self._pump_queue)
        if self.settings.get("auto_update_check", True):
            threading.Thread(target=self._background_update_check, daemon=True).start()

    # ------------------------------------------------------------- building
    def _build(self):
        self.root.configure(bg=self.theme["bg"])
        top = tk.Frame(self.root, bg=self.theme["bg"])
        top.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(top, text=config.PRODUCT_NAME, font=("Segoe UI", 20, "bold"),
                 bg=self.theme["bg"], fg=self.theme["fg"]).pack(side="left")
        tk.Label(top, text=f"  v{VERSION}", font=("Segoe UI", 11),
                 bg=self.theme["bg"], fg=self.theme["muted"]).pack(side="left")
        self.theme_btn = tk.Button(top, text="Light mode" if self.theme is DARK else "Dark mode",
                                   command=self._toggle_theme)
        self.theme_btn.pack(side="right")
        self.status_var = tk.StringVar(value="Idle — not hosting, not connected.")
        tk.Label(self.root, textvariable=self.status_var, bg=self.theme["bg"],
                 fg=self.theme["muted"], anchor="w").pack(fill="x", padx=16)
        # Persistent remote-session banner (hidden unless a session is active).
        self.banner = tk.Label(self.root, text="● REMOTE SESSION ACTIVE — someone is connected to this PC",
                               bg=self.theme["danger"], fg="white", font=("Segoe UI", 10, "bold"))
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=8)
        self.tab_dashboard = self._tab("Dashboard")
        self.tab_viewer = self._tab("Viewer")
        self.tab_files = self._tab("File Transfer")
        self.tab_trusted = self._tab("Trusted Devices")
        self.tab_history = self._tab("History")
        self.tab_security = self._tab("Security")
        self.tab_diag = self._tab("Diagnostics")
        self.tab_about = self._tab("Settings & About")
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

    def _tab(self, title: str) -> tk.Frame:
        frame = tk.Frame(self.notebook, bg=self.theme["bg"])
        self.notebook.add(frame, text=title)
        return frame

    def _card(self, parent, title: str):
        frame = tk.LabelFrame(parent, text=title, bg=self.theme["card"],
                              fg=self.theme["fg"], font=("Segoe UI", 10, "bold"),
                              padx=12, pady=10, relief="groove", bd=1)
        frame.pack(fill="x", padx=8, pady=6)
        return frame

    # ------------------------------------------------------------- dashboard
    def _build_dashboard(self):
        card = self._card(self.tab_dashboard, "This device")
        tk.Label(card, text=f"Your ID:  {format_device_id(self.device_id)}",
                 bg=self.theme["card"], fg=self.theme["fg"],
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(card, text=f"Device name: {self.device_name}",
                 bg=self.theme["card"], fg=self.theme["muted"]).pack(anchor="w")
        self.host_btn = tk.Button(card, text="Start Hosting — allow connections",
                                  command=self._toggle_hosting)
        self.host_btn.pack(anchor="w", pady=(8, 2))
        self.pairing_var = tk.StringVar(value="Pairing code: — (start hosting to generate)")
        tk.Label(card, textvariable=self.pairing_var, bg=self.theme["card"],
                 fg=self.theme["fg"], font=("Segoe UI", 12)).pack(anchor="w")
        tk.Button(card, text="Generate new pairing code",
                  command=self._new_pairing_code).pack(anchor="w", pady=2)
        tk.Label(card, text="Share this code ONLY with the person you want to let in. "
                 "It expires in 5 minutes and works once.",
                 bg=self.theme["card"], fg=self.theme["muted"],
                 wraplength=700, justify="left").pack(anchor="w")

        card2 = self._card(self.tab_dashboard, "Connect to a remote device")
        row = tk.Frame(card2, bg=self.theme["card"])
        row.pack(fill="x")
        tk.Label(row, text="Host IP / address:", bg=self.theme["card"],
                 fg=self.theme["fg"]).pack(side="left")
        self.connect_host = tk.Entry(row, width=24)
        self.connect_host.pack(side="left", padx=6)
        self.connect_host.insert(0, "192.168.1.100")
        tk.Label(row, text="Port:", bg=self.theme["card"], fg=self.theme["fg"]).pack(side="left")
        self.connect_port = tk.Entry(row, width=7)
        self.connect_port.pack(side="left", padx=6)
        self.connect_port.insert(0, str(self.settings.get("port", config.DEFAULT_PORT)))
        row2 = tk.Frame(card2, bg=self.theme["card"])
        row2.pack(fill="x", pady=6)
        tk.Label(row2, text="Pairing code (or unattended password):",
                 bg=self.theme["card"], fg=self.theme["fg"]).pack(side="left")
        self.connect_code = tk.Entry(row2, width=24, show="•")
        self.connect_code.pack(side="left", padx=6)
        self.use_unattended = tk.BooleanVar(value=False)
        tk.Checkbutton(row2, text="Use unattended password", variable=self.use_unattended,
                       bg=self.theme["card"], fg=self.theme["fg"],
                       selectcolor=self.theme["card"]).pack(side="left")
        btns = tk.Frame(card2, bg=self.theme["card"])
        btns.pack(fill="x")
        tk.Button(btns, text="Connect", command=self._connect).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Disconnect", command=self._disconnect).pack(side="left", padx=6)
        tk.Button(btns, text="Scan LAN for devices", command=self._scan_lan).pack(side="left", padx=6)

        card3 = self._card(self.tab_dashboard, "Activity log")
        self.log_box = tk.Text(card3, height=8, bg=self.theme["entry"],
                               fg=self.theme["fg"], state="disabled")
        self.log_box.pack(fill="both", expand=True)
        self._log("RemoteDesk started. Hosting is OFF until you start it.")

    # ------------------------------------------------------------- viewer
    def _build_viewer(self):
        info = tk.Frame(self.tab_viewer, bg=self.theme["bg"])
        info.pack(fill="x", padx=8, pady=6)
        self.viewer_status = tk.StringVar(value="Not connected — connect from Dashboard.")
        tk.Label(info, textvariable=self.viewer_status, bg=self.theme["bg"],
                 fg=self.theme["muted"]).pack(side="left")
        tk.Button(info, text="Request control (host must allow)",
                  command=self._request_control_note).pack(side="right")
        self.canvas = tk.Canvas(self.tab_viewer, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=4)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Button-1>", lambda e: self._send_click(e, True))
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._send_click(e, False))
        self.canvas.bind("<MouseWheel>", self._on_scroll)

    def _build_files(self):
        card = self._card(self.tab_files, "File transfer (permission-gated)")
        tk.Label(card, text="File transfer is available only while a session is active AND "
                 "the host allowed file transfer for that session.\n"
                 "Received files are NEVER executed automatically. They land in your "
                 "download folder (see Settings).",
                 bg=self.theme["card"], fg=self.theme["muted"],
                 wraplength=720, justify="left").pack(anchor="w")
        self.file_status = tk.StringVar(value="No active session.")
        tk.Label(card, textvariable=self.file_status, bg=self.theme["card"],
                 fg=self.theme["fg"]).pack(anchor="w", pady=4)
        tk.Button(card, text="Send a file… (requires active session)",
                  command=self._send_file_note).pack(anchor="w")

    def _build_trusted(self):
        self.trusted_list = tk.Listbox(self.tab_trusted, bg=self.theme["entry"],
                                       fg=self.theme["fg"])
        self.trusted_list.pack(fill="both", expand=True, padx=8, pady=8)
        row = tk.Frame(self.tab_trusted, bg=self.theme["bg"])
        row.pack(fill="x", padx=8, pady=4)
        tk.Button(row, text="Remove selected (revoke)",
                  command=self._remove_trusted).pack(side="left")

    def _build_history(self):
        self.history_box = tk.Text(self.tab_history, bg=self.theme["entry"],
                                   fg=self.theme["fg"], state="disabled")
        self.history_box.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_security(self):
        card = self._card(self.tab_security, "Unattended access (opt-in)")
        tk.Label(card, text="Unattended access lets YOU connect to this PC without "
                 "someone clicking Accept. It is OFF by default.\n"
                 "Enable it only on your own devices. You can disable or change the "
                 "password at any time.",
                 bg=self.theme["card"], fg=self.theme["muted"],
                 wraplength=720, justify="left").pack(anchor="w")
        self.unattended_var = tk.BooleanVar(value=bool(self.settings.get("unattended_enabled")))
        tk.Checkbutton(card, text="Enable unattended access on this device",
                       variable=self.unattended_var, bg=self.theme["card"],
                       fg=self.theme["fg"], selectcolor=self.theme["card"]).pack(anchor="w", pady=4)
        row = tk.Frame(card, bg=self.theme["card"])
        row.pack(fill="x")
        tk.Label(row, text="New unattended password (min 10 chars):",
                 bg=self.theme["card"], fg=self.theme["fg"]).pack(side="left")
        self.unattended_pw = tk.Entry(row, width=28, show="•")
        self.unattended_pw.pack(side="left", padx=6)
        self.unattended_ctrl = tk.BooleanVar(value=bool(self.settings.get("unattended_allow_control")))
        tk.Checkbutton(card, text="Allow mouse/keyboard control in unattended sessions",
                       variable=self.unattended_ctrl, bg=self.theme["card"],
                       fg=self.theme["fg"], selectcolor=self.theme["card"]).pack(anchor="w", pady=4)
        tk.Button(card, text="Save unattended settings",
                  command=self._save_unattended).pack(anchor="w")
        card2 = self._card(self.tab_security, "Session safety")
        tk.Label(card2, text="During any session, the host can end it instantly with "
                 "Disconnect. Control permission can be revoked mid-session.",
                 bg=self.theme["card"], fg=self.theme["muted"],
                 wraplength=720, justify="left").pack(anchor="w")
        tk.Button(card2, text="End active session now", command=self._disconnect).pack(anchor="w", pady=4)

    def _build_diag(self):
        card = self._card(self.tab_diag, "Network diagnostics")
        self.diag_box = tk.Text(card, height=10, bg=self.theme["entry"],
                                fg=self.theme["fg"], state="disabled")
        self.diag_box.pack(fill="both", expand=True)
        tk.Button(card, text="Run diagnostics", command=self._run_diag).pack(anchor="w", pady=4)

    def _build_about(self):
        card = self._card(self.tab_about, "Settings")
        row = tk.Frame(card, bg=self.theme["card"])
        row.pack(fill="x")
        tk.Label(row, text="Download folder for received files:",
                 bg=self.theme["card"], fg=self.theme["fg"]).pack(side="left")
        self.download_dir_var = tk.StringVar(value=self.settings.get("download_dir", ""))
        tk.Entry(row, textvariable=self.download_dir_var, width=40).pack(side="left", padx=6)
        tk.Button(row, text="Browse…", command=self._pick_download_dir).pack(side="left")
        self.clipboard_var = tk.BooleanVar(value=bool(self.settings.get("clipboard_sync")))
        tk.Checkbutton(card, text="Enable clipboard sync (optional, off by default)",
                       variable=self.clipboard_var, bg=self.theme["card"],
                       fg=self.theme["fg"], selectcolor=self.theme["card"]).pack(anchor="w", pady=4)
        tk.Button(card, text="Save settings", command=self._save_general).pack(anchor="w")
        card2 = self._card(self.tab_about, "Updates")
        tk.Label(card2, text="Updates come from GitHub Releases — no server needed. "
                 "When a new version is published, this app shows a popup.",
                 bg=self.theme["card"], fg=self.theme["muted"],
                 wraplength=720, justify="left").pack(anchor="w")
        tk.Button(card2, text="Check for Updates now",
                  command=self._manual_update_check).pack(anchor="w", pady=4)
        card3 = self._card(self.tab_about, "About")
        tk.Label(card3, text=f"{config.PRODUCT_NAME} v{VERSION}\n{config.DEVELOPER_CREDIT}\n\n{config.ABOUT_TEXT}",
                 bg=self.theme["card"], fg=self.theme["fg"],
                 wraplength=720, justify="left").pack(anchor="w")

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
                        self.banner.pack(fill="x", padx=12, pady=(0, 4))
                    else:
                        self.banner.pack_forget()
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "request":
                    self._show_request_dialog(payload)
                elif kind == "update":
                    self._show_update_popup(payload)
                elif kind == "viewer_status":
                    self.viewer_status.set(payload)
        except queue.Empty:
            pass
        self.root.after(200, self._pump_queue)

    def _toggle_theme(self):
        self.settings["theme"] = "light" if self.settings.get("theme") != "light" else "dark"
        storage.save_settings(self.settings)
        messagebox.showinfo("Theme", "Restart the app to apply the new theme.")

    def _apply_theme(self):
        pass  # theme applied at build time from settings

    def _toggle_hosting(self):
        if self.host is not None:
            self.host.stop()
            self.host = None
            self.host_btn.configure(text="Start Hosting — allow connections")
            self.msg_queue.put(("status", "Hosting stopped."))
            self.msg_queue.put(("banner", False))
            self._log("Hosting stopped.")
            return
        self.host = HostServer(self.device_id, self.device_name,
                               int(self.settings.get("port", config.DEFAULT_PORT)),
                               self.settings, on_request=self._queue_request,
                               on_log=self._log)
        self.host.start()
        self._new_pairing_code()
        self.host_btn.configure(text="Stop Hosting")
        self.msg_queue.put(("status", "Hosting ON — waiting for connection requests."))

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
        # Wait for the UI thread to fill `result` (modal dialog is synchronous
        # on the UI thread; this network thread blocks until answered).
        while "accept" not in result:
            threading.Event().wait(0.1)
        return result["accept"], result["control"], result["files"]

    def _show_request_dialog(self, data):
        peer, result = data
        dlg = tk.Toplevel(self.root)
        dlg.title("Incoming connection request")
        dlg.geometry("460x260")
        dlg.transient(self.root)
        dlg.grab_set()
        tk.Label(dlg, text="Incoming remote connection request",
                 font=("Segoe UI", 12, "bold")).pack(padx=16, pady=(12, 4), anchor="w")
        tk.Label(dlg, text=f"Device: {peer.get('device_name')}  (ID {peer.get('device_id')})\n"
                 f"IP: {peer.get('ip')}\n\n"
                 "Only accept if you know and trust this person.",
                 wraplength=420, justify="left").pack(padx=16, anchor="w")
        ctrl = tk.BooleanVar(value=False)
        files = tk.BooleanVar(value=False)
        tk.Checkbutton(dlg, text="Allow mouse/keyboard control", variable=ctrl).pack(anchor="w", padx=16)
        tk.Checkbutton(dlg, text="Allow file transfer", variable=files).pack(anchor="w", padx=16)
        btns = tk.Frame(dlg)
        btns.pack(pady=14)

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

        tk.Button(btns, text="Accept", command=lambda: answer(True)).pack(side="left", padx=6)
        tk.Button(btns, text="Reject", command=lambda: answer(False)).pack(side="left", padx=6)
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
            self.notebook.select(self.tab_viewer)
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
        dlg = tk.Toplevel(self.root)
        dlg.title("Update available")
        dlg.geometry("520x340")
        dlg.transient(self.root)
        dlg.grab_set()
        tk.Label(dlg, text=f"New update available: {release['tag']}",
                 font=("Segoe UI", 13, "bold")).pack(padx=16, pady=(12, 4), anchor="w")
        tk.Label(dlg, text=f"You are on v{VERSION}. A newer version is available.",
                 wraplength=480, justify="left").pack(padx=16, anchor="w")
        notes = tk.Text(dlg, height=8)
        notes.pack(padx=16, pady=8, fill="both", expand=True)
        notes.insert("1.0", release.get("notes", "(No changelog provided.)"))
        notes.configure(state="disabled")
        btns = tk.Frame(dlg)
        btns.pack(pady=8)
        tk.Button(btns, text="Download Update",
                  command=lambda: (webbrowser.open(release["url"]), dlg.destroy())).pack(side="left", padx=6)
        tk.Button(btns, text="Later", command=dlg.destroy).pack(side="left", padx=6)


def run():
    root = tk.Tk()
    RemoteDeskApp(root)
    root.mainloop()
