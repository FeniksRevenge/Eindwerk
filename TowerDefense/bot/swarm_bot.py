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
import dpi  # noqa: F401  (first: real screen pixels with display scaling)
import json
import os
import sys
import threading
import time

import cv2
import cvwin
import mss
import numpy as np

from phototrainer import list_photos, train_semi
from runner import BotRunner
from vision import CLASS_HELP, CLASSES, DEFAULT_TOLERANCE, PRESET, Detector, annotate, measure_blob, set_main_player

# When packed into SwarmBot.exe, keep config.json next to the exe (not in its temp folder).
FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
SHOTS_DIR = os.path.join(HERE, "screenshots")
CONFIG_LOCK = threading.RLock()  # the bot thread and the app both write config.json

# Screen coordinates are real pixels even with Windows display scaling (125%, 150%...).
from dpi import primary_screen_pixels  # noqa: E402  (importing dpi switches the process to real pixels)


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
SCANCODES = {"w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20, "space": 0x39}


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


class ScreenGrabber:
    """Takes screenshots of the play area non-stop on its own thread, so the bot never waits for a
    capture and always works on the freshest frame. Uses the fast Desktop Duplication API (dxcam)
    when available, otherwise mss."""

    def __init__(self, region, fast=True):
        self.region = region
        self.fast = fast  # try dxcam
        self.frame, self.frame_time, self.seq = None, 0.0, 0
        self.method = "mss"
        self.note = ""  # why it uses what it uses, for the log
        self.cond = threading.Condition()
        self.stop = threading.Event()
        self.taken = threading.Event()  # the bot took the latest frame: time to grab the next one
        threading.Thread(target=self._run, daemon=True).start()

    def _open_dxcam(self):
        try:
            import dxcam
            cam = dxcam.create(output_color="BGR")
            r = self.region
            box = (r["left"], r["top"], r["left"] + r["width"], r["top"] + r["height"])
            if cam is not None:
                return cam, box
        except Exception as e:
            self.note = f"fast capture (dxcam) not available ({e}), using mss"
        return None, None

    def _dxcam_ok(self, cam, box, sct):
        """dxcam can capture the wrong screen (laptops with 2 graphics cards), black frames, or
        different colors (HDR). Compare it with a normal screenshot before trusting it."""
        img = None
        for _ in range(100):  # dxcam gives None until the screen changes
            img = cam.grab(region=box)
            if img is not None:
                break
            time.sleep(0.01)
        ref = np.asarray(sct.grab(self.region))[:, :, :3]
        if img is None:
            return True  # nothing on screen changed for a second: can't tell, try it
        if img.shape[:2] != ref.shape[:2]:
            return False
        def small(x):  # blurred, so things that moved a little between the two shots still match
            x = cv2.resize(np.ascontiguousarray(x[:, :, :3]), (160, 90), interpolation=cv2.INTER_AREA)
            return cv2.GaussianBlur(x, (7, 7), 0).astype(np.int16)
        a, b = small(img), small(ref)
        diff = np.abs(a - b).max(axis=2)
        # The game is mostly black, so compare where there's something to see (HUD, mobs, text).
        content = np.maximum(a.max(axis=2), b.max(axis=2)) > 25
        if content.sum() >= 30:
            return float(np.median(diff[content])) < 12 and float(diff.mean()) < 12
        return float(diff.mean()) < 12

    def _run(self):
        sct = mss.mss()
        cam, box = self._open_dxcam() if self.fast else (None, None)
        if cam is not None:
            try:
                good = self._dxcam_ok(cam, box, sct)
            except Exception:
                good = False
            if good:
                self.note = "screen capture: fast (dxcam)"
            else:
                self.note = "fast capture (dxcam) gave a different picture than a normal screenshot, using mss"
                cam = None
        elif not self.fast:
            self.note = "screen capture: mss (fast capture is off in the settings)"
        self.method = "dxcam" if cam else "mss"
        last_real = time.perf_counter()
        while not self.stop.is_set():
            t = time.perf_counter()
            try:
                if cam:
                    img = cam.grab(region=box)
                    if img is None:  # screen hasn't changed since the last grab
                        if t - last_real > 0.5:
                            # nothing new for a while (e.g. dxcam lost the screen): check with mss
                            img = np.asarray(sct.grab(self.region))
                            last_real = t
                        else:
                            time.sleep(0.002)
                            continue
                    else:
                        last_real = t
                    frame = np.ascontiguousarray(img[:, :, :3])
                else:
                    frame = np.ascontiguousarray(np.asarray(sct.grab(self.region))[:, :, :3])
            except Exception:
                if cam:  # dxcam trouble (e.g. after a resolution change): fall back to mss
                    cam, self.method = None, "mss"
                    self.note = "fast capture (dxcam) stopped working, switched to mss"
                    continue
                time.sleep(0.01)
                continue
            with self.cond:
                self.frame, self.frame_time, self.seq = frame, t, self.seq + 1
                self.cond.notify_all()
            # Lightweight: grab the next frame once the bot took this one (so one is always ready),
            # instead of grabbing non-stop; refresh anyway if it waits long.
            self.taken.wait(0.03)
            self.taken.clear()

    def latest(self, after_seq):
        """Waits (up to 0.1 s) for a frame newer than `after_seq`; returns (frame, time, seq)."""
        with self.cond:
            self.cond.wait_for(lambda: self.seq > after_seq, timeout=0.1)
            out = self.frame, self.frame_time, self.seq
        self.taken.set()
        return out

    def close(self):
        self.stop.set()
        self.taken.set()


class WindowsIO:
    def __init__(self, region, require_focus=True, fire_with="space", fast_capture=True):
        self.region = region  # {"left", "top", "width", "height"} in screen pixels
        self.require_focus = require_focus
        self.fire_with = fire_with  # "space" or "mouse" (left click)
        self.grabber = ScreenGrabber(region, fast_capture)
        self.seq = 0
        self.frame_time = 0.0
        self.keys = set()
        self.down = False

    def grab(self):
        frame, self.frame_time, self.seq = self.grabber.latest(self.seq)
        while frame is None:  # very first frame
            frame, self.frame_time, self.seq = self.grabber.latest(self.seq)
        return frame

    def close(self):
        self.grabber.close()

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
        """Hold or release the fire button (Space by default, or left mouse)."""
        if down != self.down:
            if self.fire_with == "mouse":
                mouse_button(down)
            else:
                key("space", down)
            self.down = down

    def focused(self):
        return roblox_in_front() if self.require_focus else True

    def now(self):
        return time.perf_counter()


# --------------------------------------------------------------------------- config
def load_config():
    """Read config.json. The play area is always kept equal to the whole main screen."""
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError("No config.json yet. Click 'Use preset colors' first.")
    with CONFIG_LOCK:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        if use_main_screen(cfg):
            save_config(cfg)
    return cfg


def main_monitor():
    """The main (primary) screen: the one at position 0,0. The bot only ever looks at this screen."""
    with mss.mss() as sct:
        mons = sct.monitors[1:] or sct.monitors
        mon = next((m for m in mons if m["left"] == 0 and m["top"] == 0), mons[0])
    region = {"left": mon["left"], "top": mon["top"], "width": mon["width"], "height": mon["height"]}
    real = primary_screen_pixels()
    if real and (region["width"], region["height"]) != real:
        # Display scaling fooled the monitor list: trust the real resolution.
        region = {"left": 0, "top": 0, "width": real[0], "height": real[1]}
    return region


def use_main_screen(cfg):
    """Make the play area the whole main screen (top to bottom), re-scaling preset sizes to it.
    Returns True if anything changed."""
    region = main_monitor()
    if cfg.get("region") == region:
        return False
    cfg["region"] = region
    if cfg.get("preset"):
        scale = region["height"] / PRESET["ref_height"]
        cfg["colors"] = {n: {"lab": c["lab"], "radius": round(c["radius"] * scale, 1)}
                         for n, c in PRESET["colors"].items()}
    return True


def grab_screen(countdown=5):
    for i in range(countdown, 0, -1):
        print(f"  Taking a screenshot in {i}... (switch to Roblox now)")
        time.sleep(1)
    mon = main_monitor()
    with mss.mss() as sct:
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


def read_config_or_empty():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def save_config(cfg):
    cfg.setdefault("downscale", 2)
    cfg.setdefault("tolerance", DEFAULT_TOLERANCE)
    cfg.setdefault("death_timeout", 30.0)
    cfg.setdefault("require_focus", True)
    cfg.setdefault("fire_with", "space")
    cfg.setdefault("auto_shot_every", 10)
    cfg.setdefault("auto_shots", True)
    with CONFIG_LOCK:
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, CONFIG_PATH)



def apply_preset():
    """Use the colors measured from real screenshots, on the whole main screen."""
    cfg = read_config_or_empty()
    cfg["preset"] = True
    cfg.pop("region", None)
    use_main_screen(cfg)  # sets the play area and scales the preset sizes to it
    save_config(cfg)
    return True


def calibrate_from_images(paths, only):
    """Calibrate from one or more saved screenshots (e.g. taken with /). Click each thing on as many
    photos as you like; every thing's color and size is the average of all your clicks."""
    cfg = read_config_or_empty()
    samples = {}
    names = only or CLASSES
    for i, path in enumerate(paths, 1):
        shot = cv2.imread(path)
        if shot is None:
            print(f"Can't open {path}, skipped")
            continue
        header = f"Photo {i}/{len(paths)}" if len(paths) > 1 else ""
        if click_through(cfg, shot, names, samples=samples, header=header) == "quit":
            break
    cv2.destroyAllWindows()
    if not samples:
        sys.exit("Nothing clicked, nothing saved.")
    cfg.setdefault("colors", {})
    for name, got in samples.items():
        labs = np.array([g[0] for g in got], dtype=np.float64)
        radii = sorted(g[1] for g in got)
        lab, radius = [int(round(v)) for v in labs.mean(axis=0)], round(radii[len(radii) // 2], 1)
        if name == "player":
            set_main_player(cfg, lab, radius)  # the previous look is kept too
            cfg["colors"]["player"]["n"] = len(got)
        else:
            cfg["colors"][name] = {"lab": lab, "radius": radius, "n": len(got)}
        print(f"  {name}: averaged over {len(got)} click(s)")
    cfg["preset"] = False
    save_config(cfg)


def click_through(cfg, crop, names, samples=None, header=""):
    """Shows the play area and asks you to click each thing. Stores colors in cfg, or, with `samples`
    (a dict), collects them there to be averaged over several photos.
    Returns "done", "next" (N: rest of this photo skipped) or "quit" (Esc / window closed)."""
    win = "Swarm bot calibration"
    disp, s = fit_to_screen(crop)
    cfg.setdefault("colors", {})
    clicked = []
    show_on_top(win, disp)
    cv2.setMouseCallback(win, lambda ev, x, y, *_: clicked.append((x, y)) if ev == cv2.EVENT_LBUTTONDOWN else None)
    multi = samples is not None
    for name in names:
        while True:
            clicked.clear()
            extra = "   N = next photo" if multi else ""
            cv2.imshow(win, banner(disp, f"{header + ': ' if header else ''}Click on {CLASS_HELP[name]}.   "
                                         f"S = skip{extra}   Esc = {'finish' if multi else 'quit'}"))
            k = -1
            while not clicked and k not in (ord("s"), ord("n"), 27):
                k = cvwin.key(win)
            if k == 27:
                if multi:
                    return "quit"
                sys.exit("Cancelled, nothing saved.")
            if k == ord("n") and multi:
                return "next"
            if k in (ord("s"), ord("n")):
                print(f"  skipped {name}")
                break
            cx, cy = int(clicked[0][0] / s), int(clicked[0][1] / s)
            lab, radius = measure_blob(crop, cx, cy)
            if lab is None:
                cv2.imshow(win, banner(disp, "That's background. Click right on the colored part (the solid middle).  (any key)"))
                if cvwin.key_blocking(win) == 27 and cvwin.window_closed(win):
                    return "quit" if multi else sys.exit("Cancelled, nothing saved.")
                continue
            preview = disp.copy()
            cv2.circle(preview, (int(cx * s), int(cy * s)), max(3, int(radius * s)), (0, 255, 0), 2)
            cv2.imshow(win, banner(preview, f"{name}: size {radius:.0f}px.   ENTER = ok   R = redo"))
            k = -1
            while k not in (13, ord("r"), 27):
                k = cvwin.key(win)
            if k == 27:
                if multi:
                    return "quit"
                sys.exit("Cancelled, nothing saved.")
            if k == 13:
                if multi:
                    samples.setdefault(name, []).append((lab, radius))
                elif name == "player":
                    set_main_player(cfg, lab, radius)  # the previous look is kept too
                else:
                    cfg["colors"][name] = {"lab": lab, "radius": round(radius, 1)}
                print(f"  {name}: color {lab}, size {radius:.0f}px")
                break
    return "done"


def calibrate(only):
    cfg = read_config_or_empty()
    region_only = only == ["region"]
    if region_only:
        use_main_screen(cfg)
        save_config(cfg)
        print(f"Play area set to the whole main screen: {cfg['region']}")
        return
    names = only or CLASSES
    for n in names:
        if n not in CLASSES:
            sys.exit(f"Unknown thing '{n}'. Choose from: region, {', '.join(CLASSES)}")

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
        k = cvwin.key(win)
    cv2.destroyAllWindows()
    if k == 27:
        sys.exit("Cancelled, nothing saved.")
    shot, off_x, off_y = grab_screen()
    show_on_top(win, banner(np.zeros((40, 760, 3), np.uint8), "Got it."))

    # The play area is always the whole main screen.
    cfg["region"] = {"left": off_x, "top": off_y, "width": shot.shape[1], "height": shot.shape[0]}

    r = cfg["region"]
    crop = shot[r["top"] - off_y:r["top"] - off_y + r["height"], r["left"] - off_x:r["left"] - off_x + r["width"]]
    if names:
        click_through(cfg, crop, names)
        cfg["preset"] = False
    cv2.destroyAllWindows()
    if not region_only and "player" not in cfg.get("colors", {}):
        sys.exit("The player is required. Nothing saved; run calibrate again.")
    save_config(cfg)
    print(f"\nSaved {CONFIG_PATH}. Next: use Test view to check the bot sees everything.")


def view():
    cfg = load_config()
    det = Detector(cfg)
    win = "What the bot sees (Q = quit)"
    shown = False
    with mss.mss() as sct:
        while True:
            if shown and cvwin.window_closed(win):
                break  # closed with the X button
            shown = True
            t = time.perf_counter()
            frame = np.ascontiguousarray(np.asarray(sct.grab(cfg["region"]))[:, :, :3])
            dets = det.detect(frame)
            ms = (time.perf_counter() - t) * 1000
            disp, _ = fit_to_screen(annotate(frame, dets, extra=f"({ms:.0f} ms)"), 1000, 600)
            cv2.imshow(win, disp)
            if cvwin.key(win, 1) in (ord("q"), 27):
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
        self.latest = None  # the bot's latest tick (what it sees/decided), for the overlay
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
        capture_logged = blind_shot = False
        auto_every, next_auto = 0, 0.0
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
                        bot = BotRunner(cfg, WindowsIO(cfg["region"], cfg.get("require_focus", True),
                                                          cfg.get("fire_with", "space"),
                                                          cfg.get("fast_capture", True)))
                        self.running = True
                        capture_logged = False
                        blind_shot = False
                        last_status = None
                        auto_every = float(cfg.get("auto_shot_every", 10)) if cfg.get("auto_shots", True) else 0
                        next_auto = time.perf_counter() + auto_every
                        self.on_event("status", "Running")
                        self.on_event("log", "Started.")
                    except Exception as e:
                        self.on_event("log", f"Can't start: {e}")
            if self._stop.is_set():
                self._stop.clear()
                if self.running:
                    self.running = False
                    bot.release()
                    bot.io.close()
                    self.on_event("status", "Stopped")
                    self.on_event("log", "Stopped.")
            if not self.running:
                time.sleep(0.02)
                continue
            try:
                status = bot.step()
                self.latest = bot.last  # for the on-screen overlay
                while bot.notes:
                    self.on_event("log", bot.notes.pop(0))
            except Exception as e:
                self.running = False
                bot.release()
                bot.io.close()
                self.on_event("status", "Error")
                self.on_event("log", f"Error, stopped: {e}")
                continue
            if status == "dead":
                self.running = False
                bot.io.close()
                self.on_event("status", "Stopped (died)")
                self.on_event("log", f"Died ({bot.death_reason}) after {bot.run_seconds():.0f}s. "
                                     "Stopped. Press * to start again.")
                continue
            # Periodic photos for the photo trainer (capped so the folder can't fill the disk).
            if auto_every > 0 and status == "ok" and time.perf_counter() >= next_auto:
                next_auto = time.perf_counter() + auto_every
                if len(list_photos(SHOTS_DIR)) < 300 if os.path.isdir(SHOTS_DIR) else True:
                    self._take_screenshot(bot)
            grabber = getattr(bot.io, "grabber", None)
            if not capture_logged and grabber is not None and grabber.note:
                self.on_event("log", grabber.note[0].upper() + grabber.note[1:] + ".")
                capture_logged = True
            if bot.lost_report:  # lost the player for 1 s mid-run (once per run): keep a picture of it
                bot.lost_report = False
                self._take_screenshot(bot)
                p = bot.player
                self.on_event("log", "Lost track of you for 1 s" + (f" near ({p[0]:.0f}, {p[1]:.0f})" if p else "") +
                                     ": saved a screenshot of what the bot saw. If you were really there, send it "
                                     "(the bot keeps playing and only stops at the GAME OVER screen).")
            # Never found the player in the first 3 s: save what the bot sees (once per run) to check it.
            if not blind_shot and status == "waiting" and bot.waiting_time() > 3.0:
                blind_shot = True
                self._take_screenshot(bot)
                self.on_event("log", "Can't find you (the gray ball) for 3 s. Saved a screenshot of what the bot sees: "
                                     "open it (Open screenshots folder). If you're on it but not circled in the _bot.png, "
                                     "click 'Use preset colors' or 'Clear ignore list', or try turning off fast capture.")
            shown = "Waiting for the player to appear..." if status == "waiting" else "Running"
            if shown != last_status:
                self.on_event("status", shown)
                last_status = shown
            frames += 1
            if time.perf_counter() - fps_t > 1:
                method = getattr(getattr(bot.io, "grabber", None), "method", "")
                self.on_event("fps", f"{frames / (time.perf_counter() - fps_t):.0f}" + (f" ({method})" if method else ""))
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
        if args and args[0] == "calibrate" and len(args) > 2 and args[1] in ("--image", "--images"):
            paths = [a for a in args[2:] if os.path.isfile(a)]
            calibrate_from_images(paths, [a for a in args[2:] if a in CLASSES])
        elif args and args[0] == "calibrate":
            calibrate(args[1:])
        elif args and args[0] == "train":
            train_semi(read_config_or_empty(), SHOTS_DIR, save_config)
        elif args and args[0] == "preset":
            print("Preset colors applied." if apply_preset() else "Preset colors applied. Now set the play area.")
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
