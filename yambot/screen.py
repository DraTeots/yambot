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


def find_all_on_image(image, template_path, threshold=0.80, scales=None, max_results=50):
    """Locate *every* occurrence of ``template_path`` inside ``image`` (BGR).

    :func:`find_on_image` returns only the single best match (``minMaxLoc`` picks
    one peak). When the same button repeats — e.g. a "fire" icon on each friend
    card — we want them all. The repeated buttons are the same on-screen size, so
    we first find the best scale (one quick sweep), then collect every peak at
    that scale that clears ``threshold``.

    Each real button lights up a whole cluster of neighboring pixels above
    threshold, so after taking a peak we blank its template-sized neighborhood
    before looking for the next — greedy non-maximum suppression. Returns a list
    of ``(x, y, w, h, score)`` sorted strongest-first, capped at ``max_results``.
    """
    template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise FileNotFoundError(template_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    if scales is None:
        scales = np.linspace(0.8, 2.5, 18)

    # Pass 1: find the single best scale (assumes the repeats share one size).
    th, tw = template.shape[:2]
    best = None  # (score, w, h)
    for s in scales:
        w, h = int(tw * s), int(th * s)
        if w < 8 or h < 8 or w > gray.shape[1] or h > gray.shape[0]:
            continue
        resized = cv2.resize(template, (w, h), interpolation=cv2.INTER_AREA)
        res = cv2.matchTemplate(gray, resized, cv2.TM_CCOEFF_NORMED)
        _, score, _, _ = cv2.minMaxLoc(res)
        if best is None or score > best[0]:
            best = (score, w, h)

    if best is None:
        return []

    # Pass 2: at the winning scale, harvest every peak above threshold.
    _, w, h = best
    resized = cv2.resize(template, (w, h), interpolation=cv2.INTER_AREA)
    res = cv2.matchTemplate(gray, resized, cv2.TM_CCOEFF_NORMED)

    matches = []
    while len(matches) < max_results:
        _, score, _, loc = cv2.minMaxLoc(res)
        if score < threshold:
            break
        matches.append((loc[0] + w // 2, loc[1] + h // 2, w, h, float(score)))
        # Suppress this button's neighborhood so the next iteration finds a
        # *different* button, not the same peak's shoulder. -1 is below any
        # threshold for TM_CCOEFF_NORMED (range -1..1).
        x0, y0 = max(loc[0] - w // 2, 0), max(loc[1] - h // 2, 0)
        x1, y1 = loc[0] + w // 2, loc[1] + h // 2
        res[y0:y1, x0:x1] = -1.0

    return matches


def check_is_active(arrow_crop, active_template_path, passive_template_path):
    """Classify a cropped button as active or disabled by nearest color match.

    Some buttons (e.g. the pager arrows) are the *same shape* in both states and
    differ only in tone — a vivid-green "enabled" vs. a muted-gray "disabled".
    :func:`find_on_image` matches on grayscale and is brightness-invariant, so it
    locates the button but can't tell the states apart. Here we compare the crop
    against two reference images and let the closer one win.

    The metric is a raw per-pixel absolute difference in *color* (not a
    normalized correlation): we deliberately want sensitivity to brightness/tone,
    which is the entire signal. Lower distance == closer == winner.

    ``arrow_crop`` is a BGR crop of the located button. Returns
    ``(is_active, dist_active, dist_passive)`` — the two distances are returned so
    the caller can judge confidence (near-equal == a weak/misaligned match).
    """
    h, w = arrow_crop.shape[:2]

    def distance(template_path):
        ref = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
        if ref is None:
            raise FileNotFoundError(template_path)
        ref = cv2.resize(ref, (w, h), interpolation=cv2.INTER_AREA)
        return float(cv2.absdiff(arrow_crop, ref).mean())  # lower == closer

    dist_active = distance(active_template_path)
    dist_passive = distance(passive_template_path)
    return dist_active < dist_passive, dist_active, dist_passive


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
