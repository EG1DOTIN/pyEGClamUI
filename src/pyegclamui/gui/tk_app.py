"""
pyEGClamUI Lite - Ultra-Lightweight Tkinter Desktop Antivirus Interface.

Designed for low-spec systems, vintage 32-bit machines, and resource-constrained environments:
  - RAM Footprint: ~12 MB - 18 MB idle (vs 90+ MB for Qt6)
  - Zero external pip requirements (Python standard library tkinter & ttk)
  - Full access to ClamScanner, ClamD TCP 3310 socket daemon, and Quarantine Vault
  - Real-time background threaded scanning with event queue UI safety
"""

import os
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Standard Library Tkinter
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    _tk_installed = True
except ImportError:
    class _TkConstantsFallback:
        END = "end"
        NORMAL = "normal"
        DISABLED = "disabled"
        X = "x"
        Y = "y"
        BOTH = "both"
        LEFT = "left"
        RIGHT = "right"
        W = "w"
        E = "e"
        CENTER = "center"
        HORIZONTAL = "horizontal"
        VERTICAL = "vertical"

        class TclError(Exception):
            pass

    tk = _TkConstantsFallback()
    filedialog = None
    messagebox = None
    ttk = None
    _tk_installed = False


# Core Engine Imports (pure decoupled standard library / core)
from pyegclamui.core.config import AppPaths, Config
from pyegclamui.core.detector import ClamEngineDetector
from pyegclamui.core.quarantine import QuarantineItem, QuarantineManager
from pyegclamui.core.scanner import ClamScanner, ScanReport, ScanType
from pyegclamui.core.system_capability import get_system_specs
from pyegclamui.core.updater import ClamUpdater


class TkinterApp:
    """Consolidated Single-Window Lite Desktop Antivirus Dashboard."""

    def __init__(self, root: Any, initial_path: Optional[str] = None):
        self.root = root
        self.root.title("pyEGClamUI Lite - Antivirus Desktop Interface")

        # Dynamically size and center window within display boundaries (handles 800x600/1024x768 VMs gracefully)
        try:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            win_w = min(840, max(640, int(screen_w * 0.90)))
            win_h = min(620, max(460, int(screen_h * 0.85)))
            self.root.geometry(f"{win_w}x{win_h}")
            self.root.minsize(min(640, win_w), min(460, win_h))
        except Exception:
            self.root.geometry("840x620")
            self.root.minsize(640, 460)

        # Set Window Icon if available
        self._set_window_icon()


        # Core Backend Subsystems
        self.config = Config.get_instance()
        self.detector = ClamEngineDetector()
        self.quarantine_vault = QuarantineManager()
        self.scanner = ClamScanner()
        self.updater = ClamUpdater()
        self.specs = get_system_specs()

        # State Variables
        self.is_scanning = False
        self.is_updating = False
        self.scan_start_time: float = 0.0
        self.scanned_count: int = 0
        self.threats_count: int = 0
        self.active_scan_thread: Optional[threading.Thread] = None
        self.event_queue: queue.Queue = queue.Queue()

        # Build UI Components
        self._configure_styles()
        self._build_header_card()
        self._build_notebook_tabs()
        self._build_status_footer()

        # Setup periodic event queue polling for thread-safe UI updates
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(50, self._poll_event_queue)

        # Trigger auto-scan if initial path was provided via CLI
        if initial_path and os.path.exists(initial_path):
            self.root.after(300, lambda: self._start_custom_scan(initial_path))

    def _set_window_icon(self):
        """Sets application icon safely without crashing if image libraries differ."""
        try:
            icon_path = AppPaths.get_app_icon_path()
            if icon_path.exists():
                if sys.platform == "win32" and icon_path.suffix.lower() == ".ico":
                    self.root.iconbitmap(str(icon_path))
                else:
                    self._icon_img = tk.PhotoImage(file=str(icon_path))
                    self.root.iconphoto(False, self._icon_img)
        except Exception:
            pass


    def _configure_styles(self):
        """Sets up clean, modern ttk styles for the Lite interface."""
        self.style = ttk.Style(self.root)
        try:
            available_themes = self.style.theme_names()
            if "clam" in available_themes:
                self.style.theme_use("clam")
            elif "alt" in available_themes:
                self.style.theme_use("alt")
        except Exception:
            pass

    def _build_header_card(self):
        """Displays system capabilities, ClamAV engine status, and daemon mode."""
        header_frame = ttk.LabelFrame(self.root, text=" System Status & Engine Health ", padding=10)
        header_frame.pack(fill=tk.X, padx=12, pady=(10, 6))

        # Row 1: Engine & Daemon
        clamscan_path = self.detector.get_clamscan_path()
        engine_str = f"Installed ({Path(clamscan_path).name})" if clamscan_path else "Not Found"
        daemon_active, conn_type = self.detector.check_daemon_socket()
        daemon_str = f"Active ({conn_type})" if daemon_active else "Offline (Using Standard clamscan)"

        lbl_engine = ttk.Label(header_frame, text="Antivirus Engine:", font=("Helvetica", 9, "bold"))
        lbl_engine.grid(row=0, column=0, sticky=tk.W, padx=6, pady=2)
        val_engine = ttk.Label(header_frame, text=engine_str, foreground="#16a34a" if clamscan_path else "#dc2626")
        val_engine.grid(row=0, column=1, sticky=tk.W, padx=6, pady=2)

        lbl_daemon = ttk.Label(header_frame, text="Daemon Acceleration:", font=("Helvetica", 9, "bold"))
        lbl_daemon.grid(row=0, column=2, sticky=tk.W, padx=12, pady=2)
        val_daemon = ttk.Label(header_frame, text=daemon_str, foreground="#16a34a" if daemon_active else "#d97706")
        val_daemon.grid(row=0, column=3, sticky=tk.W, padx=6, pady=2)

        # Row 2: Architecture & Memory Allocation
        ram_info = f"{self.specs.get('ram_gb', 0)} GB RAM | {self.specs.get('machine', '')} ({'64-bit' if self.specs.get('is_64bit') else '32-bit'})"
        lbl_arch = ttk.Label(header_frame, text="Execution Profile:", font=("Helvetica", 9, "bold"))
        lbl_arch.grid(row=1, column=0, sticky=tk.W, padx=6, pady=2)
        val_arch = ttk.Label(header_frame, text=f"{ram_info} - Lite Mode (< 4.0GB / Low-RAM)")
        val_arch.grid(row=1, column=1, columnspan=3, sticky=tk.W, padx=6, pady=2)

    def _build_notebook_tabs(self):
        """Builds tabs for Scanner, Quarantine Vault, and Updates."""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        # 1. Scanner Tab
        self.tab_scan = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_scan, text="  🔍 Antivirus Scanner  ")
        self._build_scanner_tab()

        # 2. Quarantine Vault Tab
        self.tab_quarantine = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_quarantine, text="  🛡️ Quarantine Vault  ")
        self._build_quarantine_tab()

        # 3. Engine & Maintenance Tab
        self.tab_maintenance = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_maintenance, text="  🔄 Maintenance & Updates  ")
        self._build_maintenance_tab()

    def _build_scanner_tab(self):
        """Constructs scanner controls, live progress, and log view."""
        action_bar = ttk.Frame(self.tab_scan)
        action_bar.pack(fill=tk.X, pady=(0, 8))

        self.btn_quick = ttk.Button(action_bar, text="⚡ Quick Scan", command=self._start_quick_scan)
        self.btn_quick.pack(side=tk.LEFT, padx=4)

        self.btn_full = ttk.Button(action_bar, text="🔍 Full Scan", command=self._start_full_scan)
        self.btn_full.pack(side=tk.LEFT, padx=4)

        self.btn_custom = ttk.Button(action_bar, text="📂 Custom Scan...", command=self._browse_and_scan)
        self.btn_custom.pack(side=tk.LEFT, padx=4)

        self.btn_stop = ttk.Button(action_bar, text="🛑 Stop Scan", command=self._stop_scan, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.RIGHT, padx=4)

        # Progress & Status Card
        prog_frame = ttk.LabelFrame(self.tab_scan, text=" Scan Progress ", padding=8)
        prog_frame.pack(fill=tk.X, pady=4)

        self.lbl_progress = ttk.Label(prog_frame, text="Ready to scan. Select a scan profile above.")
        self.lbl_progress.pack(fill=tk.X, pady=(0, 4))

        self.progressbar = ttk.Progressbar(prog_frame, mode="indeterminate")
        self.progressbar.pack(fill=tk.X, pady=2)

        self.lbl_stats = ttk.Label(prog_frame, text="Scanned: 0  |  Threats Detected: 0  |  Elapsed: 00:00:00")
        self.lbl_stats.pack(fill=tk.X, pady=(4, 0))

        # Real-time Log Stream
        log_frame = ttk.LabelFrame(self.tab_scan, text=" Live Scan Stream ", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        self.txt_log = tk.Text(log_frame, wrap=tk.NONE, height=12, bg="#1e1e1e", fg="#e0e0e0", font=("Courier", 9))
        scrollbar_y = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.txt_log.yview)
        scrollbar_x = ttk.Scrollbar(log_frame, orient=tk.HORIZONTAL, command=self.txt_log.xview)
        self.txt_log.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Tags for colored logging
        self.txt_log.tag_config("info", foreground="#94a3b8")
        self.txt_log.tag_config("clean", foreground="#4ade80")
        self.txt_log.tag_config("threat", foreground="#f87171", background="#450a0a")
        self.txt_log.tag_config("warn", foreground="#fbbf24")

    def _build_quarantine_tab(self):
        """Constructs quarantine viewer with restore and delete operations."""
        ctrl_frame = ttk.Frame(self.tab_quarantine)
        ctrl_frame.pack(fill=tk.X, pady=(0, 8))

        btn_refresh = ttk.Button(ctrl_frame, text="🔄 Refresh Vault", command=self._refresh_quarantine_view)
        btn_refresh.pack(side=tk.LEFT, padx=4)

        btn_restore = ttk.Button(ctrl_frame, text="↩️ Restore Selected", command=self._restore_quarantined)
        btn_restore.pack(side=tk.LEFT, padx=4)

        btn_delete = ttk.Button(ctrl_frame, text="🗑️ Delete Selected", command=self._delete_quarantined)
        btn_delete.pack(side=tk.LEFT, padx=4)

        # Treeview for quarantined threats
        tree_frame = ttk.Frame(self.tab_quarantine)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("id", "threat", "original_path", "date", "size")
        self.tree_q = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        self.tree_q.heading("id", text="Vault ID")
        self.tree_q.heading("threat", text="Detected Threat")
        self.tree_q.heading("original_path", text="Original File Location")
        self.tree_q.heading("date", text="Date Isolated")
        self.tree_q.heading("size", text="File Size")

        self.tree_q.column("id", width=90, anchor=tk.CENTER)
        self.tree_q.column("threat", width=190, anchor=tk.W)
        self.tree_q.column("original_path", width=340, anchor=tk.W)
        self.tree_q.column("date", width=140, anchor=tk.CENTER)
        self.tree_q.column("size", width=80, anchor=tk.E)

        q_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree_q.yview)
        self.tree_q.configure(yscrollcommand=q_scroll.set)
        q_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_q.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._refresh_quarantine_view()

    def _build_maintenance_tab(self):
        """Constructs signature updates and system diagnostic panel."""
        top_frame = ttk.LabelFrame(self.tab_maintenance, text=" Virus Signature Database ", padding=10)
        top_frame.pack(fill=tk.X, pady=(0, 8))

        fc_path = self.detector.get_freshclam_path()
        fc_str = str(fc_path) if fc_path else "Not Installed (Signatures will not auto-update)"
        lbl_fc = ttk.Label(top_frame, text="FreshClam Binary:")
        lbl_fc.grid(row=0, column=0, sticky=tk.W, padx=6, pady=4)
        val_fc = ttk.Label(top_frame, text=fc_str, font=("Courier", 9))
        val_fc.grid(row=0, column=1, sticky=tk.W, padx=6, pady=4)

        is_recent, status_msg = self.updater.is_database_recent()
        lbl_status = ttk.Label(top_frame, text="Database Status:")
        lbl_status.grid(row=1, column=0, sticky=tk.W, padx=6, pady=4)
        val_status = ttk.Label(top_frame, text=status_msg, foreground="#16a34a" if is_recent else "#d97706")
        val_status.grid(row=1, column=1, sticky=tk.W, padx=6, pady=4)

        self.btn_update_sig = ttk.Button(top_frame, text="🔄 Update Virus Signatures Now", command=self._start_signature_update)
        self.btn_update_sig.grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=6, pady=8)

        # Maintenance Console
        console_frame = ttk.LabelFrame(self.tab_maintenance, text=" Maintenance Output Stream ", padding=6)
        console_frame.pack(fill=tk.BOTH, expand=True)

        self.txt_maint = tk.Text(console_frame, wrap=tk.NONE, height=10, bg="#1e1e1e", fg="#e0e0e0", font=("Courier", 9))
        m_scroll = ttk.Scrollbar(console_frame, orient=tk.VERTICAL, command=self.txt_maint.yview)
        self.txt_maint.configure(yscrollcommand=m_scroll.set)
        m_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_maint.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _build_status_footer(self):
        """Footer providing feedback status."""
        self.footer_frame = ttk.Frame(self.root, padding=(12, 4))
        self.footer_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.lbl_footer = ttk.Label(
            self.footer_frame,
            text=f"pyEGClamUI Lite | {self.specs.get('os_release', '')} | 100% Free & Open-Source (GPL-3.0)",
            foreground="#64748b",
            font=("Helvetica", 8),
        )
        self.lbl_footer.pack(side=tk.LEFT)

    # --------------------------------------------------------------------------
    # Scanner Operations
    # --------------------------------------------------------------------------
    def _start_quick_scan(self):
        paths = self.scanner.get_quick_scan_paths()
        target = paths if paths else [str(Path.home())]
        self._launch_scan(target, ScanType.QUICK_SCAN)

    def _start_full_scan(self):
        targets = self.scanner.get_system_drives()
        self._launch_scan(targets, ScanType.FULL_SCAN)

    def _browse_and_scan(self):
        choice = filedialog.askdirectory(title="Select Folder to Scan with pyEGClamUI")
        if choice:
            self._launch_scan([choice], f"{ScanType.CUSTOM_SCAN} ({Path(choice).name})")

    def _start_custom_scan(self, path: str):
        self._launch_scan([path], f"Target Scan ({Path(path).name})")

    def _launch_scan(self, targets: list[str], title: str):
        if self.is_scanning:
            return

        self.is_scanning = True
        self.scan_start_time = time.time()
        self.scanned_count = 0
        self.threats_count = 0

        self.btn_quick.config(state=tk.DISABLED)
        self.btn_full.config(state=tk.DISABLED)
        self.btn_custom.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.progressbar.start(10)

        self.txt_log.delete("1.0", tk.END)
        self._log_msg(f"=== Starting {title} ===", "info")
        self._log_msg(f"Target paths: {', '.join(targets)}", "info")

        def _worker():
            def _on_progress(file_path: str):
                self.event_queue.put(("progress_file", file_path))

            def _on_threat(threat_info: dict):
                self.event_queue.put(("threat_found", threat_info))

            def _on_status(status_str: str):
                self.event_queue.put(("status_msg", status_str))

            report = self.scanner.scan(
                scan_type=title,
                targets=targets,
                on_progress=_on_progress,
                on_threat=_on_threat,
                on_status=_on_status,
            )
            self.event_queue.put(("scan_done", report))

        self.active_scan_thread = threading.Thread(target=_worker, daemon=True)
        self.active_scan_thread.start()

    def _show_info(self, title: str, message: str):
        if messagebox:
            messagebox.showinfo(title, message)

    def _show_warning(self, title: str, message: str):
        if messagebox:
            messagebox.showwarning(title, message)

    def _show_error(self, title: str, message: str):
        if messagebox:
            messagebox.showerror(title, message)

    def _ask_yes_no(self, title: str, message: str) -> bool:
        if messagebox:
            return bool(messagebox.askyesno(title, message))
        return True

    def _stop_scan(self):
        if not self.is_scanning:
            return
        self.is_scanning = False
        self.scanner.stop()
        self.btn_stop.config(state=tk.DISABLED)
        self.lbl_progress.config(text="Stopping scan...")
        self._log_msg("Scan stop requested by user.", "warn")

    # --------------------------------------------------------------------------
    # Quarantine Operations
    # --------------------------------------------------------------------------
    def _refresh_quarantine_view(self):
        for item in self.tree_q.get_children():
            self.tree_q.delete(item)

        items = self.quarantine_vault.list_items()
        for it in items:
            q_id = it.item_id
            threat = it.threat_name
            orig = it.original_path
            date_str = it.quarantine_date
            size_bytes = it.file_size_bytes
            size_kb = f"{size_bytes // 1024} KB" if size_bytes else "0 KB"
            self.tree_q.insert("", tk.END, values=(q_id, threat, orig, date_str, size_kb))

    def _restore_quarantined(self):
        selected = self.tree_q.selection()
        if not selected:
            self._show_info("Quarantine", "Please select an item to restore.")
            return

        raw_values = self.tree_q.item(selected[0], "values")
        values = raw_values.get("values", ()) if isinstance(raw_values, dict) else raw_values
        if not values or len(values) < 3:
            return
        q_id = values[0]
        orig_path = values[2]
        if self._ask_yes_no("Restore File", f"Are you sure you want to restore:\n{orig_path}?\nEnsure this file is safe."):
            ok, msg = self.quarantine_vault.restore_item(q_id)
            if ok:
                self._show_info("Quarantine", f"File restored successfully:\n{msg}")
                self._refresh_quarantine_view()
            else:
                self._show_error("Quarantine", f"Failed to restore file:\n{msg}")

    def _delete_quarantined(self):
        selected = self.tree_q.selection()
        if not selected:
            self._show_info("Quarantine", "Please select an item to delete.")
            return

        raw_values = self.tree_q.item(selected[0], "values")
        values = raw_values.get("values", ()) if isinstance(raw_values, dict) else raw_values
        if not values or len(values) < 3:
            return
        q_id = values[0]
        orig_path = values[2]
        if self._ask_yes_no("Delete Permanently", f"Permanently delete {orig_path} from vault?\nThis cannot be undone."):
            ok, msg = self.quarantine_vault.delete_item(q_id)
            if ok:
                self._show_info("Quarantine", f"Item deleted from vault:\n{msg}")
                self._refresh_quarantine_view()
            else:
                self._show_error("Quarantine", f"Failed to delete item:\n{msg}")

    # --------------------------------------------------------------------------
    # Maintenance & Signatures
    # --------------------------------------------------------------------------
    def _start_signature_update(self):
        if self.is_updating:
            return

        self.is_updating = True
        self.btn_update_sig.config(state=tk.DISABLED)
        self.txt_maint.delete("1.0", tk.END)
        self._log_maint("Starting virus definition update via freshclam...")

        def _update_worker():
            def _log_cb(line: str):
                self.event_queue.put(("maint_log", line))

            success, msg = self.updater.run_update(on_line=_log_cb)
            status_text = "Virus definitions up to date!" if success else f"Update result: {msg}"
            self.event_queue.put(("update_done", status_text))

        threading.Thread(target=_update_worker, daemon=True).start()

    # --------------------------------------------------------------------------
    # Event Queue Polling
    # --------------------------------------------------------------------------
    def _poll_event_queue(self):
        try:
            while True:
                msg = self.event_queue.get_nowait()
                ev_type = msg[0]

                if ev_type == "progress_file":
                    file_path = msg[1]
                    self.scanned_count += 1
                    elapsed = int(time.time() - self.scan_start_time)
                    elapsed_str = f"{elapsed // 3600:02d}:{(elapsed % 3600) // 60:02d}:{elapsed % 60:02d}"
                    self.lbl_stats.config(
                        text=f"Scanned: {self.scanned_count}  |  Threats Detected: {self.threats_count}  |  Elapsed: {elapsed_str}"
                    )
                    self.lbl_progress.config(text=f"Scanning: {Path(file_path).name}")
                    self._log_msg(f"🟢 OK: {file_path}", "clean")

                elif ev_type == "threat_found":
                    t_info = msg[1]
                    self.threats_count += 1
                    file_path = t_info.get("path", "")
                    threat_name = t_info.get("threat", "Malware")
                    action = t_info.get("action", "")
                    elapsed = int(time.time() - self.scan_start_time)
                    elapsed_str = f"{elapsed // 3600:02d}:{(elapsed % 3600) // 60:02d}:{elapsed % 60:02d}"
                    self.lbl_stats.config(
                        text=f"Scanned: {self.scanned_count}  |  Threats Detected: {self.threats_count}  |  Elapsed: {elapsed_str}"
                    )
                    self._log_msg(f"🔴 THREAT DETECTED: {file_path} [{threat_name}] -> {action}", "threat")

                elif ev_type == "status_msg":
                    self.lbl_progress.config(text=msg[1])

                elif ev_type == "scan_done":
                    report: ScanReport = msg[1]
                    self.progressbar.stop()
                    self.is_scanning = False
                    self.btn_quick.config(state=tk.NORMAL)
                    self.btn_full.config(state=tk.NORMAL)
                    self.btn_custom.config(state=tk.NORMAL)
                    self.btn_stop.config(state=tk.DISABLED)

                    status = "Scan cancelled." if report.cancelled else "Scan completed."
                    self.lbl_progress.config(text=status)

                    summary = (
                        f"=== {status} in {report.duration_seconds()}s ===\n"
                        f"Total Files Scanned: {report.scanned_files} | Threats Found: {report.threats_found}"
                    )
                    self._log_msg(summary, "warn" if report.threats_found > 0 else "clean")

                    if report.threats_found > 0:
                        self._refresh_quarantine_view()
                        self._show_warning(
                            "Threats Detected",
                            f"Scan completed: {report.threats_found} threat(s) detected and remediated according to preferences."
                        )
                    else:
                        self._show_info("Scan Clean", "Scan completed. No malware found on target paths.")

                elif ev_type == "maint_log":
                    self._log_maint(msg[1])

                elif ev_type == "update_done":
                    self.is_updating = False
                    self.btn_update_sig.config(state=tk.NORMAL)
                    self._log_maint(msg[1])
                    self._show_info("Signatures Updated", msg[1])

        except queue.Empty:
            pass

        self.root.after(50, self._poll_event_queue)

    def _log_msg(self, msg: str, tag: str = "info"):
        self.txt_log.insert(tk.END, msg + "\n", tag)
        self.txt_log.see(tk.END)

    def _log_maint(self, msg: str):
        self.txt_maint.insert(tk.END, msg + "\n")
        self.txt_maint.see(tk.END)

    def _on_close(self):
        if self.is_scanning:
            if not self._ask_yes_no("Exit pyEGClamUI", "A scan is currently running. Stop scan and exit?"):
                return
            self.scanner.stop()
            self.is_scanning = False
        self.root.destroy()


def run_tkinter_app(scan_path: Optional[str] = None) -> int:
    """Launches pyEGClamUI Lite Tkinter GUI application."""
    if not _tk_installed or tk is None:
        print("\n" + "=" * 68)
        print("  pyEGClamUI Lite - Tkinter Framework Notice")
        print("=" * 68)
        print("  Tkinter is not installed in this Python environment.")
        if sys.platform.startswith("linux"):
            print("  To enable the pyEGClamUI Lite GUI on Debian/Ubuntu/antiX, run:")
            print("    sudo apt-get install -y python3-tk")
            print("  On Fedora/RHEL:")
            print("    sudo dnf install -y python3-tkinter")
            print("  On Arch Linux:")
            print("    sudo pacman -S --noconfirm tk")
        print("\n  The pyEGClamUI Core Antivirus Engine is fully operational via CLI:")
        print("    pyegclamui-scan --quick        (Fast ClamAV Scan)")
        print("    pyegclamui-scan --full         (Comprehensive System Scan)")
        print("    pyegclamui-scan --path <dir>   (Scan Custom Directory)")
        print("=" * 68 + "\n")
        return 1

    try:
        root = tk.Tk()
    except tk.TclError as err:
        print(f"\n[ERROR] Could not initialize graphical display: {err}")
        print("In headless or remote SSH environments without X11/Wayland, use the CLI scanner:")
        print("  pyegclamui-scan --quick / --full / --path <dir>")
        print("Or set up virtual frame buffer: xvfb-run pyegclamui\n")
        return 1

    app = TkinterApp(root, initial_path=scan_path)
    root.mainloop()
    return 0


def main() -> int:
    """Entry point for pyEGClamUI Lite."""
    path_arg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
    return run_tkinter_app(path_arg)


if __name__ == "__main__":
    sys.exit(main())
