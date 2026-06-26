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



_PKG_DIR = Path(__file__).parent
TEMPLATES_DIR = _PKG_DIR / "templates"

VISUAL_LOG = Path("captures")
SCREENSHOT_PATH = VISUAL_LOG / "screenshot.png"

#: The button we hunt for each cycle. Ships inside the package.
TEMPLATE_ISL_COLLECT_BUTTON = TEMPLATES_DIR / "collect_all.png"
TEMPLATE_ISL_CLOSE_BUTTON = TEMPLATES_DIR / "close_button.png"
TEMPLATE_MAP_SEPARATOR = TEMPLATES_DIR / "island_list_separator.png"
TEMPLATE_MAP_MAIN_PLANT = TEMPLATES_DIR / "main_01_plant.png"
TEMPLATE_MAP_MAIN_COLD = TEMPLATES_DIR / "main_02_cold.png"
TEMPLATE_MAP_MAIN_AIR = TEMPLATES_DIR / "main_03_air.png"

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
        w, h = int(tw * s), int(th * s)
        if w < 8 or h < 8 or w > gray.shape[1] or h > gray.shape[0]:
            continue
        resized = cv2.resize(template, (w, h), interpolation=cv2.INTER_AREA)
        res = cv2.matchTemplate(gray, resized, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if best is None or score > best[0]:
            best = (score, loc[0] + w // 2, loc[1] + h // 2, w, h)

    if best is None:
        return None

    # This is for simpler reading
    score, x, y, w, h = best
    is_ok = score >= threshold  # TM_CCOEFF_NORMED: higher == better match
    return x, y, is_ok, score, w, h


def save(image, folder, suffix=""):
    """Save ``image`` to ``folder`` named by current time (ms) + optional suffix."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # millisecond precision
    name = f"{ts}_{suffix}.png" if suffix else f"{ts}.png"
    path = folder / name
    cv2.imwrite(str(path), image)
    return path


def mark(image, x, y, radius=40, thickness=4):
    """Draw a red circle at ``(x, y)`` on a copy and return it.

    Marks the interaction point (where the mouse clicks). Only draws — the
    caller decides whether to :func:`save` the result.
    """
    out = image.copy()
    cv2.circle(out, (x, y), radius, (0, 0, 255), thickness)  # (0,0,255)=red in BGR
    return out


def box(image, x, y, w, h, thickness=3):
    """Draw a ``w``x``h`` rectangle centered at ``(x, y)`` on a copy and return it.

    Outlines the region where a subimage was matched (pairs with :func:`mark`,
    which circles the click point). Fed straight from :func:`find_on_image`'s
    returned center + ``w``/``h``, it reproduces the matched box exactly. Only
    draws — the caller decides whether to :func:`save` the result.
    """
    out = image.copy()
    x0, y0 = x - w // 2, y - h // 2
    cv2.rectangle(out, (x0, y0), (x0 + w, y0 + h), (0, 255, 0), thickness)  # green in BGR
    return out
