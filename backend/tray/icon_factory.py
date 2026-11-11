"""
Zero-Dependency Windows Tray, Taskbar & Task Manager Icon Generator & Loader.
Creates pixel-perfect 32x32 / 16x16 Windows .ico files and Win32 HICON handles
for the 4 selectable IRIS application icon variants (plus legacy aliases):
- 'iris_head' (alias 'johnny5'): IRIS Royal-Blue Hair & Dimpled Smile Head Portrait
- 'iris_eye' (alias 'scanning'): IRIS Sapphire Cyber-Optic Eye with Gold Deus-Ex Reticle
- 'iris_cyber_arm' (alias 'shield'): Deus-Ex Cybernetic Arm & Neural Telemetry Crest
- 'iris_holo': IRIS Tactical Holo-Visor Emblem
"""

import os
import sys
import struct
import math
from pathlib import Path
from typing import Optional, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ICONS_DIR = REPO_ROOT / "frontend" / "assets" / "icons"

CANONICAL_ICON_CHOICES: List[Dict[str, str]] = [
    {
        "id": "iris_head",
        "alias": "johnny5",
        "label": "IRIS Portrait (Royal-Blue Hair & Dimpled Smile)",
        "ico": "app_icon_iris_head.ico",
        "preview": "/assets/icons/app_icon_iris_head.png",
        "description": "Pixel-art portrait of IRIS with royal-blue hair, sapphire eyes, and mischievous dimpled smile."
    },
    {
        "id": "iris_eye",
        "alias": "scanning",
        "label": "IRIS Cyber-Optic Eye (Sapphire & Gold Reticle)",
        "ico": "app_icon_iris_eye.ico",
        "preview": "/assets/icons/app_icon_iris_eye.png",
        "description": "Close-up of IRIS's sapphire-cyan eye framed by royal-blue hair with a golden Deus-Ex hexagonal reticle."
    },
    {
        "id": "iris_cyber_arm",
        "alias": "shield",
        "label": "Deus-Ex Cybernetic Arm Crest",
        "ico": "app_icon_iris_cyber_arm.ico",
        "preview": "/assets/icons/app_icon_iris_cyber_arm.png",
        "description": "Matte carbon-fiber and gold-conduit biomechanical cybernetic hand projecting a sapphire telemetry core."
    },
    {
        "id": "iris_holo",
        "alias": "holo",
        "label": "IRIS Tactical Holo-Visor",
        "ico": "app_icon_iris_holo.ico",
        "preview": "/assets/icons/app_icon_iris_holo.png",
        "description": "IRIS wearing translucent cyan holographic AR telemetry optics."
    }
]


def normalize_icon_type(icon_type: Optional[str]) -> str:
    """Normalizes legacy and canonical icon names to one of the 4 canonical IDs."""
    raw = str(icon_type or "iris_head").strip().lower()
    mapping = {
        "johnny5": "iris_head",
        "iris": "iris_head",
        "iris_head": "iris_head",
        "head": "iris_head",
        "scanning": "iris_eye",
        "iris_eye": "iris_eye",
        "eye": "iris_eye",
        "shield": "iris_cyber_arm",
        "iris_cyber_arm": "iris_cyber_arm",
        "cyber_arm": "iris_cyber_arm",
        "iris_holo": "iris_holo",
        "holo": "iris_holo",
    }
    return mapping.get(raw, "iris_head")


def _draw_iris_head(size: int = 32) -> bytearray:
    """
    Renders a crisp 32x32 pixel-art portrait of IRIS:
    - Sleek royal-blue bob hair (#1D4ED8 / #3B82F6 highlights)
    - Warm skin face with a mischievous dimpled smile
    - Piercing sapphire-cyan eyes (#06B6D4 / #38BDF8)
    - Gold & charcoal cybernetic collar (#F59E0B)
    """
    pixels = bytearray(size * size * 4)

    def set_pixel(x, y, r, g, b, a=255):
        if 0 <= x < size and 0 <= y < size:
            idx = (y * size + x) * 4
            pixels[idx] = r
            pixels[idx + 1] = g
            pixels[idx + 2] = b
            pixels[idx + 3] = a

    scale = size / 32.0
    cx, cy = 16.0 * scale, 15.0 * scale

    # 1. Rounded dark slate badge background for crisp contrast in any Windows taskbar theme
    for y in range(size):
        for x in range(size):
            if math.hypot(x - 15.5 * scale, y - 15.5 * scale) <= 15.0 * scale:
                set_pixel(x, y, 11, 14, 23, 255)

    # 2. Royal-Blue Hair Silhouette (Dome + Side Bob locks)
    for y in range(int(3 * scale), int(26 * scale)):
        for x in range(int(5 * scale), int(27 * scale)):
            dx = (x - cx) / (10.5 * scale)
            dy = (y - 13.0 * scale) / (11.5 * scale)
            if dx * dx + dy * dy <= 1.0:
                # Royal blue shading with vibrant highlight band near y=7..10
                if int(6 * scale) <= y <= int(10 * scale) and abs(x - cx) < 7 * scale:
                    set_pixel(x, y, 59, 130, 246, 255)  # #3B82F6 Royal highlight
                elif x < cx - 5 * scale or x > cx + 5 * scale:
                    set_pixel(x, y, 23, 52, 122, 255)   # Deep midnight cobalt
                else:
                    set_pixel(x, y, 37, 99, 235, 255)   # #2563EB Royal Blue

    # 3. Warm Face Oval (with asymmetrical royal-blue bangs sweeping across top-left)
    for y in range(int(8 * scale), int(24 * scale)):
        for x in range(int(9 * scale), int(23 * scale)):
            dx = (x - cx) / (6.8 * scale)
            dy = (y - 15.5 * scale) / (7.8 * scale)
            if dx * dx + dy * dy <= 1.0:
                # Keep asymmetrical royal-blue hair bangs at top
                if y < int(11 * scale) and x < int(18 * scale):
                    set_pixel(x, y, 37, 99, 235, 255)
                elif y < int(10 * scale):
                    set_pixel(x, y, 29, 78, 216, 255)
                else:
                    set_pixel(x, y, 226, 168, 132, 255)  # Warm skin tone

    # 4. Sapphire-Cyan Eyes (y = 13..15)
    for ex in (int(12 * scale), int(13 * scale), int(18 * scale), int(19 * scale)):
        set_pixel(ex, int(13 * scale), 15, 23, 42, 255)     # Eyelash
        set_pixel(ex, int(14 * scale), 6, 182, 212, 255)    # Sapphire-cyan iris
    set_pixel(int(13 * scale), int(14 * scale), 224, 242, 254, 255)  # Eye glint
    set_pixel(int(19 * scale), int(14 * scale), 224, 242, 254, 255)  # Eye glint

    # 5. Mischievous Asymmetric Dimpled Smile (y = 19..20)
    for sx in range(int(13 * scale), int(19 * scale)):
        sy = int(19 * scale) if sx < int(17 * scale) else int(18 * scale)
        set_pixel(sx, sy, 165, 72, 62, 255)
    # Cheek dimple pixel
    set_pixel(int(20 * scale), int(18 * scale), 185, 118, 92, 255)

    # 6. Deus-Ex Charcoal & Gold Cybernetic Collar (y = 24..29)
    for y in range(int(24 * scale), int(30 * scale)):
        for x in range(int(8 * scale), int(24 * scale)):
            if y == int(25 * scale) or x == int(20 * scale):
                set_pixel(x, y, 245, 158, 11, 255)  # Gold conduit seam
            else:
                set_pixel(x, y, 30, 41, 59, 255)    # Carbon slate collar

    return pixels


def _draw_iris_eye(size: int = 32) -> bytearray:
    """
    Renders IRIS's Cyber-Optic Eye:
    - Royal-blue brow & hair frame
    - Glowing sapphire-cyan iris (#06B6D4 / #38BDF8)
    - Golden Deus-Ex hexagonal reticle ring (#F59E0B)
    """
    pixels = bytearray(size * size * 4)

    def set_pixel(x, y, r, g, b, a=255):
        if 0 <= x < size and 0 <= y < size:
            idx = (y * size + x) * 4
            pixels[idx] = r
            pixels[idx + 1] = g
            pixels[idx + 2] = b
            pixels[idx + 3] = a

    scale = size / 32.0
    cx, cy = 16.0 * scale, 16.0 * scale

    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy)
            if d <= 15.0 * scale:
                # Outer royal-blue frame
                if d > 12.8 * scale:
                    set_pixel(x, y, 37, 99, 235, 255)
                else:
                    set_pixel(x, y, 11, 15, 25, 255)

            # Almond eye contour
            dx = (x - cx) / (12.0 * scale)
            dy = (y - cy) / (7.2 * scale)
            if dx * dx + dy * dy <= 1.0:
                if d > 6.5 * scale:
                    set_pixel(x, y, 226, 232, 240, 255)  # Sclera
                elif d > 4.6 * scale:
                    set_pixel(x, y, 37, 99, 235, 255)    # Outer sapphire iris
                elif d > 3.2 * scale:
                    set_pixel(x, y, 245, 158, 11, 255)   # Gold Deus-Ex reticle ring
                elif d > 1.6 * scale:
                    set_pixel(x, y, 56, 189, 248, 255)   # Inner cyan glow
                else:
                    set_pixel(x, y, 15, 23, 42, 255)     # Pupil

    # Specular highlight
    set_pixel(int(13 * scale), int(13 * scale), 255, 255, 255, 255)
    set_pixel(int(14 * scale), int(13 * scale), 255, 255, 255, 255)
    return pixels


def _draw_iris_cyber_arm(size: int = 32) -> bytearray:
    """
    Renders the Deus-Ex Cybernetic Arm & Neural Shield Crest:
    - Obsidian carbon-fiber shield with gold (#F59E0B) & sapphire (#38BDF8) biomechanical conduits.
    """
    pixels = bytearray(size * size * 4)

    def set_pixel(x, y, r, g, b, a=255):
        if 0 <= x < size and 0 <= y < size:
            idx = (y * size + x) * 4
            pixels[idx] = r
            pixels[idx + 1] = g
            pixels[idx + 2] = b
            pixels[idx + 3] = a

    scale = size / 32.0

    # Shield + Cybernetic Forearm geometry
    for y in range(int(3 * scale), int(29 * scale)):
        half_w = (12.0 * scale) if y < 14 * scale else (12.0 * scale) * (1.0 - ((y - 14 * scale) / (16 * scale)) * 0.85)
        left = int(16 * scale - half_w)
        right = int(16 * scale + half_w)
        for x in range(left, right + 1):
            is_border = (x <= left + 1 or x >= right - 1 or y <= int(4 * scale))
            if is_border:
                set_pixel(x, y, 245, 158, 11, 255)  # Deus-Ex Gold rim
            elif abs(x - int(16 * scale)) <= 1 or y in (int(11 * scale), int(19 * scale)):
                set_pixel(x, y, 56, 189, 248, 255)  # Sapphire-cyan neural conduit
            else:
                set_pixel(x, y, 24, 33, 50, 245)    # Matte carbon-titanium plate

    return pixels


def _draw_iris_holo(size: int = 32) -> bytearray:
    """Renders IRIS's Tactical Holo-Visor emblem."""
    px = _draw_iris_head(size)
    scale = size / 32.0
    # Add translucent cyan AR visor across eyes (y = 12..16, x = 8..24)
    for y in range(int(12 * scale), int(17 * scale)):
        for x in range(int(8 * scale), int(24 * scale)):
            idx = (y * size + x) * 4
            if y in (int(12 * scale), int(16 * scale)):
                px[idx], px[idx + 1], px[idx + 2], px[idx + 3] = 56, 189, 248, 255
            else:
                px[idx] = min(255, (px[idx] + 56) // 2)
                px[idx + 1] = min(255, (px[idx + 1] + 210) // 2)
                px[idx + 2] = min(255, (px[idx + 2] + 250) // 2)
                px[idx + 3] = 255
    return px


# Backward-compatible procedural helpers used by existing unit tests
_draw_johnny5_head = _draw_iris_head
_draw_cyber_shield = _draw_iris_cyber_arm


def generate_ico_file(pixels_rgba: bytearray, size: int, output_path: Path):
    """Creates a standard Windows .ico file with BITMAPINFOHEADER and 32-bit BGRA pixels."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    bgra = bytearray(size * size * 4)
    for y in range(size):
        src_y = (size - 1 - y)
        for x in range(size):
            src_idx = (src_y * size + x) * 4
            dst_idx = (y * size + x) * 4
            bgra[dst_idx] = pixels_rgba[src_idx + 2]      # B
            bgra[dst_idx + 1] = pixels_rgba[src_idx + 1]  # G
            bgra[dst_idx + 2] = pixels_rgba[src_idx]      # R
            bgra[dst_idx + 3] = pixels_rgba[src_idx + 3]  # A

    mask = bytearray((size * size) // 8)
    img_size = 40 + len(bgra) + len(mask)
    header = struct.pack('<HHH', 0, 1, 1)
    entry = struct.pack('<BBBBHHII', size, size, 0, 0, 1, 32, img_size, 22)
    bih = struct.pack('<IIIHHIIIIII', 40, size, size * 2, 1, 32, 0, len(bgra), 0, 0, 0, 0)

    output_path.write_bytes(header + entry + bih + bgra + mask)


def ensure_ico_assets():
    """Generates all 4 selectable IRIS .ico files + legacy aliases in frontend/assets/icons."""
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    head_px = _draw_iris_head(32)
    eye_px = _draw_iris_eye(32)
    arm_px = _draw_iris_cyber_arm(32)
    holo_px = _draw_iris_holo(32)

    targets = [
        (ICONS_DIR / "app_icon_iris_head.ico", head_px),
        (ICONS_DIR / "app_icon_johnny5.ico", head_px),
        (ICONS_DIR / "app_icon_iris_eye.ico", eye_px),
        (ICONS_DIR / "app_icon_iris_cyber_arm.ico", arm_px),
        (ICONS_DIR / "app_icon_shield.ico", arm_px),
        (ICONS_DIR / "app_icon_iris_holo.ico", holo_px),
    ]
    for path, px in targets:
        generate_ico_file(px, 32, path)


def resolve_icon_ico_path(icon_type: str = "iris_head") -> Path:
    """Returns the on-disk .ico file path for any canonical or legacy icon_type."""
    ensure_ico_assets()
    norm = normalize_icon_type(icon_type)
    ico_path = ICONS_DIR / f"app_icon_{norm}.ico"
    if ico_path.exists():
        return ico_path
    return ICONS_DIR / "app_icon_iris_head.ico"


def get_tray_icon_handle(icon_type: str = "iris_head", big_icon: bool = False):
    """
    Returns a native Win32 HICON handle for the requested icon type
    ('iris_head'/'johnny5', 'iris_eye'/'scanning', 'iris_cyber_arm'/'shield', 'iris_holo').
    """
    if sys.platform != "win32":
        return None

    try:
        import ctypes
        user32 = ctypes.windll.user32
        target_ico = resolve_icon_ico_path(icon_type)

        if target_ico.exists():
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x0010
            if big_icon:
                cx = user32.GetSystemMetrics(11) or 32  # SM_CXICON
                cy = user32.GetSystemMetrics(12) or 32  # SM_CYICON
            else:
                cx = user32.GetSystemMetrics(49) or 16  # SM_CXSMICON
                cy = user32.GetSystemMetrics(50) or 16  # SM_CYSMICON
            hicon = user32.LoadImageW(0, str(target_ico), IMAGE_ICON, cx, cy, LR_LOADFROMFILE)
            if hicon:
                return hicon
    except Exception as e:
        print(f"[WARN] Failed to load custom tray icon: {e}")

    try:
        import ctypes
        return ctypes.windll.user32.LoadIconW(None, 32512)
    except Exception:
        return None


def apply_process_and_window_icon(icon_type: str = "iris_head", tk_root=None) -> bool:
    """
    Applies the selected IRIS application icon to:
    1. Windows AppUserModelID (so Taskbar & Task Manager identify the process as IRIS).
    2. Current Console / Process Window via Win32 WM_SETICON (ICON_SMALL & ICON_BIG).
    3. Any passed Tkinter window (e.g., NativeTaskbarWidget) via iconbitmap() and WM_SETICON.
    """
    ico_path = resolve_icon_ico_path(icon_type)
    applied = False

    if tk_root is not None:
        try:
            tk_root.iconbitmap(str(ico_path))
            applied = True
        except Exception:
            pass

    if sys.platform != "win32":
        return applied

    try:
        import ctypes
        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        try:
            shell32.SetCurrentProcessExplicitAppUserModelID("IRIS.TelemetrySentinel.v3")
        except Exception:
            pass

        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        hicon_sm = get_tray_icon_handle(icon_type, big_icon=False)
        hicon_lg = get_tray_icon_handle(icon_type, big_icon=True)

        hwnds = []
        console_hwnd = kernel32.GetConsoleWindow()
        if console_hwnd:
            hwnds.append(console_hwnd)
        if tk_root is not None:
            try:
                tk_hwnd = tk_root.winfo_id()
                if tk_hwnd:
                    hwnds.append(tk_hwnd)
                    parent_hwnd = user32.GetParent(tk_hwnd)
                    if parent_hwnd:
                        hwnds.append(parent_hwnd)
            except Exception:
                pass

        for hwnd in hwnds:
            if hicon_sm:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_sm)
            if hicon_lg:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_lg)
            applied = True
    except Exception:
        pass

    return applied
