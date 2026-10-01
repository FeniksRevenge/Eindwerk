"""
Windows side of the bot: find the Roblox window, take screenshots of its inside, press keys and move
the mouse. Everything else (seeing, deciding) is platform independent and lives in the other files.

Keys are sent as *scancodes* (physical key positions), so on an AZERTY keyboard the bot presses the keys
in the W A S D positions, which are Z Q S D, exactly what you use yourself.
"""

import ctypes
import os
import threading
import time

import numpy as np

IS_WINDOWS = os.name == "nt"


def make_dpi_aware():
    """With Windows display scaling (125%, 150%...) an unaware program sees fake, smaller coordinates.
    Real pixels everywhere: screenshots, window positions and mouse moves then all agree."""
    if not IS_WINDOWS:
        return
    for attempt in (lambda: ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)),
                    lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),
                    lambda: ctypes.windll.user32.SetProcessDPIAware()):
        try:
            if attempt():
                return
        except Exception:
            pass


make_dpi_aware()

# Physical key positions (QWERTY W A S D = AZERTY Z Q S D) and Space.
SCANCODES = {"up": 0x11, "left": 0x1E, "down": 0x1F, "right": 0x20, "space": 0x39}

if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                    ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ushort), ("wParamH", ctypes.c_ushort)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("u", _INPUTUNION)]

    user32.FindWindowW.restype = wintypes.HWND
    user32.GetForegroundWindow.restype = wintypes.HWND

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x0002, 0x0008
MOUSEEVENTF_MOVE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0001, 0x0002, 0x0004
MOUSEEVENTF_VIRTUALDESK, MOUSEEVENTF_ABSOLUTE = 0x4000, 0x8000


def _send(inp):
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def press(name, down):
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.u.ki = KEYBDINPUT(0, SCANCODES[name], KEYEVENTF_SCANCODE | (0 if down else KEYEVENTF_KEYUP), 0, 0)
    _send(inp)


def mouse_to(x, y):
    """Absolute mouse move to screen pixel (x, y), over the whole virtual desktop."""
    vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
    vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
    inp = INPUT(type=INPUT_MOUSE)
    inp.u.mi = MOUSEINPUT(int((x - vx) * 65535 / max(1, vw - 1)), int((y - vy) * 65535 / max(1, vh - 1)), 0,
                          MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, 0, 0)
    _send(inp)


def mouse_button(down):
    inp = INPUT(type=INPUT_MOUSE)
    inp.u.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP, 0, 0)
    _send(inp)


# --------------------------------------------------------------------------- the Roblox window
def find_roblox():
    """(hwnd, area) of the Roblox window. area = {"left", "top", "width", "height"}: its inside (no title
    bar or borders) in screen pixels, or None when it's minimized. (None, None) when Roblox isn't open."""
    if not IS_WINDOWS:
        return None, None
    hwnd = user32.FindWindowW(None, "Roblox")
    if not hwnd:
        return None, None
    if user32.IsIconic(hwnd):
        return hwnd, None
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    if rect.right < 200 or rect.bottom < 200:
        return hwnd, None
    return hwnd, {"left": pt.x, "top": pt.y, "width": rect.right, "height": rect.bottom}


def foreground_is(hwnd):
    return bool(hwnd) and user32.GetForegroundWindow() == hwnd


# --------------------------------------------------------------------------- screenshots
class Capture:
    """Screenshots of the Roblox window's inside on a background thread. A new one is taken as soon as
    the bot took the previous one, so the bot always gets a fresh picture without waiting long."""

    def __init__(self):
        self.frame, self.frame_time, self.area, self.seq = None, 0.0, None, 0
        self.hwnd = None
        self.cond = threading.Condition()
        self.taken = threading.Event()
        self.stop = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        import mss
        sct = mss.mss()
        next_find = 0.0
        area = None
        while not self.stop.is_set():
            now = time.perf_counter()
            if now >= next_find:  # the window may have moved or been resized
                self.hwnd, area = find_roblox()
                next_find = now + 1.0
            if area is None:
                with self.cond:
                    self.frame, self.area = None, None
                    self.seq += 1
                    self.cond.notify_all()
                time.sleep(0.2)
                continue
            try:
                t = time.perf_counter()
                frame = np.ascontiguousarray(np.asarray(sct.grab(area))[:, :, :3])
            except Exception:
                next_find = 0.0
                time.sleep(0.05)
                continue
            with self.cond:
                self.frame, self.frame_time, self.area = frame, t, dict(area)
                self.seq += 1
                self.cond.notify_all()
            self.taken.wait(0.03)
            self.taken.clear()

    def latest(self, after_seq):
        """(frame, time taken, window area, seq): waits up to 0.1 s for a frame newer than after_seq.
        frame is None when the Roblox window isn't found."""
        with self.cond:
            self.cond.wait_for(lambda: self.seq > after_seq, timeout=0.1)
            out = self.frame, self.frame_time, self.area, self.seq
        self.taken.set()
        return out

    def close(self):
        self.stop.set()
        self.taken.set()


# --------------------------------------------------------------------------- the bot's hands
class WindowsIO:
    """What the bot runner talks to: screenshots in, keys and mouse out (in window coordinates)."""

    def __init__(self, require_focus=True):
        self.require_focus = require_focus
        self.capture = Capture()
        self.seq = 0
        self.frame_time = 0.0
        self.area = None
        self.held = set()
        self.firing = False

    def grab(self):
        frame, self.frame_time, self.area, self.seq = self.capture.latest(self.seq)
        return frame

    def now(self):
        return time.perf_counter()

    def focused(self):
        return (not self.require_focus) or foreground_is(self.capture.hwnd)

    def set_keys(self, keys):
        keys = set(keys)
        for k in self.held - keys:
            press(k, False)
        for k in keys - self.held:
            press(k, True)
        self.held = keys

    def fire(self, on):
        if on != self.firing:
            press("space", on)
            self.firing = on

    def aim(self, x, y):
        if self.area:
            mouse_to(self.area["left"] + x, self.area["top"] + y)

    def click(self, x, y):
        if not self.area:
            return
        mouse_to(self.area["left"] + x, self.area["top"] + y)
        time.sleep(0.08)
        mouse_button(True)
        time.sleep(0.06)
        mouse_button(False)

    def release(self):
        self.set_keys(())
        self.fire(False)

    def close(self):
        self.release()
        self.capture.close()
