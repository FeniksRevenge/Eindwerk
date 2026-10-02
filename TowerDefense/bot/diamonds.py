"""
Finding the light-blue diamonds in the hay bales (for DiamondBot).

The diamond is a flat light blue (hue ~88-97 on OpenCV's 0-180 scale, medium saturation, bright); the hay
is yellow-brown (hue ~19), so that light blue is only ever a diamond. Light-blue pieces lying close
together are one diamond (hay straws cut a half-hidden one into slivers); together they must be big enough.
"""

import cv2
import numpy as np

HUE = (80, 108)        # light blue / cyan
SAT_MIN = 45
VAL_MIN = 120
MIN_AREA = 0.00002     # of the window's area, all visible pieces of one diamond together
MAX_AREA = 0.12        # bigger than this is sky or a UI panel, not a diamond
GROUP = 0.025          # x window height: blue pieces this close together are one (half-hidden) diamond
MIN_PIECE = 4          # px (at the size it looks): smaller specks are ignored


def find_diamonds(bgr, min_area=MIN_AREA):
    """[(x, y, area_fraction)] of the diamonds in the picture, biggest first. x, y is the middle of the
    biggest visible piece (a diamond deep in the hay shows only a few slivers: click on one of them)."""
    h, w = bgr.shape[:2]
    s = max(1, int(round(h / 1400)))  # (near full size: a buried diamond shows only slivers of a few px)
    small = cv2.resize(bgr, (w // s, h // s), interpolation=cv2.INTER_AREA) if s > 1 else bgr
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (HUE[0], SAT_MIN, VAL_MIN), (HUE[1], 255, 255)) // 255
    if not m.any():
        return []
    n, labels, stats, cent = cv2.connectedComponentsWithStats(m, connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= MIN_PIECE
    m = keep[labels].astype(np.uint8)
    # group pieces that lie close together (hay straws across one diamond cut it into pieces); done on a
    # 4x smaller mask (fast)
    q = 4
    mq = cv2.resize(m, (m.shape[1] // q + 1, m.shape[0] // q + 1), interpolation=cv2.INTER_AREA)
    mq = cv2.dilate((mq > 0).astype(np.uint8), np.ones((3, 3), np.uint8))
    g = max(3, int(GROUP * m.shape[0] / q))
    groups = cv2.dilate(mq, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (g, g)))
    ng, glabels = cv2.connectedComponents(groups, connectivity=8)
    total = m.shape[0] * m.shape[1]
    best = {}  # group -> (biggest piece area, x, y, group area)
    for j in np.flatnonzero(keep):
        x, y, bw, bh, area = stats[j]
        gid = glabels[int(cent[j][1]) // q, int(cent[j][0]) // q] or glabels[(y + bh // 2) // q, (x + bw // 2) // q]
        a_big, cx, cy, a_sum = best.get(gid, (0, 0.0, 0.0, 0))
        if area > a_big:
            a_big, cx, cy = area, cent[j][0], cent[j][1]
        best[gid] = (a_big, cx, cy, a_sum + area)
    out = []
    for gid, (a_big, cx, cy, a_sum) in best.items():
        frac = a_sum / total
        if min_area <= frac <= MAX_AREA:
            out.append((float(cx * s), float(cy * s), float(frac)))
    out.sort(key=lambda d: -d[2])
    return out


def annotate(bgr, diamonds):
    img = bgr.copy()
    for x, y, frac in diamonds:
        r = int(max(8, (frac * img.shape[0] * img.shape[1] / 3.14) ** 0.5))
        cv2.circle(img, (int(x), int(y)), r, (255, 0, 255), 3)
        cv2.drawMarker(img, (int(x), int(y)), (255, 0, 255), cv2.MARKER_CROSS, 20, 2)
    return img
