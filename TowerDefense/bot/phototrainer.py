"""
Photo trainer: teaches the bot from the screenshots you saved with /.

It opens every photo in the screenshots folder, one after another, and shows what the bot
detected (its "answer"). What it learns is stored in config.json:
- colors and sizes of each kind of thing (averaged over every confirmed example), and
- an ignore list of things you said are "not a thing" (HUD bits, chat icons, ...).

Semi-auto: you check each photo.
    ENTER            the answer is right (learn from it), next photo
    click a circle   it's wrong: pick what it really is, or X = not a thing
    click elsewhere  it missed something: pick what it is
    U                undo your last correction
    S                skip this photo (it's kept)
    Esc              stop (the current photo is kept)
Auto: goes through all photos by itself and only learns from detections it's sure about.

Every photo that's done is deleted, together with its _bot.png and .json.
"""

import glob
import os

import cv2
import numpy as np

from vision import CLASS_HELP, CLASSES, DRAW_COLORS, Detector, measure_blob

KEYS = "abcdefghijk"  # menu keys, one per class in CLASSES order
MAX_WEIGHT = 30       # new examples always keep at least ~3% influence, so it keeps adapting


def list_photos(folder):
    return sorted(p for p in glob.glob(os.path.join(folder, "shot_*.png")) if not p.endswith("_bot.png"))


def delete_photo(path):
    base = path[:-4]
    for p in (path, base + "_bot.png", base + ".json"):
        try:
            os.remove(p)
        except OSError:
            pass


def learn(cfg, cls, lab, radius):
    """Blend one confirmed example into what the bot knows about this kind of thing."""
    colors = cfg.setdefault("colors", {})
    c = colors.get(cls)
    if not c or not c.get("lab"):
        colors[cls] = {"lab": [int(round(v)) for v in lab], "radius": round(float(radius), 1), "n": 1}
        return
    n = min(int(c.get("n", 5)), MAX_WEIGHT)
    c["lab"] = [int(round((old * n + new) / (n + 1))) for old, new in zip(c["lab"], lab)]
    c["radius"] = round((float(c["radius"]) * n + float(radius)) / (n + 1), 1)
    c["n"] = n + 1


def forget(cfg, lab, radius):
    """Remember that this color+size is not a thing."""
    ignore = cfg.setdefault("ignore", [])
    for ig in ignore:
        if np.all(np.abs(np.array(ig["lab"]) - np.array(lab)) < 6) and 0.8 < radius / ig["radius"] < 1.25:
            return
    ignore.append({"lab": [int(round(v)) for v in lab], "radius": round(float(radius), 1)})


# --------------------------------------------------------------------------- auto
def confident(det, cfg):
    """Only learn by itself from detections that already match well (color and size)."""
    c = cfg["colors"].get(det["cls"])
    if not c:
        return False
    tol = np.array(cfg.get("tolerance", [30, 14, 14]))
    color_ok = np.all(np.abs(np.array(det["lab"]) - np.array(c["lab"])) <= tol * 0.5)
    return color_ok and 0.75 <= det["r"] / float(c["radius"]) <= 1.33


def train_auto(cfg, folder, progress=lambda text: None):
    photos = list_photos(folder)
    learned, skipped = {}, 0
    for i, path in enumerate(photos, 1):
        img = cv2.imread(path)
        if img is None:
            delete_photo(path)
            continue
        det = Detector(cfg)  # rebuilt each photo so it uses what it just learned
        for d in det.detect_detailed(img):
            if confident(d, cfg):
                learn(cfg, d["cls"], d["lab"], d["r"])
                learned[d["cls"]] = learned.get(d["cls"], 0) + 1
            else:
                skipped += 1
        delete_photo(path)
        progress(f"Photo {i}/{len(photos)} done")
    if not photos:
        return "No photos to train on. Press / while playing to save some."
    parts = ", ".join(f"{k} x{v}" for k, v in sorted(learned.items())) or "nothing it was sure about"
    return f"Trained on {len(photos)} photo(s). Learned from: {parts}. Unsure about {skipped} detection(s), left those alone."


# --------------------------------------------------------------------------- semi-auto
def _fit(img, max_w=1500, max_h=850):
    s = min(1.0, max_w / img.shape[1], max_h / img.shape[0])
    return cv2.resize(img, (int(img.shape[1] * s), int(img.shape[0] * s)), interpolation=cv2.INTER_AREA), s


def _bar(img, lines):
    out = img.copy()
    h = 22 * len(lines) + 10
    cv2.rectangle(out, (0, 0), (out.shape[1], h), (0, 0, 0), -1)
    for i, t in enumerate(lines):
        cv2.putText(out, t, (10, 22 + 22 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 255, 140), 1, cv2.LINE_AA)
    return out


def _draw(disp, s, items):
    out = disp.copy()
    for it in items:
        x, y, r = int(it["x"] * s), int(it["y"] * s), max(4, int(it["r"] * s))
        if it["status"] == "wrong":
            cv2.circle(out, (x, y), r + 3, (60, 60, 60), 2)
            cv2.line(out, (x - r, y - r), (x + r, y + r), (0, 0, 255), 2)
            cv2.line(out, (x - r, y + r), (x + r, y - r), (0, 0, 255), 2)
            continue
        color = DRAW_COLORS.get(it["cls"], (255, 255, 255))
        cv2.circle(out, (x, y), r + 3, color, 2 if it["status"] == "ok" else 3)
        label = it["cls"] + ("" if it["status"] == "ok" else " *")
        cv2.putText(out, label, (x - r, y - r - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return out


def _menu(win, img, title):
    """Ask which kind of thing this is. Returns a class name, "none" (not a thing) or None (cancel)."""
    lines = [title] + [f"  {KEYS[i]} = {name}   ({CLASS_HELP[name]})" for i, name in enumerate(CLASSES)]
    lines += ["  x = NOT A THING (ignore it from now on)", "  Esc = cancel"]
    cv2.imshow(win, _bar(img, lines))
    while True:
        k = cv2.waitKey(0) & 0xFF
        if k == 27:
            return None
        if k == ord("x"):
            return "none"
        if chr(k) in KEYS[:len(CLASSES)]:
            return CLASSES[KEYS.index(chr(k))]


def train_semi(cfg, folder, save):
    """Photo-by-photo review. `save(cfg)` is called after every finished photo."""
    photos = list_photos(folder)
    if not photos:
        print("No photos to train on. Press / while playing to save some.")
        return
    win = "Photo trainer"
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)
    try:
        cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)
    except Exception:
        pass
    clicks = []
    cv2.setMouseCallback(win, lambda ev, x, y, *_: clicks.append((x, y)) if ev == cv2.EVENT_LBUTTONDOWN else None)

    for n, path in enumerate(photos, 1):
        img = cv2.imread(path)
        if img is None:
            delete_photo(path)
            continue
        disp, s = _fit(img)
        items = [dict(d, status="ok") for d in Detector(cfg).detect_detailed(img)]
        history = []
        while True:
            help_lines = [f"Photo {n}/{len(photos)}: is this right?   ENTER = yes, learn + next    S = skip    Esc = stop",
                          "Click a circle = it's wrong    Click something without a circle = it was missed    U = undo"]
            cv2.imshow(win, _bar(_draw(disp, s, items), help_lines))
            clicks.clear()
            k = -1
            while not clicks and k not in (13, 27, ord("s"), ord("u")):
                k = cv2.waitKey(30) & 0xFF
            if k == 27:
                cv2.destroyAllWindows()
                return
            if k == ord("s"):
                break
            if k == ord("u"):
                if history:
                    history.pop()()
                continue
            if k == 13:
                for it in items:
                    if it["status"] == "wrong":
                        forget(cfg, it["lab"], it["r"])
                    else:
                        learn(cfg, it["cls"], it["lab"], it["r"])
                save(cfg)
                delete_photo(path)
                break
            # A click: on an existing circle (wrong answer) or on something missed.
            cx, cy = clicks[0][0] / s, clicks[0][1] / s
            hit = next((it for it in items if it["status"] != "wrong"
                        and (it["x"] - cx) ** 2 + (it["y"] - cy) ** 2 <= (it["r"] + 8) ** 2), None)
            shown = _draw(disp, s, items)
            if hit is not None:
                choice = _menu(win, shown, f"The bot said '{hit['cls']}'. What is it really?")
                if choice is None:
                    continue
                old = dict(hit)
                history.append(lambda it=hit, old=old: it.update(old))
                if choice == "none":
                    hit["status"] = "wrong"
                else:
                    hit.update(cls=choice, status="fixed")
            else:
                choice = _menu(win, shown, "What did the bot miss here?")
                if choice in (None, "none"):
                    continue
                lab, radius = measure_blob(img, int(cx), int(cy))
                if lab is None:
                    cv2.imshow(win, _bar(shown, ["That's background. Click right on the colored part.  (any key)"]))
                    cv2.waitKey(0)
                    continue
                new = {"cls": choice, "name": choice, "x": cx, "y": cy, "r": radius, "lab": lab, "status": "added"}
                items.append(new)
                history.append(lambda it=new: items.remove(it))
    cv2.destroyAllWindows()
