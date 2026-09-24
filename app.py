import tkinter as tk
from tkinter import filedialog, messagebox
from tkinterdnd2 import TkinterDnD, DND_FILES
from pathlib import Path
import zstandard as zstd
import hashlib
import threading
import time
import tarfile
import os
import json
from urllib.parse import urlparse


# ============================================================
# CONFIG
# ============================================================

CHUNK_SIZE = 4 * 1024 * 1024

# ============================================================
# COMPRESSION PROFILES
# ============================================================

COMPRESSION_PROFILES = {
    "FAST": 1,
    "BALANCED": 5,
    "MAXIMUM": 19,
}

class CompressionCancelled(Exception):
    """Raised when the user cancels an active compression operation."""
    pass

# ============================================================
# COLORS
# ============================================================

BG = "#050505"
PANEL = "#0D1117"

CYAN = "#00E5FF"
BLUE = "#2979FF"
GREEN = "#00E676"
PURPLE = "#B388FF"
YELLOW = "#FFD740"
ORANGE = "#FF9100"
RED = "#FF1744"
PINK = "#FF4081"

TEXT = "#80DEEA"
MUTED = "#78909C"


# ============================================================
# UTILITIES
# ============================================================

def format_size(size):

    units = ["B", "KB", "MB", "GB", "TB"]

    for unit in units:

        if size < 1024:
            return f"{size:.2f} {unit}"

        size /= 1024

    return f"{size:.2f} PB"


def sha256_file(path):

    sha = hashlib.sha256()

    with open(path, "rb") as f:

        while True:

            chunk = f.read(CHUNK_SIZE)

            if not chunk:
                break

            sha.update(chunk)

    return sha.hexdigest()


def calculate_folder_size(folder):

    total = 0

    for root, dirs, files in os.walk(folder):

        for name in files:

            try:
                total += (
                    Path(root) / name
                ).stat().st_size
            except OSError:
                pass

    return total


def get_file_origin(path):
    """Read Windows Mark-of-the-Web metadata when available.

    Windows may store Zone.Identifier metadata for downloaded files.
    This can identify a web source URL when that metadata exists. It is
    not a reliable way to identify the originating application for every file.
    """
    path = Path(path)

    if path.is_dir():
        return {
            "origin": "FOLDER",
            "source": "Not applicable",
            "referrer": "Not available",
            "zone": "Not applicable",
            "has_metadata": False,
            "host_url": "",
        }

    zone_map = {
        "0": "Local machine",
        "1": "Local intranet",
        "2": "Trusted sites",
        "3": "Internet / Web download",
        "4": "Restricted sites",
    }

    zone_data = {}

    if os.name == "nt":
        try:
            with open(
                str(path) + ":Zone.Identifier",
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as stream:
                for line in stream:
                    line = line.strip()
                    if "=" in line:
                        key, value = line.split("=", 1)
                        zone_data[key.strip()] = value.strip()
        except (OSError, ValueError):
            pass

    zone_id = zone_data.get("ZoneId", "")
    host_url = zone_data.get("HostUrl", "")
    referrer_url = zone_data.get("ReferrerUrl", "")

    if host_url:
        try:
            parsed = urlparse(host_url)
            host = parsed.netloc or host_url
        except ValueError:
            host = host_url

        origin = "WEB DOWNLOAD"
        source = host
    elif zone_id in zone_map:
        origin = zone_map[zone_id].upper()
        source = "Source URL not recorded"
    else:
        origin = "SOURCE UNKNOWN"
        source = "No Windows source metadata"

    return {
        "origin": origin,
        "source": source,
        "referrer": referrer_url or "Not recorded",
        "zone": zone_map.get(zone_id, "No Zone.Identifier metadata"),
        "has_metadata": bool(zone_data),
        "host_url": host_url,
    }


# ============================================================
# PROGRESS FILE READER
# ============================================================

class ProgressReader:

    def __init__(
        self,
        file_object,
        callback
    ):

        self.file = file_object
        self.callback = callback

    def read(self, size=-1):

        data = self.file.read(size)

        if data:
            self.callback(len(data))

        return data

    def close(self):
        self.file.close()


# ============================================================
# NOVA COMPRESSOR
# ============================================================

class NovaCompressor:

    def __init__(self, root):

        self.root = root

        self.root.title(
            "NOVA COMPRESSOR"
        )

        # Maximized window
        self.root.state("zoomed")

        self.root.configure(
            bg=BG
        )

        self.selected_path = None
        self.output_path = None
        self.is_running = False
        self.validate_button = None

        # Phase 3 / Step 2:
        # Safe cancellation signal for background operations.
        self.cancel_event = threading.Event()

        # Phase 3 / Step 7: persistent application settings.
        self.settings_file = Path(__file__).with_name("nova_settings.json")
        self.settings_default_profile = "BALANCED"
        self.settings_default_output = ""
        self.load_settings()

        self.compression_profile = tk.StringVar(
            value=self.settings_default_profile
        )
        self.history = []
        self.history_list = None
        self.history_count_label = None
        self.history_nav = None
        self.settings_nav = None
        self.settings_profile_var = None
        self.settings_output_var = None
        self.settings_status_label = None

        # Phase 4 / Step 2 Part 1: operation queue UI state.
        self.queue_items = []
        self.queue_list = None
        self.queue_count_label = None
        self.queue_status_label = None
        self.queue_remove_button = None
        self.queue_start_button = None
        self.queue_stop_button = None
        self.queue_running = False

        # Phase 4 / Step 3: compression analytics for the current session.
        self.analytics_lock = threading.Lock()
        self.analytics = {
            "success": 0,
            "failed": 0,
            "cancelled": 0,
            "original_bytes": 0,
            "compressed_bytes": 0,
            "saved_bytes": 0,
            "total_time": 0.0,
            "reduction_sum": 0.0,
            "ratio_sum": 0.0,
            "last_operation": "—",
        }
        self.active_compression = False
        self.analytics_values = {}

        # Phase 3 / Step 8: selected file/folder information panel.
        self.info_name_value = None
        self.info_type_value = None
        self.info_size_value = None
        self.info_location_value = None
        self.info_created_value = None
        self.info_modified_value = None
        self.info_sha_value = None
        self.info_count_value = None
        self.info_origin_value = None
        self.info_source_value = None
        self.info_zone_value = None
        self.info_analyze_button = None
        self.info_copy_sha_button = None
        self.info_current_path = None

        if self.settings_default_output:
            default_output = Path(self.settings_default_output)
            if default_output.exists() and default_output.is_dir():
                self.output_path = default_output
            else:
                self.settings_default_output = ""

        self.build_ui()

        if self.settings_default_profile != "BALANCED" or self.settings_default_output:
            self.status_label.config(
                text="● DEFAULT SETTINGS LOADED",
                fg=PURPLE
            )


    # ========================================================
    # UI
    # ========================================================

    def build_ui(self):

        # ========================================================
        # WEB-STYLE DASHBOARD UI
        # ========================================================

        # Global window
        self.root.configure(bg="#070A0F")
        self.root.minsize(1100, 700)

        # --------------------------------------------------------
        # THEME
        # --------------------------------------------------------
        WEB_BG = "#070A0F"
        SIDEBAR = "#0B1018"
        CARD = "#0F1621"
        CARD_2 = "#111B28"
        BORDER = "#1B2A3A"
        WHITE = "#F5F7FA"
        SOFT = "#A9B4C2"

        # --------------------------------------------------------
        # ROOT LAYOUT
        # --------------------------------------------------------
        shell = tk.Frame(self.root, bg=WEB_BG)
        shell.pack(fill="both", expand=True)

        # ========================================================
        # SIDEBAR
        # ========================================================
        sidebar = tk.Frame(
            shell,
            bg=SIDEBAR,
            width=245,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Brand
        brand = tk.Frame(sidebar, bg=SIDEBAR)
        brand.pack(fill="x", padx=22, pady=(25, 30))

        tk.Label(
            brand,
            text="NOVA",
            font=("Segoe UI", 25, "bold"),
            bg=SIDEBAR,
            fg=CYAN
        ).pack(anchor="w")

        tk.Label(
            brand,
            text="COMPRESSOR",
            font=("Segoe UI", 10, "bold"),
            bg=SIDEBAR,
            fg=PURPLE
        ).pack(anchor="w", pady=(0, 3))

        tk.Label(
            brand,
            text="ZSTD FILE INTELLIGENCE",
            font=("Segoe UI", 8, "bold"),
            bg=SIDEBAR,
            fg=MUTED
        ).pack(anchor="w")

        # Navigation
        tk.Label(
            sidebar,
            text="WORKSPACE",
            font=("Segoe UI", 8, "bold"),
            bg=SIDEBAR,
            fg=MUTED
        ).pack(anchor="w", padx=22, pady=(0, 10))

        def nav_item(text, color=WHITE):
            frame = tk.Frame(sidebar, bg=SIDEBAR, height=42)
            frame.pack(fill="x", padx=12, pady=2)
            frame.pack_propagate(False)

            tk.Label(
                frame,
                text=text,
                font=("Segoe UI", 10, "bold"),
                bg=SIDEBAR,
                fg=color,
                anchor="w"
            ).pack(fill="both", padx=12)
            return frame

        nav_item("▣   Dashboard", CYAN)
        nav_item("⇩   Compress")
        nav_item("⇧   Decompress")
        self.history_nav = nav_item("◷   Recent Operations")
        self.settings_nav = nav_item("⚙   Settings")

        # Engine card
        engine_card = tk.Frame(
            sidebar,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        engine_card.pack(side="bottom", fill="x", padx=14, pady=18)

        tk.Label(
            engine_card,
            text="ENGINE STATUS",
            font=("Segoe UI", 8, "bold"),
            bg=CARD,
            fg=MUTED
        ).pack(anchor="w", padx=14, pady=(12, 4))

        tk.Label(
            engine_card,
            text="●  ONLINE",
            font=("Segoe UI", 10, "bold"),
            bg=CARD,
            fg=GREEN
        ).pack(anchor="w", padx=14)

        tk.Label(
            engine_card,
            text="Adaptive ZSTD  •  SHA-256",
            font=("Segoe UI", 8),
            bg=CARD,
            fg=SOFT
        ).pack(anchor="w", padx=14, pady=(2, 12))

        # ========================================================
        # MAIN AREA
        # ========================================================
        main = tk.Frame(shell, bg=WEB_BG)
        main.pack(side="left", fill="both", expand=True)

        # --------------------------------------------------------
        # TOP BAR
        # --------------------------------------------------------
        topbar = tk.Frame(
            main,
            bg=WEB_BG,
            height=76
        )
        topbar.pack(fill="x", padx=30, pady=(18, 0))
        topbar.pack_propagate(False)

        title_area = tk.Frame(topbar, bg=WEB_BG)
        title_area.pack(side="left", fill="y")

        tk.Label(
            title_area,
            text="Compression Workspace",
            font=("Segoe UI", 20, "bold"),
            bg=WEB_BG,
            fg=WHITE
        ).pack(anchor="w")

        tk.Label(
            title_area,
            text="Compress, verify and restore your files from one place.",
            font=("Segoe UI", 9),
            bg=WEB_BG,
            fg=SOFT
        ).pack(anchor="w", pady=(2, 0))

        self.status_label = tk.Label(
            topbar,
            text="● READY",
            font=("Segoe UI", 9, "bold"),
            bg="#0D2118",
            fg=GREEN,
            padx=14,
            pady=8
        )
        self.status_label.pack(side="right", pady=12)

        # --------------------------------------------------------
        # SCROLLABLE CONTENT AREA
        # --------------------------------------------------------
        scroll_area = tk.Frame(main, bg=WEB_BG)
        scroll_area.pack(fill="both", expand=True, padx=18, pady=(5, 0))

        content_canvas = tk.Canvas(
            scroll_area,
            bg=WEB_BG,
            highlightthickness=0,
            bd=0
        )
        content_canvas.pack(side="left", fill="both", expand=True)

        self.workspace_scrollbar = tk.Scrollbar(
            scroll_area,
            orient="vertical",
            command=content_canvas.yview,
            bg="#17212D",
            activebackground=CYAN,
            troughcolor="#080C12",
            bd=0,
            width=12,
            highlightthickness=0
        )
        self.workspace_scrollbar.pack(side="right", fill="y")

        content_canvas.configure(yscrollcommand=self.workspace_scrollbar.set)

        content = tk.Frame(content_canvas, bg=WEB_BG)
        content_window = content_canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scroll_region(event=None):
            content_canvas.configure(scrollregion=content_canvas.bbox("all"))

        def fit_content_width(event):
            content_canvas.itemconfigure(content_window, width=event.width)

        content.bind("<Configure>", update_scroll_region)
        content_canvas.bind("<Configure>", fit_content_width)

        def on_mousewheel(event):
            if event.num == 4:
                content_canvas.yview_scroll(-3, "units")
            elif event.num == 5:
                content_canvas.yview_scroll(3, "units")
            else:
                content_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        content_canvas.bind_all("<MouseWheel>", on_mousewheel)
        content_canvas.bind_all("<Button-4>", on_mousewheel)
        content_canvas.bind_all("<Button-5>", on_mousewheel)

        # Extra page height keeps the dashboard vertically scrollable.
        content.configure(height=1080)

        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(1, weight=1)
        content.grid_rowconfigure(2, weight=0)

        # ========================================================
        # LEFT: SOURCE / DROP CARD
        # ========================================================
        source_card = tk.Frame(
            content,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        source_card.grid(
            row=0,
            column=0,
            rowspan=2,
            sticky="nsew",
            padx=(0, 10),
            pady=5
        )

        tk.Label(
            source_card,
            text="SOURCE & OUTPUT",
            font=("Segoe UI", 9, "bold"),
            bg=CARD,
            fg=CYAN
        ).pack(anchor="w", padx=22, pady=(20, 4))

        tk.Label(
            source_card,
            text="Choose a file or folder to process",
            font=("Segoe UI", 9),
            bg=CARD,
            fg=SOFT
        ).pack(anchor="w", padx=22, pady=(0, 15))

        # Selection buttons
        select_row = tk.Frame(source_card, bg=CARD)
        select_row.pack(fill="x", padx=20)

        def make_small_button(parent, text, color, command):
            return tk.Button(
                parent,
                text=text,
                font=("Segoe UI", 9, "bold"),
                height=2,
                bg=color,
                fg=BG,
                activebackground=CYAN,
                relief="flat",
                bd=0,
                cursor="hand2",
                command=command
            )

        make_small_button(
            select_row, "FILE", BLUE, self.select_file
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))

        make_small_button(
            select_row, "FOLDER", GREEN, self.select_folder
        ).pack(side="left", fill="x", expand=True, padx=5)

        make_small_button(
            select_row, "OUTPUT", PURPLE, self.select_output
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

        # Path cards
        path_box = tk.Frame(
            source_card,
            bg=CARD_2,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        path_box.pack(fill="x", padx=20, pady=15)

        tk.Label(
            path_box,
            text="INPUT",
            font=("Segoe UI", 8, "bold"),
            bg=CARD_2,
            fg=MUTED
        ).pack(anchor="w", padx=14, pady=(12, 2))

        self.path_label = tk.Label(
            path_box,
            text="No file or folder selected",
            font=("Segoe UI", 9, "bold"),
            bg=CARD_2,
            fg=CYAN,
            justify="left",
            anchor="w",
            wraplength=650
        )
        self.path_label.pack(fill="x", padx=14, pady=(0, 10))

        tk.Label(
            path_box,
            text="OUTPUT",
            font=("Segoe UI", 8, "bold"),
            bg=CARD_2,
            fg=MUTED
        ).pack(anchor="w", padx=14, pady=(4, 2))

        self.output_label = tk.Label(
            path_box,
            text=(
                f"OUTPUT: {self.output_path}"
                if self.output_path
                else "No output folder selected"
            ),
            font=("Segoe UI", 9, "bold"),
            bg=CARD_2,
            fg=PURPLE,
            justify="left",
            anchor="w",
            wraplength=650
        )
        self.output_label.pack(fill="x", padx=14, pady=(0, 12))

        # Drag & drop area
        self.drop_frame = tk.Frame(
            source_card,
            bg="#0B131D",
            highlightbackground=CYAN,
            highlightthickness=1,
            height=145
        )
        self.drop_frame.pack(fill="x", padx=20, pady=(0, 18))
        self.drop_frame.pack_propagate(False)

        self.drop_label = tk.Label(
            self.drop_frame,
            text="DROP FILE OR FOLDER",
            font=("Segoe UI", 15, "bold"),
            bg="#0B131D",
            fg=CYAN
        )
        self.drop_label.pack(expand=True, pady=(18, 0))

        self.drop_hint = tk.Label(
            self.drop_frame,
            text="Drag & drop one item here",
            font=("Segoe UI", 9),
            bg="#0B131D",
            fg=MUTED
        )
        self.drop_hint.pack(pady=(0, 18))

        for widget in (
            self.drop_frame,
            self.drop_label,
            self.drop_hint
        ):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.handle_drop)
            widget.dnd_bind("<<DragEnter>>", self.drag_enter)
            widget.dnd_bind("<<DragLeave>>", self.drag_leave)

        # ========================================================
        # RIGHT TOP: PROFILE CARD
        # ========================================================
        profile_card = tk.Frame(
            content,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        profile_card.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(10, 0),
            pady=5
        )

        tk.Label(
            profile_card,
            text="COMPRESSION PROFILE",
            font=("Segoe UI", 9, "bold"),
            bg=CARD,
            fg=CYAN
        ).pack(anchor="w", padx=20, pady=(18, 3))

        tk.Label(
            profile_card,
            text="Choose the ZSTD processing level",
            font=("Segoe UI", 8),
            bg=CARD,
            fg=SOFT
        ).pack(anchor="w", padx=20)

        profile_buttons = tk.Frame(profile_card, bg=CARD)
        profile_buttons.pack(fill="x", padx=15, pady=(14, 5))

        self.profile_button_widgets = {}

        profile_colors = {
            "FAST": GREEN,
            "BALANCED": BLUE,
            "MAXIMUM": PURPLE,
        }

        for profile in ("FAST", "BALANCED", "MAXIMUM"):
            button = tk.Button(
                profile_buttons,
                text=profile,
                font=("Segoe UI", 8, "bold"),
                height=2,
                bg=profile_colors[profile],
                fg=BG,
                activebackground=CYAN,
                relief="flat",
                bd=1,
                cursor="hand2",
                command=lambda p=profile: self.select_profile(p)
            )
            button.pack(
                side="left",
                fill="x",
                expand=True,
                padx=3
            )
            self.profile_button_widgets[profile] = button

        self.profile_status_label = tk.Label(
            profile_card,
            text="SELECTED: BALANCED (ZSTD LEVEL 5)",
            font=("Segoe UI", 9, "bold"),
            bg=CARD,
            fg=YELLOW
        )
        self.profile_status_label.pack(pady=(5, 16))

        self.update_profile_buttons()

        # ========================================================
        # RIGHT BOTTOM: LIVE OPERATION CARD
        # ========================================================
        operation_card = tk.Frame(
            content,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        operation_card.grid(
            row=1,
            column=1,
            sticky="nsew",
            padx=(10, 0),
            pady=(10, 5)
        )

        tk.Label(
            operation_card,
            text="LIVE OPERATION",
            font=("Segoe UI", 9, "bold"),
            bg=CARD,
            fg=CYAN
        ).pack(anchor="w", padx=20, pady=(18, 3))

        # Progress
        self.progress = tk.DoubleVar(value=0)

        self.progress_bar = tk.Scale(
            operation_card,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.progress,
            length=400,
            showvalue=False,
            state="disabled",
            bg=CARD,
            fg=CYAN,
            troughcolor="#202A36",
            highlightthickness=0,
            bd=0,
            sliderlength=1
        )
        self.progress_bar.pack(fill="x", padx=18, pady=(12, 2))

        self.progress_label = tk.Label(
            operation_card,
            text="0.00%",
            font=("Segoe UI", 20, "bold"),
            bg=CARD,
            fg=WHITE
        )
        self.progress_label.pack(pady=(0, 2))

        self.info_label = tk.Label(
            operation_card,
            text="SPEED: 0 MB/s     ETA: --",
            font=("Segoe UI", 8, "bold"),
            bg=CARD,
            fg=ORANGE
        )
        self.info_label.pack(pady=(0, 10))

        # Action buttons
        action_row = tk.Frame(operation_card, bg=CARD)
        action_row.pack(fill="x", padx=18, pady=(5, 8))

        self.compress_button = tk.Button(
            action_row,
            text="COMPRESS",
            font=("Segoe UI", 9, "bold"),
            height=2,
            bg=ORANGE,
            fg=BG,
            activebackground=YELLOW,
            relief="flat",
            cursor="hand2",
            command=self.start_compression
        )
        self.compress_button.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 4)
        )

        self.decompress_button = tk.Button(
            action_row,
            text="DECOMPRESS",
            font=("Segoe UI", 9, "bold"),
            height=2,
            bg=RED,
            fg=BG,
            activebackground=PINK,
            relief="flat",
            cursor="hand2",
            command=self.start_decompression
        )
        self.decompress_button.pack(
            side="left",
            fill="x",
            expand=True,
            padx=4
        )

        # ========================================================
        # PHASE 4 / STEP 4 PART 1: ZSTD VALIDATION
        # ========================================================
        self.validate_button = tk.Button(
            action_row,
            text="VALIDATE ZSTD",
            font=("Segoe UI", 9, "bold"),
            height=2,
            bg=CYAN,
            fg=BG,
            activebackground=GREEN,
            relief="flat",
            cursor="hand2",
            command=self.start_validation
        )
        self.validate_button.pack(
            side="left",
            fill="x",
            expand=True,
            padx=4
        )

        self.stop_button = tk.Button(
            action_row,
            text="STOP",
            font=("Segoe UI", 9, "bold"),
            height=2,
            bg=YELLOW,
            fg=BG,
            activebackground=RED,
            relief="flat",
            cursor="hand2",
            state="disabled",
            command=self.cancel_operation
        )
        self.stop_button.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(4, 0)
        )

        # Result panel
        result_box = tk.Frame(
            operation_card,
            bg=CARD_2,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        result_box.pack(fill="both", expand=True, padx=18, pady=(5, 18))

        tk.Label(
            result_box,
            text="RESULT",
            font=("Segoe UI", 8, "bold"),
            bg=CARD_2,
            fg=MUTED
        ).pack(anchor="w", padx=12, pady=(10, 2))

        self.result_label = tk.Label(
            result_box,
            text="Waiting for an operation...",
            font=("Consolas", 9),
            justify="left",
            anchor="nw",
            bg=CARD_2,
            fg=TEXT,
            wraplength=520,
            padx=12,
            pady=8
        )
        self.result_label.pack(fill="both", expand=True)

        # ========================================================
        # RECENT OPERATIONS HISTORY (PHASE 3 / STEP 6)
        # ========================================================
        history_card = tk.Frame(
            content,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        history_card.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=0,
            pady=(10, 5)
        )

        history_header = tk.Frame(history_card, bg=CARD)
        history_header.pack(fill="x", padx=20, pady=(16, 8))

        tk.Label(
            history_header,
            text="RECENT OPERATIONS",
            font=("Segoe UI", 9, "bold"),
            bg=CARD,
            fg=CYAN
        ).pack(side="left")

        self.history_count_label = tk.Label(
            history_header,
            text="0 / 10",
            font=("Segoe UI", 8, "bold"),
            bg=CARD,
            fg=MUTED
        )
        self.history_count_label.pack(side="right", padx=(10, 8))

        self.history_clear_button = tk.Button(
            history_header,
            text="CLEAR",
            font=("Segoe UI", 8, "bold"),
            bg="#182536",
            fg=SOFT,
            activebackground=CYAN,
            activeforeground=BG,
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.clear_history
        )
        self.history_clear_button.pack(side="right")

        history_box = tk.Frame(
            history_card,
            bg=CARD_2,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        history_box.pack(fill="x", padx=20, pady=(0, 18))

        history_scrollbar = tk.Scrollbar(
            history_box,
            orient="vertical",
            bg="#17212D",
            activebackground=CYAN,
            troughcolor="#080C12",
            bd=0,
            width=10,
            highlightthickness=0
        )
        history_scrollbar.pack(side="right", fill="y")

        self.history_list = tk.Listbox(
            history_box,
            height=7,
            bg=CARD_2,
            fg=TEXT,
            selectbackground="#183149",
            selectforeground=WHITE,
            activestyle="none",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Consolas", 9),
            yscrollcommand=history_scrollbar.set
        )
        self.history_list.pack(fill="x", padx=10, pady=10)
        history_scrollbar.config(command=self.history_list.yview)

        self.history_list.insert(
            "end",
            "READY  |  No operations recorded yet"
        )

        # Clicking the sidebar item jumps directly to the history panel.
        if self.history_nav is not None:
            self.history_nav.bind(
                "<Button-1>",
                lambda event: content_canvas.yview_moveto(1.0)
            )
            for child in self.history_nav.winfo_children():
                child.bind(
                    "<Button-1>",
                    lambda event: content_canvas.yview_moveto(1.0)
                )

        # ========================================================
        # FILE / FOLDER INFORMATION (PHASE 3 / STEP 8)
        # ========================================================
        info_card = tk.Frame(
            content,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        info_card.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=0,
            pady=(10, 5)
        )

        info_header = tk.Frame(info_card, bg=CARD)
        info_header.pack(fill="x", padx=20, pady=(16, 8))

        tk.Label(
            info_header,
            text="FILE / FOLDER INFORMATION",
            font=("Segoe UI", 9, "bold"),
            bg=CARD,
            fg=CYAN
        ).pack(side="left")

        tk.Label(
            info_header,
            text="Details for the currently selected item",
            font=("Segoe UI", 8),
            bg=CARD,
            fg=SOFT
        ).pack(side="left", padx=12)

        info_body = tk.Frame(info_card, bg=CARD)
        info_body.pack(fill="x", padx=20, pady=(0, 14))
        info_body.grid_columnconfigure(0, weight=1)
        info_body.grid_columnconfigure(1, weight=1)
        info_body.grid_columnconfigure(2, weight=1)

        def info_value_card(parent, title, row, column, value="—", fg_value=WHITE):
            box = tk.Frame(
                parent,
                bg=CARD_2,
                highlightbackground=BORDER,
                highlightthickness=1
            )
            box.grid(
                row=row,
                column=column,
                sticky="nsew",
                padx=4,
                pady=4
            )

            tk.Label(
                box,
                text=title,
                font=("Segoe UI", 8, "bold"),
                bg=CARD_2,
                fg=MUTED
            ).pack(anchor="w", padx=12, pady=(10, 2))

            value_label = tk.Label(
                box,
                text=value,
                font=("Segoe UI", 9, "bold"),
                bg=CARD_2,
                fg=fg_value,
                justify="left",
                anchor="w",
                wraplength=420
            )
            value_label.pack(fill="x", padx=12, pady=(0, 10))
            return value_label

        self.info_name_value = info_value_card(
            info_body, "NAME", 0, 0
        )
        self.info_type_value = info_value_card(
            info_body, "TYPE", 0, 1, fg_value=CYAN
        )
        self.info_size_value = info_value_card(
            info_body, "SIZE", 0, 2, fg_value=YELLOW
        )
        self.info_location_value = info_value_card(
            info_body, "LOCATION", 1, 0, fg_value=PURPLE
        )
        self.info_created_value = info_value_card(
            info_body, "CREATED", 1, 1
        )
        self.info_modified_value = info_value_card(
            info_body, "MODIFIED", 1, 2
        )
        self.info_count_value = info_value_card(
            info_body, "CONTENT", 2, 0, fg_value=GREEN
        )
        self.info_sha_value = info_value_card(
            info_body, "SHA-256", 2, 1, value="Not calculated", fg_value=TEXT
        )

        self.info_origin_value = info_value_card(
            info_body, "ORIGIN / SOURCE", 3, 0,
            value="Source unknown", fg_value=GREEN
        )
        self.info_source_value = info_value_card(
            info_body, "SOURCE URL / HOST", 3, 1,
            value="Not available", fg_value=PURPLE
        )
        self.info_zone_value = info_value_card(
            info_body, "WINDOWS SOURCE METADATA", 3, 2,
            value="Not checked", fg_value=TEXT
        )

        sha_action = tk.Frame(info_body, bg=CARD_2)
        sha_action.grid(
            row=2,
            column=2,
            sticky="nsew",
            padx=4,
            pady=4
        )

        tk.Label(
            sha_action,
            text="ANALYSIS",
            font=("Segoe UI", 8, "bold"),
            bg=CARD_2,
            fg=MUTED
        ).pack(anchor="w", padx=12, pady=(10, 2))

        self.info_analyze_button = tk.Button(
            sha_action,
            text="CALCULATE SHA-256",
            font=("Segoe UI", 8, "bold"),
            bg=BLUE,
            fg=BG,
            activebackground=CYAN,
            relief="flat",
            bd=0,
            cursor="hand2",
            state="disabled",
            command=self.start_sha_analysis
        )
        self.info_analyze_button.pack(anchor="w", padx=12, pady=(4, 6))

        self.info_copy_sha_button = tk.Button(
            sha_action,
            text="COPY SHA-256",
            font=("Segoe UI", 8, "bold"),
            bg="#182536",
            fg=SOFT,
            activebackground=CYAN,
            activeforeground=BG,
            relief="flat",
            bd=0,
            cursor="hand2",
            state="disabled",
            command=self.copy_info_sha
        )
        self.info_copy_sha_button.pack(anchor="w", padx=12, pady=2)

        self.info_copy_path_button = tk.Button(
            sha_action,
            text="COPY PATH",
            font=("Segoe UI", 8, "bold"),
            bg="#182536",
            fg=SOFT,
            activebackground=CYAN,
            activeforeground=BG,
            relief="flat",
            bd=0,
            cursor="hand2",
            state="disabled",
            command=self.copy_info_path
        )
        self.info_copy_path_button.pack(anchor="w", padx=12, pady=2)

        self.info_open_button = tk.Button(
            sha_action,
            text="OPEN LOCATION",
            font=("Segoe UI", 8, "bold"),
            bg=PURPLE,
            fg=BG,
            activebackground=CYAN,
            relief="flat",
            bd=0,
            cursor="hand2",
            state="disabled",
            command=self.open_info_location
        )
        self.info_open_button.pack(anchor="w", padx=12, pady=(2, 10))

        # Initial blank state.
        self.clear_info_panel()

        # ========================================================
        # SETTINGS (PHASE 3 / STEP 7)
        # ========================================================
        settings_card = tk.Frame(
            content,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        settings_card.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=0,
            pady=(10, 5)
        )

        settings_header = tk.Frame(settings_card, bg=CARD)
        settings_header.pack(fill="x", padx=20, pady=(16, 6))

        tk.Label(
            settings_header,
            text="SETTINGS",
            font=("Segoe UI", 9, "bold"),
            bg=CARD,
            fg=CYAN
        ).pack(side="left")

        tk.Label(
            settings_header,
            text="Default preferences for NOVA COMPRESSOR",
            font=("Segoe UI", 8),
            bg=CARD,
            fg=SOFT
        ).pack(side="left", padx=12)

        settings_body = tk.Frame(settings_card, bg=CARD)
        settings_body.pack(fill="x", padx=20, pady=(4, 14))
        settings_body.grid_columnconfigure(0, weight=1)
        settings_body.grid_columnconfigure(1, weight=1)

        # Default compression profile
        profile_setting = tk.Frame(
            settings_body,
            bg=CARD_2,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        profile_setting.grid(
            row=0, column=0, sticky="nsew", padx=(0, 8)
        )

        tk.Label(
            profile_setting,
            text="DEFAULT COMPRESSION PROFILE",
            font=("Segoe UI", 8, "bold"),
            bg=CARD_2,
            fg=MUTED
        ).pack(anchor="w", padx=14, pady=(12, 3))

        self.settings_profile_var = tk.StringVar(
            value=self.settings_default_profile
        )

        settings_profile_menu = tk.OptionMenu(
            profile_setting,
            self.settings_profile_var,
            *COMPRESSION_PROFILES.keys()
        )
        settings_profile_menu.config(
            font=("Segoe UI", 9, "bold"),
            bg=BLUE,
            fg=BG,
            activebackground=CYAN,
            activeforeground=BG,
            relief="flat",
            highlightthickness=0,
            bd=0,
            cursor="hand2"
        )
        settings_profile_menu["menu"].config(
            font=("Segoe UI", 9),
            bg=CARD_2,
            fg=WHITE,
            activebackground=CYAN,
            activeforeground=BG
        )
        settings_profile_menu.pack(
            fill="x", padx=14, pady=(2, 14)
        )

        # Default output folder
        output_setting = tk.Frame(
            settings_body,
            bg=CARD_2,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        output_setting.grid(
            row=0, column=1, sticky="nsew", padx=(8, 0)
        )

        tk.Label(
            output_setting,
            text="DEFAULT OUTPUT FOLDER",
            font=("Segoe UI", 8, "bold"),
            bg=CARD_2,
            fg=MUTED
        ).pack(anchor="w", padx=14, pady=(12, 3))

        self.settings_output_var = tk.StringVar(
            value=self.settings_default_output or "Not set"
        )

        output_value = tk.Label(
            output_setting,
            textvariable=self.settings_output_var,
            font=("Segoe UI", 8, "bold"),
            bg=CARD_2,
            fg=PURPLE,
            justify="left",
            anchor="w",
            wraplength=500
        )
        output_value.pack(fill="x", padx=14, pady=(2, 8))

        output_button = tk.Button(
            output_setting,
            text="BROWSE OUTPUT FOLDER",
            font=("Segoe UI", 8, "bold"),
            bg=PURPLE,
            fg=BG,
            activebackground=CYAN,
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.choose_default_output
        )
        output_button.pack(anchor="w", padx=14, pady=(0, 14))

        settings_actions = tk.Frame(settings_card, bg=CARD)
        settings_actions.pack(fill="x", padx=20, pady=(0, 16))

        tk.Button(
            settings_actions,
            text="SAVE SETTINGS",
            font=("Segoe UI", 9, "bold"),
            bg=GREEN,
            fg=BG,
            activebackground=CYAN,
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.save_settings
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            settings_actions,
            text="RESET SETTINGS",
            font=("Segoe UI", 9, "bold"),
            bg=RED,
            fg=BG,
            activebackground=PINK,
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.reset_settings
        ).pack(side="left")

        self.settings_status_label = tk.Label(
            settings_actions,
            text="Current defaults loaded.",
            font=("Segoe UI", 8, "bold"),
            bg=CARD,
            fg=MUTED
        )
        self.settings_status_label.pack(side="left", padx=14)

        # Settings nav jumps to the settings card.
        if self.settings_nav is not None:
            self.settings_nav.bind(
                "<Button-1>",
                lambda event: content_canvas.yview_moveto(1.0)
            )
            for child in self.settings_nav.winfo_children():
                child.bind(
                    "<Button-1>",
                    lambda event: content_canvas.yview_moveto(1.0)
                )

        # ========================================================
        # OPERATION QUEUE (PHASE 4 / STEP 2 PART 1)
        # ========================================================
        queue_card = tk.Frame(
            content,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        queue_card.grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=0,
            pady=(10, 5)
        )

        queue_header = tk.Frame(queue_card, bg=CARD)
        queue_header.pack(fill="x", padx=20, pady=(16, 8))

        tk.Label(
            queue_header,
            text="OPERATION QUEUE",
            font=("Segoe UI", 9, "bold"),
            bg=CARD,
            fg=CYAN
        ).pack(side="left")

        self.queue_count_label = tk.Label(
            queue_header,
            text="0 ITEMS",
            font=("Segoe UI", 8, "bold"),
            bg=CARD,
            fg=MUTED
        )
        self.queue_count_label.pack(side="right")

        tk.Label(
            queue_card,
            text="Add multiple files or folders. Start Queue processes them sequentially with conflict handling.",
            font=("Segoe UI", 8),
            bg=CARD,
            fg=SOFT
        ).pack(anchor="w", padx=20, pady=(0, 10))

        queue_actions = tk.Frame(queue_card, bg=CARD)
        queue_actions.pack(fill="x", padx=20, pady=(0, 10))

        def queue_button(parent, text, color, command, state="normal"):
            return tk.Button(
                parent,
                text=text,
                font=("Segoe UI", 8, "bold"),
                height=2,
                bg=color,
                fg=BG,
                activebackground=CYAN,
                relief="flat",
                bd=0,
                cursor="hand2",
                state=state,
                command=command
            )

        queue_button(
            queue_actions, "ADD FILES", BLUE, self.queue_add_files
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))

        queue_button(
            queue_actions, "ADD FOLDER", GREEN, self.queue_add_folder
        ).pack(side="left", fill="x", expand=True, padx=5)

        self.queue_remove_button = queue_button(
            queue_actions, "REMOVE SELECTED", PURPLE, self.queue_remove_selected, state="disabled"
        )
        self.queue_remove_button.pack(side="left", fill="x", expand=True, padx=5)

        queue_button(
            queue_actions, "CLEAR QUEUE", RED, self.queue_clear
        ).pack(side="left", fill="x", expand=True, padx=5)

        self.queue_start_button = queue_button(
            queue_actions, "START QUEUE", ORANGE, self.start_queue, state="disabled"
        )
        self.queue_start_button.pack(side="left", fill="x", expand=True, padx=5)

        self.queue_stop_button = queue_button(
            queue_actions, "STOP QUEUE", YELLOW, self.stop_queue, state="disabled"
        )
        self.queue_stop_button.pack(side="left", fill="x", expand=True, padx=(5, 0))

        queue_box = tk.Frame(
            queue_card,
            bg=CARD_2,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        queue_box.pack(fill="x", padx=20, pady=(0, 10))

        queue_scrollbar = tk.Scrollbar(
            queue_box,
            orient="vertical",
            bg="#17212D",
            activebackground=CYAN,
            troughcolor="#080C12",
            bd=0,
            width=10,
            highlightthickness=0
        )
        queue_scrollbar.pack(side="right", fill="y")

        self.queue_list = tk.Listbox(
            queue_box,
            height=7,
            bg=CARD_2,
            fg=TEXT,
            selectbackground="#183149",
            selectforeground=WHITE,
            activestyle="none",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Consolas", 9),
            yscrollcommand=queue_scrollbar.set,
            exportselection=False
        )
        self.queue_list.pack(fill="x", padx=10, pady=10)
        queue_scrollbar.config(command=self.queue_list.yview)
        self.queue_list.bind("<<ListboxSelect>>", self.queue_selection_changed)

        self.queue_status_label = tk.Label(
            queue_card,
            text="QUEUE READY — 0 ITEMS",
            font=("Segoe UI", 8, "bold"),
            bg=CARD,
            fg=GREEN
        )
        self.queue_status_label.pack(anchor="w", padx=20, pady=(0, 14))

        # ========================================================
        # COMPRESSION ANALYTICS (PHASE 4 / STEP 3)
        # ========================================================
        analytics_card = tk.Frame(
            content,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        analytics_card.grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=0,
            pady=(10, 5)
        )

        analytics_header = tk.Frame(analytics_card, bg=CARD)
        analytics_header.pack(fill="x", padx=20, pady=(16, 8))

        tk.Label(
            analytics_header,
            text="COMPRESSION ANALYTICS",
            font=("Segoe UI", 9, "bold"),
            bg=CARD,
            fg=CYAN
        ).pack(side="left")

        tk.Label(
            analytics_header,
            text="Live session statistics",
            font=("Segoe UI", 8),
            bg=CARD,
            fg=SOFT
        ).pack(side="left", padx=12)

        tk.Button(
            analytics_header,
            text="RESET",
            font=("Segoe UI", 7, "bold"),
            bg="#182536",
            fg=SOFT,
            activebackground=CYAN,
            activeforeground=BG,
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.reset_analytics
        ).pack(side="right")

        analytics_grid = tk.Frame(analytics_card, bg=CARD)
        analytics_grid.pack(fill="x", padx=16, pady=(0, 16))
        for column in range(4):
            analytics_grid.grid_columnconfigure(column, weight=1)

        def analytics_value_box(title, row, column, key, fg_value=WHITE):
            box = tk.Frame(
                analytics_grid,
                bg=CARD_2,
                highlightbackground=BORDER,
                highlightthickness=1
            )
            box.grid(
                row=row,
                column=column,
                sticky="nsew",
                padx=4,
                pady=4
            )

            tk.Label(
                box,
                text=title,
                font=("Segoe UI", 7, "bold"),
                bg=CARD_2,
                fg=MUTED
            ).pack(anchor="w", padx=12, pady=(10, 2))

            value = tk.Label(
                box,
                text="—",
                font=("Segoe UI", 11, "bold"),
                bg=CARD_2,
                fg=fg_value,
                justify="left",
                anchor="w",
                wraplength=280
            )
            value.pack(fill="x", padx=12, pady=(0, 10))
            self.analytics_values[key] = value

        analytics_value_box("SUCCESSFUL", 0, 0, "success", GREEN)
        analytics_value_box("FAILED", 0, 1, "failed", RED)
        analytics_value_box("CANCELLED", 0, 2, "cancelled", YELLOW)
        analytics_value_box("TOTAL OPERATIONS", 0, 3, "total", CYAN)

        analytics_value_box("ORIGINAL DATA", 1, 0, "original", WHITE)
        analytics_value_box("COMPRESSED DATA", 1, 1, "compressed", CYAN)
        analytics_value_box("SPACE SAVED", 1, 2, "saved", GREEN)
        analytics_value_box("AVG REDUCTION", 1, 3, "reduction", YELLOW)

        analytics_value_box("AVG RATIO", 2, 0, "ratio", PURPLE)
        analytics_value_box("TOTAL TIME", 2, 1, "time", ORANGE)
        analytics_value_box("LAST OPERATION", 2, 2, "last", WHITE)

        self.refresh_analytics_ui()

        # Extra bottom breathing room for the scrollable page.
        tk.Frame(
            content,
            bg=WEB_BG,
            height=180
        ).grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="ew"
        )

    # ========================================================
    # COMPRESSION ANALYTICS
    # ========================================================

    def record_compression_success(
        self,
        original_size,
        compressed_size,
        reduction,
        ratio,
        elapsed,
        source=None
    ):
        with self.analytics_lock:
            self.analytics["success"] += 1
            self.analytics["original_bytes"] += int(original_size or 0)
            self.analytics["compressed_bytes"] += int(compressed_size or 0)
            self.analytics["saved_bytes"] += max(
                int(original_size or 0) - int(compressed_size or 0),
                0
            )
            self.analytics["total_time"] += float(elapsed or 0.0)
            self.analytics["reduction_sum"] += float(reduction or 0.0)
            self.analytics["ratio_sum"] += float(ratio or 0.0)
            self.analytics["last_operation"] = (
                Path(source).name if source else "Compression"
            )

        self.root.after(0, self.refresh_analytics_ui)


    def record_compression_failure(self, source=None):
        with self.analytics_lock:
            self.analytics["failed"] += 1
            self.analytics["last_operation"] = (
                f"FAILED: {Path(source).name}" if source else "FAILED"
            )

        self.root.after(0, self.refresh_analytics_ui)


    def record_compression_cancelled(self, source=None):
        with self.analytics_lock:
            self.analytics["cancelled"] += 1
            self.analytics["last_operation"] = (
                f"CANCELLED: {Path(source).name}"
                if source else "CANCELLED"
            )

        self.root.after(0, self.refresh_analytics_ui)


    def refresh_analytics_ui(self):
        if not self.analytics_values:
            return

        with self.analytics_lock:
            data = dict(self.analytics)

        success = data["success"]
        failed = data["failed"]
        cancelled = data["cancelled"]
        total = success + failed + cancelled

        avg_reduction = (
            data["reduction_sum"] / success
            if success else 0.0
        )
        avg_ratio = (
            data["ratio_sum"] / success
            if success else 0.0
        )

        values = {
            "success": str(success),
            "failed": str(failed),
            "cancelled": str(cancelled),
            "total": str(total),
            "original": format_size(data["original_bytes"]),
            "compressed": format_size(data["compressed_bytes"]),
            "saved": format_size(data["saved_bytes"]),
            "reduction": f"{avg_reduction:.2f}%",
            "ratio": f"{avg_ratio:.2f}:1",
            "time": f"{data['total_time']:.2f} sec",
            "last": data["last_operation"],
        }

        for key, value in values.items():
            label = self.analytics_values.get(key)
            if label is not None:
                label.config(text=value)


    def reset_analytics(self):
        with self.analytics_lock:
            self.analytics = {
                "success": 0,
                "failed": 0,
                "cancelled": 0,
                "original_bytes": 0,
                "compressed_bytes": 0,
                "saved_bytes": 0,
                "total_time": 0.0,
                "reduction_sum": 0.0,
                "ratio_sum": 0.0,
                "last_operation": "—",
            }
        self.refresh_analytics_ui()


    # ========================================================
    # RECENT OPERATIONS HISTORY
    # ========================================================

    def add_history(self, operation, source, output=None, detail=None):

        if self.history_list is None:
            return

        timestamp = time.strftime("%H:%M:%S")
        source_name = Path(source).name if source else "Unknown"
        output_name = Path(output).name if output else "-"

        entry = {
            "time": timestamp,
            "operation": operation,
            "source": source_name,
            "output": output_name,
            "detail": detail or "",
        }

        self.history.insert(0, entry)
        self.history = self.history[:10]

        self.refresh_history_ui()


    def refresh_history_ui(self):

        if self.history_list is None:
            return

        self.history_list.delete(0, "end")

        if not self.history:
            self.history_list.insert(
                "end",
                "READY  |  No operations recorded yet"
            )
        else:
            for item in self.history:
                detail = (
                    f" | {item['detail']}"
                    if item["detail"]
                    else ""
                )
                self.history_list.insert(
                    "end",
                    f"{item['time']}  |  {item['operation']:<18} | "
                    f"{item['source']} -> {item['output']}{detail}"
                )

        if self.history_count_label is not None:
            self.history_count_label.config(
                text=f"{len(self.history)} / 10"
            )

        if self.history:
            self.history_list.selection_clear(0, "end")
            self.history_list.selection_set(0)
            self.history_list.see(0)


    def clear_history(self):

        self.history.clear()
        self.refresh_history_ui()


    # ========================================================
    # SETTINGS (PHASE 3 / STEP 7)
    # ========================================================

    def load_settings(self):

        if not self.settings_file.exists():
            return

        try:
            with open(
                self.settings_file,
                "r",
                encoding="utf-8"
            ) as f:
                data = json.load(f)

            profile = data.get(
                "default_profile",
                "BALANCED"
            )

            if profile in COMPRESSION_PROFILES:
                self.settings_default_profile = profile

            output = data.get(
                "default_output",
                ""
            )

            if isinstance(output, str):
                self.settings_default_output = output.strip()

        except (OSError, json.JSONDecodeError):
            # Invalid settings should never prevent the application from
            # starting. Fall back to safe defaults.
            self.settings_default_profile = "BALANCED"
            self.settings_default_output = ""


    def choose_default_output(self):

        path = filedialog.askdirectory(
            title="Select Default Output Folder"
        )

        if not path:
            return

        self.settings_default_output = str(Path(path))

        if self.settings_output_var is not None:
            self.settings_output_var.set(
                self.settings_default_output
            )

        if self.settings_status_label is not None:
            self.settings_status_label.config(
                text="Output folder selected. Click SAVE SETTINGS.",
                fg=YELLOW
            )


    def save_settings(self):

        profile = (
            self.settings_profile_var.get()
            if self.settings_profile_var is not None
            else self.compression_profile.get()
        )

        output = (
            self.settings_output_var.get().strip()
            if self.settings_output_var is not None
            else self.settings_default_output
        )

        if profile not in COMPRESSION_PROFILES:
            messagebox.showerror(
                "NOVA SETTINGS",
                "Invalid compression profile selected."
            )
            return

        if output and (
            not Path(output).exists()
            or not Path(output).is_dir()
        ):
            messagebox.showerror(
                "NOVA SETTINGS",
                "The selected default output folder does not exist."
            )
            return

        data = {
            "default_profile": profile,
            "default_output": output,
        }

        try:
            with open(
                self.settings_file,
                "w",
                encoding="utf-8"
            ) as f:
                json.dump(
                    data,
                    f,
                    indent=4
                )

            self.settings_default_profile = profile
            self.settings_default_output = output

            # Apply defaults immediately to the workspace.
            self.compression_profile.set(profile)
            self.update_profile_buttons()

            if output:
                self.output_path = Path(output)
                self.output_label.config(
                    text=f"OUTPUT: {self.output_path}",
                    fg=PURPLE
                )
            else:
                self.output_path = None
                self.output_label.config(
                    text="No output folder selected",
                    fg=PURPLE
                )

            self.status_label.config(
                text="● SETTINGS SAVED",
                fg=GREEN
            )

            if self.settings_status_label is not None:
                self.settings_status_label.config(
                    text="Settings saved successfully.",
                    fg=GREEN
                )

        except OSError as error:
            messagebox.showerror(
                "NOVA SETTINGS",
                f"Could not save settings:\n{error}"
            )


    def reset_settings(self):

        self.settings_default_profile = "BALANCED"
        self.settings_default_output = ""

        if self.settings_profile_var is not None:
            self.settings_profile_var.set("BALANCED")

        if self.settings_output_var is not None:
            self.settings_output_var.set("Not set")

        self.compression_profile.set("BALANCED")
        self.update_profile_buttons()

        self.output_path = None
        self.output_label.config(
            text="No output folder selected",
            fg=PURPLE
        )

        try:
            if self.settings_file.exists():
                self.settings_file.unlink()
        except OSError as error:
            messagebox.showerror(
                "NOVA SETTINGS",
                f"Could not reset settings:\n{error}"
            )
            return

        self.status_label.config(
            text="● SETTINGS RESET",
            fg=YELLOW
        )

        if self.settings_status_label is not None:
            self.settings_status_label.config(
                text="Settings reset to defaults.",
                fg=YELLOW
            )


    # ========================================================
    # FILE / FOLDER INFORMATION (PHASE 3 / STEP 8)
    # ========================================================

    def clear_info_panel(self):

        if self.info_name_value is None:
            return

        for label in (
            self.info_name_value,
            self.info_type_value,
            self.info_size_value,
            self.info_location_value,
            self.info_created_value,
            self.info_modified_value,
            self.info_count_value,
            self.info_origin_value,
            self.info_source_value,
            self.info_zone_value,
        ):
            label.config(text="—")

        self.info_sha_value.config(text="Not calculated")
        self.info_current_path = None

        if self.info_analyze_button is not None:
            self.info_analyze_button.config(state="disabled")
        if self.info_copy_sha_button is not None:
            self.info_copy_sha_button.config(state="disabled")
        if self.info_copy_path_button is not None:
            self.info_copy_path_button.config(state="disabled")
        if self.info_open_button is not None:
            self.info_open_button.config(state="disabled")


    def update_info_panel(self, path):

        path = Path(path)
        self.info_current_path = path

        try:
            stat = path.stat()
            created = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(stat.st_ctime)
            )
            modified = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(stat.st_mtime)
            )

            if path.is_file():
                suffix = path.suffix.lower()
                file_type = f"FILE{(' • ' + suffix.upper()) if suffix else ''}"

                self.info_name_value.config(text=path.name)
                self.info_type_value.config(text=file_type)
                self.info_size_value.config(text=format_size(stat.st_size))
                self.info_location_value.config(text=str(path.parent))
                self.info_created_value.config(text=created)
                self.info_modified_value.config(text=modified)
                self.info_count_value.config(text="1 file")
                self.info_sha_value.config(text="Not calculated")

                origin_info = get_file_origin(path)
                self.info_origin_value.config(
                    text=origin_info["origin"],
                    fg=GREEN if origin_info["has_metadata"] else YELLOW
                )
                self.info_source_value.config(
                    text=origin_info.get("host_url") or origin_info["source"],
                    fg=PURPLE
                )
                self.info_zone_value.config(
                    text=origin_info["zone"]
                )

                if self.info_analyze_button is not None:
                    self.info_analyze_button.config(
                        state="normal",
                        text="CALCULATE SHA-256"
                    )
                if self.info_copy_sha_button is not None:
                    self.info_copy_sha_button.config(state="disabled")
                if self.info_copy_path_button is not None:
                    self.info_copy_path_button.config(state="normal")
                if self.info_open_button is not None:
                    self.info_open_button.config(state="normal")

            elif path.is_dir():
                total_files = 0
                total_dirs = 0
                total_size = 0

                for root, dirs, files in os.walk(path):
                    total_dirs += len(dirs)
                    total_files += len(files)
                    for filename in files:
                        try:
                            total_size += (
                                Path(root) / filename
                            ).stat().st_size
                        except OSError:
                            pass

                self.info_name_value.config(text=path.name)
                self.info_type_value.config(text="FOLDER")
                self.info_size_value.config(text=format_size(total_size))
                self.info_location_value.config(text=str(path.parent))
                self.info_created_value.config(text=created)
                self.info_modified_value.config(text=modified)
                self.info_count_value.config(
                    text=f"{total_files} files • {total_dirs} folders"
                )
                self.info_sha_value.config(
                    text="Folder SHA-256 not calculated"
                )
                self.info_origin_value.config(
                    text="FOLDER",
                    fg=GREEN
                )
                self.info_source_value.config(
                    text="Origin is not determined for a folder",
                    fg=PURPLE
                )
                self.info_zone_value.config(
                    text="Folder-level source metadata not available"
                )

                if self.info_analyze_button is not None:
                    self.info_analyze_button.config(
                        state="disabled",
                        text="SHA-256 FOR FILES ONLY"
                    )
                if self.info_copy_sha_button is not None:
                    self.info_copy_sha_button.config(state="disabled")
                if self.info_copy_path_button is not None:
                    self.info_copy_path_button.config(state="normal")
                if self.info_open_button is not None:
                    self.info_open_button.config(state="normal")

        except OSError as error:
            self.info_name_value.config(text="Unable to read item")
            self.info_type_value.config(text="ERROR")
            self.info_size_value.config(text="—")
            self.info_location_value.config(text=str(error))
            self.info_created_value.config(text="—")
            self.info_modified_value.config(text="—")
            self.info_count_value.config(text="—")
            self.info_sha_value.config(text="Not available")
            self.info_origin_value.config(text="Not available", fg=RED)
            self.info_source_value.config(text="Not available", fg=RED)
            self.info_zone_value.config(text="Not available", fg=RED)

            if self.info_analyze_button is not None:
                self.info_analyze_button.config(state="disabled")
            if self.info_copy_sha_button is not None:
                self.info_copy_sha_button.config(state="disabled")
            if self.info_copy_path_button is not None:
                self.info_copy_path_button.config(state="disabled")
            if self.info_open_button is not None:
                self.info_open_button.config(state="disabled")


    def start_sha_analysis(self):

        if self.is_running:
            return

        path = self.info_current_path

        if not path or not path.is_file():
            return

        if self.info_analyze_button is not None:
            self.info_analyze_button.config(
                state="disabled",
                text="CALCULATING..."
            )

        self.info_sha_value.config(text="Calculating SHA-256...")

        thread = threading.Thread(
            target=self.calculate_selected_sha,
            args=(path,),
            daemon=True
        )
        thread.start()


    def calculate_selected_sha(self, path):

        try:
            digest = sha256_file(path)
            self.root.after(
                0,
                self.sha_analysis_complete,
                path,
                digest,
                None
            )
        except Exception as error:
            self.root.after(
                0,
                self.sha_analysis_complete,
                path,
                None,
                str(error)
            )


    def sha_analysis_complete(self, path, digest, error):

        if self.info_current_path != path:
            return

        if error:
            self.info_sha_value.config(
                text=f"ERROR: {error}",
                fg=RED
            )
            self.info_analyze_button.config(
                state="normal",
                text="RETRY SHA-256"
            )
            return

        self.info_sha_value.config(
            text=digest,
            fg=TEXT
        )
        self.info_analyze_button.config(
            state="normal",
            text="RECALCULATE SHA-256"
        )
        if self.info_copy_sha_button is not None:
            self.info_copy_sha_button.config(state="normal")


    def copy_info_sha(self):

        value = self.info_sha_value.cget("text").strip()
        if not value or value.startswith("Calculating") or value.startswith("ERROR"):
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()
        self.status_label.config(
            text="● SHA-256 COPIED",
            fg=GREEN
        )


    def copy_info_path(self):

        if not self.info_current_path:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(str(self.info_current_path))
        self.root.update()
        self.status_label.config(
            text="● PATH COPIED",
            fg=GREEN
        )


    def open_info_location(self):

        path = self.info_current_path
        if not path or not path.exists():
            return
        try:
            location = path.parent if path.is_file() else path
            os.startfile(str(location))
            self.status_label.config(
                text="● LOCATION OPENED",
                fg=PURPLE
            )
        except OSError as error:
            messagebox.showerror(
                "NOVA",
                f"Could not open location:\n{error}"
            )


    # ========================================================
    # OPERATION QUEUE (PHASE 4 / STEP 2)
    # ========================================================

    def queue_add_files(self):

        if self.queue_running:
            return

        paths = filedialog.askopenfilenames(
            title="Add Files to Queue"
        )

        if not paths:
            return

        added = 0

        for raw_path in paths:
            path = Path(raw_path)

            if not path.is_file():
                continue

            if any(item["path"] == path for item in self.queue_items):
                continue

            self.queue_items.append({
                "path": path,
                "status": "WAITING",
                "detail": ""
            })
            added += 1

        self.refresh_queue_ui()

        if added:
            self.status_label.config(
                text=f"● {added} FILE{'S' if added != 1 else ''} ADDED TO QUEUE",
                fg=CYAN
            )


    def queue_add_folder(self):

        if self.queue_running:
            return

        path = filedialog.askdirectory(
            title="Add Folder to Queue"
        )

        if not path:
            return

        path = Path(path)

        if any(item["path"] == path for item in self.queue_items):
            return

        self.queue_items.append({
            "path": path,
            "status": "WAITING",
            "detail": ""
        })

        self.refresh_queue_ui()
        self.status_label.config(
            text="● FOLDER ADDED TO QUEUE",
            fg=GREEN
        )


    def queue_remove_selected(self):

        if self.queue_running or self.queue_list is None:
            return

        selected = list(self.queue_list.curselection())

        if not selected:
            return

        for index in reversed(selected):
            if 0 <= index < len(self.queue_items):
                self.queue_items.pop(index)

        self.refresh_queue_ui()


    def queue_clear(self):

        if self.queue_running:
            return

        self.queue_items.clear()
        self.refresh_queue_ui()
        self.status_label.config(
            text="● QUEUE CLEARED",
            fg=YELLOW
        )


    def queue_selection_changed(self, event=None):

        if self.queue_remove_button is None:
            return

        selected = bool(self.queue_list and self.queue_list.curselection())
        can_remove = selected and not self.queue_running
        self.queue_remove_button.config(
            state="normal" if can_remove else "disabled"
        )


    def refresh_queue_ui(self):

        if self.queue_list is None:
            return

        self.queue_list.delete(0, "end")

        for index, item in enumerate(self.queue_items, start=1):
            path = item["path"]
            item_type = "FOLDER" if path.is_dir() else "FILE"
            detail = item.get("detail", "")
            detail_text = f" | {detail}" if detail else ""
            self.queue_list.insert(
                "end",
                f"{index:02d}  |  {item_type:<6} |  {item['status']:<10} |  {path}{detail_text}"
            )

        count = len(self.queue_items)

        if self.queue_count_label is not None:
            self.queue_count_label.config(
                text=f"{count} ITEM{'S' if count != 1 else ''}"
            )

        if self.queue_status_label is not None:
            if count == 0:
                text = "QUEUE READY — 0 ITEMS"
            else:
                waiting = sum(1 for item in self.queue_items if item["status"] == "WAITING")
                processing = sum(1 for item in self.queue_items if item["status"] == "PROCESSING")
                complete = sum(1 for item in self.queue_items if item["status"] == "COMPLETE")
                failed = sum(1 for item in self.queue_items if item["status"] == "FAILED")
                cancelled = sum(1 for item in self.queue_items if item["status"] == "CANCELLED")
                text = (
                    f"QUEUE {'RUNNING' if self.queue_running else 'READY'} — {count} ITEMS  |  "
                    f"WAITING: {waiting}  PROCESSING: {processing}  COMPLETE: {complete}  "
                    f"FAILED: {failed}  CANCELLED: {cancelled}"
                )

            self.queue_status_label.config(text=text)

        if self.queue_start_button is not None:
            has_waiting = any(item["status"] == "WAITING" for item in self.queue_items)
            self.queue_start_button.config(
                state="normal" if has_waiting and not self.queue_running else "disabled"
            )

        if self.queue_stop_button is not None:
            self.queue_stop_button.config(
                state="normal" if self.queue_running else "disabled"
            )

        self.queue_selection_changed()


    def _get_safe_queue_output_dir(self, source):
        """
        Return an output directory that is never the same as, or inside,
        the folder being compressed.

        For queue-only folder compression, an unsafe configured output
        directory is automatically redirected to a sibling directory.
        """
        source = Path(source).resolve()
        configured = Path(self.output_path).resolve()

        try:
            configured.relative_to(source)
            unsafe = True
        except ValueError:
            unsafe = False

        if not unsafe:
            configured.mkdir(parents=True, exist_ok=True)
            return configured

        base = source.parent / f"{source.name}_NOVA_QUEUE_OUTPUT"
        candidate = base
        index = 1

        while candidate.exists() and not candidate.is_dir():
            candidate = source.parent / (
                f"{source.name}_NOVA_QUEUE_OUTPUT ({index})"
            )
            index += 1

        candidate.mkdir(parents=True, exist_ok=True)
        return candidate


    def _queue_prepare_item_ui(self, index, done_event):

        item = self.queue_items[index]
        source = item["path"]

        if self.cancel_event.is_set():
            item["status"] = "CANCELLED"
            item["detail"] = "Queue stopped"
            done_event.set()
            self.refresh_queue_ui()
            return

        self.selected_path = source

        if source.is_file():
            self.path_label.config(
                text=f"FILE: {source}",
                fg=CYAN
            )
        else:
            self.path_label.config(
                text=f"FOLDER: {source}",
                fg=GREEN
            )

        original_output_path = self.output_path
        queue_output_path = original_output_path
        auto_routed = False

        if source.is_dir():
            queue_output_path = self._get_safe_queue_output_dir(source)
            auto_routed = (
                Path(queue_output_path).resolve()
                != Path(original_output_path).resolve()
            )

        if queue_output_path:
            self.output_label.config(
                text=f"OUTPUT: {queue_output_path}",
                fg=PURPLE
            )

        item["status"] = "PROCESSING"
        item["detail"] = (
            f"Auto output: {queue_output_path.name}"
            if auto_routed
            else "Resolving output"
        )
        self.refresh_queue_ui()

        try:
            self.output_path = queue_output_path

            resolved = self.resolve_compression_output_conflict()

            item["output"] = (
                self.compression_output_path
                if resolved
                else None
            )
            item["decision_cancelled"] = not resolved

            if resolved:
                item["detail"] = (
                    f"Auto output: {queue_output_path.name}"
                    if auto_routed
                    else "Output resolved"
                )
            else:
                item["detail"] = "Conflict cancelled"

        except Exception as error:
            item["output"] = None
            item["decision_cancelled"] = True
            item["detail"] = str(error)[:80]

        finally:
            self.output_path = original_output_path

        self.output_label.config(
            text=f"OUTPUT: {original_output_path}",
            fg=PURPLE
        )

        done_event.set()
        self.refresh_queue_ui()


    def _queue_process_item(self, item):

        source = item["path"]
        output = item.get("output")

        if output is None:
            raise ValueError("Compression output path was not resolved.")

        if source.is_file():
            metrics = self._queue_compress_file(source, output)
        elif source.is_dir():
            metrics = self._queue_compress_folder(source, output)
        else:
            raise ValueError("Queued path is invalid.")

        return metrics


    def start_queue(self):

        if self.queue_running or self.is_running:
            return

        if not self.output_path:
            messagebox.showwarning(
                "NOVA — QUEUE",
                "Please select an output folder first."
            )
            return

        pending = [
            item for item in self.queue_items
            if item["status"] == "WAITING"
        ]

        if not pending:
            messagebox.showinfo(
                "NOVA — QUEUE",
                "There are no WAITING items in the queue."
            )
            return

        self.queue_running = True
        self.cancel_event.clear()
        self.refresh_queue_ui()
        self.set_buttons(False)
        self.status_label.config(
            text=f"● QUEUE STARTED — {len(pending)} ITEM{'S' if len(pending) != 1 else ''}",
            fg=ORANGE
        )

        thread = threading.Thread(
            target=self._queue_worker,
            daemon=True
        )
        thread.start()


    def stop_queue(self):

        if not self.queue_running:
            return

        self.cancel_event.set()
        self.status_label.config(
            text="● QUEUE STOPPING...",
            fg=YELLOW
        )
        self.result_label.config(
            text="Stopping queue safely after the current operation...",
            fg=YELLOW
        )
        self.refresh_queue_ui()


    def _queue_worker(self):

        summary = {
            "complete": 0,
            "failed": 0,
            "cancelled": 0,
        }

        for index, item in enumerate(self.queue_items):

            if item["status"] != "WAITING":
                continue

            if self.cancel_event.is_set():
                item["status"] = "CANCELLED"
                item["detail"] = "Queue stopped before processing"
                summary["cancelled"] += 1
                continue

            done_event = threading.Event()
            self.root.after(
                0,
                self._queue_prepare_item_ui,
                index,
                done_event
            )
            done_event.wait()

            if self.cancel_event.is_set():
                item["status"] = "CANCELLED"
                item["detail"] = "Queue stopped"
                summary["cancelled"] += 1
                continue

            if item.get("decision_cancelled"):
                item["status"] = "CANCELLED"
                if not item.get("detail") or item["detail"] == "Output resolved":
                    item["detail"] = "Conflict cancelled"
                summary["cancelled"] += 1
                self.root.after(0, self.refresh_queue_ui)
                continue

            item["status"] = "PROCESSING"
            item["detail"] = "Compressing"
            self.root.after(0, self.refresh_queue_ui)

            try:
                metrics = self._queue_process_item(item)

                item["status"] = "COMPLETE"
                item["detail"] = metrics.get("detail", "Complete")
                summary["complete"] += 1

                source = item["path"]
                self.record_compression_success(
                    metrics.get("original_size", 0),
                    metrics.get("compressed_size", 0),
                    metrics.get("reduction", 0),
                    metrics.get("ratio", 0),
                    metrics.get("elapsed", 0),
                    source
                )

                output = metrics["output"]
                detail = metrics.get("history_detail", "QUEUE")

                self.root.after(
                    0,
                    self.add_history,
                    "COMPRESSED FOLDER" if source.is_dir() else "COMPRESSED FILE",
                    source,
                    output,
                    detail
                )

                self.root.after(
                    0,
                    self.result_label.config,
                    {"text": f"QUEUE ITEM COMPLETE\\n\\n{source.name}\\n\\nOUTPUT:\\n{output}", "fg": GREEN}
                )

            except CompressionCancelled:
                item["status"] = "CANCELLED"
                item["detail"] = "Stopped by user"
                summary["cancelled"] += 1
                self.record_compression_cancelled(item["path"])
                self.root.after(0, self.refresh_queue_ui)
                break

            except Exception as error:
                item["status"] = "FAILED"
                item["detail"] = str(error)[:80]
                summary["failed"] += 1
                self.record_compression_failure(item["path"])
                self.root.after(
                    0,
                    self.status_label.config,
                    {"text": f"● QUEUE ITEM FAILED — {source.name}", "fg": RED}
                )
                self.root.after(0, self.refresh_queue_ui)
                # Continue with the next item.
                continue

            self.root.after(0, self.refresh_queue_ui)

        # Any still-waiting items are cancelled when STOP QUEUE was used.
        if self.cancel_event.is_set():
            for item in self.queue_items:
                if item["status"] == "WAITING":
                    item["status"] = "CANCELLED"
                    item["detail"] = "Queue stopped"
                    summary["cancelled"] += 1
                    self.record_compression_cancelled(item["path"])

        self.root.after(0, self._queue_finished_ui, summary)


    def _queue_finished_ui(self, summary):

        self.queue_running = False
        self.cancel_event.clear()
        self.is_running = False
        self.set_buttons(True)

        self.progress.set(100 if summary["complete"] else 0)

        total = (
            summary["complete"] +
            summary["failed"] +
            summary["cancelled"]
        )

        if summary["failed"]:
            status_text = (
                f"● QUEUE FINISHED — {summary['complete']} COMPLETE / "
                f"{summary['failed']} FAILED / {summary['cancelled']} CANCELLED"
            )
            status_color = RED
        elif summary["cancelled"]:
            status_text = (
                f"● QUEUE STOPPED — {summary['complete']} COMPLETE / "
                f"{summary['cancelled']} CANCELLED"
            )
            status_color = YELLOW
        else:
            status_text = f"● QUEUE COMPLETE — {summary['complete']} ITEM{'S' if total != 1 else ''}"
            status_color = GREEN

        self.status_label.config(
            text=status_text,
            fg=status_color
        )

        self.refresh_queue_ui()

        self.result_label.config(
            text=(
                "QUEUE SUMMARY\n\n"
                f"COMPLETE  : {summary['complete']}\n"
                f"FAILED    : {summary['failed']}\n"
                f"CANCELLED : {summary['cancelled']}"
            ),
            fg=status_color
        )


    def _queue_compress_file(self, source, output):

        profile = self.compression_profile.get()
        level = COMPRESSION_PROFILES[profile]
        output = Path(output)
        partial_output = Path(str(output) + ".partial")
        hash_file = Path(str(output) + ".sha256")
        hash_partial = Path(str(hash_file) + ".partial")

        original_size = source.stat().st_size
        original_hash = sha256_file(source)

        if partial_output.exists():
            partial_output.unlink()
        if hash_partial.exists():
            hash_partial.unlink()

        self.root.after(
            0,
            self.status_label.config,
            {"text": f"● QUEUE COMPRESSING — {source.name}", "fg": ORANGE}
        )

        compressor = zstd.ZstdCompressor(level=level)
        start = time.time()
        processed = 0

        try:
            with open(source, "rb") as fin:
                with open(partial_output, "wb") as fout:
                    with compressor.stream_writer(fout) as writer:
                        while True:
                            if self.cancel_event.is_set():
                                raise CompressionCancelled("Queue compression cancelled.")

                            chunk = fin.read(CHUNK_SIZE)
                            if not chunk:
                                break

                            writer.write(chunk)
                            processed += len(chunk)
                            self.update_compression_progress(
                                processed,
                                original_size,
                                start
                            )

            if self.cancel_event.is_set():
                raise CompressionCancelled("Queue compression cancelled.")

            # Prepare the matching SHA-256 sidecar before swapping output.
            hash_partial.write_text(
                original_hash,
                encoding="utf-8"
            )

            partial_output.replace(output)
            hash_partial.replace(hash_file)

        except CompressionCancelled:
            if partial_output.exists():
                partial_output.unlink()
            if hash_partial.exists():
                hash_partial.unlink()
            raise
        except Exception:
            if partial_output.exists():
                partial_output.unlink()
            if hash_partial.exists():
                hash_partial.unlink()
            raise

        elapsed = time.time() - start
        compressed_size = output.stat().st_size
        reduction = ((1 - compressed_size / original_size) * 100) if original_size else 0
        ratio = (original_size / compressed_size) if compressed_size else 0

        return {
            "output": output,
            "detail": f"{profile} / L{level}",
            "history_detail": f"{profile} / L{level}",
            "original_size": original_size,
            "compressed_size": compressed_size,
            "reduction": reduction,
            "ratio": ratio,
            "elapsed": elapsed,
        }


    def _queue_compress_folder(self, source, output):

        profile = self.compression_profile.get()
        level = COMPRESSION_PROFILES[profile]
        output = Path(output)
        partial_output = Path(str(output) + ".partial")
        hash_file = Path(str(output) + ".sha256")
        hash_partial = Path(str(hash_file) + ".partial")

        total_size = calculate_folder_size(source)

        try:
            output.parent.resolve().relative_to(source.resolve())
            raise ValueError(
                "Output folder cannot be inside the folder being compressed."
            )
        except ValueError as error:
            if "Output folder" in str(error):
                raise

        if partial_output.exists():
            partial_output.unlink()
        if hash_partial.exists():
            hash_partial.unlink()

        self.root.after(
            0,
            self.status_label.config,
            {"text": f"● QUEUE COMPRESSING — {source.name}", "fg": ORANGE}
        )

        compressor = zstd.ZstdCompressor(level=level)
        start = time.time()
        processed = 0

        def progress_callback(count):
            nonlocal processed
            if self.cancel_event.is_set():
                raise CompressionCancelled("Queue compression cancelled.")
            processed += count
            self.update_compression_progress(processed, total_size, start)

        try:
            with open(partial_output, "wb") as fout:
                with compressor.stream_writer(fout) as zstd_writer:
                    with tarfile.open(fileobj=zstd_writer, mode="w|") as tar:
                        base_parent = source.parent

                        for root, dirs, files in os.walk(source):
                            if self.cancel_event.is_set():
                                raise CompressionCancelled("Queue compression cancelled.")

                            root_path = Path(root)

                            for dirname in dirs:
                                if self.cancel_event.is_set():
                                    raise CompressionCancelled("Queue compression cancelled.")
                                directory = root_path / dirname
                                arcname = directory.relative_to(base_parent)
                                info = tar.gettarinfo(str(directory), arcname=str(arcname))
                                tar.addfile(info)

                            for filename in files:
                                if self.cancel_event.is_set():
                                    raise CompressionCancelled("Queue compression cancelled.")
                                file_path = root_path / filename
                                arcname = file_path.relative_to(base_parent)
                                info = tar.gettarinfo(str(file_path), arcname=str(arcname))

                                if info.isreg():
                                    with open(file_path, "rb") as f:
                                        reader = ProgressReader(f, progress_callback)
                                        try:
                                            tar.addfile(info, reader)
                                        finally:
                                            reader.close()
                                else:
                                    tar.addfile(info)

            if self.cancel_event.is_set():
                raise CompressionCancelled("Queue compression cancelled.")

            archive_hash = sha256_file(partial_output)
            hash_partial.write_text(archive_hash, encoding="utf-8")

            partial_output.replace(output)
            hash_partial.replace(hash_file)

        except CompressionCancelled:
            if partial_output.exists():
                partial_output.unlink()
            if hash_partial.exists():
                hash_partial.unlink()
            raise
        except Exception:
            if partial_output.exists():
                partial_output.unlink()
            if hash_partial.exists():
                hash_partial.unlink()
            raise

        elapsed = time.time() - start
        compressed_size = output.stat().st_size
        reduction = ((1 - compressed_size / total_size) * 100) if total_size else 0
        ratio = (total_size / compressed_size) if compressed_size else 0

        return {
            "output": output,
            "detail": f"{profile} / L{level}",
            "history_detail": f"{profile} / L{level}",
            "original_size": total_size,
            "compressed_size": compressed_size,
            "reduction": reduction,
            "ratio": ratio,
            "elapsed": elapsed,
        }


    # ========================================================
    # DRAG & DROP

    # ========================================================

    def drag_enter(self, event):

        self.drop_frame.config(
            bg="#13261E",
            highlightbackground=GREEN
        )

        self.drop_label.config(
            bg="#13261E",
            fg=GREEN
        )

        self.drop_hint.config(
            bg="#18232B"
        )


    def drag_leave(self, event):

        self.drop_frame.config(
            bg="#0B131D",
            highlightbackground=CYAN
        )

        self.drop_label.config(
            bg="#0B131D",
            fg=CYAN
        )

        self.drop_hint.config(
            bg="#0B131D"
        )


    def handle_drop(self, event):

        self.drag_leave(event)

        try:

            paths = self.root.tk.splitlist(
                event.data
            )

            if not paths:
                return

            if len(paths) > 1:

                messagebox.showwarning(
                    "NOVA COMPRESSOR",
                    "Please drop one file or one folder at a time."
                )
                return

            path = Path(paths[0])

            if not path.exists():

                messagebox.showerror(
                    "NOVA ERROR",
                    f"Path not found:\n{path}"
                )
                return

            self.selected_path = path
            self.update_info_panel(path)

            if path.is_file():

                self.path_label.config(
                    text=f"FILE: {path}",
                    fg=CYAN
                )

                self.status_label.config(
                    text="● FILE DROPPED",
                    fg=GREEN
                )

                self.drop_label.config(
                    text="FILE READY"
                )

            elif path.is_dir():

                self.path_label.config(
                    text=f"FOLDER: {path}",
                    fg=GREEN
                )

                self.status_label.config(
                    text="● FOLDER DROPPED",
                    fg=GREEN
                )

                self.drop_label.config(
                    text="FOLDER READY"
                )

            else:

                messagebox.showerror(
                    "NOVA ERROR",
                    "Dropped item is not a supported file or folder."
                )

        except Exception as error:

            messagebox.showerror(
                "NOVA ERROR",
                str(error)
            )


    # ========================================================
    # SELECT FILE
    # ========================================================

    def select_file(self):

        path = filedialog.askopenfilename(
            title="Select File"
        )

        if not path:
            return

        self.selected_path = Path(path)
        self.update_info_panel(self.selected_path)

        self.path_label.config(
            text=f"FILE: {self.selected_path}",
            fg=CYAN
        )

        self.status_label.config(
            text="● FILE SELECTED",
            fg=GREEN
        )


    # ========================================================
    # SELECT FOLDER
    # ========================================================

    def select_folder(self):

        path = filedialog.askdirectory(
            title="Select Folder"
        )

        if not path:
            return

        self.selected_path = Path(path)
        self.update_info_panel(self.selected_path)

        self.path_label.config(
            text=f"FOLDER: {self.selected_path}",
            fg=GREEN
        )

        self.status_label.config(
            text="● FOLDER SELECTED",
            fg=GREEN
        )


    # ========================================================
    # OUTPUT
    # ========================================================

    def select_output(self):

        path = filedialog.askdirectory(
            title="Select Output Folder"
        )

        if not path:
            return

        self.output_path = Path(path)

        self.output_label.config(
            text=f"OUTPUT: {self.output_path}",
            fg=PURPLE
        )

        if self.settings_output_var is not None:
            self.settings_output_var.set(
                str(self.output_path)
            )

        self.status_label.config(
            text="● OUTPUT READY",
            fg=PURPLE
        )


    # ========================================================
    # COMPRESSION PROFILE
    # ========================================================

    def select_profile(self, profile):

        if self.is_running:
            return

        self.compression_profile.set(profile)
        self.update_profile_buttons()

        if self.settings_profile_var is not None:
            self.settings_profile_var.set(profile)

        level = COMPRESSION_PROFILES[profile]

        self.status_label.config(
            text=f"● PROFILE SELECTED — {profile}",
            fg=YELLOW
        )

    def update_profile_buttons(self):

        selected = self.compression_profile.get()

        for profile, button in self.profile_button_widgets.items():

            if profile == selected:
                button.config(
                    relief="sunken",
                    bd=3,
                    text=f"✓ {profile}"
                )
            else:
                button.config(
                    relief="flat",
                    bd=1,
                    text=profile
                )

        level = COMPRESSION_PROFILES[selected]

        self.profile_status_label.config(
            text=f"SELECTED: {selected} (ZSTD LEVEL {level})"
        )


    # ========================================================
    # ADAPTIVE LEVEL
    # ========================================================

    def analyze_file(self, path):

        sample_size = 16 * 1024 * 1024

        with open(path, "rb") as f:

            sample = f.read(
                sample_size
            )

        if not sample:
            return 1

        compressor = zstd.ZstdCompressor(
            level=1
        )

        compressed = compressor.compress(
            sample
        )

        ratio = (
            len(compressed) /
            len(sample)
        )

        if ratio < 0.10:
            return 3

        elif ratio < 0.30:
            return 5

        elif ratio < 0.60:
            return 9

        elif ratio < 0.90:
            return 3

        else:
            return 1


    # ========================================================
    # PHASE 4 / STEP 1 — OUTPUT CONFLICT MANAGER
    # ========================================================

    def get_default_compression_output(self):

        if not self.selected_path or not self.output_path:
            return None

        if self.selected_path.is_file():
            return self.output_path / (self.selected_path.name + ".zst")

        if self.selected_path.is_dir():
            return self.output_path / f"{self.selected_path.name}.tar.zst"

        return None


    def make_unique_output_path(self, path):

        path = Path(path)

        if not path.exists() and not Path(str(path) + ".sha256").exists():
            return path

        # Keep the semantic extension intact:
        # file.txt.zst -> file.txt (1).zst
        # Folder.tar.zst -> Folder (1).tar.zst
        if path.name.lower().endswith(".tar.zst"):
            stem = path.name[:-8]
            suffix = ".tar.zst"
        elif path.suffix.lower() == ".zst":
            stem = path.stem
            suffix = path.suffix
        else:
            stem = path.stem
            suffix = path.suffix

        index = 1

        while True:
            candidate = path.with_name(
                f"{stem} ({index}){suffix}"
            )

            if (
                not candidate.exists()
                and
                not Path(str(candidate) + ".sha256").exists()
                and
                not Path(str(candidate) + ".partial").exists()
            ):
                return candidate

            index += 1


    def resolve_compression_output_conflict(self):

        candidate = self.get_default_compression_output()

        if candidate is None:
            return False

        hash_candidate = Path(str(candidate) + ".sha256")
        partial_candidate = Path(str(candidate) + ".partial")

        conflict = (
            candidate.exists()
            or hash_candidate.exists()
            or partial_candidate.exists()
        )

        if not conflict:
            self.compression_output_path = candidate
            return True

        dialog = tk.Toplevel(self.root)
        dialog.title("NOVA — Output Already Exists")
        dialog.configure(bg="#070A0F")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        result = {"choice": None}

        card = tk.Frame(
            dialog,
            bg="#0F1621",
            highlightbackground="#1B2A3A",
            highlightthickness=1
        )
        card.pack(padx=18, pady=18)

        tk.Label(
            card,
            text="OUTPUT ALREADY EXISTS",
            font=("Segoe UI", 13, "bold"),
            bg="#0F1621",
            fg=CYAN
        ).pack(anchor="w", padx=18, pady=(18, 6))

        tk.Label(
            card,
            text=f"NOVA found an existing compression output:\n{candidate}",
            font=("Segoe UI", 9),
            justify="left",
            bg="#0F1621",
            fg="#A9B4C2",
            wraplength=560
        ).pack(anchor="w", padx=18)

        tk.Label(
            card,
            text="Choose how to handle the existing output.",
            font=("Segoe UI", 9, "bold"),
            bg="#0F1621",
            fg="#F5F7FA"
        ).pack(anchor="w", padx=18, pady=(10, 16))

        button_row = tk.Frame(card, bg="#0F1621")
        button_row.pack(fill="x", padx=18, pady=(0, 18))

        def choose(choice):
            result["choice"] = choice
            dialog.destroy()

        tk.Button(
            button_row, text="OVERWRITE",
            font=("Segoe UI", 9, "bold"),
            bg=ORANGE, fg=BG,
            activebackground=YELLOW,
            relief="flat", cursor="hand2",
            command=lambda: choose("overwrite")
        ).pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=8)

        tk.Button(
            button_row, text="CREATE NEW",
            font=("Segoe UI", 9, "bold"),
            bg=GREEN, fg=BG,
            activebackground=CYAN,
            relief="flat", cursor="hand2",
            command=lambda: choose("new")
        ).pack(side="left", fill="x", expand=True, padx=6, ipady=8)

        tk.Button(
            button_row, text="CANCEL",
            font=("Segoe UI", 9, "bold"),
            bg=RED, fg=BG,
            activebackground=PINK,
            relief="flat", cursor="hand2",
            command=lambda: choose("cancel")
        ).pack(side="left", fill="x", expand=True, padx=(6, 0), ipady=8)

        dialog.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))
        dialog.update_idletasks()

        width = dialog.winfo_reqwidth()
        height = dialog.winfo_reqheight()
        x = self.root.winfo_x() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - height) // 2
        dialog.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")

        self.root.wait_window(dialog)

        choice = result["choice"]

        if choice == "overwrite":
            self.compression_output_path = candidate
            return True

        if choice == "new":
            self.compression_output_path = self.make_unique_output_path(candidate)
            return True

        self.compression_output_path = None
        return False


    # ========================================================
    # START COMPRESSION
    # ========================================================

    def start_compression(self):

        if self.is_running:
            return

        if not self.selected_path:

            messagebox.showwarning(
                "NOVA",
                "Please select a file or folder."
            )

            return

        if not self.output_path:

            messagebox.showwarning(
                "NOVA",
                "Please select output folder."
            )

            return

        # Phase 4 / Step 1: resolve any existing output before
        # starting the background compression worker.
        if not self.resolve_compression_output_conflict():
            self.status_label.config(
                text="● COMPRESSION CANCELLED",
                fg=YELLOW
            )
            return

        self.active_compression = True
        self.is_running = True
        self.cancel_event.clear()

        self.set_buttons(
            False
        )

        self.progress.set(0)

        self.result_label.config(
            text=""
        )

        thread = threading.Thread(
            target=self.compress_selected,
            daemon=True
        )

        thread.start()


    # ========================================================
    # SELECTED COMPRESSION
    # ========================================================

    def compress_selected(self):

        try:

            if self.selected_path.is_file():

                self.compress_file()

            elif self.selected_path.is_dir():

                self.compress_folder()

            else:

                raise ValueError(
                    "Selected path is invalid."
                )

        except Exception as e:

            self.root.after(
                0,
                self.operation_error,
                str(e)
            )


    # ========================================================
    # FILE COMPRESSION
    # ========================================================

    def compress_file(self):

        source = self.selected_path

        profile = self.compression_profile.get()
        level = COMPRESSION_PROFILES[profile]

        output = self.compression_output_path

        if output is None:
            raise ValueError(
                "Compression output path was not resolved."
            )

        partial_output = Path(
            str(output) + ".partial"
        )

        hash_file = Path(
            str(output) + ".sha256"
        )

        original_size = source.stat().st_size

        self.root.after(
            0,
            lambda: self.status_label.config(
                text=f"● COMPRESSING FILE — {profile} — LEVEL {level}",
                fg=ORANGE
            )
        )

        # Remove stale partial output from an earlier interrupted run.
        if partial_output.exists():
            partial_output.unlink()

        original_hash = sha256_file(
            source
        )

        compressor = zstd.ZstdCompressor(
            level=level
        )

        start = time.time()
        processed = 0

        try:

            with open(source, "rb") as fin:

                with open(
                    partial_output,
                    "wb"
                ) as fout:

                    with compressor.stream_writer(
                        fout
                    ) as writer:

                        while True:

                            if self.cancel_event.is_set():
                                raise CompressionCancelled(
                                    "File compression cancelled by user."
                                )

                            chunk = fin.read(
                                CHUNK_SIZE
                            )

                            if not chunk:
                                break

                            writer.write(
                                chunk
                            )

                            processed += len(
                                chunk
                            )

                            self.update_compression_progress(
                                processed,
                                original_size,
                                start
                            )

            if self.cancel_event.is_set():
                raise CompressionCancelled(
                    "File compression cancelled by user."
                )

            # Finalize only after the complete stream succeeds.
            partial_output.replace(output)

        except CompressionCancelled:

            if partial_output.exists():
                partial_output.unlink()

            # A previous final archive must not be reported as the
            # result of this cancelled run.
            if output.exists():
                output.unlink()

            if hash_file.exists():
                hash_file.unlink()

            self.root.after(
                0,
                self.operation_cancelled,
                "FILE COMPRESSION CANCELLED"
            )
            return

        except Exception:

            if partial_output.exists():
                partial_output.unlink()

            raise

        elapsed = time.time() - start

        compressed_size = output.stat().st_size

        reduction = (
            1 -
            compressed_size /
            original_size
        ) * 100 if original_size else 0

        ratio = (
            original_size /
            compressed_size
            if compressed_size
            else 0
        )

        with open(
            hash_file,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                original_hash
            )

        self.root.after(
            0,
            self.file_compression_complete,
            output,
            hash_file,
            profile,
            level,
            original_size,
            compressed_size,
            reduction,
            ratio,
            elapsed
        )


    # ========================================================
    # FOLDER COMPRESSION
    # ========================================================

    def compress_folder(self):

        source = self.selected_path

        output = self.compression_output_path

        if output is None:
            raise ValueError(
                "Compression output path was not resolved."
            )

        partial_output = Path(
            str(output) + ".partial"
        )

        hash_file = Path(
            str(output) + ".sha256"
        )

        total_size = calculate_folder_size(
            source
        )

        # Prevent output inside source folder.
        try:

            self.output_path.resolve().relative_to(
                source.resolve()
            )

            raise ValueError(
                "Output folder cannot be inside "
                "the folder being compressed."
            )

        except ValueError as e:

            if "Output folder" in str(e):
                raise

        self.root.after(
            0,
            lambda: self.status_label.config(
                text="● COMPRESSING FOLDER",
                fg=ORANGE
            )
        )

        profile = self.compression_profile.get()
        level = COMPRESSION_PROFILES[profile]

        self.root.after(
            0,
            lambda: self.status_label.config(
                text=f"● COMPRESSING FOLDER — {profile} — LEVEL {level}",
                fg=ORANGE
            )
        )

        # Remove stale partial output from an earlier interrupted run.
        if partial_output.exists():
            partial_output.unlink()

        compressor = zstd.ZstdCompressor(
            level=level
        )

        start = time.time()
        processed = 0

        def progress_callback(count):

            nonlocal processed

            if self.cancel_event.is_set():
                raise CompressionCancelled(
                    "Folder compression cancelled by user."
                )

            processed += count

            self.update_compression_progress(
                processed,
                total_size,
                start
            )

        try:

            with open(
                partial_output,
                "wb"
            ) as fout:

                with compressor.stream_writer(
                    fout
                ) as zstd_writer:

                    with tarfile.open(
                        fileobj=zstd_writer,
                        mode="w|"
                    ) as tar:

                        base_parent = source.parent

                        for root, dirs, files in os.walk(
                            source
                        ):

                            if self.cancel_event.is_set():
                                raise CompressionCancelled(
                                    "Folder compression cancelled by user."
                                )

                            root_path = Path(root)

                            # Add directories.
                            for dirname in dirs:

                                if self.cancel_event.is_set():
                                    raise CompressionCancelled(
                                        "Folder compression cancelled by user."
                                    )

                                directory = (
                                    root_path /
                                    dirname
                                )

                                arcname = directory.relative_to(
                                    base_parent
                                )

                                info = tar.gettarinfo(
                                    str(directory),
                                    arcname=str(arcname)
                                )

                                tar.addfile(
                                    info
                                )

                            # Add files.
                            for filename in files:

                                if self.cancel_event.is_set():
                                    raise CompressionCancelled(
                                        "Folder compression cancelled by user."
                                    )

                                file_path = (
                                    root_path /
                                    filename
                                )

                                arcname = file_path.relative_to(
                                    base_parent
                                )

                                info = tar.gettarinfo(
                                    str(file_path),
                                    arcname=str(arcname)
                                )

                                if info.isreg():

                                    with open(
                                        file_path,
                                        "rb"
                                    ) as f:

                                        reader = ProgressReader(
                                            f,
                                            progress_callback
                                        )

                                        try:
                                            tar.addfile(
                                                info,
                                                reader
                                            )
                                        finally:
                                            reader.close()

                                else:

                                    tar.addfile(
                                        info
                                    )

            if self.cancel_event.is_set():
                raise CompressionCancelled(
                    "Folder compression cancelled by user."
                )

            # Finalize only after the complete archive succeeds.
            partial_output.replace(output)

        except CompressionCancelled:

            if partial_output.exists():
                partial_output.unlink()

            if output.exists():
                output.unlink()

            if hash_file.exists():
                hash_file.unlink()

            self.root.after(
                0,
                self.operation_cancelled,
                "FOLDER COMPRESSION CANCELLED"
            )
            return

        except Exception:

            if partial_output.exists():
                partial_output.unlink()

            raise

        elapsed = time.time() - start

        compressed_size = output.stat().st_size

        reduction = (
            1 -
            compressed_size /
            total_size
        ) * 100 if total_size else 0

        ratio = (
            total_size /
            compressed_size
            if compressed_size
            else 0
        )

        # Hash compressed archive only after successful completion.
        archive_hash = sha256_file(
            output
        )

        with open(
            hash_file,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                archive_hash
            )

        self.root.after(
            0,
            self.folder_compression_complete,
            output,
            hash_file,
            profile,
            level,
            total_size,
            compressed_size,
            reduction,
            ratio,
            elapsed
        )


    # ========================================================
    # PHASE 4 / STEP 4 PART 1: VALIDATE ZSTD
    # ========================================================

    def start_validation(self):

        if self.is_running:
            return

        selected = self.selected_path

        if not (
            selected
            and selected.is_file()
            and selected.name.lower().endswith(".zst")
        ):
            path = filedialog.askopenfilename(
                title="Select Zstd Archive to Validate",
                filetypes=[
                    ("Zstd files", "*.zst"),
                    ("All files", "*.*")
                ]
            )

            if not path:
                return

            selected = Path(path)

        if not selected.exists() or not selected.is_file():
            messagebox.showwarning(
                "NOVA",
                "Selected Zstd archive does not exist."
            )
            return

        self.selected_path = selected
        self.update_info_panel(selected)

        self.is_running = True
        self.cancel_event.clear()

        self.status_label.config(
            text="● VALIDATING ZSTD ARCHIVE",
            fg=CYAN
        )

        self.set_buttons(False)
        self.progress.set(0)
        self.progress_label.config(
            text="PROGRESS: VALIDATING...",
            fg=CYAN
        )
        self.info_label.config(
            text="CHECKING ZSTD FRAME / ARCHIVE...",
            fg=ORANGE
        )
        self.result_label.config(text="")

        thread = threading.Thread(
            target=self.validate_zstd_archive,
            args=(selected,),
            daemon=True
        )
        thread.start()


    def validate_zstd_archive(self, source):

        start = time.time()
        compressed_size = source.stat().st_size
        decompressed_bytes = 0
        member_count = 0
        is_tar_archive = source.name.lower().endswith(".tar.zst")

        try:
            with open(source, "rb") as fin:
                decompressor = zstd.ZstdDecompressor()

                # For normal .zst files, the sidecar stores the SHA-256
                # of the original/uncompressed source data.
                decoded_hash = hashlib.sha256()

                with decompressor.stream_reader(fin) as reader:

                    if is_tar_archive:
                        with tarfile.open(
                            fileobj=reader,
                            mode="r|"
                        ) as tar:
                            for member in tar:
                                if self.cancel_event.is_set():
                                    raise CompressionCancelled(
                                        "Validation cancelled by user."
                                    )

                                member_count += 1

                                if member.isreg():
                                    extracted = tar.extractfile(member)

                                    if extracted is not None:
                                        while True:
                                            chunk = extracted.read(CHUNK_SIZE)

                                            if not chunk:
                                                break

                                            decompressed_bytes += len(chunk)

                                        extracted.close()

                    else:
                        while True:
                            if self.cancel_event.is_set():
                                raise CompressionCancelled(
                                    "Validation cancelled by user."
                                )

                            chunk = reader.read(CHUNK_SIZE)

                            if not chunk:
                                break

                            decompressed_bytes += len(chunk)
                            decoded_hash.update(chunk)

            elapsed = time.time() - start

            hash_file = Path(str(source) + ".sha256")
            expected_hash = None
            hash_status = "NOT AVAILABLE"

            if is_tar_archive:
                # Folder archives currently store the SHA-256 of the
                # compressed .tar.zst archive in the sidecar.
                actual_hash = sha256_file(source)
                hash_mode = "ARCHIVE SHA-256"
            else:
                # File archives store the SHA-256 of the original source.
                actual_hash = decoded_hash.hexdigest()
                hash_mode = "DECODED DATA SHA-256"

            if hash_file.exists():

                with open(
                    hash_file,
                    "r",
                    encoding="utf-8"
                ) as f:
                    expected_hash = f.read().strip().lower()

                hash_status = (
                    "PASS"
                    if expected_hash == actual_hash.lower()
                    else "FAIL"
                )

            self.root.after(
                0,
                self.validation_complete,
                source,
                compressed_size,
                decompressed_bytes,
                member_count,
                elapsed,
                actual_hash,
                expected_hash,
                hash_status,
                hash_mode,
                is_tar_archive
            )

        except CompressionCancelled as e:

            self.root.after(
                0,
                self.operation_cancelled,
                str(e)
            )

        except Exception as e:

            self.root.after(
                0,
                self.operation_error,
                f"ZSTD VALIDATION FAILED:\\n{e}"
            )


    def validation_complete(
        self,
        source,
        compressed_size,
        decompressed_bytes,
        member_count,
        elapsed,
        actual_hash,
        expected_hash,
        hash_status,
        hash_mode,
        is_tar_archive
    ):

        self.is_running = False
        self.cancel_event.clear()
        self.set_buttons(True)
        self.progress.set(100)

        # Strict integrity validation:
        # A readable ZSTD stream is not enough for an integrity PASS.
        # The SHA-256 sidecar must exist and match the decoded/archive hash.
        validation_passed = hash_status == "PASS"
        result_color = GREEN if validation_passed else RED

        self.status_label.config(
            text=(
                "● ZSTD VALIDATION PASSED"
                if validation_passed
                else "● ZSTD VALIDATION FAILED"
            ),
            fg=result_color
        )

        self.progress_label.config(
            text="PROGRESS: 100.00%",
            fg=result_color
        )

        self.info_label.config(
            text=f"VALIDATED IN {elapsed:.2f}s",
            fg=result_color
        )

        archive_type = (
            "TAR + ZSTD ARCHIVE"
            if is_tar_archive
            else "ZSTD FILE"
        )

        extra = (
            f"\\nTAR MEMBERS    : {member_count}"
            if is_tar_archive
            else ""
        )

        self.add_history(
            "VALIDATED ZSTD",
            source,
            source,
            f"{archive_type} / {hash_mode} {hash_status}"
        )

        status_line = (
            "PASS"
            if validation_passed
            else "FAIL"
        )

        self.result_label.config(
            text=(
                f"VALIDATION      : {status_line}\\n"
                f"TYPE            : {archive_type}\\n"
                f"ARCHIVE         : {source}\\n"
                f"COMPRESSED      : {format_size(compressed_size)}\\n"
                f"DECODED DATA    : {format_size(decompressed_bytes)}\\n"
                f"TIME            : {elapsed:.2f} sec\\n"
                f"{hash_mode:<17}: {hash_status}\\n"
                f"HASH            : {actual_hash}{extra}\\n"
                f"SIDECAR         : {expected_hash or 'Not found'}\\n\\n"
                f"ZSTD frame and archive stream are readable."
            ),
            fg=result_color
        )

        if validation_passed:

            if is_tar_archive:
                message = (
                    "ZSTD archive validation passed.\\n\\n"
                    "The archive is readable and its archive SHA-256 "
                    "matches the sidecar."
                )
            else:
                message = (
                    "ZSTD archive validation passed.\\n\\n"
                    "The archive decoded successfully and the SHA-256 "
                    "of the decoded source data matches the sidecar."
                )

            messagebox.showinfo(
                "NOVA — VALIDATION PASSED",
                message
            )

        else:

            if hash_status == "NOT AVAILABLE":
                message = (
                    "ZSTD archive stream is readable.\\n\\n"
                    "The SHA-256 sidecar is missing, so integrity "
                    "verification cannot pass."
                )
            else:
                message = (
                    "ZSTD archive decoded, but the SHA-256 sidecar does "
                    "not match the expected data."
                )

            messagebox.showerror(
                "NOVA — VALIDATION FAILED",
                message
            )


    # ========================================================
    # START DECOMPRESSION
    # ========================================================

    def start_decompression(self):

        if self.is_running:
            return

        # PHASE 3 / STEP 5:
        # Use a .zst file already selected by Drag & Drop
        # or Select File. Only open the dialog when no valid
        # compressed archive is selected.
        selected = self.selected_path

        if (
            selected
            and selected.is_file()
            and selected.name.lower().endswith(".zst")
        ):
            source_path = selected
        else:
            path = filedialog.askopenfilename(
                title="Select Compressed File",
                filetypes=[
                    ("Zstd files", "*.zst"),
                    ("All files", "*.*")
                ]
            )

            if not path:
                return

            source_path = Path(path)

        if not self.output_path:

            messagebox.showwarning(
                "NOVA",
                "Please select output folder first."
            )

            return

        self.selected_path = source_path
        self.update_info_panel(source_path)

        self.path_label.config(
            text=f"FILE: {self.selected_path}",
            fg=CYAN
        )

        self.is_running = True
        self.cancel_event.clear()

        self.status_label.config(
            text="● DECOMPRESSION STARTING",
            fg=RED
        )

        self.set_buttons(
            False
        )

        self.progress.set(0)

        self.result_label.config(
            text=""
        )

        thread = threading.Thread(
            target=self.decompress_selected,
            daemon=True
        )

        thread.start()


    # ========================================================
    # DECOMPRESSION
    # ========================================================

    def decompress_selected(self):

        try:

            source = self.selected_path

            if source.name.endswith(
                ".tar.zst"
            ):

                self.decompress_folder()

            else:

                self.decompress_file()

        except Exception as e:

            self.root.after(
                0,
                self.operation_error,
                str(e)
            )


    # ========================================================
    # FILE DECOMPRESSION
    # ========================================================

    def decompress_file(self):

        source = self.selected_path

        output_name = source.name[:-4]

        output = (
            self.output_path /
            output_name
        )

        self.root.after(
            0,
            lambda: self.status_label.config(
                text="● DECOMPRESSING FILE",
                fg=RED
            )
        )

        decompressor = zstd.ZstdDecompressor()

        start = time.time()

        restored_size = 0

        with open(
            source,
            "rb"
        ) as fin:

            with open(
                output,
                "wb"
            ) as fout:

                with decompressor.stream_reader(
                    fin
                ) as reader:

                    while True:

                        chunk = reader.read(
                            CHUNK_SIZE
                        )

                        if not chunk:
                            break

                        fout.write(
                            chunk
                        )

                        restored_size += len(
                            chunk
                        )

        elapsed = time.time() - start

        self.verify_after_decompression(
            source,
            output,
            restored_size,
            elapsed
        )


   # ========================================================
   # FOLDER DECOMPRESSION
       # ========================================================

    def decompress_folder(self):
        source = self.selected_path

        # ----------------------------------------------------
        # IMPORTANT:
        # The TAR archive already contains the original
        # folder name (for example: TestFolder/).
        #
        # Therefore extraction must happen directly into
        # the selected output folder.
        # ----------------------------------------------------

        destination = self.output_path

        destination.mkdir(
            parents=True,
            exist_ok=True
        )

        self.root.after(
            0,
            lambda: self.status_label.config(
                text="● DECOMPRESSING FOLDER",
                fg=RED
            )
        )

        decompressor = zstd.ZstdDecompressor()

        start = time.time()

        with open(
            source,
            "rb"
        ) as fin:

            with decompressor.stream_reader(
                fin
            ) as reader:

                with tarfile.open(
                    fileobj=reader,
                    mode="r|"
                ) as tar:

                    for member in tar:

                        target = (
                            destination /
                            member.name
                        ).resolve()

                        destination_resolved = (
                            destination.resolve()
                        )

                        # ------------------------------------------------
                        # SECURITY:
                        # Prevent archive path traversal
                        # ------------------------------------------------

                        try:

                            target.relative_to(
                                destination_resolved
                            )

                        except ValueError:

                            raise ValueError(
                                "Unsafe archive path detected: "
                                + member.name
                            )

                        tar.extract(
                            member,
                            path=destination
                        )

        elapsed = time.time() - start

        self.root.after(
            0,
            self.folder_decompression_complete,
            destination,
            elapsed
        )

    # ========================================================
    # VERIFY FILE
    # ========================================================

    def verify_after_decompression(
        self,
        source,
        output,
        restored_size,
        elapsed
    ):

        hash_file = Path(
            str(source) + ".sha256"
        )

        restored_hash = sha256_file(
            output
        )

        expected_hash = None

        if hash_file.exists():

            with open(
                hash_file,
                "r",
                encoding="utf-8"
            ) as f:

                expected_hash = f.read().strip()

        verified = (
            expected_hash is not None
            and
            expected_hash == restored_hash
        )

        self.root.after(
            0,
            self.file_decompression_complete,
            output,
            restored_size,
            elapsed,
            expected_hash,
            restored_hash,
            verified
        )


    # ========================================================
    # PROGRESS
    # ========================================================

    def update_compression_progress(
        self,
        processed,
        total,
        start
    ):

        if total <= 0:
            percent = 100
        else:
            percent = (
                processed /
                total *
                100
            )

        if percent > 100:
            percent = 100

        elapsed = time.time() - start

        speed = (
            processed / elapsed
            if elapsed > 0
            else 0
        )

        remaining = (
            total - processed
        )

        eta = (
            remaining / speed
            if speed > 0
            else 0
        )

        self.root.after(
            0,
            self.update_progress_ui,
            percent,
            speed,
            eta
        )


    def update_progress_ui(
        self,
        percent,
        speed,
        eta
    ):

        self.progress.set(
            percent
        )

        self.progress_label.config(
            text=f"PROGRESS: {percent:.2f}%",
            fg=YELLOW
        )

        speed_mb = (
            speed /
            (1024 * 1024)
        )

        self.info_label.config(
            text=(
                f"SPEED: {speed_mb:.2f} MB/s    "
                f"ETA: {eta:.1f}s"
            ),
            fg=ORANGE
        )


    # ========================================================
    # FILE COMPLETE
    # ========================================================

    def file_compression_complete(
        self,
        output,
        hash_file,
        profile,
        level,
        original_size,
        compressed_size,
        reduction,
        ratio,
        elapsed
    ):

        self.is_running = False

        self.set_buttons(
            True
        )

        self.progress.set(
            100
        )

        self.status_label.config(
            text="● FILE COMPRESSION COMPLETE",
            fg=GREEN
        )

        self.active_compression = False
        self.record_compression_success(
            original_size,
            compressed_size,
            reduction,
            ratio,
            elapsed,
            self.selected_path
        )

        self.add_history(
            "COMPRESSED FILE",
            self.selected_path,
            output,
            f"{profile} / L{level}"
        )

        self.result_label.config(
            text=(
                f"TYPE           : FILE\n"
                f"PROFILE        : {profile}\n"
                f"ZSTD LEVEL     : {level}\n"
                f"ORIGINAL       : {format_size(original_size)}\n"
                f"COMPRESSED     : {format_size(compressed_size)}\n"
                f"REDUCTION      : {reduction:.4f}%\n"
                f"RATIO          : {ratio:.2f}:1\n"
                f"TIME           : {elapsed:.2f} sec\n\n"
                f"OUTPUT:\n{output}\n\n"
                f"SHA-256:\n{hash_file}"
            ),
            fg=CYAN
        )

        messagebox.showinfo(
            "NOVA",
            "File compression complete."
        )


    # ========================================================
    # FOLDER COMPLETE
    # ========================================================

    def folder_compression_complete(
        self,
        output,
        hash_file,
        profile,
        level,
        original_size,
        compressed_size,
        reduction,
        ratio,
        elapsed
    ):

        self.is_running = False

        self.set_buttons(
            True
        )

        self.progress.set(
            100
        )

        self.status_label.config(
            text="● FOLDER COMPRESSION COMPLETE",
            fg=GREEN
        )

        self.active_compression = False
        self.record_compression_success(
            original_size,
            compressed_size,
            reduction,
            ratio,
            elapsed,
            self.selected_path
        )

        self.add_history(
            "COMPRESSED FOLDER",
            self.selected_path,
            output,
            f"{profile} / L{level}"
        )

        self.result_label.config(
            text=(
                f"TYPE           : FOLDER\n"
                f"PROFILE        : {profile}\n"
                f"ZSTD LEVEL     : {level}\n"
                f"ORIGINAL       : {format_size(original_size)}\n"
                f"COMPRESSED     : {format_size(compressed_size)}\n"
                f"REDUCTION      : {reduction:.4f}%\n"
                f"RATIO          : {ratio:.2f}:1\n"
                f"TIME           : {elapsed:.2f} sec\n\n"
                f"OUTPUT:\n{output}\n\n"
                f"SHA-256:\n{hash_file}"
            ),
            fg=CYAN
        )

        messagebox.showinfo(
            "NOVA",
            "Folder compression complete."
        )


    # ========================================================
    # FILE DECOMPRESSION COMPLETE
    # ========================================================

    def file_decompression_complete(
        self,
        output,
        restored_size,
        elapsed,
        expected_hash,
        restored_hash,
        verified
    ):

        self.is_running = False

        self.set_buttons(
            True
        )

        if verified:

            status = (
                "● VERIFIED — 100% IDENTICAL"
            )

            color = GREEN

        else:

            status = (
                "● VERIFICATION FAILED"
            )

            color = RED

        self.status_label.config(
            text=status,
            fg=color
        )

        speed = (
            restored_size / elapsed
            if elapsed > 0
            else 0
        )

        self.add_history(
            "DECOMPRESSED FILE",
            self.selected_path,
            output,
            "SHA-256 PASS" if verified else "SHA-256 FAIL"
        )

        self.result_label.config(
            text=(
                f"TYPE           : FILE\n"
                f"RESTORED       : {format_size(restored_size)}\n"
                f"TIME           : {elapsed:.2f} sec\n"
                f"SPEED          : {format_size(speed)}/s\n\n"
                f"EXPECTED SHA:\n"
                f"{expected_hash}\n\n"
                f"RESTORED SHA:\n"
                f"{restored_hash}\n\n"
                f"VERIFICATION   : "
                f"{'PASS — 100% IDENTICAL' if verified else 'FAIL'}"
            ),
            fg=color
        )

        if verified:

            messagebox.showinfo(
                "NOVA — VERIFIED",
                "File restored successfully.\n\n"
                "SHA-256 MATCH\n"
                "100% IDENTICAL"
            )

        else:

            messagebox.showerror(
                "NOVA — FAILED",
                "SHA-256 verification failed."
            )


    # ========================================================
    # FOLDER DECOMPRESSION COMPLETE
    # ========================================================

    def folder_decompression_complete(
        self,
        destination,
        elapsed
    ):

        self.is_running = False

        self.set_buttons(
            True
        )

        self.progress.set(
            100
        )

        self.status_label.config(
            text="● FOLDER RESTORED",
            fg=GREEN
        )

        self.add_history(
            "DECOMPRESSED FOLDER",
            self.selected_path,
            destination,
            "STRUCTURE RESTORED"
        )

        self.result_label.config(
            text=(
                f"TYPE           : FOLDER\n"
                f"RESTORED TO    : {destination}\n"
                f"TIME           : {elapsed:.2f} sec\n\n"
                f"FOLDER STRUCTURE RESTORED: PASS"
            ),
            fg=GREEN
        )

        messagebox.showinfo(
            "NOVA",
            "Folder restored successfully."
        )


    # ========================================================
    # ERROR
    # ========================================================

    def operation_error(
        self,
        error
    ):

        self.is_running = False

        self.set_buttons(
            True
        )

        if self.active_compression:
            self.record_compression_failure(self.selected_path)
            self.active_compression = False

        self.status_label.config(
            text="● OPERATION FAILED",
            fg=RED
        )

        self.result_label.config(
            text=f"ERROR:\n{error}",
            fg=RED
        )

        messagebox.showerror(
            "NOVA ERROR",
            error
        )


    # ========================================================
    # CANCEL OPERATION
    # ========================================================

    def cancel_operation(self):

        if self.queue_running:
            self.stop_queue()
            return

        if not self.is_running:
            return

        self.cancel_event.set()

        self.status_label.config(
            text="● CANCELLING...",
            fg=YELLOW
        )

        self.result_label.config(
            text="Stopping operation safely...",
            fg=YELLOW
        )

        self.stop_button.config(
            state="disabled"
        )


    def operation_cancelled(self, message):

        if self.active_compression:
            self.record_compression_cancelled(self.selected_path)
            self.active_compression = False

        self.is_running = False
        self.cancel_event.clear()

        self.set_buttons(
            True
        )

        self.progress.set(0)

        self.progress_label.config(
            text="PROGRESS: 0.00%",
            fg=YELLOW
        )

        self.info_label.config(
            text="SPEED: 0 MB/s    ETA: --",
            fg=ORANGE
        )

        self.status_label.config(
            text=f"● {message}",
            fg=YELLOW
        )

        self.result_label.config(
            text=(
                "OPERATION CANCELLED SAFELY\n\n"
                "Partial output was removed."
            ),
            fg=YELLOW
        )


    # ========================================================
    # BUTTON STATE
    # ========================================================

    def set_buttons(
        self,
        enabled
    ):

        state = (
            "normal"
            if enabled
            else "disabled"
        )

        self.compress_button.config(
            state=state
        )

        self.decompress_button.config(
            state=state
        )

        if self.validate_button is not None:
            self.validate_button.config(
                state=state
            )

        self.stop_button.config(
            state="disabled" if enabled else "normal"
        )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    root = TkinterDnD.Tk()

    app = NovaCompressor(
        root
    )

    root.mainloop()