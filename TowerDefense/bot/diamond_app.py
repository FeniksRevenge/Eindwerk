"""
DiamondBot: holds the left mouse button in Roblox, and when a light-blue diamond shows up in the hay it
moves the cursor to it, lets go of the left button, holds it again and moves back to where it was.

    *   start          -   stop          /   save a screenshot of what it sees

Keeps Windows awake and wiggles the mouse by 1 pixel every minute so Roblox doesn't kick you for being idle.
"""

import json
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

LOOK_EVERY = 0.1      # s between looks at the screen
CONFIRM = 2           # a diamond must be seen this many times in a row (not a flicker)
MOVE_PAUSE = 0.06     # s to wait after moving the cursor / before and after letting go
AFTER_CLICK = 0.6     # s not to look for diamonds after one was clicked (it disappears)
SAME_SPOT = 0.04      # x window height: a diamond still there after clicking it ...
MAX_TRIES = 3         # ... is clicked at most this many times, then left alone for a while
GIVE_UP = 10.0        # s to leave such a spot alone
WIGGLE_EVERY = 60.0   # s: move the mouse by 1 pixel and back (Roblox idle kick)
AWAKE_EVERY = 30.0    # s: tell Windows again that the screen is in use


def load_settings():
    try:
        with open(CONFIG) as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    return {"require_focus": bool(s.get("require_focus", True)), "hold": bool(s.get("hold", True))}


def save_settings(s):
    try:
        with open(CONFIG, "w") as f:
            json.dump(s, f, indent=2)
    except OSError:
        pass


class DiamondRunner:
    """The clicking logic. io must have: grab() -> (picture, window area) or (None, None), cursor(),
    move(x, y) (screen pixels), button(down), focused(), now(), awake(), sleep(s)."""

    def __init__(self, io, hold=True, log=lambda text: None):
        self.io, self.hold, self.log = io, hold, log
        self.held = False
        self.seen = 0            # times in a row a diamond was seen
        self.quiet_until = 0.0
        self.tries = []          # (time, x, y) of recent clicks, to notice a diamond that won't go away
        self.blocked = []        # (until, x, y): spots left alone for a while
        self.clicked = 0
        now = io.now()
        self.next_wiggle, self.next_awake = now + WIGGLE_EVERY, now

    def release(self):
        if self.held:
            self.io.button(False)
            self.held = False

    def step(self):
        """Returns "running", "paused" (Roblox not in front) or "no_window"."""
        from diamonds import find_diamonds
        io, now = self.io, self.io.now()
        if now >= self.next_awake:
            io.awake()
            self.next_awake = now + AWAKE_EVERY
        frame, area = io.grab()
        if frame is None:
            self.release()
            return "no_window"
        if not io.focused():
            self.release()
            self.seen = 0
            return "paused"
        if self.hold and not self.held:
            io.button(True)
            self.held = True
        if now >= self.next_wiggle:  # still here (Roblox idle kick)
            x, y = io.cursor()
            io.move(x + 1, y)
            io.sleep(0.03)
            io.move(x, y)
            self.next_wiggle = now + WIGGLE_EVERY
        if now < self.quiet_until:
            return "running"
        H = frame.shape[0]
        self.blocked = [b for b in self.blocked if b[0] > now]
        found = [d for d in find_diamonds(frame)
                 if not any(abs(d[0] - bx) < SAME_SPOT * H * 2 and abs(d[1] - by) < SAME_SPOT * H * 2
                            for _, bx, by in self.blocked)]
        if not found:
            self.seen = 0
            return "running"
        self.seen += 1
        if self.seen < CONFIRM:
            return "running"
        x, y, _ = found[0]
        self.tries = [t for t in self.tries if now - t[0] < GIVE_UP]
        again = [t for t in self.tries if abs(t[1] - x) < SAME_SPOT * H and abs(t[2] - y) < SAME_SPOT * H]
        if len(again) >= MAX_TRIES:
            self.blocked.append((now + GIVE_UP, x, y))
            self.log(f"A diamond at ({x:.0f}, {y:.0f}) didn't go away after {MAX_TRIES} clicks; leaving it "
                     f"alone for {GIVE_UP:.0f} s.")
            return "running"
        self._grab_diamond(area["left"] + x, area["top"] + y)
        self.tries.append((now, x, y))
        self.clicked += 1
        self.seen = 0
        self.quiet_until = io.now() + AFTER_CLICK
        return "running"

    def _grab_diamond(self, sx, sy):
        """Cursor to the diamond, let go of the left button, hold it again, cursor back."""
        io = self.io
        home = io.cursor()
        io.move(int(sx), int(sy))
        io.sleep(MOVE_PAUSE)
        io.button(False)
        io.sleep(MOVE_PAUSE)
        io.button(True)
        self.held = True
        io.sleep(MOVE_PAUSE)
        io.move(*home)
        if not self.hold:  # (holding is off: just a click on the diamond)
            io.button(False)
            self.held = False


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
                    self.runner = DiamondRunner(self.io, self.settings["hold"], log=lambda t: self.on_event("log", t))
                    self.running, last = True, None
                    self.on_event("log", "Started: holding the left mouse button, watching for diamonds.")
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
            shown = {"running": "Running", "paused": "Paused (Roblox isn't the window in front)",
                     "no_window": "Roblox window not found"}[status]
            if shown != last:
                self.on_event("status", shown)
                last = shown
            self.on_event("count", str(self.runner.clicked))
            time.sleep(max(0.0, LOOK_EVERY - (time.perf_counter() - t0)))
        if self.running:
            self._halt("Stopped")

    def _halt(self, text):
        self.running = False
        try:
            self.runner.release()
        finally:
            self.io.close()
        self.on_event("status", text)
        self.on_event("log", f"{text}. Diamonds clicked: {self.runner.clicked}.")

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
    tk.Label(box, text="  diamonds:", bg=PANEL, fg=MUTED, font=FONT).pack(side="left")
    tk.Label(box, textvariable=count, bg=PANEL, fg=FG, font=("Segoe UI Semibold", 12)).pack(side="left")
    row = tk.Frame(wrap, bg=BG)
    row.pack(fill="x")
    ttk.Button(row, text="Start  ( * )", command=bot._start.set).pack(side="left", expand=True, fill="x", padx=(0, 6))
    ttk.Button(row, text="Stop  ( - )", command=bot._stop.set).pack(side="left", expand=True, fill="x")
    tk.Label(wrap, text=hot, bg=BG, fg=MUTED, font=FONT).pack(anchor="w", pady=(6, 8))
    hold = tk.BooleanVar(value=bot.settings["hold"])
    focus = tk.BooleanVar(value=bot.settings["require_focus"])

    def save():
        bot.settings.update(hold=bool(hold.get()), require_focus=bool(focus.get()))
        save_settings(bot.settings)
    ttk.Checkbutton(wrap, text="Hold the left mouse button (off: only click the diamonds)", variable=hold,
                    command=save).pack(anchor="w")
    ttk.Checkbutton(wrap, text="Only while Roblox is the window in front", variable=focus,
                    command=save).pack(anchor="w", pady=(2, 8))
    tk.Label(wrap, text="Put the mouse where it should hold, then press *. Changes apply at the next Start.",
             bg=BG, fg=MUTED, font=FONT).pack(anchor="w")
    log = tk.Text(wrap, height=8, width=70, bg=PANEL, fg=FG, font=MONO, relief="flat",
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
    write("Open Roblox at the hay bales, put the mouse where it should hold, then press * (or Start).")
    root.after(100, poll)
    root.mainloop()


def selftest():
    """For the exe build: it finds a drawn diamond in drawn hay, and the click sequence is right."""
    import cv2
    import numpy as np
    img = np.full((720, 1280, 3), (63, 140, 183), np.uint8)               # hay
    pts = np.array([[700, 300], [760, 340], [740, 420], [670, 430], [640, 350]], np.int32)
    cv2.fillPoly(img, [pts], (192, 183, 113))                               # diamond
    from diamonds import find_diamonds
    found = find_diamonds(img)
    if len(found) != 1 or abs(found[0][0] - 700) > 30 or abs(found[0][1] - 365) > 30:
        return False

    class FakeIO:
        def __init__(self):
            self.t, self.calls, self.pos = 0.0, [], (100, 100)
        def grab(self): return img, {"left": 10, "top": 20, "width": 1280, "height": 720}  # noqa: E301,E704
        def cursor(self): return self.pos  # noqa: E704
        def move(self, x, y): self.calls.append(("move", x, y)); self.pos = (x, y)  # noqa: E702,E704
        def button(self, down): self.calls.append(("button", down))  # noqa: E704
        def focused(self): return True  # noqa: E704
        def now(self): return self.t  # noqa: E704
        def awake(self): pass  # noqa: E704
        def sleep(self, s): self.t += s  # noqa: E704
    io = FakeIO()
    r = DiamondRunner(io)
    for _ in range(3):
        r.step()
        io.t += LOOK_EVERY
    c = io.calls
    return (c[0] == ("button", True) and ("button", False) in c and r.clicked == 1 and
            c[-1] == ("move", 100, 100) and any(m[0] == "move" and abs(m[1] - 710) < 30 for m in c))


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
