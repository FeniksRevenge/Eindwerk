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
from vision import CLASS_HELP, CLASSES, DEFAULT_TOLERANCE, Detector, annotate, measure_blob

# When packed into SwarmBot.exe, keep config.json next to the exe (not in its temp folder).
FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
SHOTS_DIR = os.path.join(HERE, "screenshots")

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
        raise FileNotFoundError("No config.json yet. Calibrate first.")
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


def show_on_top(win, img):
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)
    cv2.imshow(win, img)
    try:
        cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)
    except Exception:
        pass
    cv2.waitKey(1)


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

    win = "Swarm bot calibration"
    intro = np.zeros((230, 760, 3), np.uint8)
    lines = [("CALIBRATION", (120, 255, 140), 0.9),
             ("1. Start the game in Roblox with as many kinds of mobs on screen as you can", (230, 230, 230), 0.5),
             ("   (press P in the game to pause once they're there).", (230, 230, 230), 0.5),
             ("2. Come back to this window and press ENTER.", (230, 230, 230), 0.5),
             ("3. Switch to Roblox: a screenshot is taken 5 seconds later.", (230, 230, 230), 0.5),
             ("Esc = cancel", (150, 150, 150), 0.5)]
    for i, (text, color, size) in enumerate(lines):
        cv2.putText(intro, text, (20, 40 + i * 34), cv2.FONT_HERSHEY_SIMPLEX, size, color, 1, cv2.LINE_AA)
    show_on_top(win, intro)
    k = -1
    while k not in (13, 27):
        k = cv2.waitKey(30) & 0xFF
    cv2.destroyAllWindows()
    if k == 27:
        sys.exit("Cancelled, nothing saved.")
    shot, off_x, off_y = grab_screen()
    show_on_top(win, banner(np.zeros((40, 760, 3), np.uint8), "Got it."))

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
            if lab is None:
                cv2.imshow(win, banner(disp, "That's background. Click right on the colored part (the solid middle).  (any key)"))
                cv2.waitKey(0)
                continue
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
    print(f"\nSaved {CONFIG_PATH}. Next: use Test view to check the bot sees everything.")


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
            disp, _ = fit_to_screen(annotate(frame, dets, extra=f"({ms:.0f} ms)"), 1000, 600)
            cv2.imshow(win, disp)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    cv2.destroyAllWindows()


# --------------------------------------------------------------------------- run
class BotController:
    """Runs the bot on a background thread. Used by both the command line and the app (gui.py).

    `on_event(kind, text)` is called from the bot thread with kind "status", "log" or "fps".
    """

    def __init__(self, on_event=lambda kind, text: print(text)):
        self.on_event = on_event
        self._start = threading.Event()
        self._stop = threading.Event()
        self._quit = threading.Event()
        self._snap = threading.Event()
        self.shots_saved = 0
        self.running = False
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def start(self):
        self._start.set()

    def stop(self):
        self._stop.set()

    def screenshot(self):
        self._snap.set()

    def quit(self):
        self._quit.set()
        self._stop.set()

    def listen_hotkeys(self):
        """Global * (start), - (stop) and / (screenshot) keys, working even while Roblox has focus."""
        from pynput import keyboard

        def on_press(k):
            ch = getattr(k, "char", None)
            vk = getattr(k, "vk", None)
            if ch == "*" or vk == 106:            # * (Shift+8 or numpad *)
                self.start()
            elif ch == "-" or vk in (109, 189):   # - (main keyboard or numpad -)
                self.stop()
            elif ch == "/" or vk == 111:          # / (main keyboard or numpad /)
                self.screenshot()

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()
        return listener

    def _loop(self):
        bot = None
        frames, fps_t = 0, time.perf_counter()
        last_status = None
        while not self._quit.is_set():
            if self._snap.is_set():
                self._snap.clear()
                self._take_screenshot(bot if self.running else None)
            if self._start.is_set():
                self._start.clear()
                self._stop.clear()
                if not self.running:
                    try:
                        cfg = load_config()  # re-read, in case calibration changed it
                        bot = BotRunner(cfg, WindowsIO(cfg["region"], cfg.get("require_focus", True)))
                        self.running = True
                        last_status = None
                        self.on_event("status", "Running")
                        self.on_event("log", "Started.")
                    except Exception as e:
                        self.on_event("log", f"Can't start: {e}")
            if self._stop.is_set():
                self._stop.clear()
                if self.running:
                    self.running = False
                    bot.release()
                    self.on_event("status", "Stopped")
                    self.on_event("log", "Stopped.")
            if not self.running:
                time.sleep(0.02)
                continue
            try:
                status = bot.step()
                while bot.notes:
                    self.on_event("log", bot.notes.pop(0))
            except Exception as e:
                self.running = False
                bot.release()
                self.on_event("status", "Error")
                self.on_event("log", f"Error, stopped: {e}")
                continue
            if status == "dead":
                self.running = False
                self.on_event("status", "Stopped (died)")
                self.on_event("log", "Player disappeared (died?), stopped. Press * to start again.")
                continue
            shown = "Waiting for the player to appear..." if status == "waiting" else "Running"
            if shown != last_status:
                self.on_event("status", shown)
                last_status = shown
            frames += 1
            if time.perf_counter() - fps_t > 1:
                self.on_event("fps", f"{frames / (time.perf_counter() - fps_t):.0f}")
                frames, fps_t = 0, time.perf_counter()
        if bot is not None:
            bot.release()


    def _take_screenshot(self, bot):
        """Grab what the bot sees right now and save it on another thread, so play isn't interrupted."""
        try:
            if bot is not None and bot.last is not None:
                last = dict(bot.last)
            else:  # bot not running: just look at the screen
                cfg = load_config()
                with mss.mss() as sct:
                    frame = np.ascontiguousarray(np.asarray(sct.grab(cfg["region"]))[:, :, :3])
                last = {"frame": frame, "dets": Detector(cfg).detect(frame), "player": None,
                        "keys": (), "aim": None, "fire": False}
        except Exception as e:
            self.on_event("log", f"Screenshot failed: {e}")
            return
        self.shots_saved += 1
        n = self.shots_saved
        threading.Thread(target=self._write_screenshot, args=(last, n, bot is not None), daemon=True).start()

    def _write_screenshot(self, last, n, running):
        try:
            os.makedirs(SHOTS_DIR, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
            base = os.path.join(SHOTS_DIR, f"shot_{stamp}")
            extra = f"speed {last['speed']:.0f}px/s" if last.get("speed") else ("bot running" if running else "bot not running")
            cv2.imwrite(base + ".png", last["frame"])
            cv2.imwrite(base + "_bot.png", annotate(last["frame"], last["dets"], last["player"], last["keys"],
                                                    last["aim"], extra))
            info = {k: last.get(k) for k in ("player", "keys", "aim", "fire", "speed")}
            info["detections"] = last["dets"]
            info["bot_running"] = running
            with open(base + ".json", "w") as f:
                json.dump(info, f, indent=1, default=float)
            self.on_event("log", f"Screenshot {n} saved: {os.path.basename(base)}.png")
        except Exception as e:
            self.on_event("log", f"Screenshot failed: {e}")


def run():
    load_config()
    ctl = BotController()
    ctl.listen_hotkeys()
    print("Bot ready.  *  = start    -  = stop    /  = screenshot    (Ctrl+C in this window = quit)")
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        ctl.quit()
        ctl.thread.join(1)


def main(args):
    try:
        if args and args[0] == "calibrate":
            calibrate(args[1:])
        elif args and args[0] == "view":
            view()
        elif os.name != "nt":
            sys.exit("Running the bot needs Windows.")
        else:
            run()
    except FileNotFoundError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main(sys.argv[1:])
