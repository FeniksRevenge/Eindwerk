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



# --------------------------------------------------------------------------- Windows HDR
# dxcam gives wrong colors while Windows HDR is on, so the bot turns HDR off while it runs and back on
# when it stops (Windows' DisplayConfig API: the same switch as Settings > Display > Use HDR).
if IS_WINDOWS:
    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class PATH_SOURCE(ctypes.Structure):
        _fields_ = [("adapterId", LUID), ("id", ctypes.c_uint32), ("modeInfoIdx", ctypes.c_uint32),
                    ("statusFlags", ctypes.c_uint32)]

    class RATIONAL(ctypes.Structure):
        _fields_ = [("Numerator", ctypes.c_uint32), ("Denominator", ctypes.c_uint32)]

    class PATH_TARGET(ctypes.Structure):
        _fields_ = [("adapterId", LUID), ("id", ctypes.c_uint32), ("modeInfoIdx", ctypes.c_uint32),
                    ("outputTechnology", ctypes.c_uint32), ("rotation", ctypes.c_uint32),
                    ("scaling", ctypes.c_uint32), ("refreshRate", RATIONAL), ("scanLineOrdering", ctypes.c_uint32),
                    ("targetAvailable", wintypes.BOOL), ("statusFlags", ctypes.c_uint32)]

    class PATH_INFO(ctypes.Structure):
        _fields_ = [("sourceInfo", PATH_SOURCE), ("targetInfo", PATH_TARGET), ("flags", ctypes.c_uint32)]

    class MODE_INFO(ctypes.Structure):
        _fields_ = [("infoType", ctypes.c_uint32), ("id", ctypes.c_uint32), ("adapterId", LUID),
                    ("data", ctypes.c_byte * 48)]

    class INFO_HEADER(ctypes.Structure):
        _fields_ = [("type", ctypes.c_uint32), ("size", ctypes.c_uint32), ("adapterId", LUID), ("id", ctypes.c_uint32)]

    class GET_ADVANCED_COLOR(ctypes.Structure):
        _fields_ = [("header", INFO_HEADER), ("value", ctypes.c_uint32), ("colorEncoding", ctypes.c_uint32),
                    ("bitsPerColorChannel", ctypes.c_uint32)]

    class SET_ADVANCED_COLOR(ctypes.Structure):
        _fields_ = [("header", INFO_HEADER), ("value", ctypes.c_uint32)]

_hdr_turned_off = []  # displays the bot switched HDR off on (to switch back on later)


def _displays():
    n_paths, n_modes = ctypes.c_uint32(), ctypes.c_uint32()
    if user32.GetDisplayConfigBufferSizes(2, ctypes.byref(n_paths), ctypes.byref(n_modes)) != 0:  # active paths
        return []
    paths, modes = (PATH_INFO * n_paths.value)(), (MODE_INFO * n_modes.value)()
    if user32.QueryDisplayConfig(2, ctypes.byref(n_paths), paths, ctypes.byref(n_modes), modes, None) != 0:
        return []
    return [(p.targetInfo.adapterId, p.targetInfo.id) for p in paths[:n_paths.value]]


def _hdr_on(adapter, target):
    info = GET_ADVANCED_COLOR()
    info.header.type, info.header.size = 9, ctypes.sizeof(GET_ADVANCED_COLOR)  # GET_ADVANCED_COLOR_INFO
    info.header.adapterId, info.header.id = adapter, target
    if user32.DisplayConfigGetDeviceInfo(ctypes.byref(info)) != 0:
        return False
    return bool(info.value & 0x2)  # advancedColorEnabled


def _set_hdr(adapter, target, on):
    s = SET_ADVANCED_COLOR()
    s.header.type, s.header.size = 10, ctypes.sizeof(SET_ADVANCED_COLOR)  # SET_ADVANCED_COLOR_STATE
    s.header.adapterId, s.header.id = adapter, target
    s.value = 1 if on else 0
    return user32.DisplayConfigSetDeviceInfo(ctypes.byref(s)) == 0


def hdr_off():
    """Turn Windows HDR off on every display that has it on. Returns how many were switched."""
    if not IS_WINDOWS:
        return 0
    n = 0
    try:
        for adapter, target in _displays():
            if _hdr_on(adapter, target) and _set_hdr(adapter, target, False):
                _hdr_turned_off.append((adapter, target))
                n += 1
    except Exception:
        pass
    return n


def hdr_restore():
    """Turn HDR back on where the bot turned it off."""
    while _hdr_turned_off:
        adapter, target = _hdr_turned_off.pop()
        try:
            _set_hdr(adapter, target, True)
        except Exception:
            pass


import atexit  # noqa: E402
atexit.register(hdr_restore)

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
def fit_color_lut(dx, ref):
    """Per-channel color fix from dxcam pixels to normal-screenshot pixels (N x 3 each, same spots).
    Returns (lut 256x3 or None, mean error on colored pixels after the fix, number of colored pixels).
    Pixels that changed between the two pictures (moving things) are outliers; medians ignore them."""
    colored = ref.max(axis=1) > 40
    n = int(colored.sum())
    if n < 2000:
        return None, 0.0, n
    lut = np.zeros((256, 3), np.uint8)
    for c in range(3):
        x, y = dx[:, c].astype(np.int32), ref[:, c].astype(np.float32)
        med = np.full(256, np.nan, np.float32)
        counts = np.bincount(x, minlength=256)
        ys = y[np.argsort(x, kind="stable")]
        starts = np.concatenate([[0], np.cumsum(counts)])
        for v in np.nonzero(counts >= 5)[0]:
            med[v] = np.median(ys[starts[v]:starts[v + 1]])
        known = np.nonzero(~np.isnan(med))[0]
        if len(known) < 2:
            return None, 0.0, n
        full = np.interp(np.arange(256), known, med[known])
        lut[:, c] = np.clip(np.maximum.accumulate(full), 0, 255).astype(np.uint8)  # keep it increasing
    fixed = lut[dx, np.arange(3)]
    both = colored & (fixed.max(axis=1) > 40)  # colored in both (things that moved in between aren't)
    diff = np.abs(fixed.astype(np.int16) - ref.astype(np.int16)).max(axis=1)[both]
    err = float(np.median(diff)) if len(diff) else 0.0
    return lut, err, n


def apply_color_lut(frame, lut):
    if lut is None:
        return frame
    import cv2
    return cv2.LUT(frame, lut.reshape(256, 1, 3))

class Capture:
    """Screenshots of the Roblox window's inside on a background thread. A new one is taken as soon as
    the bot took the previous one, so the bot always gets a fresh picture without waiting long.
    Uses dxcam (Windows' fast Desktop Duplication, a few ms per picture) when it works, else mss."""

    def __init__(self, fast=True):
        self.frame, self.frame_time, self.area, self.seq = None, 0.0, None, 0
        self.hwnd = None
        self.fast = fast
        self.method = "mss"
        self.note = ""
        self.hdr_note = ""
        self.cond = threading.Condition()
        self.taken = threading.Event()
        self.stop = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _open_dxcam(self, sct, area):
        switched = hdr_off()
        if switched:
            self.hdr_note = f"Windows HDR turned off while the bot runs ({switched} display(s)); it's turned back on when you stop."
            time.sleep(1.5)  # the screen flickers while it switches
        return self._open_dxcam_checked(sct, area)

    def _open_dxcam_checked(self, sct, area):
        """(camera, color fix) if dxcam works, or (None, None). dxcam can give different colors than
        a normal screenshot (HDR, color profiles): it learns a per-channel color fix from a dxcam
        picture and a normal screenshot of the same moment, and only uses dxcam if that fix makes
        them match."""
        try:
            import dxcam
            cam = dxcam.create(output_color="BGR")
        except Exception as e:
            self.note = f"fast capture (dxcam) not available ({e}); using mss"
            return None, None
        if cam is None:
            return None, None
        box = (area["left"], area["top"], area["left"] + area["width"], area["top"] + area["height"])
        pairs = []
        for _ in range(300):  # a few pairs with enough colored things on screen
            try:
                img = cam.grab(region=box)
            except Exception as e:
                self.note = f"fast capture (dxcam) can't capture the Roblox window ({e}); using mss"
                return None, None
            if img is None:
                time.sleep(0.01)
                continue
            ref = np.ascontiguousarray(np.asarray(sct.grab(area))[:, :, :3])
            if img.shape[:2] != ref.shape[:2]:
                self.note = "fast capture (dxcam) gave a different size; using mss"
                return None, None
            pairs.append((np.ascontiguousarray(img[:, :, :3]), ref))
            if len(pairs) >= 3:
                break
            time.sleep(0.05)
        if not pairs:
            self.note = "fast capture (dxcam) gave no pictures; using mss"
            return None, None
        dx = np.concatenate([p[0].reshape(-1, 3) for p in pairs])
        ref = np.concatenate([p[1].reshape(-1, 3) for p in pairs])
        lut, err, n = fit_color_lut(dx, ref)
        if lut is None:
            self.note = f"fast capture (dxcam): can't check its colors (only {n} colored pixels); using mss"
            return None, None
        ident = np.arange(256)[:, None]
        shift = int(np.abs(lut[30:241].astype(int) - ident[30:241]).max())
        if err > 8 or shift > 12:
            # colors still differ (HDR couldn't be switched off?): use dxcam anyway, with the color fix
            self.note = (f"fast capture (dxcam) on, but its colors differ from a normal screenshot (shift {shift}, "
                         f"error {err:.0f}); is Windows HDR still on? If the bot can't see you, turn HDR off.")
            return cam, lut
        self.note = f"fast capture (dxcam) on, colors checked (shift {shift})"
        return cam, None

    def _run(self):
        import mss
        sct = mss.mss()
        cam, cam_area, lut = None, None, None
        next_find, area, last_frame, last_new = 0.0, None, None, 0.0
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
            if self.fast and cam is None and cam_area is None:
                cam, lut = self._open_dxcam(sct, area)  # tried once; mss if it doesn't work
                self.method = "dxcam" if cam else "mss"
            cam_area = dict(area)
            try:
                t = time.perf_counter()
                frame = None
                if cam is not None and cam_area == area:
                    box = (area["left"], area["top"], area["left"] + area["width"], area["top"] + area["height"])
                    img = cam.grab(region=box)
                    if img is not None:
                        frame = apply_color_lut(np.ascontiguousarray(img[:, :, :3]), lut)
                    elif last_frame is not None and t - last_new < 0.15:
                        time.sleep(0.003)  # nothing changed on screen yet
                        continue
                if frame is None:
                    frame = np.ascontiguousarray(np.asarray(sct.grab(area))[:, :, :3])
                last_frame, last_new = frame, t
            except Exception:
                if cam is not None:  # dxcam stopped working (window moved off screen...): mss from now on
                    cam, self.method = None, "mss"
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
        hdr_restore()


# --------------------------------------------------------------------------- the bot's hands
def keep_awake(on):
    """While the bot runs: don't let Windows sleep or turn the screen off (screen capture stops then)."""
    try:
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x1, 0x2
        flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED if on else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))
    except Exception:
        pass


class WindowsIO:
    """What the bot runner talks to: screenshots in, keys and mouse out (in window coordinates)."""

    def __init__(self, require_focus=True, fast_capture=True):
        keep_awake(True)
        self.require_focus = require_focus
        self.capture = Capture(fast_capture)
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
        keep_awake(False)
