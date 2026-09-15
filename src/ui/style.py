"""Windows 11 Fluent styling from the user's own system settings.

Only named widgets are restyled. A blanket QWidget background rule would replace
the native windows11 rendering everywhere and paint a box behind every label.
Colours come from the registry, so the window matches the user's accent and
light/dark choice.
"""

from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

logger = logging.getLogger(__name__)

FONT_DISPLAY = '"Segoe UI Variable Display Semibold", "Segoe UI Semibold", sans-serif'
FONT_BODY = '"Segoe UI Variable Text", "Segoe UI", sans-serif'
FONT_STRONG = '"Segoe UI Variable Text Semibold", "Segoe UI Semibold", sans-serif'
FONT_SMALL = '"Segoe UI Variable Small", "Segoe UI", sans-serif'


def _registry(path: str, name: str):
    if sys.platform != "win32":
        return None
    try:
        import winreg

        return winreg.QueryValueEx(winreg.OpenKey(winreg.HKEY_CURRENT_USER, path), name)[0]
    except Exception:
        logger.debug("could not read HKCU\\%s\\%s", path, name, exc_info=True)
        return None


def _blend(fg: str, bg: str, alpha: float) -> str:
    """Composite fg over bg. Fluent draws hover/pressed as the accent at reduced opacity."""
    f = [int(fg[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * alpha + y * (1 - alpha)):02X}" for x, y in zip(f, b))


def system_palette() -> SimpleNamespace:
    # AccentPalette is eight RGBx shades, light to dark: [1]=Light2, [4]=Dark1.
    # WinUI fills accent buttons with Dark1 in light mode and Light2 in dark mode.
    blob = _registry(r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent", "AccentPalette")
    shades = [f"#{blob[i]:02X}{blob[i + 1]:02X}{blob[i + 2]:02X}" for i in range(0, 32, 4)] if blob and len(blob) >= 32 else None
    light = _registry(r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "AppsUseLightTheme")
    if light is None or light:
        p = SimpleNamespace(
            window="#F3F3F3", card="#FFFFFF", card_hover="#F9F9F9", stroke="#E5E5E5",
            text="#1A1A1A", text2="#5D5D5D", control="#FDFDFD", control_hover="#F5F5F5",
            control_stroke="#DCDCDC", accent=shades[4] if shades else "#005FB8", on_accent="#FFFFFF",
        )
    else:
        p = SimpleNamespace(
            window="#202020", card="#2B2B2B", card_hover="#323232", stroke="#353535",
            text="#FFFFFF", text2="#C8C8C8", control="#2D2D2D", control_hover="#353535",
            control_stroke="#3A3A3A", accent=shades[1] if shades else "#60CDFF",
            on_accent="#000000",  # black text on a bright accent in dark mode, as WinUI does
        )
    p.accent_hover = _blend(p.accent, p.window, 0.90)
    p.accent_pressed = _blend(p.accent, p.window, 0.80)
    return p


def build_stylesheet(p: SimpleNamespace) -> str:
    return f"""
#root {{ background: {p.window}; }}
QLabel {{ background: transparent; color: {p.text}; }}
QScrollArea, #listHost {{ background: transparent; border: none; }}

#title {{ font-family: {FONT_DISPLAY}; font-size: 20px; }}
#deviceName, #emptyTitle {{ font-family: {FONT_STRONG}; font-size: 14px; }}
#subtitle, #deviceMeta, #emptyHint {{ font-family: {FONT_SMALL}; font-size: 12px; color: {p.text2}; }}
/* No font on the icons: a QSS font-family overrides the QFont set in code. */
#deviceIcon {{ color: {p.accent}; }}
#emptyIcon {{ color: {p.text2}; }}

#card, #emptyCard, #updateBar {{ background: {p.card}; border: 1px solid {p.stroke}; border-radius: 8px; }}
#card:hover {{ background: {p.card_hover}; }}

/* Fluent buttons: 32px tall, 4px radius, regular weight. */
QPushButton {{
    background: {p.control}; color: {p.text};
    border: 1px solid {p.control_stroke}; border-radius: 4px;
    padding: 5px 12px; min-height: 20px;
    font-family: {FONT_BODY}; font-size: 14px;
}}
QPushButton:hover {{ background: {p.control_hover}; }}
#primary {{ background: {p.accent}; color: {p.on_accent}; border-color: {p.accent}; padding: 5px 16px; }}
#primary:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
#primary:pressed {{ background: {p.accent_pressed}; border-color: {p.accent_pressed}; }}
#primary:disabled {{ background: {p.control}; color: {p.text2}; border-color: {p.control_stroke}; }}

QToolTip {{
    background: {p.card}; color: {p.text}; border: 1px solid {p.stroke};
    border-radius: 4px; padding: 6px 8px; font-family: {FONT_BODY}; font-size: 12px;
}}
"""
