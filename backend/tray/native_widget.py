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

class NativeTaskbarWidget:
    """
    Chromeless, always-on-top, dark-mode desktop widget docked right above the Windows taskbar.
    Displays live multi-account dual-bar telemetry, local AI cost savings, and hover tooltips.
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
        """Fetches live comparison and providers telemetry with automatic active port probing."""
        comp, provs = None, None
        ports_to_try = []
        for p in [getattr(self, "active_port", None), 8765, self.port]:
            if p and p not in ports_to_try:
                ports_to_try.append(p)

        working_port = None
        for p in ports_to_try:
            try:
                req_c = urllib.request.Request(f"http://{self.host}:{p}/api/usage/comparison")
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

        return comp, provs

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
        self.root.configure(bg="#080b11")

        # Main Bordered Container
        main_frame = tk.Frame(self.root, bg="#0d131f", highlightbackground="#06b6d4", highlightthickness=1)
        main_frame.pack(fill="both", expand=True, padx=2, pady=2)

        # Header (Draggable)
        header = tk.Frame(main_frame, bg="#111827", height=32)
        header.pack(fill="x", side="top", padx=0, pady=0)

        # Bind dragging
        header.bind("<Button-1>", self._start_drag)
        header.bind("<B1-Motion>", self._on_drag)

        title_lbl = tk.Label(
            header,
            text="⚡ AI USAGE MONITOR",
            bg="#111827",
            fg="#06b6d4",
            font=("Segoe UI", 9, "bold")
        )
        title_lbl.pack(side="left", padx=8, pady=4)
        title_lbl.bind("<Button-1>", self._start_drag)
        title_lbl.bind("<B1-Motion>", self._on_drag)

        live_badge = tk.Label(
            header,
            text="● Live",
            bg="#111827",
            fg="#10b981",
            font=("Segoe UI", 8, "bold")
        )
        live_badge.pack(side="left", padx=2)

        # Close and Action Buttons
        btn_close = tk.Label(
            header,
            text="✕",
            bg="#111827",
            fg="#94a3b8",
            font=("Segoe UI", 10, "bold"),
            cursor="hand2"
        )
        btn_close.pack(side="right", padx=8)
        btn_close.bind("<Button-1>", lambda e: self.close())
        btn_close.bind("<Enter>", lambda e: btn_close.configure(fg="#f43f5e"))
        btn_close.bind("<Leave>", lambda e: btn_close.configure(fg="#94a3b8"))

        btn_open = tk.Label(
            header,
            text="↗",
            bg="#111827",
            fg="#94a3b8",
            font=("Segoe UI", 10, "bold"),
            cursor="hand2"
        )
        btn_open.pack(side="right", padx=4)
        btn_open.bind("<Button-1>", lambda e: self._open_browser())
        btn_open.bind("<Enter>", lambda e: btn_open.configure(fg="#38bdf8"))
        btn_open.bind("<Leave>", lambda e: btn_open.configure(fg="#94a3b8"))

        # Accounts List Canvas
        self.canvas = tk.Canvas(main_frame, bg="#0d131f", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=6)

        # Bottom Savings Strip
        bottom_strip = tk.Frame(main_frame, bg="#080b11", height=24)
        bottom_strip.pack(fill="x", side="bottom", padx=6, pady=4)

        self.savings_lbl = tk.Label(
            bottom_strip,
            text="💰 Local AI Saved: $0.00",
            bg="#080b11",
            fg="#34d399",
            font=("Segoe UI", 8, "bold")
        )
        self.savings_lbl.pack(side="left", padx=4)

        self.port_lbl = tk.Label(
            bottom_strip,
            text=f"Port {getattr(self, 'active_port', self.port)}",
            bg="#080b11",
            fg="#64748b",
            font=("Segoe UI", 8)
        )
        self.port_lbl.pack(side="right", padx=4)

        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Leave>", self._on_canvas_leave)

    def _start_drag(self, event):
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

    def render_canvas(self):
        """Draws the 5 accounts cards with dual bars and status badges."""
        if not self.canvas:
            return
        self.canvas.delete("all")

        providers_order = ["claude", "gemini", "chatgpt", "ollama", "copilot"]
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
        card_h = 58
        card_w = self.width - 24

        self._hit_boxes = []

        for p_key in providers_order:
            item = prov_map.get(p_key, {
                "tokens_today": 0,
                "session_balance_remaining_pct": 100,
                "weekly_balance_remaining_pct": 100,
                "daily_allowance": 500000,
                "weekly_allowance": 3500000
            })
            p_stat = prov_info.get(p_key, {})
            is_active = p_stat.get("status") == "ACTIVE"
            dot_color = "#10b981" if is_active else ("#f43f5e" if p_stat.get("status") == "ERROR" else "#64748b")

            # Background pill
            self.canvas.create_rectangle(
                4, card_y, card_w, card_y + card_h,
                fill="#151e2e", outline="#1e293b", width=1
            )
            self._hit_boxes.append((4, card_y, card_w, card_y + card_h, p_key, item, p_stat))

            # Status dot
            self.canvas.create_oval(12, card_y + 10, 18, card_y + 16, fill=dot_color, outline="")

            # Provider Name
            self.canvas.create_text(
                26, card_y + 13,
                text=display_names[p_key],
                anchor="w",
                fill="#f1f5f9",
                font=("Segoe UI", 9, "bold")
            )

            # Tokens today
            tok_str = f"{item.get('tokens_today', 0):,} tok"
            self.canvas.create_text(
                card_w - 12, card_y + 13,
                text=tok_str,
                anchor="e",
                fill="#06b6d4",
                font=("Segoe UI", 8, "bold")
            )

            # Bar 1: Session Balance
            sess_pct = max(0, min(100, item.get("session_balance_remaining_pct", 100)))
            bar_x = 72
            bar_w = card_w - bar_x - 48
            bar1_y = card_y + 26
            bar_h = 7

            self.canvas.create_text(12, bar1_y + 3, text="Session:", anchor="w", fill="#94a3b8", font=("Segoe UI", 7))
            self.canvas.create_rectangle(bar_x, bar1_y, bar_x + bar_w, bar1_y + bar_h, fill="#1e293b", outline="")
            fill_w1 = int(bar_w * (sess_pct / 100.0))
            color1 = "#f43f5e" if sess_pct < 20 else "#06b6d4"
            if fill_w1 > 0:
                self.canvas.create_rectangle(bar_x, bar1_y, bar_x + fill_w1, bar1_y + bar_h, fill=color1, outline="")
            self.canvas.create_text(card_w - 12, bar1_y + 3, text=f"{sess_pct}%", anchor="e", fill="#cbd5e1", font=("Segoe UI", 7))

            # Bar 2: Weekly Balance
            week_pct = max(0, min(100, item.get("weekly_balance_remaining_pct", 100)))
            bar2_y = card_y + 39

            self.canvas.create_text(12, bar2_y + 3, text="Weekly:", anchor="w", fill="#94a3b8", font=("Segoe UI", 7))
            self.canvas.create_rectangle(bar_x, bar2_y, bar_x + bar_w, bar2_y + bar_h, fill="#1e293b", outline="")
            fill_w2 = int(bar_w * (week_pct / 100.0))
            color2 = "#f59e0b" if week_pct < 20 else "#8b5cf6"
            if fill_w2 > 0:
                self.canvas.create_rectangle(bar_x, bar2_y, bar_x + fill_w2, bar2_y + bar_h, fill=color2, outline="")
            self.canvas.create_text(card_w - 12, bar2_y + 3, text=f"{week_pct}%", anchor="e", fill="#cbd5e1", font=("Segoe UI", 7))

            card_y += card_h + 6

        # Update Savings Label
        if comp.get("local_savings"):
            saved = comp["local_savings"].get("savings_today_usd", 0.0)
            self.savings_lbl.configure(text=f"💰 Local AI Saved: ${saved:.2f}")

    def _on_canvas_motion(self, event):
        """Displays a weather-style telemetry hover flyout when hovering over an account."""
        hovered = None
        for (x1, y1, x2, y2, p_key, item, p_stat) in getattr(self, "_hit_boxes", []):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                hovered = (p_key, item, p_stat)
                break

        if hovered:
            self._show_flyout(hovered[0], hovered[1], hovered[2])
        else:
            self._hide_flyout()

    def _on_canvas_leave(self, event):
        self._hide_flyout()

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

        self.flyout_labels["sess_quota"].configure(
            text=f"• Current Session:   {sess_rem}% rem  ({sess_used}% used)",
            fg="#38bdf8"
        )
        self.flyout_labels["sess_reset"].configure(
            text=f"  ↳ {sess_reset_str}",
            fg="#94a3b8"
        )
        self.flyout_labels["week_quota"].configure(
            text=f"• Weekly Pool:        {week_rem}% rem  ({week_used}% used)",
            fg="#a855f7"
        )
        self.flyout_labels["week_reset"].configure(
            text=f"  ↳ Resets {weekly_reset_str}",
            fg="#94a3b8"
        )
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
