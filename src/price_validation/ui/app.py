"""
ui/app.py — main Tkinter dark-mode application window.
"""
from __future__ import annotations
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from price_validation.config import settings
from price_validation.config.paths import PRICING_TEMPLATE_DIR
from price_validation.ingestion.fetch import fetch_supplier
from price_validation.ingestion.loader import MONTHS, load_pricing_template, load_supplier_shipment
from price_validation.ingestion.loader import FEATURE_COLS_PT   # for index key labels
from price_validation.validation.compare import compare
from price_validation.report.writer import write_report

# --------------------------------------------------------------------------- #
# Dark-mode palette
# --------------------------------------------------------------------------- #
BG       = "#1e1e1e"
BG2      = "#2d2d2d"
BG3      = "#3c3c3c"
FG       = "#f0f0f0"
FG_DIM   = "#a0a0a0"
ACCENT   = "#0078d4"
ACCENT2  = "#005a9e"
BTN_FG   = "#ffffff"
ENTRY_BG = "#3a3a3a"
SEL_BG   = "#094771"
BORDER   = "#555555"

# Cross-check index options: label -> (pt_col_key, shp_col_key)
INDEX_OPTIONS: list[str] = [
    "HP/ODM Part#",
    "Color",
    "Product",
    "Size",
    "ODM & Site",
    "GTK Suppliers",
    "Platforms/Project",
]


def _style_button(btn: tk.Button, accent: bool = False) -> None:
    bg = ACCENT if accent else BG3
    btn.configure(
        bg=bg, fg=BTN_FG, activebackground=ACCENT2, activeforeground=BTN_FG,
        relief=tk.FLAT, cursor="hand2", padx=10, pady=4,
        font=("Segoe UI", 9),
    )


def _style_label(lbl: tk.Label, dim: bool = False) -> None:
    lbl.configure(bg=BG, fg=FG_DIM if dim else FG, font=("Segoe UI", 9))


def _style_entry(ent: tk.Entry) -> None:
    ent.configure(
        bg=ENTRY_BG, fg=FG, insertbackground=FG,
        relief=tk.FLAT, highlightthickness=1,
        highlightbackground=BORDER, highlightcolor=ACCENT,
        font=("Segoe UI", 9),
    )


# --------------------------------------------------------------------------- #
# Add Supplier Dialog
# --------------------------------------------------------------------------- #
class AddSupplierDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, on_save):
        super().__init__(parent)
        self.title("Add Supplier")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self._on_save = on_save
        self._build()
        self._center(parent)

    def _center(self, parent):
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w)//2}+{py + (ph - h)//2}")

    def _build(self):
        pad = {"padx": 16, "pady": 8}
        tk.Label(self, text="Supplier Name", bg=BG, fg=FG, font=("Segoe UI", 9)).grid(
            row=0, column=0, sticky="w", **pad)
        self._name_var = tk.StringVar()
        name_ent = tk.Entry(self, textvariable=self._name_var, width=32)
        _style_entry(name_ent)
        name_ent.grid(row=0, column=1, **pad)

        tk.Label(self, text="Shipment Folder", bg=BG, fg=FG, font=("Segoe UI", 9)).grid(
            row=1, column=0, sticky="w", **pad)
        self._path_var = tk.StringVar()
        path_frame = tk.Frame(self, bg=BG)
        path_frame.grid(row=1, column=1, **pad, sticky="ew")
        path_ent = tk.Entry(path_frame, textvariable=self._path_var, width=26)
        _style_entry(path_ent)
        path_ent.pack(side=tk.LEFT)
        browse_btn = tk.Button(path_frame, text="Browse…",
                               command=self._browse)
        _style_button(browse_btn)
        browse_btn.pack(side=tk.LEFT, padx=(6, 0))

        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(4, 12))
        save_btn = tk.Button(btn_frame, text="Save", command=self._save)
        _style_button(save_btn, accent=True)
        save_btn.pack(side=tk.LEFT, padx=6)
        cancel_btn = tk.Button(btn_frame, text="Cancel", command=self.destroy)
        _style_button(cancel_btn)
        cancel_btn.pack(side=tk.LEFT, padx=6)

    def _browse(self):
        folder = filedialog.askdirectory(title="Select Shipment Folder")
        if folder:
            self._path_var.set(folder)

    def _save(self):
        name = self._name_var.get().strip()
        path = self._path_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Supplier name cannot be empty.", parent=self)
            return
        if not path:
            messagebox.showerror("Error", "Please select a shipment folder.", parent=self)
            return
        self._on_save(name, path)
        self.destroy()


# --------------------------------------------------------------------------- #
# Validate Config Dialog
# --------------------------------------------------------------------------- #
class ValidateConfigDialog(tk.Toplevel):
    """Ask FY, months, and cross-check index keys before running validation."""

    def __init__(self, parent: tk.Tk, on_start):
        super().__init__(parent)
        self.title("Validate — Configuration")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self._on_start = on_start
        self._build()
        self._center(parent)

    def _center(self, parent):
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w)//2}+{py + (ph - h)//2}")

    def _build(self):
        pad = {"padx": 16, "pady": 6}

        # FY input
        tk.Label(self, text="Fiscal Year (e.g. 25):", bg=BG, fg=FG,
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", **pad)
        self._fy_var = tk.StringVar()
        fy_ent = tk.Entry(self, textvariable=self._fy_var, width=8)
        _style_entry(fy_ent)
        fy_ent.grid(row=0, column=1, sticky="w", **pad)

        # Month checkboxes
        tk.Label(self, text="Months to validate:", bg=BG, fg=FG,
                 font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="nw", **pad)
        month_frame = tk.Frame(self, bg=BG)
        month_frame.grid(row=1, column=1, sticky="w", **pad)
        self._month_vars: dict[str, tk.BooleanVar] = {}
        # Jan–Nov only (12 months but spec says Jan to Nov)
        valid_months = MONTHS[:11]  # Jan..Nov
        for i, mo in enumerate(valid_months):
            var = tk.BooleanVar()
            cb = tk.Checkbutton(
                month_frame, text=mo, variable=var,
                bg=BG, fg=FG, selectcolor=BG3, activebackground=BG,
                activeforeground=FG, font=("Segoe UI", 9),
            )
            cb.grid(row=i // 6, column=i % 6, sticky="w", padx=4)
            self._month_vars[mo] = var

        # Cross-check index
        tk.Label(self, text="Cross-check Index\n(select ≥ 2):", bg=BG, fg=FG,
                 font=("Segoe UI", 9, "bold"), justify="left").grid(
            row=2, column=0, sticky="nw", **pad)
        idx_frame = tk.Frame(self, bg=BG)
        idx_frame.grid(row=2, column=1, sticky="w", **pad)
        self._index_vars: dict[str, tk.BooleanVar] = {}
        for i, key in enumerate(INDEX_OPTIONS):
            var = tk.BooleanVar()
            cb = tk.Checkbutton(
                idx_frame, text=key, variable=var,
                bg=BG, fg=FG, selectcolor=BG3, activebackground=BG,
                activeforeground=FG, font=("Segoe UI", 9),
            )
            cb.grid(row=i, column=0, sticky="w")
            self._index_vars[key] = var

        # Allow options
        allow_frame = tk.Frame(self, bg=BG)
        allow_frame.grid(row=3, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 0))
        tk.Label(allow_frame, text="Allow (skip reporting):", bg=BG, fg=FG,
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        self._allow_pt_only_var = tk.BooleanVar(value=False)
        cb_pt_only = tk.Checkbutton(
            allow_frame,
            text="Master Table has entry but Supplier Shipment doesn't",
            variable=self._allow_pt_only_var,
            bg=BG, fg=FG, selectcolor=BG3, activebackground=BG, activeforeground=FG,
            font=("Segoe UI", 9),
        )
        cb_pt_only.pack(side=tk.LEFT, padx=(8, 0))

        # Buttons
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=(8, 14))
        start_btn = tk.Button(btn_frame, text="Start Validate", command=self._start)
        _style_button(start_btn, accent=True)
        start_btn.pack(side=tk.LEFT, padx=6)
        cancel_btn = tk.Button(btn_frame, text="Cancel", command=self.destroy)
        _style_button(cancel_btn)
        cancel_btn.pack(side=tk.LEFT, padx=6)

    def _start(self):
        fy = self._fy_var.get().strip()
        # Validate FY: exactly 2 digits
        if not (len(fy) == 2 and fy.isdigit()):
            messagebox.showerror(
                "Invalid FY",
                "Please enter exactly 2 digits for Fiscal Year (e.g. 25).",
                parent=self,
            )
            return

        months = [mo for mo, var in self._month_vars.items() if var.get()]
        if not months:
            messagebox.showerror("No Months", "Please select at least one month.", parent=self)
            return

        index_keys = [k for k, var in self._index_vars.items() if var.get()]
        if len(index_keys) < 2:
            messagebox.showerror(
                "Index Keys", "Please select at least 2 cross-check index fields.", parent=self
            )
            return

        allow_pt_only = self._allow_pt_only_var.get()
        self.destroy()
        self._on_start(fy, months, index_keys, allow_pt_only)


# --------------------------------------------------------------------------- #
# Main Application Window
# --------------------------------------------------------------------------- #
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Price Validation Tool")
        self.configure(bg=BG)
        self.minsize(900, 500)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._cfg = settings.load()
        self._supplier_rows: list[dict] = []  # UI row state per supplier
        self._build_ui()
        self._load_suppliers()

    def _on_close(self):
        self.destroy()
        sys.exit(0)

    # ---------------------------------------------------------------------- #
    # UI construction
    # ---------------------------------------------------------------------- #
    def _build_ui(self):
        # ── Top toolbar ──
        toolbar = tk.Frame(self, bg=BG2, pady=8)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        title_lbl = tk.Label(toolbar, text="Price Validation Tool",
                             bg=BG2, fg=FG, font=("Segoe UI", 13, "bold"))
        title_lbl.pack(side=tk.LEFT, padx=16)

        self._validate_btn = tk.Button(toolbar, text="Validate",
                                       command=self._on_validate)
        _style_button(self._validate_btn, accent=True)
        self._validate_btn.pack(side=tk.RIGHT, padx=8)

        self._fetch_btn = tk.Button(toolbar, text="Fetch Data",
                                    command=self._on_fetch)
        _style_button(self._fetch_btn, accent=True)
        self._fetch_btn.pack(side=tk.RIGHT, padx=4)

        add_btn = tk.Button(toolbar, text="Add Supplier",
                            command=self._on_add_supplier)
        _style_button(add_btn)
        add_btn.pack(side=tk.RIGHT, padx=4)

        clear_files_btn = tk.Button(toolbar, text="Clear Files",
                                    command=self._on_clear_files)
        _style_button(clear_files_btn)
        clear_files_btn.pack(side=tk.RIGHT, padx=4)

        # Select-all toggle
        self._select_all_var = tk.BooleanVar(value=True)
        sel_all_cb = tk.Checkbutton(
            toolbar, text="Select All",
            variable=self._select_all_var,
            command=self._on_select_all,
            bg=BG2, fg=FG, selectcolor=BG3,
            activebackground=BG2, activeforeground=FG,
            font=("Segoe UI", 9),
        )
        sel_all_cb.pack(side=tk.RIGHT, padx=8)

        # ── Pricing template path row ──
        pt_frame = tk.Frame(self, bg=BG, pady=4)
        pt_frame.pack(side=tk.TOP, fill=tk.X, padx=16)
        tk.Label(pt_frame, text="Pricing Template:", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self._pt_path_var = tk.StringVar(
            value=self._cfg.get("pricing_template_path", ""))
        pt_ent = tk.Entry(pt_frame, textvariable=self._pt_path_var, width=60)
        _style_entry(pt_ent)
        pt_ent.pack(side=tk.LEFT, padx=(8, 4))
        browse_pt = tk.Button(pt_frame, text="Browse…",
                              command=self._browse_pt)
        _style_button(browse_pt)
        browse_pt.pack(side=tk.LEFT)

        sep = tk.Frame(self, bg=BORDER, height=1)
        sep.pack(fill=tk.X, padx=8, pady=(4, 0))

        # ── Supplier list header ──
        hdr = tk.Frame(self, bg=BG3)
        hdr.pack(fill=tk.X, padx=8, pady=(2, 0))
        tk.Label(hdr, text="", bg=BG3, width=3).pack(side=tk.LEFT)
        tk.Label(hdr, text="Supplier Name", bg=BG3, fg=FG,
                 font=("Segoe UI", 9, "bold"), width=18, anchor="w").pack(side=tk.LEFT)
        tk.Label(hdr, text="Shipment Folder", bg=BG3, fg=FG,
                 font=("Segoe UI", 9, "bold"), width=36, anchor="w").pack(side=tk.LEFT)
        tk.Label(hdr, text="", bg=BG3, width=8).pack(side=tk.RIGHT)  # remove btn
        tk.Label(hdr, text="Latest File", bg=BG3, fg=FG,
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Status bar (pack BOTTOM first so list frame fills the rest) ──
        self._status_var = tk.StringVar(value="Ready.")
        status_bar = tk.Label(self, textvariable=self._status_var,
                              bg=BG2, fg=FG_DIM, font=("Segoe UI", 8),
                              anchor="w", padx=8)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # ── Log panel ──
        log_outer = tk.Frame(self, bg=BG2)
        log_outer.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 2))
        log_hdr = tk.Frame(log_outer, bg=BG2)
        log_hdr.pack(fill=tk.X)
        tk.Label(log_hdr, text="Log", bg=BG2, fg=FG_DIM,
                 font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=4)
        clear_btn = tk.Button(log_hdr, text="Clear",
                              command=self._clear_log)
        _style_button(clear_btn)
        clear_btn.configure(font=("Segoe UI", 7), pady=1, padx=6)
        clear_btn.pack(side=tk.RIGHT, padx=4, pady=1)
        log_body = tk.Frame(log_outer, bg=BG)
        log_body.pack(fill=tk.X)
        log_scroll = tk.Scrollbar(log_body, orient=tk.VERTICAL)
        self._log_text = tk.Text(
            log_body, height=5, state=tk.DISABLED,
            bg="#141414", fg=FG, font=("Consolas", 8),
            relief=tk.FLAT, wrap=tk.WORD,
            yscrollcommand=log_scroll.set,
        )
        log_scroll.config(command=self._log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        # colour tags
        self._log_text.tag_configure("INFO",    foreground=FG_DIM)
        self._log_text.tag_configure("SUCCESS", foreground="#6fdb8c")
        self._log_text.tag_configure("WARN",    foreground="#ffd166")
        self._log_text.tag_configure("ERROR",   foreground="#ff6b6b")

        # ── Scrollable supplier list ──
        list_frame = tk.Frame(self, bg=BG)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        canvas = tk.Canvas(list_frame, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                 command=canvas.yview)
        self._supplier_frame = tk.Frame(canvas, bg=BG)
        self._supplier_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self._supplier_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _browse_pt(self):
        path = filedialog.askopenfilename(
            title="Select Pricing Template Excel",
            filetypes=[("Excel files", "*.xlsx *.xlsm"), ("All files", "*.*")],
            initialdir=str(PRICING_TEMPLATE_DIR),
        )
        if path:
            self._pt_path_var.set(path)
            self._cfg["pricing_template_path"] = path
            settings.save(self._cfg)

    # ---------------------------------------------------------------------- #
    # Supplier list management
    # ---------------------------------------------------------------------- #
    def _load_suppliers(self):
        for supplier in self._cfg.get("suppliers", []):
            self._add_supplier_row(supplier["name"], supplier["shipment_folder"])

    def _add_supplier_row(self, name: str, folder: str, fetched_file: str = ""):
        row_data = {
            "name": name,
            "folder": folder,
            "checked": tk.BooleanVar(value=True),
            "file_var": tk.StringVar(value=fetched_file),
        }
        self._supplier_rows.append(row_data)

        row_frame = tk.Frame(self._supplier_frame, bg=BG, pady=3)
        row_frame.pack(fill=tk.X, padx=4)
        row_data["frame"] = row_frame

        cb = tk.Checkbutton(
            row_frame, variable=row_data["checked"],
            bg=BG, fg=FG, selectcolor=BG3,
            activebackground=BG, activeforeground=FG,
        )
        cb.pack(side=tk.LEFT)

        tk.Label(row_frame, text=name, bg=BG, fg=FG,
                 font=("Segoe UI", 9), width=18, anchor="w").pack(side=tk.LEFT)
        tk.Label(row_frame, text=folder, bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 8), width=36, anchor="w",
                 wraplength=260).pack(side=tk.LEFT)

        remove_btn = tk.Button(
            row_frame, text="Remove",
            command=lambda rd=row_data: self._remove_supplier(rd),
        )
        _style_button(remove_btn)
        remove_btn.configure(font=("Segoe UI", 8), pady=2)
        remove_btn.pack(side=tk.RIGHT, padx=(4, 0))

        # Read-only entry fills remaining space — user can scroll to see full name
        file_ent = tk.Entry(
            row_frame, textvariable=row_data["file_var"],
            state="readonly", readonlybackground=BG2,
            fg=ACCENT, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=BORDER,
            font=("Segoe UI", 8),
        )
        file_ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))

        sep = tk.Frame(self._supplier_frame, bg=BORDER, height=1)
        sep.pack(fill=tk.X, padx=4)

    def _remove_supplier(self, row_data: dict):
        if not messagebox.askyesno("Remove", f"Remove supplier '{row_data['name']}'?"):
            return
        row_data["frame"].destroy()
        self._supplier_rows.remove(row_data)
        self._save_suppliers()

    def _save_suppliers(self):
        self._cfg["suppliers"] = [
            {"name": rd["name"], "shipment_folder": rd["folder"]}
            for rd in self._supplier_rows
        ]
        settings.save(self._cfg)

    def _on_select_all(self):
        state = self._select_all_var.get()
        for rd in self._supplier_rows:
            rd["checked"].set(state)

    # ---------------------------------------------------------------------- #
    # Clear cached shipment files
    # ---------------------------------------------------------------------- #
    def _on_clear_files(self):
        from price_validation.config.paths import SUPPLIER_SHIPMENTS_DIR
        selected = [rd for rd in self._supplier_rows if rd["checked"].get()]
        if not selected:
            messagebox.showinfo("No Selection", "No suppliers selected.")
            return
        names = ", ".join(rd["name"] for rd in selected)
        if not messagebox.askyesno(
            "Clear Files",
            f"Delete all cached shipment files for:\n{names}\n\nThis cannot be undone.",
        ):
            return
        total = 0
        for rd in selected:
            dest_dir = SUPPLIER_SHIPMENTS_DIR / rd["name"]
            if dest_dir.exists():
                files = list(dest_dir.iterdir())
                for f in files:
                    if f.is_file():
                        f.unlink()
                        total += 1
                        self._log(f"[{rd['name']}] Deleted: {f.name}", level="WARN")
            rd["file_var"].set("")
        self._set_status(f"Cleared {total} file(s).")
        self._log(f"Clear Files done — {total} file(s) removed.", level="SUCCESS")

    # ---------------------------------------------------------------------- #
    # Add Supplier
    # ---------------------------------------------------------------------- #
    def _on_add_supplier(self):
        def save_cb(name: str, folder: str):
            # Prevent duplicates
            existing_names = [rd["name"] for rd in self._supplier_rows]
            if name in existing_names:
                messagebox.showerror("Duplicate", f"Supplier '{name}' already exists.")
                return
            self._add_supplier_row(name, folder)
            self._save_suppliers()
            self._set_status(f"Supplier '{name}' added.")
            self._log(f"Supplier '{name}' added. Folder: {folder}")

        AddSupplierDialog(self, on_save=save_cb)

    # ---------------------------------------------------------------------- #
    # Fetch Data
    # ---------------------------------------------------------------------- #
    def _on_fetch(self):
        selected = [rd for rd in self._supplier_rows if rd["checked"].get()]
        if not selected:
            messagebox.showinfo("No Selection", "No suppliers selected.")
            return
        self._fetch_btn.configure(state=tk.DISABLED)
        self._set_status("Fetching data…")

        def _run():
            errors = []
            for rd in selected:
                try:
                    dest = fetch_supplier(rd["name"], rd["folder"])
                    if dest:
                        rd["file_var"].set(dest.name)
                        self.after(0, lambda n=rd["name"], d=dest: self._log(
                            f"[{n}] Fetched: {d.name}"))
                    else:
                        rd["file_var"].set("(no Excel found)")
                        errors.append(f"{rd['name']}: no Excel found in folder")
                        self.after(0, lambda n=rd["name"]: self._log(
                            f"[{n}] No Excel found in folder.", level="WARN"))
                except Exception as exc:
                    rd["file_var"].set("ERROR")
                    errors.append(f"{rd['name']}: {exc}")
                    self.after(0, lambda n=rd["name"], e=exc: self._log(
                        f"[{n}] Fetch error: {e}", level="ERROR"))

            def _done():
                self._fetch_btn.configure(state=tk.NORMAL)
                if errors:
                    self._set_status("Fetch complete with warnings.")
                    self._log(f"Fetch complete — {len(errors)} warning(s).", level="WARN")
                else:
                    self._set_status("Fetch complete.")
                    self._log("Fetch complete.", level="SUCCESS")

            self.after(0, _done)

        threading.Thread(target=_run, daemon=True).start()

    # ---------------------------------------------------------------------- #
    # Validate
    # ---------------------------------------------------------------------- #
    def _on_validate(self):
        selected = [rd for rd in self._supplier_rows if rd["checked"].get()]
        if not selected:
            messagebox.showinfo("No Selection", "No suppliers selected.")
            return

        pt_path = self._pt_path_var.get().strip()
        if not pt_path:
            messagebox.showerror(
                "No Pricing Template",
                "Please select the Pricing Template Excel file first.",
            )
            return

        def start_cb(fy: str, months: list[str], index_keys: list[str], allow_pt_only: bool):
            self._run_validation(selected, pt_path, fy, months, index_keys, allow_pt_only)

        ValidateConfigDialog(self, on_start=start_cb)

    def _run_validation(
        self,
        selected_rows: list[dict],
        pt_path: str,
        fy: str,
        months: list[str],
        index_keys: list[str],
        allow_pt_only: bool = False,
    ):
        self._validate_btn.configure(state=tk.DISABLED)
        self._set_status("Validating…")

        def _run():
            from pathlib import Path
            from price_validation.config.paths import SUPPLIER_SHIPMENTS_DIR
            errors: list[str] = []
            reports: list[str] = []

            for rd in selected_rows:
                supplier_name = rd["name"]
                file_name = rd["file_var"].get()
                if not file_name or file_name in ("(no Excel found)", "ERROR", ""):
                    err_msg = f"{supplier_name}: no fetched file available"
                    errors.append(err_msg)
                    self.after(0, lambda m=err_msg: self._log(m, level="WARN"))
                    continue

                shp_path = SUPPLIER_SHIPMENTS_DIR / supplier_name / file_name

                try:
                    # Load PT filtered to this supplier
                    self.after(0, lambda n=supplier_name: self._log(
                        f"[{n}] Loading master table (filtered by supplier)…"))
                    df_pt = load_pricing_template(
                        Path(pt_path), fy, months, index_keys, supplier_name=supplier_name
                    )
                    self.after(0, lambda n=supplier_name, r=len(df_pt): self._log(
                        f"[{n}] Master table loaded. {r} rows, months: {', '.join(months)}",
                        level="SUCCESS"))

                    self.after(0, lambda n=supplier_name: self._log(
                        f"[{n}] Loading shipment…"))
                    df_shp = load_supplier_shipment(shp_path, fy, months, index_keys)
                    self.after(0, lambda n=supplier_name, r=len(df_shp): self._log(
                        f"[{n}] Shipment loaded. {r} rows.", level="SUCCESS"))
                    mismatches = compare(df_pt, df_shp, months, supplier_name, allow_pt_only)
                    self.after(0, lambda n=supplier_name, c=len(mismatches): self._log(
                        f"[{n}] Compare done. {c} mismatch(es) found.",
                        level="WARN" if c else "SUCCESS"))
                    out = write_report(supplier_name, fy, months, mismatches)
                    reports.append(str(out))
                    self.after(0, lambda n=supplier_name, o=out: self._log(
                        f"[{n}] Report saved: {o}", level="SUCCESS"))
                except Exception as exc:
                    err_msg = f"{supplier_name}: {exc}"
                    errors.append(err_msg)
                    self.after(0, lambda m=err_msg: self._log(m, level="ERROR"))

            def _done():
                self._validate_btn.configure(state=tk.NORMAL)
                self._set_status(
                    f"Validation done. {len(reports)} report(s) saved."
                    + (f" {len(errors)} error(s)." if errors else "")
                )
                if errors:
                    self._log(
                        f"Validation complete — {len(reports)} report(s), {len(errors)} error(s).",
                        level="WARN",
                    )
                else:
                    self._log(
                        f"Validation complete — {len(reports)} report(s), no errors.",
                        level="SUCCESS",
                    )

            self.after(0, _done)

        threading.Thread(target=_run, daemon=True).start()

    # ---------------------------------------------------------------------- #
    # Helpers
    # ---------------------------------------------------------------------- #
    def _set_status(self, msg: str):
        self._status_var.set(msg)

    def _log(self, msg: str, level: str = "INFO") -> None:
        """Append a timestamped line to the log panel (thread-safe via after())."""
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"

        def _insert():
            self._log_text.configure(state=tk.NORMAL)
            self._log_text.insert(tk.END, line, level)
            self._log_text.see(tk.END)
            self._log_text.configure(state=tk.DISABLED)

        # If called from the main thread, run directly; otherwise schedule
        try:
            self._log_text.winfo_exists()
            _insert()
        except tk.TclError:
            pass

    def _clear_log(self) -> None:
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state=tk.DISABLED)

    def run(self):
        self._log("Application started.", level="INFO")
        self.mainloop()
