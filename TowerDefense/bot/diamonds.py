"""
Finding the light-blue diamonds in the hay bales (for DiamondBot).

The diamond is a flat light blue (hue ~88-97 on OpenCV's 0-180 scale, medium saturation, bright); the hay
is yellow-brown (hue ~19). So: light-blue pixels, grouped into solid blobs at least a minimum size.
"""

import cv2
import numpy as np

HUE = (80, 108)        # light blue / cyan
SAT_MIN = 45
VAL_MIN = 120
MIN_AREA = 0.00002     # of the window's area (a small, half-hidden diamond can be ~0.006%; a close one ~1%)
MAX_AREA = 0.12        # bigger than this is sky or a UI panel, not a diamond


def find_diamonds(bgr, min_area=MIN_AREA):
    """[(x, y, area_fraction)] of the diamonds in the picture, biggest first (x, y in picture pixels)."""
    h, w = bgr.shape[:2]
    s = max(1, int(round(h / 720)))  # look at it at ~720 px high (small, half-hidden diamonds too)
    small = cv2.resize(bgr, (w // s, h // s), interpolation=cv2.INTER_AREA) if s > 1 else bgr
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    m = ((hsv[..., 0] >= HUE[0]) & (hsv[..., 0] <= HUE[1]) & (hsv[..., 1] >= SAT_MIN) &
         (hsv[..., 2] >= VAL_MIN)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))   # (single specks)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))  # (hay straws across a diamond)
    n, _labels, stats, cent = cv2.connectedComponentsWithStats(m, connectivity=8)
    total = m.shape[0] * m.shape[1]
    out = []
    for j in range(1, n):
        x, y, bw, bh, area = stats[j]
        frac = area / total
        if not (min_area <= frac <= MAX_AREA):
            continue
        if area < 0.25 * bw * bh or max(bw, bh) > 4 * min(bw, bh):
            continue  # a diamond (even half hidden in the hay) is a blob, not a thin line or scattered specks
        out.append((float(cent[j][0] * s), float(cent[j][1] * s), float(frac)))
    out.sort(key=lambda d: -d[2])
    return out


def annotate(bgr, diamonds):
    img = bgr.copy()
    for x, y, frac in diamonds:
        r = int(max(8, (frac * img.shape[0] * img.shape[1] / 3.14) ** 0.5))
        cv2.circle(img, (int(x), int(y)), r, (255, 0, 255), 3)
        cv2.drawMarker(img, (int(x), int(y)), (255, 0, 255), cv2.MARKER_CROSS, 20, 2)
    return img
