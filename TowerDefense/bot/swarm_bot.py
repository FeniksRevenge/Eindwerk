"""
Screen bot for the Roblox arcade swarm game (Windows).

    py swarm_bot.py calibrate          one-time setup: play area + colors of everything
    py swarm_bot.py calibrate boss     redo only some things (keeps the play area)
    py swarm_bot.py view               show what the bot sees, without touching anything
    py swarm_bot.py                    run: * starts, - stops, stops by itself when you die

It reads the screen and presses WASD / moves and holds the mouse like a person would.
It only sends input while the Roblox window is in front.
"""

import ctypes
import json
import os
import sys
import threading
import time

import cv2
import mss
import numpy as np

from runner import BotRunner
from vision import CLASS_HELP, CLASSES, DEFAULT_TOLERANCE, Detector, measure_blob

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")

# Make screen coordinates real pixels even with Windows display scaling (125%, 150%...).
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# --------------------------------------------------------------------------- Windows input
if os.name == "nt":
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

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x0002, 0x0008
MOUSEEVENTF_MOVE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0001, 0x0002, 0x0004
MOUSEEVENTF_VIRTUALDESK, MOUSEEVENTF_ABSOLUTE = 0x4000, 0x8000
SCANCODES = {"w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20}


def _send(inp):
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def key(name, down):
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.u.ki = KEYBDINPUT(0, SCANCODES[name], KEYEVENTF_SCANCODE | (0 if down else KEYEVENTF_KEYUP), 0, 0)
    _send(inp)


def mouse_move(x, y):
    # Absolute move over the whole virtual desktop (works with multiple monitors).
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


def roblox_in_front():
    hwnd = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return "roblox" in buf.value.lower()


class WindowsIO:
    def __init__(self, region, require_focus=True):
        self.region = region  # {"left", "top", "width", "height"} in screen pixels
        self.require_focus = require_focus
        self.sct = mss.mss()
        self.keys = set()
        self.down = False

    def grab(self):
        return np.ascontiguousarray(np.asarray(self.sct.grab(self.region))[:, :, :3])

    def set_keys(self, keys):
        keys = set(keys)
        for k in self.keys - keys:
            key(k, False)
        for k in keys - self.keys:
            key(k, True)
        self.keys = keys

    def aim(self, x, y):
        mouse_move(self.region["left"] + x, self.region["top"] + y)

    def mouse(self, down):
        if down != self.down:
            mouse_button(down)
            self.down = down

    def focused(self):
        return roblox_in_front() if self.require_focus else True

    def now(self):
        return time.perf_counter()


# --------------------------------------------------------------------------- config
def load_config():
    if not os.path.exists(CONFIG_PATH):
        sys.exit("No config.json yet. Run calibrate.bat (or: py swarm_bot.py calibrate) first.")
    with open(CONFIG_PATH) as f:
        return json.load(f)


def grab_screen(countdown=5):
    for i in range(countdown, 0, -1):
        print(f"  Taking a screenshot in {i}... (switch to Roblox now)")
        time.sleep(1)
    with mss.mss() as sct:
        mon = sct.monitors[0]  # all monitors
        img = np.ascontiguousarray(np.asarray(sct.grab(mon))[:, :, :3])
    return img, mon["left"], mon["top"]


def fit_to_screen(img, max_w=1500, max_h=850):
    s = min(1.0, max_w / img.shape[1], max_h / img.shape[0])
    return cv2.resize(img, (int(img.shape[1] * s), int(img.shape[0] * s)), interpolation=cv2.INTER_AREA), s


def banner(img, text):
    out = img.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1], 34), (0, 0, 0), -1)
    cv2.putText(out, text, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 255, 140), 1, cv2.LINE_AA)
    return out


def calibrate(only):
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    names = only or CLASSES
    for n in names:
        if n not in CLASSES:
            sys.exit(f"Unknown thing '{n}'. Choose from: {', '.join(CLASSES)}")

    print("\nCALIBRATION")
    print("Get the game running in Roblox with as many kinds of mobs on screen as you can.")
    print("Tip: pause the game (P) once they're on screen, then come back here.\n")
    input("Press Enter here, then switch to Roblox within 5 seconds...")
    shot, off_x, off_y = grab_screen()

    win = "Swarm bot calibration"
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)

    if not only or "region" not in cfg:
        disp, s = fit_to_screen(shot)
        print("\nDrag a box around the whole play area, then press Enter (C = cancel).")
        x, y, w, h = cv2.selectROI(win, banner(disp, "Drag a box around the PLAY AREA, then press ENTER"), False, False)
        if w == 0 or h == 0:
            sys.exit("No play area selected, nothing saved.")
        cfg["region"] = {"left": int(x / s) + off_x, "top": int(y / s) + off_y, "width": int(w / s), "height": int(h / s)}

    r = cfg["region"]
    crop = shot[r["top"] - off_y:r["top"] - off_y + r["height"], r["left"] - off_x:r["left"] - off_x + r["width"]]
    disp, s = fit_to_screen(crop)
    cfg.setdefault("colors", {})
    clicked = []
    cv2.setMouseCallback(win, lambda ev, x, y, *_: clicked.append((x, y)) if ev == cv2.EVENT_LBUTTONDOWN else None)

    for name in names:
        while True:
            clicked.clear()
            cv2.imshow(win, banner(disp, f"Click on {CLASS_HELP[name]}.   S = skip (not on screen)   Esc = quit"))
            k = -1
            while not clicked and k not in (ord("s"), 27):
                k = cv2.waitKey(30) & 0xFF
            if k == 27:
                sys.exit("Cancelled, nothing saved.")
            if k == ord("s"):
                print(f"  skipped {name}")
                break
            cx, cy = int(clicked[0][0] / s), int(clicked[0][1] / s)
            lab, radius = measure_blob(crop, cx, cy)
            preview = disp.copy()
            cv2.circle(preview, (int(cx * s), int(cy * s)), max(3, int(radius * s)), (0, 255, 0), 2)
            cv2.imshow(win, banner(preview, f"{name}: size {radius:.0f}px.   ENTER = ok   R = redo"))
            k = -1
            while k not in (13, ord("r")):
                k = cv2.waitKey(30) & 0xFF
            if k == 13 and radius > 0:
                cfg["colors"][name] = {"lab": lab, "radius": round(radius, 1)}
                print(f"  {name}: color {lab}, size {radius:.0f}px")
                break
    cv2.destroyAllWindows()

    cfg.setdefault("downscale", 2)
    cfg.setdefault("tolerance", DEFAULT_TOLERANCE)
    cfg.setdefault("death_timeout", 1.5)
    cfg.setdefault("require_focus", True)
    if "player" not in cfg["colors"]:
        sys.exit("The player is required. Nothing saved; run calibrate again.")
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"\nSaved {CONFIG_PATH}. Next: run test_view.bat to check the bot sees everything.")


COLORS = {"player": (140, 230, 120), "enemy_bullet": (80, 80, 255), "shooter_bullet": (80, 80, 255), "grunt": (60, 60, 230), "runner": (90, 220, 230),
          "shooter": (50, 150, 255), "tank": (230, 130, 70), "boss": (200, 40, 200)}


def view():
    cfg = load_config()
    det = Detector(cfg)
    win = "What the bot sees (Q = quit)"
    with mss.mss() as sct:
        while True:
            t = time.perf_counter()
            frame = np.ascontiguousarray(np.asarray(sct.grab(cfg["region"]))[:, :, :3])
            dets = det.detect(frame)
            ms = (time.perf_counter() - t) * 1000
            for name, items in dets.items():
                for (x, y, r) in items:
                    cv2.circle(frame, (int(x), int(y)), int(r) + 3, COLORS[name], 2)
                    cv2.putText(frame, name, (int(x - r), int(y - r - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLORS[name], 1)
            counts = "  ".join(f"{n}:{len(v)}" for n, v in dets.items() if v)
            disp, _ = fit_to_screen(frame, 1000, 600)
            cv2.imshow(win, banner(disp, f"{counts or 'nothing found'}   ({ms:.0f} ms)"))
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    cv2.destroyAllWindows()


# --------------------------------------------------------------------------- run
def run():
    from pynput import keyboard

    cfg = load_config()
    io = WindowsIO(cfg["region"], cfg.get("require_focus", True))
    bot = BotRunner(cfg, io)
    flags = {"start": False, "stop": False}

    def on_press(k):
        ch = getattr(k, "char", None)
        vk = getattr(k, "vk", None)
        if ch == "*" or vk == 106:            # * (Shift+8 or numpad *)
            flags["start"] = True
        elif ch == "-" or vk in (109, 189):   # - (main keyboard or numpad -)
            flags["stop"] = True

    threading.Thread(target=keyboard.Listener(on_press=on_press).run, daemon=True).start()
    print("Bot ready.  *  = start    -  = stop    (Ctrl+C in this window = quit)")
    running = False
    frames, fps_t = 0, time.perf_counter()
    try:
        while True:
            if flags["start"]:
                flags["start"] = False
                if not running:
                    bot.reset()
                    running = True
                    print("Started.")
            if flags["stop"]:
                flags["stop"] = False
                if running:
                    running = False
                    bot.release()
                    print("Stopped (you pressed -).")
            if not running:
                time.sleep(0.02)
                continue
            status = bot.step()
            if status == "dead":
                running = False
                print("Player disappeared (died?), stopped. Press * to start again.")
            frames += 1
            if time.perf_counter() - fps_t > 5:
                print(f"  running at {frames / (time.perf_counter() - fps_t):.0f} fps")
                frames, fps_t = 0, time.perf_counter()
    except KeyboardInterrupt:
        pass
    finally:
        bot.release()


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "calibrate":
        calibrate(args[1:])
    elif args and args[0] == "view":
        view()
    else:
        if os.name != "nt":
            sys.exit("Running the bot needs Windows.")
        run()
