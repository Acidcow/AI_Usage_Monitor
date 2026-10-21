"""
AI Usage Monitor - Native Windows Taskbar Floating Widget.
Built with Python 3 Standard Library (tkinter + ctypes).
Zero external dependencies. No web browser required.
"""

import sys
import os
import json
import urllib.request
import threading
from pathlib import Path
from typing import Optional, Dict, Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

THEMES = {
    "obsidian_neon": {
        "bg": "#080b11",
        "container_bg": "#0d131f",
        "card_bg": "#151e2e",
        "header_bg": "#111827",
        "border": "#06b6d4",
        "text": "#f1f5f9",
        "subtext": "#94a3b8",
        "accent": "#06b6d4",
        "cyan": "#06b6d4",
        "accent2": "#8b5cf6",
        "success": "#10b981",
        "danger": "#f43f5e",
        "strip_bg": "#080b11"
    },
    "cyberpunk": {
        "bg": "#0d0221",
        "container_bg": "#150836",
        "card_bg": "#220e4b",
        "header_bg": "#1b0a3d",
        "border": "#f43f5e",
        "text": "#fff1f2",
        "subtext": "#fda4af",
        "accent": "#f43f5e",
        "cyan": "#ec4899",
        "accent2": "#fbbf24",
        "success": "#06b6d4",
        "danger": "#e11d48",
        "strip_bg": "#0d0221"
    },
    "matrix_emerald": {
        "bg": "#021208",
        "container_bg": "#062312",
        "card_bg": "#0a361c",
        "header_bg": "#051c0e",
        "border": "#10b981",
        "text": "#dcfce7",
        "subtext": "#86efac",
        "accent": "#10b981",
        "cyan": "#10b981",
        "accent2": "#34d399",
        "success": "#22c55e",
        "danger": "#f87171",
        "strip_bg": "#021208"
    },
    "midnight_slate": {
        "bg": "#0f172a",
        "container_bg": "#1e293b",
        "card_bg": "#334155",
        "header_bg": "#1e293b",
        "border": "#64748b",
        "text": "#f8fafc",
        "subtext": "#94a3b8",
        "accent": "#38bdf8",
        "cyan": "#38bdf8",
        "accent2": "#818cf8",
        "success": "#34d399",
        "danger": "#fb7185",
        "strip_bg": "#0f172a"
    }
}

PROVIDER_COLORS = {
    "claude": "#f59e0b",
    "gemini": "#38bdf8",
    "chatgpt": "#10b981",
    "ollama": "#a855f7",
    "copilot": "#06b6d4"
}

class NativeTaskbarWidget:
    """
    Chromeless, always-on-top, dark-mode desktop widget docked right above the Windows taskbar.
    Displays live multi-account dual-bar telemetry, local AI cost savings, hover tooltips,
    right-click pinning, dynamic height auto-resizing, and sparkline trend charts.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765, width: int = 370, height: int = 390):
        self.host = host
        self.port = port
        self.active_port = port
        self.width = width
        self.height = height
        self.root = None
        self.is_running = False
        self._drag_data = {"x": 0, "y": 0}
        self.cached_comparison = None
        self.cached_providers = None
        self.flyout_window = None

        # Configuration and Customization State
        self.theme_name = "obsidian_neon"
        self.font_scale = "standard"
        self.auto_resize = True
        self.fade_unpinned = False
        self.view_mode = "balances" # "balances" or "trends"
        self.pinned_items = set(["claude", "gemini", "ollama"])
        self.hide_parent_chart_on_expand = False
        self.hidden_platforms = set()
        self.quota_tracking_mode = "individual"
        self.has_focus = True
        self._hit_boxes = []
        self._pin_hit_boxes = []

    @property
    def theme(self) -> Dict[str, str]:
        return THEMES.get(self.theme_name, THEMES["obsidian_neon"])

    def _get_font(self, base_size: int, weight: str = "normal") -> tuple:
        if isinstance(self.font_scale, (int, float)):
            size = max(6, int(base_size * float(self.font_scale)))
        else:
            scale = {"small": -1, "standard": 0, "large": 2}.get(self.font_scale, 0)
            size = max(6, base_size + scale)
        return ("Segoe UI", size, weight)

    def calculate_position(self) -> tuple:
        """Calculates bottom-right docking coordinates right above the Windows taskbar."""
        x, y = 100, 100
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                class RECT(ctypes.Structure):
                    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]
                rect = RECT()
                ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0) # SPI_GETWORKAREA
                x = max(10, rect.right - self.width - 16)
                y = max(10, rect.bottom - self.height - 16)
            except Exception:
                x = max(10, 1920 - self.width - 16)
                y = max(10, 1040 - self.height - 16)
        return x, y

    def fetch_data(self) -> tuple:
        """Fetches live comparison, providers, and app settings with automatic active port probing."""
        comp, provs = None, None
        ports_to_try = []
        for p in [getattr(self, "active_port", None), 8765, self.port]:
            if p and p not in ports_to_try:
                ports_to_try.append(p)

        working_port = None
        for p in ports_to_try:
            try:
                req_c = urllib.request.Request(f"http://{self.host}:{p}/api/usage/comparison?filter_visibility=true")
                with urllib.request.urlopen(req_c, timeout=1.5) as resp:
                    if resp.status == 200:
                        comp = json.loads(resp.read().decode("utf-8"))
                        working_port = p
                        break
            except Exception:
                continue

        if working_port:
            self.active_port = working_port
            try:
                req_p = urllib.request.Request(f"http://{self.host}:{self.active_port}/api/providers")
                with urllib.request.urlopen(req_p, timeout=1.5) as resp:
                    if resp.status == 200:
                        provs = json.loads(resp.read().decode("utf-8"))
            except Exception:
                pass

            try:
                req_s = urllib.request.Request(f"http://{self.host}:{self.active_port}/api/settings")
                with urllib.request.urlopen(req_s, timeout=1.0) as resp:
                    if resp.status == 200:
                        st = json.loads(resp.read().decode("utf-8"))
                        self._apply_settings_from_server(st)
            except Exception:
                pass

            if self.view_mode in ("trends", "interval"):
                try:
                    ts_mode = "interval_delta" if self.view_mode == "interval" else "cumulative"
                    req_ts = urllib.request.Request(f"http://{self.host}:{self.active_port}/api/usage/timeseries?window=1h&bucket_minutes=5&mode={ts_mode}")
                    with urllib.request.urlopen(req_ts, timeout=1.5) as resp:
                        if resp.status == 200:
                            self.cached_timeseries = json.loads(resp.read().decode("utf-8"))
                except Exception:
                    pass

        return comp, provs

    def _apply_settings_from_server(self, st: dict):
        if not isinstance(st, dict):
            return
        theme_changed = False
        new_theme = self.theme_name
        new_font = self.font_scale
        if "widget_theme" in st and st["widget_theme"] in THEMES:
            if st["widget_theme"] != self.theme_name:
                new_theme = st["widget_theme"]
                theme_changed = True
            else:
                self.theme_name = st["widget_theme"]
        if "widget_font_size" in st:
            if st["widget_font_size"] != self.font_scale:
                new_font = st["widget_font_size"]
                theme_changed = True
            else:
                self.font_scale = st["widget_font_size"]
        if theme_changed:
            self.apply_theme(new_theme, new_font)
        if "widget_auto_resize" in st:
            self.auto_resize = bool(st["widget_auto_resize"])
        if "widget_fade_unpinned" in st:
            self.fade_unpinned = (st["widget_fade_unpinned"] is True or st["widget_fade_unpinned"] == "true")
        if "widget_view_mode" in st:
            self.view_mode = st["widget_view_mode"]
        if "widget_hide_parent_chart_on_expand" in st:
            self.hide_parent_chart_on_expand = bool(st["widget_hide_parent_chart_on_expand"])
        if "pinned_items" in st and isinstance(st["pinned_items"], list):
            self.pinned_items = set(p.lower().strip() for p in st["pinned_items"] if isinstance(p, str))
        if "estate_visibility" in st:
            ev = st["estate_visibility"]
            if isinstance(ev, dict) and "hidden_platforms" in ev:
                self.hidden_platforms = set(p.lower().strip() for p in ev["hidden_platforms"] if isinstance(p, str))
        if "quota_tracking_mode" in st:
            self.quota_tracking_mode = st["quota_tracking_mode"]

    def _save_settings_async(self, payload: dict):
        def _post():
            try:
                port = getattr(self, "active_port", 8765) or 8765
                req = urllib.request.Request(
                    f"http://{self.host}:{port}/api/settings",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                urllib.request.urlopen(req, timeout=1.5)
            except Exception:
                pass
        threading.Thread(target=_post, daemon=True).start()

    def build_ui(self):
        import tkinter as tk

        self.root = tk.Tk()
        self.root.title("AI Usage Monitor Taskbar Widget")
        self.root.overrideredirect(True) # Chromeless
        self.root.attributes("-topmost", True) # Pinned on top
        try:
            self.root.attributes("-alpha", 0.97) # Subtle dark transparency
        except Exception:
            pass

        x, y = self.calculate_position()
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")
        th = self.theme
        self.root.configure(bg=th["bg"])

        # Main Bordered Container
        main_frame = tk.Frame(self.root, bg=th["container_bg"], highlightbackground=th["border"], highlightthickness=1)
        main_frame.pack(fill="both", expand=True, padx=2, pady=2)
        self.main_frame = main_frame

        # Header (Draggable)
        header = tk.Frame(main_frame, bg=th["header_bg"], height=32)
        header.pack(fill="x", side="top", padx=0, pady=0)
        self.header_frame = header

        # Bind dragging
        header.bind("<Button-1>", self._start_drag)
        header.bind("<B1-Motion>", self._on_drag)

        title_lbl = tk.Label(
            header,
            text="⚡ AI USAGE MONITOR",
            bg=th["header_bg"],
            fg=th["accent"],
            font=self._get_font(9, "bold")
        )
        title_lbl.pack(side="left", padx=8, pady=4)
        title_lbl.bind("<Button-1>", self._start_drag)
        title_lbl.bind("<B1-Motion>", self._on_drag)

        live_badge = tk.Label(
            header,
            text="● Live",
            bg=th["header_bg"],
            fg=th["success"],
            font=self._get_font(8, "bold")
        )
        live_badge.pack(side="left", padx=2)

        # Close and Action Buttons
        btn_close = tk.Label(
            header,
            text="✕",
            bg=th["header_bg"],
            fg=th["subtext"],
            font=self._get_font(10, "bold"),
            cursor="hand2"
        )
        btn_close.pack(side="right", padx=6)
        btn_close.bind("<Button-1>", lambda e: self.close())
        btn_close.bind("<Enter>", lambda e: btn_close.configure(fg=th["danger"]))
        btn_close.bind("<Leave>", lambda e: btn_close.configure(fg=th["subtext"]))

        btn_open = tk.Label(
            header,
            text="↗",
            bg=th["header_bg"],
            fg=th["subtext"],
            font=self._get_font(10, "bold"),
            cursor="hand2"
        )
        btn_open.pack(side="right", padx=3)
        btn_open.bind("<Button-1>", lambda e: self._open_browser())
        btn_open.bind("<Enter>", lambda e: btn_open.configure(fg=th["accent"]))
        btn_open.bind("<Leave>", lambda e: btn_open.configure(fg=th["subtext"]))

        btn_settings = tk.Label(
            header,
            text="⚙",
            bg=th["header_bg"],
            fg=th["subtext"],
            font=self._get_font(9),
            cursor="hand2"
        )
        btn_settings.pack(side="right", padx=3)
        btn_settings.bind("<Button-1>", lambda e: self._open_settings())
        btn_settings.bind("<Enter>", lambda e: btn_settings.configure(fg=th["accent"]))
        btn_settings.bind("<Leave>", lambda e: btn_settings.configure(fg=th["subtext"]))

        self.btn_view_mode = tk.Label(
            header,
            text="📈" if self.view_mode == "trends" else "📊",
            bg=th["header_bg"],
            fg=th["accent"],
            font=self._get_font(9, "bold"),
            cursor="hand2"
        )
        self.btn_view_mode.pack(side="right", padx=4)
        self.btn_view_mode.bind("<Button-1>", lambda e: self._toggle_view_mode())

        # Accounts List Canvas
        self.canvas = tk.Canvas(main_frame, bg=th["container_bg"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=6)

        # Bottom Savings Strip
        bottom_strip = tk.Frame(main_frame, bg=th["strip_bg"], height=24)
        bottom_strip.pack(fill="x", side="bottom", padx=6, pady=4)
        self.bottom_strip = bottom_strip

        self.savings_lbl = tk.Label(
            bottom_strip,
            text="💰 Local AI Saved: $0.00",
            bg=th["strip_bg"],
            fg=th["success"],
            font=self._get_font(8, "bold")
        )
        self.savings_lbl.pack(side="left", padx=4)

        self.port_lbl = tk.Label(
            bottom_strip,
            text=f"Port {getattr(self, 'active_port', self.port)}",
            bg=th["strip_bg"],
            fg=th["subtext"],
            font=self._get_font(8)
        )
        self.port_lbl.pack(side="right", padx=4)

        self.root.bind("<FocusIn>", self._on_focus_in)
        self.root.bind("<FocusOut>", self._on_focus_out)
        self.root.bind("<Button-1>", lambda e: self._on_focus_in())
        main_frame.bind("<Button-1>", lambda e: self._on_focus_in())

        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Leave>", self._on_canvas_leave)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Button-3>", self._on_canvas_right_click)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

    def _start_drag(self, event):
        self._on_focus_in()
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _on_drag(self, event):
        deltax = event.x - self._drag_data["x"]
        deltay = event.y - self._drag_data["y"]
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def _open_browser(self):
        import webbrowser
        target_port = getattr(self, "active_port", 8765) or 8765
        webbrowser.open(f"http://{self.host}:{target_port}/")

    def _open_settings(self):
        import webbrowser
        target_port = getattr(self, "active_port", 8765) or 8765
        webbrowser.open(f"http://{self.host}:{target_port}/?tab=settings")

    def _toggle_view_mode(self):
        cycle = {"balances": "trends", "trends": "interval", "interval": "balances"}
        self.view_mode = cycle.get(self.view_mode, "balances")
        icons = {"balances": "📊", "trends": "📈", "interval": "⚡"}
        if hasattr(self, "btn_view_mode"):
            self.btn_view_mode.configure(text=icons.get(self.view_mode, "📊"))
        self._save_settings_async({"widget_view_mode": self.view_mode})
        self.render_canvas()

    def set_view_mode(self, mode: str):
        if mode in ("balances", "trends", "interval"):
            self.view_mode = mode
            if hasattr(self, "btn_view_mode"):
                icons = {"balances": "📊", "trends": "📈", "interval": "⚡"}
                self.btn_view_mode.configure(text=icons.get(self.view_mode, "📊"))
            self._save_settings_async({"widget_view_mode": self.view_mode})
            self.render_canvas()

    def _on_focus_in(self, event=None):
        if not self.has_focus:
            self.has_focus = True
            if self.fade_unpinned:
                self.render_canvas()

    def _on_focus_out(self, event=None):
        if self.has_focus:
            self.has_focus = False
            if self.fade_unpinned:
                self.render_canvas()

    def _poll_focus(self):
        """Continuously checks foreground window state on Windows to detect focus loss."""
        if not self.root or not self.is_running:
            return
        if sys.platform == "win32":
            try:
                import ctypes
                fg = ctypes.windll.user32.GetForegroundWindow()
                hwnd = self.root.winfo_id()
                fly_hwnd = self.flyout_window.winfo_id() if getattr(self, "flyout_window", None) else None
                is_fg = (fg == hwnd or (fly_hwnd and fg == fly_hwnd))
                if not is_fg:
                    parent = ctypes.windll.user32.GetParent(hwnd)
                    if fg == parent and parent != 0:
                        is_fg = True
                if is_fg != self.has_focus:
                    if is_fg:
                        self._on_focus_in()
                    else:
                        self._on_focus_out()
            except Exception:
                pass
        if self.root and self.is_running:
            self.root.after(600, self._poll_focus)

    def _on_canvas_click(self, event):
        """Toggles expanding or collapsing children for the clicked account or pinning if clicked on pin icon."""
        canvas_y = self.canvas.canvasy(event.y)
        # Check pin hit boxes first
        for pbox in getattr(self, "_pin_hit_boxes", []):
            px1, py1, px2, py2, p_key = pbox
            if px1 <= event.x <= px2 and py1 <= canvas_y <= py2:
                if p_key in self.pinned_items:
                    self.pinned_items.remove(p_key)
                else:
                    self.pinned_items.add(p_key)
                self._save_settings_async({"pinned_items": list(self.pinned_items)})
                self.render_canvas()
                return

        for box in getattr(self, "_hit_boxes", []):
            x1, y1, x2, y2, p_key, is_header = box[0], box[1], box[2], box[3], box[4], box[5]
            if x1 <= event.x <= x2 and y1 <= canvas_y <= y2:
                if not hasattr(self, "expanded_accounts"):
                    self.expanded_accounts = {}
                self.expanded_accounts[p_key] = not self.expanded_accounts.get(p_key, False)
                self.render_canvas()
                break

    def _on_canvas_right_click(self, event):
        """Right-click pins or unpins an account or item."""
        canvas_y = self.canvas.canvasy(event.y)
        for box in getattr(self, "_hit_boxes", []):
            x1, y1, x2, y2, p_key = box[0], box[1], box[2], box[3], box[4]
            if x1 <= event.x <= x2 and y1 <= canvas_y <= y2:
                if p_key in self.pinned_items:
                    self.pinned_items.remove(p_key)
                else:
                    self.pinned_items.add(p_key)
                self._save_settings_async({"pinned_items": list(self.pinned_items)})
                self.render_canvas()
                break

    def _on_mousewheel(self, event):
        """Scrolls canvas up and down smoothly."""
        if hasattr(self, "canvas") and self.canvas:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def get_providers_order(self) -> list:
        """Returns the ordered list of providers respecting visibility toggles and focus-loss pinning fade."""
        all_providers = ["claude", "gemini", "chatgpt", "ollama", "copilot"]
        visible = [p for p in all_providers if p.lower() not in self.hidden_platforms]
        if self.fade_unpinned and not self.has_focus:
            return [p for p in visible if p.lower() in self.pinned_items]
        return visible

    def toggle_pin(self, key: str):
        """Programmatic toggle for pinning/unpinning a provider or model."""
        if key in self.pinned_items:
            self.pinned_items.remove(key)
        else:
            self.pinned_items.add(key)
        self._save_settings_async({"pinned_items": list(self.pinned_items)})
        if hasattr(self, "canvas") and self.canvas:
            self.render_canvas()

    def toggle_view_mode(self):
        """Public alias to toggle between balances and trends."""
        self._toggle_view_mode()

    def apply_theme(self, theme_name: str, font_scale: Any = "standard"):
        """Applies a theme palette and font scaling."""
        if theme_name in THEMES:
            self.theme_name = theme_name
        self.font_scale = font_scale
        if hasattr(self, "root") and self.root:
            th = self.theme
            self.root.configure(bg=th["bg"])
            if hasattr(self, "main_frame"):
                self.main_frame.configure(bg=th["container_bg"], highlightbackground=th["border"])
            if hasattr(self, "header_frame"):
                self.header_frame.configure(bg=th["header_bg"])
            if hasattr(self, "canvas"):
                self.canvas.configure(bg=th["container_bg"])
            if hasattr(self, "bottom_strip"):
                self.bottom_strip.configure(bg=th["strip_bg"])
            if hasattr(self, "savings_lbl"):
                self.savings_lbl.configure(bg=th["strip_bg"], fg=th["success"])
            if hasattr(self, "port_lbl"):
                self.port_lbl.configure(bg=th["strip_bg"], fg=th["subtext"])
            self.render_canvas()

    def _get_sparkline_points(self, tok_today: int, tok_week: int, width: int = 90, height: int = 22) -> list:
        today = int(tok_today)
        week = int(tok_week)
        base = (week / 7.0) if week > 0 else max(100.0, float(today))
        raw = [
            base * 0.7,
            base * 0.9,
            base * 1.1,
            base * 0.85,
            base * 1.15,
            base * 0.95,
            float(today)
        ]
        min_v = min(raw)
        max_v = max(raw)
        rng = max(1.0, max_v - min_v)
        step = width / (len(raw) - 1)
        pts = []
        for i, val in enumerate(raw):
            x = int(i * step)
            y = int(height - ((val - min_v) / rng) * (height - 6) - 3)
            pts.append((x, y))
        return pts

    def _draw_sub_bar(self, x, y, w, pct, label, color):
        """Helper to draw a labeled percentage progress bar on canvas."""
        pct_val = max(0, min(100, float(pct)))
        bar_x = x + 62
        bar_w = w - bar_x - 38
        bar_h = 6

        self.canvas.create_text(x + 4, y + 3, text=label, anchor="w", fill=self.theme["subtext"], font=self._get_font(7))
        self.canvas.create_rectangle(bar_x, y, bar_x + bar_w, y + bar_h, fill="#1e293b", outline="")
        fill_w = int(bar_w * (pct_val / 100.0))
        if fill_w > 0:
            self.canvas.create_rectangle(bar_x, y, bar_x + fill_w, y + bar_h, fill=color, outline="")
        self.canvas.create_text(x + w - 4, y + 3, text=f"{pct_val:.0f}%", anchor="e", fill=self.theme["text"], font=self._get_font(7))

    def _draw_sparkline(self, x, y, w, h, points, stroke_color, label=""):
        """Draws a sleek sparkline line-chart depicting recent usage trends."""
        self.canvas.create_rectangle(x, y, x + w, y + h, fill="#0b121e", outline="#1e293b", width=1)
        if not points or len(points) < 2:
            points = [12, 18, 15, 32, 28, 48, 35, 62]
        min_v = min(points)
        max_v = max(points)
        rng = max(1.0, float(max_v - min_v))

        pad_x = 8
        pad_y = 6
        plot_w = w - (pad_x * 2)
        plot_h = h - (pad_y * 2)
        n = len(points)

        coords = []
        for i, pt in enumerate(points):
            px = x + pad_x + int((i / (n - 1)) * plot_w)
            py = y + h - pad_y - int(((pt - min_v) / rng) * plot_h)
            coords.extend([px, py])

        # Polyline with smooth curves
        self.canvas.create_line(*coords, fill=stroke_color, width=2, smooth=True)
        # Endpoint indicator
        last_x, last_y = coords[-2], coords[-1]
        self.canvas.create_oval(last_x - 3, last_y - 3, last_x + 3, last_y + 3, fill=stroke_color, outline="#ffffff")
        if label:
            self.canvas.create_text(x + 8, y + 8, text=label, anchor="w", fill=self.theme["subtext"], font=self._get_font(7))
        self.canvas.create_text(x + w - 8, y + 8, text=f"{points[-1]} t/s", anchor="e", fill=self.theme["accent"], font=self._get_font(7, "bold"))

    def _draw_multi_sparkline(self, x, y, w, h, series_list, label=""):
        """Draws an overlaid multi-series line chart on the Tkinter canvas."""
        self.canvas.create_rectangle(x, y, x + w, y + h, fill="#0b121e", outline="#1e293b", width=1)
        if not series_list:
            return

        all_points = []
        for pts, _, _ in series_list:
            all_points.extend(pts)
        if not all_points:
            all_points = [10, 20, 15, 30]

        min_v = min(all_points)
        max_v = max(all_points)
        rng = max(1.0, float(max_v - min_v))

        pad_x = 8
        pad_y = 6
        plot_w = w - (pad_x * 2)
        plot_h = h - (pad_y * 2)

        for points, color, name in series_list:
            if not points or len(points) < 2:
                continue
            n = len(points)
            coords = []
            for i, pt in enumerate(points):
                px = x + pad_x + int((i / (n - 1)) * plot_w)
                py = y + h - pad_y - int(((pt - min_v) / rng) * plot_h)
                coords.extend([px, py])
            if len(coords) >= 4:
                self.canvas.create_line(*coords, fill=color, width=2, smooth=True)
                last_x, last_y = coords[-2], coords[-1]
                self.canvas.create_oval(last_x - 2, last_y - 2, last_x + 2, last_y + 2, fill=color, outline="#ffffff")

        if label:
            self.canvas.create_text(x + 8, y + 8, text=label, anchor="w", fill=self.theme["subtext"], font=self._get_font(7))

    def _get_provider_child_series(self, p_key: str, item: dict) -> list:
        """Returns a list of tuples (points, color, label) for each child in the provider hierarchy."""
        ts = getattr(self, "cached_timeseries", None)
        num_bins = ts.get("num_bins", 8) if ts else 8
        zero_bins = [0] * num_bins

        def find_points(id_pattern):
            if not ts or "series" not in ts:
                return None
            for s in ts.get("series", []):
                s_id = s.get("id", "")
                s_key = s.get("key", "")
                if s_id == id_pattern or (s_key and id_pattern.lower() in s_key.lower()):
                    return s.get("points")
            return None

        t_seed = int(item.get("tokens_today", 0))
        h = item.get("hierarchy", {})
        if p_key == "claude":
            team_pts = find_points("team")
            ind_pts = find_points("individual")
            if team_pts is None:
                team_pts = [int(t_seed * f) for f in [0.2, 0.45, 0.35, 0.6, 0.55, 0.85, 0.7, 0.95]]
            if ind_pts is None:
                ind_pts = [int(t_seed * f) for f in [0.1, 0.25, 0.18, 0.35, 0.32, 0.55, 0.45, 0.65]]
            team_name = h.get("team_name") or "Synthesis2"
            user_name = h.get("user_name") or "James Eckhardt"
            return [
                (team_pts, "#c084fc", f"{team_name} (Team)"),
                (ind_pts, "#38bdf8", f"{user_name} (Individual)")
            ]
        elif p_key == "gemini":
            acct_pts = find_points("gemini")
            k1_pts = find_points("tok_gem_flash")
            k2_pts = find_points("tok_gem_pro")
            if acct_pts is None:
                acct_pts = [int(t_seed * f) for f in [0.25, 0.35, 0.5, 0.4, 0.65, 0.55, 0.8, 0.9]]
            if k1_pts is None:
                k1_pts = [int(t_seed * f) for f in [0.1, 0.15, 0.28, 0.22, 0.38, 0.3, 0.45, 0.55]]
            if k2_pts is None:
                k2_pts = [int(t_seed * f) for f in [0.08, 0.12, 0.16, 0.14, 0.22, 0.2, 0.28, 0.32]]
            acct_name = h.get("account_name") or h.get("account_id") or "acidcow@gmail.com"
            return [
                (acct_pts, "#60a5fa", f"{acct_name} (Account)"),
                (k1_pts, "#34d399", "Gemini 2.0 Flash"),
                (k2_pts, "#f472b6", "Gemini 1.5 Pro")
            ]
        elif p_key == "ollama":
            if ts and "series" in ts:
                ollama_series = [s for s in ts.get("series", []) if s.get("id", "").startswith("ollama_model_")]
                if ollama_series:
                    colors = ["#06b6d4", "#a855f7", "#38bdf8", "#34d399", "#fbbf24", "#ec4899"]
                    return [
                        (s.get("points") or zero_bins, s.get("color") or colors[i % len(colors)], s.get("name") or s.get("label") or s.get("id", "").replace("ollama_model_", ""))
                        for i, s in enumerate(ollama_series)
                    ]
            models_list = item.get("models", [])
            if not models_list:
                models_list = item.get("hierarchy", {}).get("models", [])
            active_models = [m for m in models_list if (m.get("tokens_today", 0) > 0 or m.get("total_tokens", 0) > 0)]
            if not active_models and models_list:
                active_models = models_list[:2]
            colors = ["#06b6d4", "#a855f7", "#38bdf8", "#34d399", "#fbbf24", "#ec4899"]
            result = []
            for idx, m in enumerate(active_models[:3]):
                m_name = m.get("model") or m.get("name") or "Local Model"
                m_toks = int(m.get("tokens_today", 0))
                color = colors[idx % len(colors)]
                pts = [int(m_toks * f) for f in [0.1, 0.2, 0.15, 0.3, 0.25, 0.45, 0.35, 0.5]] if m_toks > 0 else zero_bins
                result.append((pts, color, m_name))
            return result if result else [(zero_bins, "#06b6d4", "Ollama")]
        elif p_key == "chatgpt":
            pts = find_points("chatgpt") or [int(t_seed * f) for f in [0.2, 0.3, 0.25, 0.4, 0.35, 0.5, 0.45, 0.6]]
            return [(pts, "#10b981", "Default Project")]
        else:
            co_pts = find_points("copilot") or [int(t_seed * f) for f in [0.15, 0.2, 0.18, 0.28, 0.24, 0.35, 0.3, 0.4]]
            return [(co_pts, "#06b6d4", "Enterprise E5")]

    def calculate_card_height(self, p_key: str, is_expanded: bool, item: Optional[dict] = None) -> int:
        """Calculates optimal card height based on expanded state, tracking mode, and child hierarchy."""
        item = item or {}
        h = item.get("hierarchy", {})
        child_series = self._get_provider_child_series(p_key, item)
        if self.view_mode in ("trends", "interval"):
            if not is_expanded:
                return 74
            child_count = len(child_series)
            child_height = child_count * 44
            if self.hide_parent_chart_on_expand:
                return 32 + child_height
            return 76 + child_height
        else:
            if not is_expanded:
                return 58
            if p_key == "claude":
                tracking_mode = getattr(self, "quota_tracking_mode", "individual")
                if tracking_mode == "individual":
                    return 66
                return 106
            elif p_key == "gemini":
                num_toks = len(h.get("tokens", [])) or 2
                return 62 + (num_toks * 36)
            return 62

    def render_canvas(self):
        """Draws the accounts cards with click-to-expand multi-level bars, sparklines, and pin badges."""
        if not self.canvas:
            return
        self.canvas.delete("all")
        th = self.theme

        if not hasattr(self, "expanded_accounts"):
            self.expanded_accounts = {"claude": False, "gemini": False}

        providers_order = self.get_providers_order()

        display_names = {
            "claude": "Claude",
            "gemini": "Gemini",
            "chatgpt": "ChatGPT",
            "ollama": "Ollama (Local)",
            "copilot": "Copilot"
        }

        comp = self.cached_comparison or {}
        prov_map = comp.get("providers", {})
        prov_info = self.cached_providers or {}

        card_y = 4
        card_w = self.width - 24

        self._hit_boxes = []
        self._pin_hit_boxes = []

        if not providers_order:
            if self.fade_unpinned and not self.has_focus:
                self.canvas.create_text(
                    card_w // 2, 40,
                    text="Unpinned items hidden (unfocused)",
                    fill=th["subtext"],
                    font=self._get_font(8, "italic")
                )
            else:
                self.canvas.create_text(
                    card_w // 2, 40,
                    text="No visible providers active",
                    fill=th["subtext"],
                    font=self._get_font(8, "italic")
                )

        for p_key in providers_order:
            item = prov_map.get(p_key, {
                "tokens_today": 0,
                "session_balance_remaining_pct": 100,
                "weekly_balance_remaining_pct": 100
            })
            p_stat = prov_info.get(p_key, {})
            is_active = p_stat.get("status") == "ACTIVE"
            dot_color = th["success"] if is_active else (th["danger"] if p_stat.get("status") == "ERROR" else th["subtext"])

            h = item.get("hierarchy", {})
            is_expanded = bool(self.expanded_accounts.get(p_key, False))
            is_pinned = p_key in self.pinned_items

            account_label = ""
            if p_key == "claude":
                account_label = h.get("account_name") or "Synthesis2"
            elif p_key == "gemini":
                account_label = h.get("account_name") or "acidcow@gmail.com"

            child_series = self._get_provider_child_series(p_key, item)

            # Determine card height based on expanded state and view mode
            card_h = self.calculate_card_height(p_key, is_expanded, item)

            # Main Card Box
            self.canvas.create_rectangle(
                4, card_y, card_w, card_y + card_h,
                fill=th["card_bg"], outline="#1e293b", width=1
            )
            self._hit_boxes.append((4, card_y, card_w, card_y + card_h, p_key, True, item, p_stat))

            # Header Line: Expand Toggle Icon + Status Dot + Pin + Swatch + Name + Account Badge + Tokens
            toggle_icon = "▼" if is_expanded else "▶"
            self.canvas.create_text(
                12, card_y + 13,
                text=toggle_icon,
                anchor="w",
                fill=th["accent"],
                font=self._get_font(7, "bold")
            )

            # Pin indicator (Clickable hit box)
            pin_symbol = "📌" if is_pinned else "○"
            pin_fill = "#fbbf24" if is_pinned else "#64748b"
            self.canvas.create_text(
                22, card_y + 13,
                text=pin_symbol,
                anchor="w",
                fill=pin_fill,
                font=self._get_font(7)
            )
            self._pin_hit_boxes.append((20, card_y + 4, 32, card_y + 20, p_key))

            # Status Dot
            self.canvas.create_oval(34, card_y + 10, 40, card_y + 16, fill=dot_color, outline="")

            # Provider Color Swatch Block to left of name
            prov_color = PROVIDER_COLORS.get(p_key, th["accent"])
            self.canvas.create_rectangle(44, card_y + 9, 52, card_y + 17, fill=prov_color, outline="")

            # Provider Name
            self.canvas.create_text(
                56, card_y + 13,
                text=display_names[p_key],
                anchor="w",
                fill=th["text"],
                font=self._get_font(9, "bold")
            )

            # Account Badge
            if account_label:
                badge_bg = "#1e293b" if p_key == "claude" else "#172554"
                badge_fg = "#fbbf24" if p_key == "claude" else "#93c5fd"
                self.canvas.create_rectangle(
                    132, card_y + 5, 132 + min(110, len(account_label) * 6 + 12), card_y + 20,
                    fill=badge_bg, outline=""
                )
                self.canvas.create_text(
                    138, card_y + 12,
                    text=account_label[:18],
                    anchor="w",
                    fill=badge_fg,
                    font=self._get_font(7, "bold")
                )

            # Tokens today
            tok_str = f"{item.get('tokens_today', 0):,} tok"
            self.canvas.create_text(
                card_w - 10, card_y + 13,
                text=tok_str,
                anchor="e",
                fill=th["accent"],
                font=self._get_font(8, "bold")
            )

            # --- CARD BODY ---
            if self.view_mode in ("trends", "interval"):
                if not is_expanded:
                    # Overlaid line plots corresponding to each child
                    self._draw_multi_sparkline(10, card_y + 26, card_w - 16, 40, child_series, "All Children Overlaid:")
                else:
                    cur_y = card_y + 26
                    if not self.hide_parent_chart_on_expand:
                        self._draw_multi_sparkline(10, cur_y, card_w - 16, 40, child_series, "All Children Overlaid:")
                        cur_y += 44
                    for c_pts, c_col, c_name in child_series:
                        # Swatch block for child
                        self.canvas.create_rectangle(12, cur_y + 4, 18, cur_y + 10, fill=c_col, outline="")
                        self.canvas.create_text(22, cur_y + 7, text=c_name, fill=c_col, anchor="w", font=self._get_font(7, "bold"))
                        self._draw_sparkline(10, cur_y + 14, card_w - 16, 26, c_pts, c_col, "")
                        cur_y += 44
            else:
                if not is_expanded:
                    # Collapsed Dual Bars
                    sess_pct = max(0, min(100, item.get("session_balance_remaining_pct", 100)))
                    week_pct = max(0, min(100, item.get("weekly_balance_remaining_pct", 100)))
                    c1 = th["danger"] if sess_pct < 20 else th["accent"]
                    c2 = "#f59e0b" if week_pct < 20 else th["accent2"]
                    self._draw_sub_bar(10, card_y + 26, card_w - 16, sess_pct, "Session:", c1)
                    self._draw_sub_bar(10, card_y + 39, card_w - 16, week_pct, "Weekly:", c2)
                else:
                    # Expanded Multi-Level Hierarchical Bars
                    if p_key == "claude":
                        tracking_mode = h.get("tracking_mode", "individual")
                        if tracking_mode != "individual":
                            team_info = h.get("team", {})
                            t_sess = team_info.get("session_remaining_pct", 44.0)
                            t_week = team_info.get("weekly_remaining_pct", 74.0)
                            self.canvas.create_rectangle(8, card_y + 26, card_w - 6, card_y + 62, fill="#131b2c", outline="#1e293b")
                            self.canvas.create_text(14, card_y + 34, text="👥 Synthesis2 (Team Pool)", anchor="w", fill="#c084fc", font=self._get_font(7, "bold"))
                            self._draw_sub_bar(14, card_y + 42, card_w - 22, t_sess, "Team Sess:", th["accent"])
                            self._draw_sub_bar(14, card_y + 51, card_w - 22, t_week, "Team Wk:", th["accent2"])

                            ind_info = h.get("individual", {})
                            i_sess = ind_info.get("session_remaining_pct", 40.0)
                            i_week = ind_info.get("weekly_remaining_pct", 73.0)
                            self.canvas.create_rectangle(8, card_y + 66, card_w - 6, card_y + 102, fill="#0f172a", outline="#1e293b")
                            self.canvas.create_text(14, card_y + 74, text=f"👤 {h.get('user_name', 'My Quota')}", anchor="w", fill="#38bdf8", font=self._get_font(7, "bold"))
                            self._draw_sub_bar(14, card_y + 82, card_w - 22, i_sess, "My Sess:", "#38bdf8")
                            self._draw_sub_bar(14, card_y + 91, card_w - 22, i_week, "My Wk:", "#3b82f6")
                        else:
                            ind_info = h.get("individual", {})
                            i_sess = ind_info.get("session_remaining_pct", item.get("session_balance_remaining_pct", 100.0))
                            i_week = ind_info.get("weekly_remaining_pct", item.get("weekly_balance_remaining_pct", 100.0))
                            self.canvas.create_rectangle(8, card_y + 26, card_w - 6, card_y + 62, fill="#0f172a", outline="#1e293b")
                            self.canvas.create_text(14, card_y + 34, text=f"👤 {h.get('user_name', 'Personal Direct Quota')}", anchor="w", fill="#38bdf8", font=self._get_font(7, "bold"))
                            self._draw_sub_bar(14, card_y + 42, card_w - 22, i_sess, "Session:", "#38bdf8")
                            self._draw_sub_bar(14, card_y + 51, card_w - 22, i_week, "Weekly:", "#3b82f6")

                    elif p_key == "gemini":
                        self.canvas.create_rectangle(8, card_y + 26, card_w - 6, card_y + 58, fill="#0d1b30", outline="#1e293b")
                        self.canvas.create_text(14, card_y + 34, text="🌐 acidcow@gmail.com (Account Pool)", anchor="w", fill="#60a5fa", font=self._get_font(7, "bold"))
                        self._draw_sub_bar(14, card_y + 42, card_w - 22, item.get("session_balance_remaining_pct", 88.0), "Account:", "#3b82f6")

                        sub_y = card_y + 62
                        child_toks = h.get("tokens", [])
                        for tok in child_toks:
                            tok_name = tok.get("name", "Gemini Token")
                            tok_sess = tok.get("session_balance_remaining_pct", 90.0)
                            tok_week = tok.get("weekly_balance_remaining_pct", 85.0)

                            self.canvas.create_rectangle(8, sub_y, card_w - 6, sub_y + 34, fill="#111c2e", outline="#1e293b")
                            self.canvas.create_text(14, sub_y + 8, text=f"🔑 {tok_name[:24]}", anchor="w", fill=th["success"], font=self._get_font(7, "bold"))
                            self._draw_sub_bar(14, sub_y + 16, card_w - 22, tok_sess, "Sess:", th["success"])
                            self._draw_sub_bar(14, sub_y + 24, card_w - 22, tok_week, "Wk:", th["accent"])
                            sub_y += 36
                    else:
                        sess_pct = max(0, min(100, item.get("session_balance_remaining_pct", 100)))
                        week_pct = max(0, min(100, item.get("weekly_balance_remaining_pct", 100)))
                        self._draw_sub_bar(10, card_y + 26, card_w - 16, sess_pct, "Session:", th["accent"])
                        self._draw_sub_bar(10, card_y + 39, card_w - 16, week_pct, "Weekly:", th["accent2"])

            card_y += card_h + 6

        # Auto-resize window height dynamically if enabled
        if self.auto_resize:
            target_h = max(220, min(700, card_y + 44))
            if abs(target_h - self.height) >= 6:
                self.height = target_h
                x, y = self.calculate_position()
                self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")

        # Configure scrollregion
        self.canvas.configure(scrollregion=(0, 0, card_w, max(self.height - 70, card_y + 10)))

        # Update Savings Label
        if comp.get("local_savings"):
            saved = comp["local_savings"].get("savings_today_usd", 0.0)
            self.savings_lbl.configure(text=f"💰 Local AI Saved: ${saved:.2f}")

    def _on_canvas_motion(self, event):
        """Displays a weather-style telemetry hover flyout when hovering over an account."""
        hovered = None
        canvas_y = self.canvas.canvasy(event.y)
        for box in getattr(self, "_hit_boxes", []):
            x1, y1, x2, y2, p_key = box[0], box[1], box[2], box[3], box[4]
            item, p_stat = box[6], box[7]
            if x1 <= event.x <= x2 and y1 <= canvas_y <= y2:
                hovered = (p_key, item, p_stat)
                break

        if hovered:
            self._show_flyout(hovered[0], hovered[1], hovered[2])
        else:
            self._hide_flyout()

    def _on_canvas_leave(self, event=None):
        """Hides the hover flyout when the mouse leaves the canvas."""
        self._hide_flyout()

    def format_flyout_quota_lines(self, p_key: str, item: dict, tracking_mode: str = "individual") -> dict:
        """
        Formats flyout quota and reset lines based on tracking mode ('individual' vs 'team').
        In individual mode, displays direct personal quotas without the confusing/calculated team pool line.
        """
        sess_rem = item.get("session_balance_remaining_pct", 100.0)
        sess_used = item.get("session_used_pct", 0.0)
        week_rem = item.get("weekly_balance_remaining_pct", 100.0)
        week_used = item.get("weekly_used_pct", 0.0)
        weekly_reset_str = item.get("weekly_reset_str", "Mon 3:00 AM")
        sess_reset_str = item.get("session_reset_str", "5h rolling window")

        hier = item.get("hierarchy", {})
        ind_data = hier.get("individual", {})
        team_data = hier.get("team", {})

        ind_sess_rem = ind_data.get("session_remaining_pct", sess_rem)
        ind_sess_used = ind_data.get("session_used_pct", sess_used)
        team_sess_rem = team_data.get("session_remaining_pct", 44.0)
        team_sess_used = team_data.get("session_used_pct", 56.0)

        ind_week_rem = ind_data.get("weekly_remaining_pct", week_rem)
        ind_week_used = ind_data.get("weekly_used_pct", week_used)
        team_week_rem = team_data.get("weekly_remaining_pct", 74.0)
        team_week_used = team_data.get("weekly_used_pct", 26.0)

        effective_mode = tracking_mode or hier.get("tracking_mode", "individual")

        if effective_mode == "team" and p_key == "claude" and (ind_sess_used != team_sess_used or ind_week_used != team_week_used):
            return {
                "sess_quota": {
                    "text": f"• 👤 My Quota:   {ind_sess_rem}% rem ({ind_sess_used}% used)",
                    "fg": "#38bdf8"
                },
                "sess_reset": {
                    "text": f"• 👥 Team Pool:  {team_sess_rem}% rem ({team_sess_used}% used)  ↳ {sess_reset_str}",
                    "fg": "#06b6d4"
                },
                "week_quota": {
                    "text": f"• 👤 My Weekly:  {ind_week_rem}% rem ({ind_week_used}% used)",
                    "fg": "#c084fc"
                },
                "week_reset": {
                    "text": f"• 👥 Team Weekly:{team_week_rem}% rem ({team_week_used}% used)  ↳ {weekly_reset_str}",
                    "fg": "#a855f7"
                }
            }
        else:
            quota_label = "👤 Session Quota" if p_key == "claude" else "Current Session"
            week_label = "👤 Weekly Quota" if p_key == "claude" else "Weekly Pool"
            
            s_tok_extra = ""
            w_tok_extra = ""
            if p_key == "claude" and item.get("session_tokens_available") is not None:
                s_avail = item.get("session_tokens_available", 0)
                s_lim = item.get("session_tokens_limit", 200000)
                s_tok_extra = f" [{s_avail:,} / {s_lim:,} tok]"
            if p_key == "claude" and item.get("weekly_tokens_available") is not None:
                w_avail = item.get("weekly_tokens_available", 0)
                w_lim = item.get("weekly_tokens_limit", 1400000)
                w_tok_extra = f" [{w_avail:,} / {w_lim:,} tok]"

            return {
                "sess_quota": {
                    "text": f"• {quota_label}:   {sess_rem}% rem  ({sess_used}% used){s_tok_extra}",
                    "fg": "#38bdf8"
                },
                "sess_reset": {
                    "text": f"  ↳ {sess_reset_str}",
                    "fg": "#94a3b8"
                },
                "week_quota": {
                    "text": f"• {week_label}:        {week_rem}% rem  ({week_used}% used){w_tok_extra}",
                    "fg": "#c084fc" if p_key == "claude" else "#a855f7"
                },
                "week_reset": {
                    "text": f"  ↳ Resets {weekly_reset_str}",
                    "fg": "#94a3b8"
                }
            }

    def _show_flyout(self, p_key: str, item: dict, p_stat: dict):
        import tkinter as tk
        import time
        display_names = {
            "claude": "Claude (Anthropic)",
            "gemini": "Google Gemini",
            "chatgpt": "ChatGPT / OpenAI",
            "ollama": "Ollama Local Engine",
            "copilot": "M365 Copilot"
        }

        fly_w = self.width
        fly_h = 215

        if not self.flyout_window:
            self.flyout_window = tk.Toplevel(self.root)
            self.flyout_window.overrideredirect(True)
            self.flyout_window.attributes("-topmost", True)
            self.flyout_window.configure(bg="#070b14")

            # Outer Border Frame
            f_frame = tk.Frame(self.flyout_window, bg="#070b14", highlightbackground="#06b6d4", highlightthickness=1)
            f_frame.pack(fill="both", expand=True)

            # Header Frame
            self.flyout_hdr = tk.Frame(f_frame, bg="#0d1424", height=30)
            self.flyout_hdr.pack(fill="x", side="top", padx=0, pady=0)

            self.flyout_dot = tk.Label(self.flyout_hdr, text="●", bg="#0d1424", fg="#10b981", font=("Segoe UI", 9))
            self.flyout_dot.pack(side="left", padx=(8, 4), pady=4)

            self.flyout_title = tk.Label(self.flyout_hdr, text="", bg="#0d1424", fg="#f8fafc", font=("Segoe UI", 9, "bold"))
            self.flyout_title.pack(side="left", padx=2, pady=4)

            self.flyout_badge = tk.Label(self.flyout_hdr, text="", bg="#1e293b", fg="#38bdf8", font=("Segoe UI", 7, "bold"), padx=6, pady=1)
            self.flyout_badge.pack(side="right", padx=8, pady=4)

            # Subtle Divider
            div = tk.Frame(f_frame, bg="#1e293b", height=1)
            div.pack(fill="x", side="top")

            # Scrollable Body Container
            body_box = tk.Frame(f_frame, bg="#070b14")
            body_box.pack(fill="both", expand=True, padx=4, pady=4)

            self.flyout_canvas = tk.Canvas(body_box, bg="#070b14", highlightthickness=0)
            self.flyout_scrollbar = tk.Scrollbar(
                body_box,
                orient="vertical",
                command=self.flyout_canvas.yview,
                width=4,
                bg="#1e293b",
                activebackground="#06b6d4",
                troughcolor="#070b14",
                bd=0,
                relief="flat"
            )

            self.flyout_content = tk.Frame(self.flyout_canvas, bg="#070b14")
            self.flyout_content.bind(
                "<Configure>",
                lambda e: self.flyout_canvas.configure(scrollregion=self.flyout_canvas.bbox("all"))
            )

            self.flyout_canvas.create_window((0, 0), window=self.flyout_content, anchor="nw", width=fly_w - 24)
            self.flyout_canvas.configure(yscrollcommand=self.flyout_scrollbar.set)

            self.flyout_scrollbar.pack(side="right", fill="y")
            self.flyout_canvas.pack(side="left", fill="both", expand=True)

            def _on_wheel(e):
                self.flyout_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

            self.flyout_canvas.bind("<MouseWheel>", _on_wheel)
            self.flyout_content.bind("<MouseWheel>", _on_wheel)

            # Reusable Labels in content frame
            self.flyout_labels = {}
            row_keys = ["sess_quota", "sess_reset", "week_quota", "week_reset", "tokens_info", "cost_info", "engine_status"]
            for rk in row_keys:
                lbl = tk.Label(self.flyout_content, text="", bg="#070b14", fg="#cbd5e1", font=("Segoe UI", 8), justify="left", anchor="w")
                lbl.pack(fill="x", padx=6, pady=1)
                lbl.bind("<MouseWheel>", _on_wheel)
                self.flyout_labels[rk] = lbl

        # Positioning: Docked directly above the widget, matching width and x-alignment
        wx = self.root.winfo_rootx()
        wy = self.root.winfo_rooty() - fly_h - 6
        if wy < 10:
            wy = self.root.winfo_rooty() + self.root.winfo_height() + 6
        self.flyout_window.geometry(f"{fly_w}x{fly_h}+{wx}+{wy}")

        is_active = p_stat.get("status") == "ACTIVE"
        dot_color = "#10b981" if is_active else ("#f43f5e" if p_stat.get("status") == "ERROR" else "#64748b")
        plan_str = p_stat.get("plan_type") or item.get("plan_type", "Active")

        self.flyout_dot.configure(fg=dot_color)
        self.flyout_title.configure(text=display_names.get(p_key, p_key))
        self.flyout_badge.configure(text=plan_str.upper())

        # Session Quota calculation
        sess_rem = item.get("session_balance_remaining_pct", 100)
        sess_used = item.get("session_used_pct", round(100.0 - sess_rem, 1))

        # Session Reset calculation
        reset_epoch = item.get("reset_epoch")
        if reset_epoch:
            diff = int(reset_epoch - time.time())
            if diff > 0:
                h = diff // 3600
                m = (diff % 3600) // 60
                sess_reset_str = f"Resets in {h} hr {m} min" if h > 0 else f"Resets in {m} min"
            else:
                sess_reset_str = "Resets soon"
        elif p_key == "claude":
            sess_reset_str = "Resets in 2 hr 6 min"
        else:
            sess_reset_str = "Standard cycle"

        # Weekly Quota & Reset
        week_rem = item.get("weekly_balance_remaining_pct", 100)
        week_used = item.get("weekly_used_pct", round(100.0 - week_rem, 1))
        weekly_reset_str = item.get("weekly_reset_str") or "Mon 3:00 AM"

        tokens_today = item.get("tokens_today", 0)
        tokens_week = item.get("tokens_week", 0)
        cost_today = item.get("cost_today_usd", 0.0)

        lines = self.format_flyout_quota_lines(p_key=p_key, item=item, tracking_mode=getattr(self, "quota_tracking_mode", "individual"))
        for rk in ("sess_quota", "sess_reset", "week_quota", "week_reset"):
            if rk in lines:
                self.flyout_labels[rk].configure(text=lines[rk]["text"], fg=lines[rk]["fg"])
            if rk in lines:
                self.flyout_labels[rk].configure(text=lines[rk]["text"], fg=lines[rk]["fg"])

        self.flyout_labels["tokens_info"].configure(
            text=f"• Tokens: {tokens_today:,} today  |  {tokens_week:,} weekly",
            fg="#e2e8f0"
        )
        self.flyout_labels["cost_info"].configure(
            text=f"• Est. Cost Today: ${cost_today:.4f}",
            fg="#34d399" if p_key != "ollama" else "#10b981"
        )
        self.flyout_labels["engine_status"].configure(
            text=f"• Engine: {p_stat.get('status', 'ACTIVE')} • Telemetry Live",
            fg="#10b981" if is_active else "#f43f5e"
        )

        self.flyout_window.deiconify()

    def _hide_flyout(self):
        if self.flyout_window:
            self.flyout_window.withdraw()

    def update_loop(self):
        """Polls every 2 seconds and refreshes the canvas UI."""
        if not self.is_running:
            return

        def _worker():
            c, p = self.fetch_data()
            if self.root and self.is_running:
                self.root.after(0, lambda: self._apply_update(c, p))

        threading.Thread(target=_worker, daemon=True).start()
        if self.root and self.is_running:
            self.root.after(2000, self.update_loop)

    def _apply_update(self, c, p):
        if c:
            self.cached_comparison = c
        if p:
            self.cached_providers = p
        if getattr(self, "port_lbl", None) and getattr(self, "active_port", None):
            self.port_lbl.configure(text=f"Port {self.active_port}")
        self.render_canvas()

    def run(self):
        """Runs the Tkinter mainloop."""
        self.is_running = True
        self.build_ui()
        self.root.after(600, self._poll_focus)
        # Immediate initial update
        def _initial_worker():
            c, p = self.fetch_data()
            if self.root and self.is_running:
                self.root.after(0, lambda: self._apply_update(c, p))
        threading.Thread(target=_initial_worker, daemon=True).start()
        self.update_loop()
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.close()

    def close(self):
        self.is_running = False
        if self.flyout_window:
            try:
                self.flyout_window.destroy()
            except Exception:
                pass
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None

def run_native_widget(host="127.0.0.1", port=8765):
    widget = NativeTaskbarWidget(host=host, port=port)
    widget.run()

if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
    run_native_widget(host, port)
