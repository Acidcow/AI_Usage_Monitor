"""
Zero-Dependency Windows Tray Icon Generator & Loader.
Creates pixel-perfect 32x32 / 16x16 Windows .ico files and HICON handles
for Johnny 5 (Short Circuit) and Cyber Shield with neon purple slash.
"""

import os
import sys
import struct
import math
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ICONS_DIR = REPO_ROOT / "frontend" / "assets" / "icons"

def _draw_johnny5_head(size: int = 32) -> bytearray:
    """
    Renders Johnny 5 head with glowing cyan optic sensors,
    metallic brow visor bar, antenna mount, and chin chassis.
    Returns RGBA bytearray (size * size * 4).
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

    # Draw Johnny 5 Features
    # Top antenna / laser mount: x: 15..17, y: 2..5
    for y in range(int(2 * scale), int(6 * scale)):
        for x in range(int(15 * scale), int(18 * scale)):
            set_pixel(x, y, 6, 182, 212, 255) # Glowing cyan
    set_pixel(int(16 * scale), int(2 * scale), 244, 63, 94, 255) # Red sensor dot

    # Forehead visor bar / brow (metallic plate)
    for y in range(int(6 * scale), int(10 * scale)):
        for x in range(int(7 * scale), int(26 * scale)):
            # Shading
            lum = 180 if y == int(6 * scale) else 140
            set_pixel(x, y, lum, lum + 10, lum + 25, 255)

    # Binocular Eye Housings
    # Left eye center: (11, 15), Right eye center: (21, 15), Radius: 5.2
    eye_radius = 5.2 * scale
    left_cx, left_cy = 11.0 * scale, 15.5 * scale
    right_cx, right_cy = 21.0 * scale, 15.5 * scale

    for y in range(int(10 * scale), int(22 * scale)):
        for x in range(int(4 * scale), int(28 * scale)):
            d_left = math.hypot(x - left_cx, y - left_cy)
            d_right = math.hypot(x - right_cx, y - right_cy)

            # Left Eye
            if d_left <= eye_radius:
                if d_left > eye_radius - 1.2:
                    # Metal rim
                    set_pixel(x, y, 71, 85, 105, 255) # Slate dark
                elif d_left > eye_radius - 2.2:
                    # Outer cyan glow
                    set_pixel(x, y, 8, 145, 178, 255) # Deep cyan
                elif d_left > 1.5 * scale:
                    # Vibrant neon cyan iris
                    set_pixel(x, y, 6, 182, 212, 255) # Cyan
                else:
                    # Bright center optic lens / glint
                    set_pixel(x, y, 224, 242, 254, 255) # Pure white/light cyan

            # Right Eye
            if d_right <= eye_radius:
                if d_right > eye_radius - 1.2:
                    set_pixel(x, y, 71, 85, 105, 255)
                elif d_right > eye_radius - 2.2:
                    set_pixel(x, y, 8, 145, 178, 255)
                elif d_right > 1.5 * scale:
                    set_pixel(x, y, 6, 182, 212, 255)
                else:
                    set_pixel(x, y, 224, 242, 254, 255)

    # Eye Bridge
    for y in range(int(14 * scale), int(17 * scale)):
        for x in range(int(15 * scale), int(18 * scale)):
            set_pixel(x, y, 100, 116, 139, 255)

    # Lower chassis / chin grill
    for y in range(int(22 * scale), int(29 * scale)):
        for x in range(int(9 * scale), int(24 * scale)):
            # Taper chin towards bottom
            dx = abs(x - 16 * scale)
            max_w = (28 * scale - y) * 0.8
            if dx <= max_w:
                if y % 2 == 0:
                    set_pixel(x, y, 51, 65, 85, 255) # Dark metal
                else:
                    set_pixel(x, y, 6, 182, 212, 230) # Glowing cyan slot

    return pixels

def _draw_cyber_shield(size: int = 32) -> bytearray:
    """
    Renders transparent dark cyber shield with cyan outline
    and striking neon purple diagonal slash.
    Returns RGBA bytearray.
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

    # Shield geometry
    for y in range(int(4 * scale), int(29 * scale)):
        # Width narrows towards bottom tip at (16, 28)
        if y < 14 * scale:
            half_w = 11.5 * scale
        else:
            prog = (y - 14 * scale) / (14 * scale)
            half_w = (11.5 * scale) * (1.0 - (prog * 0.9))

        left = int(16 * scale - half_w)
        right = int(16 * scale + half_w)

        for x in range(left, right + 1):
            # Check border
            is_border = (x == left or x == right or y == int(4 * scale) or y >= int(27 * scale))
            if is_border:
                # Cyan border
                set_pixel(x, y, 6, 182, 212, 255)
            else:
                # Dark cyber shield body
                set_pixel(x, y, 15, 23, 42, 220)

    # Neon Purple Diagonal Slash (Top Right to Bottom Left)
    # Line from approx (23, 6) to (8, 26)
    x0, y0 = 23.0 * scale, 6.0 * scale
    x1, y1 = 8.0 * scale, 26.0 * scale
    slash_len = math.hypot(x1 - x0, y1 - y0)

    for y in range(int(4 * scale), int(29 * scale)):
        for x in range(int(4 * scale), int(28 * scale)):
            # Distance from point to line segment
            vx, vy = x1 - x0, y1 - y0
            wx, wy = x - x0, y - y0
            c1 = wx * vx + wy * vy
            if c1 <= 0:
                dist = math.hypot(wx, wy)
            elif (vx*vx + vy*vy) <= c1:
                dist = math.hypot(x - x1, y - y1)
            else:
                b = c1 / (vx*vx + vy*vy)
                dist = math.hypot(x - (x0 + b*vx), y - (y0 + b*vy))

            if dist < 2.4 * scale:
                if dist < 0.8 * scale:
                    # White-violet energy core
                    set_pixel(x, y, 243, 232, 255, 255)
                elif dist < 1.6 * scale:
                    # Vivid neon purple
                    set_pixel(x, y, 168, 85, 247, 255)
                else:
                    # Purple glow
                    set_pixel(x, y, 192, 132, 252, 220)

    return pixels

def generate_ico_file(pixels_rgba: bytearray, size: int, output_path: Path):
    """
    Creates a standard Windows .ico file with BITMAPINFOHEADER and 32-bit BGRA pixels.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert RGBA to bottom-to-top BGRA
    bgra = bytearray(size * size * 4)
    for y in range(size):
        src_y = (size - 1 - y) # bottom-to-top
        for x in range(size):
            src_idx = (src_y * size + x) * 4
            dst_idx = (y * size + x) * 4
            r = pixels_rgba[src_idx]
            g = pixels_rgba[src_idx + 1]
            b = pixels_rgba[src_idx + 2]
            a = pixels_rgba[src_idx + 3]
            bgra[dst_idx] = b
            bgra[dst_idx + 1] = g
            bgra[dst_idx + 2] = r
            bgra[dst_idx + 3] = a

    # 1bpp AND mask (all 0 for transparent pixels defined by 32bpp alpha)
    mask = bytearray((size * size) // 8)

    img_size = 40 + len(bgra) + len(mask)
    header = struct.pack('<HHH', 0, 1, 1) # Reserved, ICO type, 1 image
    entry = struct.pack('<BBBBHHII', size, size, 0, 0, 1, 32, img_size, 22)
    bih = struct.pack('<IIIHHIIIIII', 40, size, size * 2, 1, 32, 0, len(bgra), 0, 0, 0, 0)

    ico_bytes = header + entry + bih + bgra + mask
    output_path.write_bytes(ico_bytes)

def ensure_ico_assets():
    """Generates the .ico files in frontend/assets/icons if not present."""
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    johnny5_ico = ICONS_DIR / "app_icon_johnny5.ico"
    shield_ico = ICONS_DIR / "app_icon_shield.ico"

    if not johnny5_ico.exists():
        j5_px = _draw_johnny5_head(32)
        generate_ico_file(j5_px, 32, johnny5_ico)

    if not shield_ico.exists():
        sh_px = _draw_cyber_shield(32)
        generate_ico_file(sh_px, 32, shield_ico)

def get_tray_icon_handle(icon_type: str = "johnny5"):
    """
    Returns a native Win32 HICON handle for the requested icon type ('johnny5' | 'shield').
    """
    if sys.platform != "win32":
        return None

    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        ensure_ico_assets()
        target_ico = ICONS_DIR / (f"app_icon_{icon_type}.ico" if icon_type in ("johnny5", "shield") else "app_icon_johnny5.ico")

        if target_ico.exists():
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x0010
            # Load 16x16 or 32x32 depending on system metrics
            cx = user32.GetSystemMetrics(49) or 16 # SM_CXSMICON
            cy = user32.GetSystemMetrics(50) or 16 # SM_CYSMICON
            hicon = user32.LoadImageW(0, str(target_ico), IMAGE_ICON, cx, cy, LR_LOADFROMFILE)
            if hicon:
                return hicon

        # Fallback to in-memory HICON creation via CreateIconIndirect
        gdi32 = ctypes.windll.gdi32

        class ICONINFO(ctypes.Structure):
            _fields_ = [
                ('fIcon', wintypes.BOOL),
                ('xHotspot', wintypes.DWORD),
                ('yHotspot', wintypes.DWORD),
                ('hbmMask', wintypes.HBITMAP),
                ('hbmColor', wintypes.HBITMAP)
            ]

        size = 32
        px = _draw_cyber_shield(size) if icon_type == "shield" else _draw_johnny5_head(size)

        # Convert to BGRA
        bgra = bytearray(size * size * 4)
        for y in range(size):
            src_y = size - 1 - y
            for x in range(size):
                s_i = (src_y * size + x) * 4
                d_i = (y * size + x) * 4
                bgra[d_i] = px[s_i + 2]
                bgra[d_i + 1] = px[s_i + 1]
                bgra[d_i + 2] = px[s_i]
                bgra[d_i + 3] = px[s_i + 3]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ('biSize', wintypes.DWORD),
                ('biWidth', wintypes.LONG),
                ('biHeight', wintypes.LONG),
                ('biPlanes', wintypes.WORD),
                ('biBitCount', wintypes.WORD),
                ('biCompression', wintypes.DWORD),
                ('biSizeImage', wintypes.DWORD),
                ('biXPelsPerMeter', wintypes.LONG),
                ('biYPelsPerMeter', wintypes.LONG),
                ('biClrUsed', wintypes.DWORD),
                ('biClrImportant', wintypes.DWORD)
            ]

        bmi = BITMAPINFOHEADER(40, size, size, 1, 32, 0, size * size * 4, 0, 0, 0, 0)
        hdc = user32.GetDC(0)
        p_bits = ctypes.c_void_p()
        hbm_color = gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(p_bits), 0, 0)
        user32.ReleaseDC(0, hdc)

        if hbm_color and p_bits:
            ctypes.memmove(p_bits, bytes(bgra), len(bgra))
            hbm_mask = gdi32.CreateBitmap(size, size, 1, 1, None)
            ii = ICONINFO(True, 0, 0, hbm_mask, hbm_color)
            hicon = user32.CreateIconIndirect(ctypes.byref(ii))
            gdi32.DeleteObject(hbm_mask)
            gdi32.DeleteObject(hbm_color)
            return hicon

    except Exception as e:
        print(f"[WARN] Failed to create custom tray icon: {e}")

    # Fallback to standard app icon if all else fails
    try:
        return ctypes.windll.user32.LoadIconW(None, 32512)
    except Exception:
        return None
