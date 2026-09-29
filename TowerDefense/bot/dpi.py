"""
Windows display scaling (125%, 150%, ...) makes unaware programs see a smaller, "fake" screen, so a
screenshot would only cover part of it. Importing this module first switches the app to real pixels.
"""

import ctypes
import os


def make_dpi_aware():
    if os.name != "nt":
        return
    try:  # Windows 10 1703+: per-monitor v2
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:  # Windows 8.1+
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def primary_screen_pixels():
    """Real resolution of the main screen (not affected by display scaling), or None."""
    if os.name != "nt":
        return None
    try:
        user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
        hdc = user32.GetDC(0)
        w, h = gdi32.GetDeviceCaps(hdc, 118), gdi32.GetDeviceCaps(hdc, 117)  # DESKTOPHORZRES/VERTRES
        user32.ReleaseDC(0, hdc)
        return (w, h) if w > 0 and h > 0 else None
    except Exception:
        return None


make_dpi_aware()
