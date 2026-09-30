"""Key waiting for OpenCV windows that also notices when you close the window with its X
(otherwise the program keeps waiting for a key forever, invisibly)."""

import cv2

ESC = 27
NO_KEY = 255


def window_closed(win):
    try:
        return cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return True


def key(win, delay=30):
    """Like cv2.waitKey(delay) & 0xFF, but returns ESC if the window was closed."""
    k = cv2.waitKey(delay) & 0xFF
    if k == NO_KEY and window_closed(win):
        return ESC
    return k


def key_blocking(win):
    """Wait until a key is pressed (or the window is closed -> ESC)."""
    while True:
        k = key(win, 50)
        if k != NO_KEY:
            return k
