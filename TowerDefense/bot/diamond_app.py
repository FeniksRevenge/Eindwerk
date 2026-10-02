"""
DiamondBot, for the hay bales in Roblox. Over and over:
  1. press 2 (dynamite), hold the left mouse button 1.5 s, let go;
  2. press 5 (your tool), hold the left mouse button 15 s. When a light-blue diamond shows up in the hay
     it moves the cursor to it, lets go of the left button, holds it again and goes back.
All the time the cursor slowly circles around where you put it, so what you're holding can't hide a
diamond for long. Keys, times and the circle are settings.

    *   start          -   stop          /   save a screenshot of what it sees

Keeps Windows awake; the circling and the key presses keep Roblox from kicking you for being idle.
"""

import json
import math
import os
import sys
import threading
import time

FROZEN = getattr(sys, "frozen", False)
for _name in ("stdout", "stderr"):  # the exe has no console: errors printed there would pop up a crash window
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w"))
HOME = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
CONFIG = os.path.join(HOME, "diamond_config.json")
PICTURES = os.path.join(HOME, "pictures")

STEP = 0.05           # s between steps (cursor moves on the circle every step)
LOOK_EVERY = 0.1      # s between looks for diamonds
CONFIRM = 2           # a diamond must be seen this many times in a row (not a flicker)
MOVE_PAUSE = 0.06     # s to wait after moving the cursor / before and after letting go
KEY_PAUSE = 0.12      # s after pressing a number key (the item switches)
AFTER_CLICK = 0.6     # s not to look for diamonds after one was clicked (it disappears)
SAME_SPOT = 0.04      # x window height: a diamond still there after clicking it ...
MAX_TRIES = 3         # ... is clicked at most this many times, then left alone for a while
GIVE_UP = 10.0        # s to leave such a spot alone
AWAKE_EVERY = 30.0    # s: tell Windows again that the screen is in use

DEFAULTS = {"require_focus": True, "dynamite_key": "2", "dynamite_hold": 1.5, "tool_key": "5",
            "tool_hold": 15.0, "circle": 60, "circle_secs": 6.0}
KEYS = [str(i) for i in range(10)]


def load_settings():
    try:
        with open(CONFIG) as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    out = dict(DEFAULTS)
    for k, v in s.items():
        if k in DEFAULTS:
            try:
                out[k] = type(DEFAULTS[k])(v)
            except (TypeError, ValueError):
                pass
    if out["dynamite_key"] not in KEYS:
        out["dynamite_key"] = DEFAULTS["dynamite_key"]
    if out["tool_key"] not in KEYS:
        out["tool_key"] = DEFAULTS["tool_key"]
    return out


def save_settings(s):
    try:
        with open(CONFIG, "w") as f:
            json.dump(s, f, indent=2)
    except OSError:
        pass


class DiamondRunner:
    """The logic. io must have: grab() -> (picture, window area) or (None, None), cursor(), move(x, y)
    (screen pixels), button(down), key(name) (press and let go), focused(), now(), awake(), sleep(s)."""

    def __init__(self, io, settings, log=lambda text: None):
        self.io, self.s, self.log = io, dict(DEFAULTS, **settings), log
        self.home = io.cursor()     # the middle of the circle: where the mouse was at Start
        self.t0 = io.now()
        self.held = False
        self.phase, self.phase_end = None, 0.0   # "dynamite" / "tool"
        self.seen = 0
        self.next_look = 0.0
        self.tries, self.blocked = [], []
        self.clicked, self.cycles = 0, 0
        self.next_awake = 0.0

    # ------------------------------------------------------------------ mouse
    def _button(self, down):
        if down != self.held:
            self.io.button(down)
            self.held = down

    def release(self):
        self._button(False)

    def circle_point(self, now):
        r = self.s["circle"]
        a = 2 * math.pi * (now - self.t0) / max(0.5, self.s["circle_secs"])
        return int(self.home[0] + r * math.cos(a)), int(self.home[1] + r * math.sin(a))

    # ------------------------------------------------------------------ one step
    def step(self):
        """Returns "dynamite", "tool", "paused" (Roblox not in front) or "no_window"."""
        io, now = self.io, self.io.now()
        if now >= self.next_awake:
            io.awake()
            self.next_awake = now + AWAKE_EVERY
        frame, area = io.grab()
        if frame is None or not io.focused():
            self.release()
            self.phase = None  # start the cycle again (with the dynamite) when it's back
            return "no_window" if frame is None else "paused"
        if self.phase is None or now >= self.phase_end:
            self._next_phase()
            now = io.now()
        io.move(*self.circle_point(now))
        if self.phase == "tool" and now >= self.next_look:
            self.next_look = now + LOOK_EVERY
            self._look(frame, area, now)
        return self.phase

    def _next_phase(self):
        io = self.io
        self.release()
        io.sleep(MOVE_PAUSE)
        if self.phase == "dynamite":  # dynamite thrown: the tool for a while
            io.key(self.s["tool_key"])
            io.sleep(KEY_PAUSE)
            self._button(True)
            self.phase, self.phase_end = "tool", io.now() + self.s["tool_hold"]
            self.seen = 0
        else:
            io.key(self.s["dynamite_key"])
            io.sleep(KEY_PAUSE)
            self._button(True)
            self.phase, self.phase_end = "dynamite", io.now() + self.s["dynamite_hold"]
            self.cycles += 1

    def _look(self, frame, area, now):
        from diamonds import find_diamonds
        H = frame.shape[0]
        self.blocked = [b for b in self.blocked if b[0] > now]
        found = [d for d in find_diamonds(frame)
                 if not any(abs(d[0] - bx) < SAME_SPOT * H * 2 and abs(d[1] - by) < SAME_SPOT * H * 2
                            for _, bx, by in self.blocked)]
        if not found:
            self.seen = 0
            return
        self.seen += 1
        if self.seen < CONFIRM:
            return
        x, y, _ = found[0]
        self.tries = [t for t in self.tries if now - t[0] < GIVE_UP]
        again = [t for t in self.tries if abs(t[1] - x) < SAME_SPOT * H and abs(t[2] - y) < SAME_SPOT * H]
        if len(again) >= MAX_TRIES:
            self.blocked.append((now + GIVE_UP, x, y))
            self.log(f"A diamond at ({x:.0f}, {y:.0f}) didn't go away after {MAX_TRIES} clicks; leaving it "
                     f"alone for {GIVE_UP:.0f} s.")
            return
        self._grab_diamond(area["left"] + x, area["top"] + y)
        self.tries.append((now, x, y))
        self.clicked += 1
        self.seen = 0
        self.next_look = self.io.now() + AFTER_CLICK

    def _grab_diamond(self, sx, sy):
        """Cursor to the diamond, let go of the left button, hold it again, cursor back onto the circle."""
        io = self.io
        io.move(int(sx), int(sy))
        io.sleep(MOVE_PAUSE)
        self._button(False)
        io.sleep(MOVE_PAUSE)
        self._button(True)
        io.sleep(MOVE_PAUSE)
        io.move(*self.circle_point(io.now()))


class WindowsDiamondIO:
    def __init__(self, require_focus=True):
        import mss
        import winio
        self.w, self.require_focus = winio, require_focus
        self.sct = mss.mss()
        self.hwnd, self.area, self.next_find = None, None, 0.0
        winio.keep_awake(True)

    def grab(self):
        import numpy as np
        now = time.perf_counter()
        if now >= self.next_find or self.area is None:
            self.hwnd, self.area = self.w.find_roblox()
            self.next_find = now + 1.0
        if self.area is None:
            return None, None
        try:
            frame = np.ascontiguousarray(np.asarray(self.sct.grab(self.area))[:, :, :3])
        except Exception:
            self.area = None
            return None, None
        return frame, self.area

    def cursor(self):
        return self.w.cursor_pos()

    def move(self, x, y):
        self.w.mouse_to(x, y)

    def button(self, down):
        self.w.mouse_button(down)

    def key(self, name):
        self.w.press(name, True)
        time.sleep(0.05)
        self.w.press(name, False)

    def focused(self):
        return (not self.require_focus) or self.w.foreground_is(self.hwnd)

    def now(self):
        return time.perf_counter()

    def awake(self):
        self.w.keep_awake(True)
        self.w.still_here()

    def sleep(self, s):
        time.sleep(s)

    def close(self):
        self.w.keep_awake(False)


class Bot:
    def __init__(self, on_event):
        self.on_event = on_event
        self.settings = load_settings()
        self._start, self._stop, self._quit, self._snap = (threading.Event() for _ in range(4))
        self.running, self.runner, self.io = False, None, None
        threading.Thread(target=self._loop, daemon=True).start()

    def hotkeys(self):
        from pynput import keyboard

        def on_press(k):
            ch, vk = getattr(k, "char", None), getattr(k, "vk", None)
            if ch == "*" or vk == 106:
                self._start.set()
            elif ch == "-" or vk in (109, 189):
                self._stop.set()
            elif ch == "/" or vk == 111:
                self._snap.set()
        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()

    def _loop(self):
        last = None
        while not self._quit.is_set():
            if self._snap.is_set():
                self._snap.clear()
                self._screenshot()
            if self._start.is_set():
                self._start.clear()
                self._stop.clear()
                if not self.running:
                    self.io = WindowsDiamondIO(self.settings["require_focus"])
                    self.runner = DiamondRunner(self.io, self.settings, log=lambda t: self.on_event("log", t))
                    self.running, last = True, None
                    s = self.settings
                    self.on_event("log", f"Started: {s['dynamite_key']} + hold {s['dynamite_hold']:g} s, then "
                                         f"{s['tool_key']} + hold {s['tool_hold']:g} s (grabbing diamonds), circling "
                                         f"{s['circle']} px around {self.runner.home}.")
            if self._stop.is_set():
                self._stop.clear()
                if self.running:
                    self._halt("Stopped")
            if not self.running:
                time.sleep(0.05)
                continue
            t0 = time.perf_counter()
            try:
                status = self.runner.step()
            except Exception as e:
                self._halt("Error")
                self.on_event("log", f"Error, stopped: {e!r}")
                continue
            shown = {"dynamite": "Dynamite", "tool": "Holding the tool, watching for diamonds",
                     "paused": "Paused (Roblox isn't the window in front)",
                     "no_window": "Roblox window not found"}[status]
            if shown != last:
                self.on_event("status", shown)
                last = shown
            self.on_event("count", f"{self.runner.clicked}   rounds: {self.runner.cycles}")
            time.sleep(max(0.0, STEP - (time.perf_counter() - t0)))
        if self.running:
            self._halt("Stopped")

    def _halt(self, text):
        self.running = False
        try:
            self.runner.release()
        finally:
            self.io.close()
        self.on_event("status", text)
        self.on_event("log", f"{text}. Diamonds grabbed: {self.runner.clicked}, rounds: {self.runner.cycles}.")

    def _screenshot(self):
        import cv2
        import mss
        import numpy as np
        import winio
        from diamonds import annotate, find_diamonds
        _, area = winio.find_roblox()
        if area is None:
            self.on_event("log", "Screenshot: Roblox window not found.")
            return
        with mss.mss() as sct:
            frame = np.ascontiguousarray(np.asarray(sct.grab(area))[:, :, :3])
        found = find_diamonds(frame)
        os.makedirs(PICTURES, exist_ok=True)
        base = os.path.join(PICTURES, "diamond_" + time.strftime("%Y%m%d_%H%M%S"))
        cv2.imwrite(base + ".png", frame)
        cv2.imwrite(base + "_found.png", annotate(frame, found))
        self.on_event("log", f"Screenshot saved: {os.path.basename(base)}.png ({len(found)} diamond(s) found, "
                             f"circled in _found.png)")


def app():
    import queue
    import tkinter as tk
    from tkinter import ttk
    BG, PANEL, LINE, FG, MUTED = "#07090d", "#11151c", "#232a35", "#e4e7ec", "#8a93a1"
    FONT, MONO = ("Segoe UI", 10), ("Consolas", 9)
    root = tk.Tk()
    root.title("Diamond Bot")
    root.configure(bg=BG)
    root.resizable(False, False)
    events = queue.Queue()
    bot = Bot(lambda kind, text: events.put((kind, text)))
    try:
        bot.hotkeys()
        hot = "Keys work while you're in Roblox:  *  start    -  stop    /  screenshot"
    except Exception as e:
        hot = f"Hotkeys unavailable ({e}); use the buttons."
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TButton", background=PANEL, foreground=FG, bordercolor=LINE, padding=(10, 6), font=FONT)
    style.configure("TCheckbutton", background=BG, foreground=FG, font=FONT)
    style.map("TCheckbutton", background=[("active", BG)])
    wrap = tk.Frame(root, bg=BG, padx=16, pady=14)
    wrap.pack(fill="both", expand=True)
    tk.Label(wrap, text="DIAMOND BOT", bg=BG, fg=FG, font=("Consolas", 16, "bold")).pack(anchor="w")
    status, count = tk.StringVar(value="Idle"), tk.StringVar(value="0")
    box = tk.Frame(wrap, bg=PANEL, highlightbackground=LINE, highlightthickness=1, padx=12, pady=10)
    box.pack(fill="x", pady=(10, 10))
    tk.Label(box, textvariable=status, bg=PANEL, fg=FG, font=("Segoe UI Semibold", 12)).pack(side="left")
    tk.Label(box, text="   diamonds:", bg=PANEL, fg=MUTED, font=FONT).pack(side="left")
    tk.Label(box, textvariable=count, bg=PANEL, fg=FG, font=("Segoe UI Semibold", 12)).pack(side="left")
    row = tk.Frame(wrap, bg=BG)
    row.pack(fill="x")
    ttk.Button(row, text="Start  ( * )", command=bot._start.set).pack(side="left", expand=True, fill="x", padx=(0, 6))
    ttk.Button(row, text="Stop  ( - )", command=bot._stop.set).pack(side="left", expand=True, fill="x")
    tk.Label(wrap, text=hot, bg=BG, fg=MUTED, font=FONT).pack(anchor="w", pady=(6, 8))

    s = bot.settings
    fields = {}
    grid = tk.Frame(wrap, bg=BG)
    grid.pack(anchor="w")
    rows = [("Dynamite: key", "dynamite_key", "then hold (s)", "dynamite_hold"),
            ("Tool: key", "tool_key", "then hold (s)", "tool_hold"),
            ("Circle: size (px)", "circle", "one round (s)", "circle_secs")]

    def save(*_):
        for k, var in fields.items():
            v = var.get().strip()
            try:
                val = type(DEFAULTS[k])(float(v)) if not isinstance(DEFAULTS[k], str) else v
            except ValueError:
                continue
            if isinstance(DEFAULTS[k], str) and val not in KEYS:
                continue
            if not isinstance(DEFAULTS[k], str) and val < 0:
                continue
            bot.settings[k] = val
        bot.settings["require_focus"] = bool(focus.get())
        save_settings(bot.settings)

    for r, (l1, k1, l2, k2) in enumerate(rows):
        for c, (lab, key) in enumerate(((l1, k1), (l2, k2))):
            tk.Label(grid, text=lab, bg=BG, fg=FG, font=FONT).grid(row=r, column=2 * c, sticky="w", padx=(0 if c == 0 else 14, 4), pady=2)
            var = tk.StringVar(value=f"{s[key]:g}" if isinstance(s[key], float) else str(s[key]))
            tk.Entry(grid, textvariable=var, width=6, bg=PANEL, fg=FG, insertbackground=FG, relief="flat",
                     highlightbackground=LINE, highlightthickness=1, font=FONT).grid(row=r, column=2 * c + 1, sticky="w")
            var.trace_add("write", save)
            fields[key] = var
    focus = tk.BooleanVar(value=s["require_focus"])
    ttk.Checkbutton(wrap, text="Only while Roblox is the window in front", variable=focus,
                    command=save).pack(anchor="w", pady=(6, 4))
    tk.Label(wrap, text="Put the mouse where it should circle, then press *. Changes apply at the next Start.",
             bg=BG, fg=MUTED, font=FONT).pack(anchor="w")
    log = tk.Text(wrap, height=8, width=74, bg=PANEL, fg=FG, font=MONO, relief="flat",
                  highlightbackground=LINE, highlightthickness=1, wrap="word")
    log.pack(fill="both", pady=(8, 0))

    def write(text):
        log.insert("end", time.strftime("%H:%M:%S  ") + text + "\n")
        if int(log.index("end-1c").split(".")[0]) > 2000:
            log.delete("1.0", "500.0")
        log.see("end")

    def poll():
        while True:
            try:
                kind, text = events.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                status.set(text)
            elif kind == "count":
                count.set(text)
            else:
                write(text)
        root.after(100, poll)

    def close():
        bot._quit.set()
        root.after(300, root.destroy)
    root.protocol("WM_DELETE_WINDOW", close)
    write("Open Roblox at the hay bales, put the mouse where it should circle, then press * (or Start).")
    root.after(100, poll)
    root.mainloop()


class FakeIO:
    """For tests: a drawn screen; records what the bot does with the mouse and keys."""

    def __init__(self, frame, diamonds=()):
        self.t, self.calls, self.pos, self.down = 0.0, [], (500, 400), False
        self.frame, self.diamonds = frame, list(diamonds)  # diamonds: (x, y, w, h) boxes drawn on the frame

    def grab(self):
        import cv2
        img = self.frame.copy()
        for x, y, w, h in self.diamonds:
            pts = [[x + w // 2, y], [x + w, y + h // 3], [x + w * 3 // 4, y + h], [x + w // 4, y + h], [x, y + h // 3]]
            cv2.fillPoly(img, [__import__("numpy").array(pts, "int32")], (192, 183, 113))
        return img, {"left": 0, "top": 0, "width": img.shape[1], "height": img.shape[0]}

    def cursor(self):
        return self.pos

    def move(self, x, y):
        self.pos = (x, y)
        self.calls.append(("move", round(self.t, 2), x, y))

    def button(self, down):
        if self.down and not down:  # letting go over a diamond collects it
            self.diamonds = [d for d in self.diamonds if not (d[0] <= self.pos[0] <= d[0] + d[2] and
                                                              d[1] <= self.pos[1] <= d[1] + d[3])]
        self.down = down
        self.calls.append(("button", round(self.t, 2), down))

    def key(self, name):
        self.calls.append(("key", round(self.t, 2), name))

    def focused(self):
        return True

    def now(self):
        return self.t

    def awake(self):
        pass

    def sleep(self, s):
        self.t += s


def selftest():
    """For the exe build: it finds a drawn diamond in drawn hay, and the cycle and the grab are right."""
    import numpy as np
    hay = np.full((720, 1280, 3), (63, 140, 183), np.uint8)
    io = FakeIO(hay)
    r = DiamondRunner(io, {})
    while io.t < 20:  # 20 s: dynamite (1.5 s), tool (15 s), dynamite again
        if 5 < io.t < 5.05:
            io.diamonds.append((700, 300, 80, 70))
        r.step()
        io.t += STEP
    keys = [c[2] for c in io.calls if c[0] == "key"]
    downs = [c[1] for c in io.calls if c[0] == "button" and c[2]]
    moves = [c for c in io.calls if c[0] == "move"]
    far = max(abs(m[2] - 500) for m in moves[:50])
    return (keys[:3] == ["2", "5", "2"] and r.clicked == 1 and not io.diamonds and len(downs) >= 3 and
            40 <= far <= 70)  # it circled ~60 px around where the mouse was


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        try:
            ok = selftest()
            msg = "ok" if ok else "detection/clicking failed"
        except Exception as e:
            ok, msg = False, f"error: {e!r}"
        with open(os.path.join(HOME, "selftest.txt"), "w") as f:
            f.write(msg)
        sys.exit(0 if ok else 1)
    app()
