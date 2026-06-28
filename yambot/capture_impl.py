"""Lower implementation layer for screen capture.

:func:`yambot.screen.screenshot` is the public upper layer; it delegates the
actual grab to one of the impls here, chosen by :func:`make_capture_impl` per
OS. The interface is intentionally tiny — ``grab(path) -> BGR ndarray`` — so the
capture backend stays swappable later (e.g. a different Windows grabber, or a
per-window capture) without touching the matching code.

Heavy/OS-specific libraries (``mss``) are imported lazily so importing this
module never pulls them in on Linux.
"""

import subprocess
import sys

import cv2


class SpectacleCaptureImpl:
    """Linux/Wayland capture via Spectacle (KDE's grabber). Unchanged behaviour.

    ``-b -n -f`` runs it headless (no GUI, no notification, full screen) and
    ``-o`` chooses the output file; we read it back with OpenCV so the rest of
    the pipeline gets a numpy array.
    """

    def grab(self, path):
        path = str(path)
        subprocess.run(
            ["spectacle", "-b", "-n", "-f", "-o", path],
            check=True,
            stderr=subprocess.DEVNULL,
        )
        img = cv2.imread(path)
        if img is None:
            raise RuntimeError(f"could not read screenshot at {path}")
        return img


class MssCaptureImpl:
    """Windows capture via ``mss`` — a fast, dependency-light full-screen grab.

    ``mss`` returns a BGRA buffer; we drop the alpha channel to hand OpenCV the
    BGR array it expects. ``path`` is accepted for interface parity (and used to
    mirror the on-disk screenshot the Linux path leaves behind), but capture
    itself goes straight to memory.

    TODO(HiDPI): the returned frame is in *physical* pixels. On scaled Windows
    displays that differs from the pointer's logical coordinate space, so clicks
    derived from these coordinates can be off. The scaling fix belongs here in
    the screen layer and is deliberately deferred for now.
    """

    def __init__(self):
        import mss  # lazy: only imported on Windows
        import numpy as np

        self._np = np
        self._sct = mss.mss()

    def grab(self, path):
        monitor = self._sct.monitors[0]  # the full virtual screen
        shot = self._sct.grab(monitor)
        img = self._np.array(shot)[:, :, :3]  # BGRA -> BGR
        if path is not None:
            cv2.imwrite(str(path), img)
        return img


def make_capture_impl():
    """Pick the capture impl for the current OS.

    Linux -> Spectacle (unchanged); Windows -> mss.
    """
    if sys.platform.startswith("linux"):
        return SpectacleCaptureImpl()
    if sys.platform == "win32":
        return MssCaptureImpl()
    raise RuntimeError(f"yambot: no capture backend for platform {sys.platform!r}")
