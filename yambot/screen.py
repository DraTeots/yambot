"""Screen capture and on-screen button location.

This module is the *eyes* of yambot. It has no opinion about input devices —
it only grabs a frame, finds a template inside it, and can annotate/save the
result for debugging. Driving the mouse lives in :mod:`yambot.mouse`.
"""

import subprocess
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

#: Where a freshly grabbed full-screen frame is written by default.
VISUAL_LOG = Path("captures")
SCREENSHOT_PATH = VISUAL_LOG / "screenshot.png"


def screenshot(path=SCREENSHOT_PATH):
    """Capture the full screen via Spectacle, save to ``path``, return a BGR image.

    Spectacle is the KDE screen grabber; ``-b -n -f`` makes it run headless
    (no GUI, no notification, full screen) and ``-o`` chooses the output file.
    We read the file back with OpenCV so the rest of the pipeline gets a numpy
    array.
    """
    path = Path(path)
    subprocess.run(
        ["spectacle", "-b", "-n", "-f", "-o", str(path)],
        check=True,
        stderr=subprocess.DEVNULL,
    )
    img = cv2.imread(str(path))
    if img is None:
        raise RuntimeError(f"could not read screenshot at {path}")
    return img


def find_on_image(image, template_path, threshold=0.80, scales=None):
    """Locate ``template_path`` inside ``image`` (BGR) by template matching.

    Sweeps a range of scales so a minified template still matches a larger
    on-screen button. Returns ``(x, y, is_ok, score, w, h)`` — the matched
    region's center pixel, whether ``score`` cleared ``threshold``, the score
    itself, and the matched width/height — or ``None`` if no scale fit the image.
    """
    template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise FileNotFoundError(template_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # template is minified -> on-screen button is bigger -> scale template up.
    # widen/narrow once you know the real ratio (see notes).
    if scales is None:
        scales = np.linspace(0.8, 2.5, 18)

    best = None  # (score, x_center, y_center, w, h)
    th, tw = template.shape[:2]
    for s in scales:
        width, height = int(tw * s), int(th * s)
        if width < 8 or height < 8 or width > gray.shape[1] or height > gray.shape[0]:
            continue
        resized = cv2.resize(template, (width, height), interpolation=cv2.INTER_AREA)
        res = cv2.matchTemplate(gray, resized, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if best is None or score > best[0]:
            best = (score, loc[0] + width // 2, loc[1] + height // 2, width, height)

    if best is None:
        return None

    # This is for simpler reading
    score, x, y, width, height = best
    is_ok = score >= threshold  # TM_CCOEFF_NORMED: higher == better match
    return x, y, width, height, score, is_ok


def save_to_folder(image, folder, suffix=""):
    """Save ``image`` to ``folder`` named by current time (ms) + optional suffix."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # millisecond precision
    name = f"{ts}_{suffix}.png" if suffix else f"{ts}.png"
    path = folder / name
    cv2.imwrite(str(path), image)
    return path


def mark_circle(image, x, y, radius=40, thickness=4, color=(0, 0, 255)):
    """Draw a red circle at ``(x, y)`` on a copy and return it.

    Marks the interaction point (where the mouse clicks). Only draws — the
    caller decides whether to :func:`save` the result.
    """
    out = image.copy()
    cv2.circle(out, (x, y), radius, color, thickness)  # (0,0,255)=red in BGR
    return out


def mark_box(image, x, y, w, h, thickness=3, color=(0, 255, 0)):
    """Draw a ``w``x``h`` rectangle centered at ``(x, y)`` on a copy and return it.

    Outlines the region where a subimage was matched (pairs with :func:`mark`,
    which circles the click point). Fed straight from :func:`find_on_image`'s
    returned center + ``w``/``h``, it reproduces the matched box exactly. Only
    draws — the caller decides whether to :func:`save` the result.
    """
    out = image.copy()
    x0, y0 = x - w // 2, y - h // 2
    cv2.rectangle(out, (x0, y0), (x0 + w, y0 + h), color, thickness)  # green in BGR
    return out
