import sys
import threading
import time
import webbrowser
from typing import Optional, Callable

class WindowsTrayManager:
    """
    Zero-Dependency Native Windows System Tray (Taskbar Notification Area) Integration.
    Uses shell32.dll and user32.dll directly via ctypes.
    """

    def __init__(
        self,
        app_name: str = "AI Usage Monitor",
        on_open_dashboard: Optional[Callable] = None,
        on_open_widget: Optional[Callable] = None,
        on_sync_now: Optional[Callable] = None,
        on_exit: Optional[Callable] = None
    ):
        self.app_name = app_name
        self.on_open_dashboard = on_open_dashboard
        self.on_open_widget = on_open_widget
        self.on_sync_now = on_sync_now
        self.on_exit = on_exit

        self.is_windows = sys.platform == "win32"
        self._thread: Optional[threading.Thread] = None
        self._hwnd = None
        self._running = False
        self._tooltip = f"{app_name}\nInitializing..."

    def start(self):
        if not self.is_windows:
            print("[INFO] Non-Windows OS detected; native system tray disabled.")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_tray_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self.is_windows and self._hwnd:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                WM_CLOSE = 0x0010
                user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
            except Exception:
                pass

    def update_tooltip(self, text: str):
        """Updates the taskbar tray icon tooltip text dynamically."""
        self._tooltip = text[:127] # Win32 szTip max 128 chars
        if self.is_windows and self._hwnd:
            try:
                self._update_icon()
            except Exception:
                pass

    def _update_icon(self):
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_byte * 8),
            ]

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [
                ('cbSize', wintypes.DWORD),
                ('hWnd', wintypes.HWND),
                ('uID', wintypes.UINT),
                ('uFlags', wintypes.UINT),
                ('uCallbackMessage', wintypes.UINT),
                ('hIcon', wintypes.HICON),
                ('szTip', wintypes.WCHAR * 128),
                ('dwState', wintypes.DWORD),
                ('dwStateMask', wintypes.DWORD),
                ('szInfo', wintypes.WCHAR * 256),
                ('uTimeoutOrVersion', wintypes.UINT),
                ('szInfoTitle', wintypes.WCHAR * 64),
                ('dwInfoFlags', wintypes.DWORD),
                ('guidItem', GUID),
                ('hBalloonIcon', wintypes.HICON),
            ]

        NIM_MODIFY = 0x00000001
        NIF_TIP = 0x00000004

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_TIP
        nid.szTip = self._tooltip

        ctypes.windll.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _run_tray_loop(self):
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32
            kernel32 = ctypes.windll.kernel32

            WM_USER = 0x0400
            WM_TRAYCALLBACK = WM_USER + 20
            WM_COMMAND = 0x0111
            WM_RBUTTONUP = 0x0205
            WM_LBUTTONDBLCLK = 0x0203
            WM_LBUTTONUP = 0x0202
            WM_DESTROY = 0x0002

            NIM_ADD = 0x00000000
            NIM_DELETE = 0x00000002
            NIF_MESSAGE = 0x00000001
            NIF_ICON = 0x00000002
            NIF_TIP = 0x00000004
            IDI_APPLICATION = 32512

            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", wintypes.DWORD),
                    ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_byte * 8),
                ]

            class NOTIFYICONDATAW(ctypes.Structure):
                _fields_ = [
                    ('cbSize', wintypes.DWORD),
                    ('hWnd', wintypes.HWND),
                    ('uID', wintypes.UINT),
                    ('uFlags', wintypes.UINT),
                    ('uCallbackMessage', wintypes.UINT),
                    ('hIcon', wintypes.HICON),
                    ('szTip', wintypes.WCHAR * 128),
                    ('dwState', wintypes.DWORD),
                    ('dwStateMask', wintypes.DWORD),
                    ('szInfo', wintypes.WCHAR * 256),
                    ('uTimeoutOrVersion', wintypes.UINT),
                    ('szInfoTitle', wintypes.WCHAR * 64),
                    ('dwInfoFlags', wintypes.DWORD),
                    ('guidItem', GUID),
                    ('hBalloonIcon', wintypes.HICON),
                ]

            # Menu command IDs
            CMD_DASHBOARD = 1001
            CMD_WIDGET = 1002
            CMD_SYNC = 1003
            CMD_EXIT = 1004

            LRESULT = getattr(wintypes, 'LRESULT', ctypes.c_ssize_t)
            user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.DefWindowProcW.restype = LRESULT

            WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

            def wnd_proc(hwnd, msg, wparam, lparam):
                if msg == WM_TRAYCALLBACK:
                    if lparam == WM_LBUTTONDBLCLK or lparam == WM_LBUTTONUP:
                        if self.on_open_dashboard:
                            self.on_open_dashboard()
                    elif lparam == WM_RBUTTONUP:
                        # Show Right-click Context Menu
                        hmenu = user32.CreatePopupMenu()
                        MF_STRING = 0x00000000
                        MF_SEPARATOR = 0x00000800

                        user32.AppendMenuW(hmenu, MF_STRING, CMD_DASHBOARD, "⚡ Open AI Usage Dashboard")
                        user32.AppendMenuW(hmenu, MF_STRING, CMD_WIDGET, "🪟 Launch Mini Status Widget")
                        user32.AppendMenuW(hmenu, MF_STRING, CMD_SYNC, "🔄 Sync Quota Now")
                        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
                        user32.AppendMenuW(hmenu, MF_STRING, CMD_EXIT, "❌ Exit AI Usage Monitor")

                        class POINT(ctypes.Structure):
                            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

                        pt = POINT()
                        user32.GetCursorPos(ctypes.byref(pt))
                        user32.SetForegroundWindow(hwnd)
                        TPM_RIGHTBUTTON = 0x0002
                        user32.TrackPopupMenu(hmenu, TPM_RIGHTBUTTON, pt.x, pt.y, 0, hwnd, None)
                        user32.DestroyMenu(hmenu)
                    return 0

                elif msg == WM_COMMAND:
                    cmd_id = int(wparam) & 0xFFFF
                    if cmd_id == CMD_DASHBOARD:
                        if self.on_open_dashboard:
                            self.on_open_dashboard()
                    elif cmd_id == CMD_WIDGET:
                        if self.on_open_widget:
                            self.on_open_widget()
                    elif cmd_id == CMD_SYNC:
                        if self.on_sync_now:
                            self.on_sync_now()
                    elif cmd_id == CMD_EXIT:
                        if self.on_exit:
                            self.on_exit()
                        user32.DestroyWindow(hwnd)
                    return 0

                elif msg == WM_DESTROY:
                    # Remove tray icon cleanly
                    nid = NOTIFYICONDATAW()
                    nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
                    nid.hWnd = hwnd
                    nid.uID = 1
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
                    user32.PostQuitMessage(0)
                    return 0

                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

            # Register Window Class
            class WNDCLASSW(ctypes.Structure):
                _fields_ = [
                    ('style', wintypes.UINT),
                    ('lpfnWndProc', WNDPROC),
                    ('cbClsExtra', ctypes.c_int),
                    ('cbWndExtra', ctypes.c_int),
                    ('hInstance', wintypes.HINSTANCE),
                    ('hIcon', wintypes.HICON),
                    ('hCursor', wintypes.HANDLE),
                    ('hbrBackground', wintypes.HBRUSH),
                    ('lpszMenuName', wintypes.LPCWSTR),
                    ('lpszClassName', wintypes.LPCWSTR)
                ]

            hinstance = kernel32.GetModuleHandleW(None)
            class_name = f"AIUsageMonitorTrayClass_{id(self)}_{int(time.time() * 1000)}"
            self._proc_delegate = WNDPROC(wnd_proc)  # Retain reference to prevent garbage collection crash

            wcls = WNDCLASSW()
            wcls.lpfnWndProc = self._proc_delegate
            wcls.hInstance = hinstance
            wcls.lpszClassName = class_name
            user32.RegisterClassW(ctypes.byref(wcls))

            # Create message-only / hidden window
            hwnd = user32.CreateWindowExW(
                0, class_name, "AI Usage Monitor Tray Window",
                0, 0, 0, 0, 0, 0, 0, hinstance, None
            )
            self._hwnd = hwnd

            # Add System Tray Icon
            hicon = user32.LoadIconW(None, IDI_APPLICATION)
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = hwnd
            nid.uID = 1
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = WM_TRAYCALLBACK
            nid.hIcon = hicon
            nid.szTip = self._tooltip

            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

            # Message pump
            msg = wintypes.MSG()
            while self._running and user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        except Exception as e:
            print(f"[WARN] Tray loop encountered error: {e}")
