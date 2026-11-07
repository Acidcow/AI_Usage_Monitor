"""
Canonical Theme & Layout Density Engine Contracts (AIUM-1008)
Zero-dependency definitions for ultra-modern selectable themes,
density configurations, provider color palette, and WCAG AA contrast calculations.
"""

from typing import Dict, Any, List, Optional

CANONICAL_THEME_IDS = [
    "linear-obsidian",
    "geist-monochrome",
    "cyberpunk-hud",
    "catppuccin-mocha",
    "tokyo-night",
    "executive-paper",
]

THEME_ALIASES: Dict[str, str] = {
    # Legacy web UI aliases
    "cyberpunk_dark": "cyberpunk-hud",
    "glass_slate": "linear-obsidian",
    "high_contrast_light": "executive-paper",
    "matrix_emerald": "geist-monochrome",
    # Legacy native widget / tray aliases
    "obsidian_neon": "linear-obsidian",
    "cyberpunk": "cyberpunk-hud",
    "midnight_slate": "tokyo-night",
}

LAYOUT_DENSITIES: List[str] = [
    "compact",
    "balanced",
    "ultrawide",
]

LAYOUT_DENSITY_CONFIGS: Dict[str, Dict[str, Any]] = {
    "compact": {
        "id": "compact",
        "name": "Compact Density",
        "card_padding": "10px 14px",
        "gap": "8px",
        "font_scale": 0.92,
        "description": "High-density data view with tight paddings and maximized screen real estate",
    },
    "balanced": {
        "id": "balanced",
        "name": "Balanced Density",
        "card_padding": "18px 20px",
        "gap": "16px",
        "font_scale": 1.0,
        "description": "Default comfortable layout with balanced spacing and readable typography",
    },
    "ultrawide": {
        "id": "ultrawide",
        "name": "Ultrawide / Expanded",
        "card_padding": "24px 28px",
        "gap": "24px",
        "font_scale": 1.05,
        "description": "Spacious layout optimized for wide monitors and dashboard multi-column arrays",
    },
}

PROVIDER_PALETTE: Dict[str, str] = {
    "claude": "#F59E0B",
    "ollama": "#10B981",
    "gemini": "#3B82F6",
    "copilot": "#8B5CF6",
    "chatgpt": "#10B981",
}


def calculate_relative_luminance(hex_color: str) -> float:
    """
    Calculates the relative luminance of an sRGB hex color according to WCAG 2.1 specs.
    Returns float in range [0.0, 1.0].
    """
    hex_clean = hex_color.lstrip("#").strip()
    if len(hex_clean) == 3:
        hex_clean = "".join(c * 2 for c in hex_clean)
    if len(hex_clean) != 6:
        raise ValueError(f"Invalid hex color format: {hex_color}")

    r = int(hex_clean[0:2], 16) / 255.0
    g = int(hex_clean[2:4], 16) / 255.0
    b = int(hex_clean[4:6], 16) / 255.0

    def _to_linear(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _to_linear(r) + 0.7152 * _to_linear(g) + 0.0722 * _to_linear(b)


def calculate_contrast_ratio(hex1: str, hex2: str) -> float:
    """
    Calculates the WCAG contrast ratio between two hex colors.
    Returns ratio from 1.0 to 21.0.
    """
    l1 = calculate_relative_luminance(hex1)
    l2 = calculate_relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def meets_wcag_aa(hex_foreground: str, hex_background: str, is_large_text: bool = False) -> bool:
    """
    Verifies if contrast ratio meets WCAG AA criteria (>= 4.5:1 for normal text, >= 3.0:1 for large text).
    """
    ratio = calculate_contrast_ratio(hex_foreground, hex_background)
    threshold = 3.0 if is_large_text else 4.5
    return ratio >= threshold


class ThemeDict(dict):
    """
    Subclass of dict providing attribute access and convenience methods for themes.
    Fully JSON-serializable and backward-compatible with standard dictionary lookups.
    """
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'ThemeDict' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def to_dict(self) -> Dict[str, Any]:
        return dict(self)


def _build_theme(
    theme_id: str,
    name: str,
    mode: str,
    bg_main: str,
    bg_card: str,
    accent_primary: str,
    text_main: str,
    text_muted: str,
    text_dim: str,
    border_color: str,
    accent2: str,
    success: str,
    danger: str,
    font_family: str = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
) -> ThemeDict:
    return ThemeDict({
        "id": theme_id,
        "name": name,
        "mode": mode,
        "bg_main": bg_main,
        "bg_card": bg_card,
        "accent_primary": accent_primary,
        "text_main": text_main,
        "text_muted": text_muted,
        "text_dim": text_dim,
        "border_color": border_color,
        "font_family": font_family,
        # Native widget and legacy compatibility keys:
        "bg": bg_main,
        "container_bg": bg_card,
        "card_bg": bg_card,
        "header_bg": bg_card,
        "border": border_color,
        "text": text_main,
        "subtext": text_muted,
        "accent": accent_primary,
        "cyan": accent_primary,
        "accent2": accent2,
        "success": success,
        "danger": danger,
        "strip_bg": bg_main,
    })


# 1. Linear Obsidian (Default Modern Dark)
_LINEAR_OBSIDIAN = _build_theme(
    theme_id="linear-obsidian",
    name="Linear Obsidian",
    mode="Dark",
    bg_main="#090A0F",
    bg_card="#12141C",
    accent_primary="#5E6AD2",
    text_main="#F3F4F6",
    text_muted="#9CA3AF",
    text_dim="#8B95A5",
    border_color="#1F2430",
    accent2="#8B5CF6",
    success="#10B981",
    danger="#F43F5E",
)

# 2. Vercel Geist Monochrome (Dark OLED)
_GEIST_MONOCHROME = _build_theme(
    theme_id="geist-monochrome",
    name="Vercel Geist Monochrome",
    mode="Dark OLED",
    bg_main="#000000",
    bg_card="#0A0A0A",
    accent_primary="#00E599",
    text_main="#FFFFFF",
    text_muted="#A1A1AA",
    text_dim="#8E8E98",
    border_color="#27272A",
    accent2="#52525B",
    success="#00E599",
    danger="#EF4444",
)

# 3. Cyberpunk Neo-HUD (Dark Tactical)
_CYBERPUNK_HUD = _build_theme(
    theme_id="cyberpunk-hud",
    name="Cyberpunk Neo-HUD",
    mode="Dark Tactical",
    bg_main="#07090E",
    bg_card="#0D121F",
    accent_primary="#00F0FF",
    text_main="#E2F1FF",
    text_muted="#7C9CBF",
    text_dim="#6989AC",
    border_color="#1B2A4A",
    accent2="#F43F5E",
    success="#00F0FF",
    danger="#FF0055",
)

# 4. Catppuccin Mocha (Warm Dark)
_CATPPUCCIN_MOCHA = _build_theme(
    theme_id="catppuccin-mocha",
    name="Catppuccin Mocha",
    mode="Warm Dark",
    bg_main="#1E1E2E",
    bg_card="#181825",
    accent_primary="#CBA6F7",
    text_main="#CDD6F4",
    text_muted="#A6ADC8",
    text_dim="#9399B2",
    border_color="#313244",
    accent2="#F5C2E7",
    success="#A6E3A1",
    danger="#F38BA8",
)

# 5. Tokyo Night Storm (Oceanic Dark)
_TOKYO_NIGHT = _build_theme(
    theme_id="tokyo-night",
    name="Tokyo Night Storm",
    mode="Oceanic Dark",
    bg_main="#1A1B26",
    bg_card="#24283B",
    accent_primary="#7AA2F7",
    text_main="#C0CAF5",
    text_muted="#9AA5CE",
    text_dim="#828BB8",
    border_color="#3B4261",
    accent2="#BB9AF7",
    success="#9ECE6A",
    danger="#F7768E",
)

# 6. Executive Paper (Daylight High-Contrast Light)
_EXECUTIVE_PAPER = _build_theme(
    theme_id="executive-paper",
    name="Executive Paper (Daylight)",
    mode="High-Contrast Light",
    bg_main="#F8FAFC",
    bg_card="#FFFFFF",
    accent_primary="#2563EB",
    text_main="#0F172A",
    text_muted="#475569",
    text_dim="#64748B",
    border_color="#E2E8F0",
    accent2="#4F46E5",
    success="#16A34A",
    danger="#DC2626",
)

# Canonical and Aliased Catalog
THEMES_CATALOG: Dict[str, ThemeDict] = {
    # 6 Canonical themes
    "linear-obsidian": _LINEAR_OBSIDIAN,
    "geist-monochrome": _GEIST_MONOCHROME,
    "cyberpunk-hud": _CYBERPUNK_HUD,
    "catppuccin-mocha": _CATPPUCCIN_MOCHA,
    "tokyo-night": _TOKYO_NIGHT,
    "executive-paper": _EXECUTIVE_PAPER,
    # Backward compatibility aliases
    "cyberpunk_dark": _CYBERPUNK_HUD,
    "glass_slate": _LINEAR_OBSIDIAN,
    "high_contrast_light": _EXECUTIVE_PAPER,
    "matrix_emerald": _GEIST_MONOCHROME,
    "obsidian_neon": _LINEAR_OBSIDIAN,
    "cyberpunk": _CYBERPUNK_HUD,
    "midnight_slate": _TOKYO_NIGHT,
}


def resolve_theme_id(theme_id: Optional[str]) -> str:
    """
    Normalizes a theme ID or legacy alias to a canonical theme ID.
    Defaults to 'linear-obsidian' if theme_id is unrecognized or None.
    """
    if not theme_id:
        return "linear-obsidian"
    normalized = str(theme_id).strip().lower().replace(" ", "-")
    if normalized in THEME_ALIASES:
        return THEME_ALIASES[normalized]
    if normalized in THEMES_CATALOG:
        return THEMES_CATALOG[normalized]["id"]
    return "linear-obsidian"


def get_theme(theme_id: Optional[str]) -> ThemeDict:
    """
    Retrieves the ThemeDict for the given theme ID or alias.
    Falls back to 'linear-obsidian' if not found.
    """
    canonical_id = resolve_theme_id(theme_id)
    return THEMES_CATALOG.get(canonical_id, _LINEAR_OBSIDIAN)


def get_all_themes() -> List[ThemeDict]:
    """
    Returns the list of the 6 canonical themes in standard presentation order.
    """
    return [THEMES_CATALOG[tid] for tid in CANONICAL_THEME_IDS]
