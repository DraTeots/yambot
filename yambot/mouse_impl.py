"""Lower implementation layer for the virtual mouse.

:class:`~yambot.mouse.VirtualMouse` is the public upper layer; it delegates the
actual device work to one of the impls here, chosen by :func:`make_mouse_impl`
at construction time. Each impl only needs three operations — **move**,
**left-click**, **scroll** — which is all yambot uses.

Third-party libraries are imported lazily inside each impl (not at module top
level) so importing this module never drags in ``evdev`` on Windows or
``pynput`` on Linux.
"""

import sys
import time


class EvdevMouseImpl:
    """Linux/Wayland mouse: an absolute virtual pointer via evdev/uinput.

    Moved verbatim from the original ``VirtualMouse`` so Linux behaviour is
    unchanged. We declare ABSOLUTE X/Y axes spanning ``0..=65535``; the
    compositor stretches that range onto the real screen, so we map a pixel
    found in a screenshot using the *screenshot's own* dimensions and never need
    the real screen resolution.

    Creating the device needs write access to ``/dev/uinput`` — join the
    ``input`` group (see the README).
    """

    #: Absolute-axis range. The compositor stretches this onto the whole screen.
    ABS_MIN = 0
    ABS_MAX = 65535
    ABS_CENTER = (ABS_MIN + ABS_MAX) // 2

    #: libinput convention: 120 high-resolution wheel units == one wheel detent.
    WHEEL_HI_RES_PER_NOTCH = 120

    def __init__(self, name="yambot-virtual-mouse", warmup=0.3):
        from evdev import AbsInfo, UInput
        from evdev import ecodes as e

        self._e = e
        abs_axis = AbsInfo(
            value=self.ABS_CENTER, min=self.ABS_MIN, max=self.ABS_MAX, fuzz=0, flat=0, resolution=0
        )
        capabilities = {
            e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT],
            # The wheel is a *relative* axis even though pointing is absolute.
            e.EV_REL: [e.REL_WHEEL, e.REL_WHEEL_HI_RES],
            e.EV_ABS: [(e.ABS_X, abs_axis), (e.ABS_Y, abs_axis)],
        }
        self.input = UInput(capabilities, name=name)
        # The compositor needs a beat to notice the new device before the first
        # event will be routed anywhere. Same 300ms the Rust version waits.
        time.sleep(warmup)

    @classmethod
    def _to_abs(cls, value, span):
        """Map a pixel coordinate in ``0..span-1`` onto the ``ABS_MIN..ABS_MAX`` range."""
        if span <= 1:
            return cls.ABS_CENTER
        frac = min(max(value / (span - 1), 0.0), 1.0)
        return cls.ABS_MIN + round(frac * (cls.ABS_MAX - cls.ABS_MIN))

    def move_to(self, x, y, width, height):
        """Jump the pointer to pixel ``(x, y)`` of a ``width``x``height`` frame."""
        e = self._e
        self.input.write(e.EV_ABS, e.ABS_X, self._to_abs(x, width))
        self.input.write(e.EV_ABS, e.ABS_Y, self._to_abs(y, height))
        self.input.syn()

    def left_click(self, hold=0.02):
        """Press and release the left button."""
        e = self._e
        self.input.write(e.EV_KEY, e.BTN_LEFT, 1)  # 1 = press
        self.input.syn()
        time.sleep(hold)
        self.input.write(e.EV_KEY, e.BTN_LEFT, 0)  # 0 = release
        self.input.syn()

    def scroll(self, notches, interval=0.01):
        """Emit ``abs(notches)`` discrete wheel steps. Positive = up, negative = down.

        One *notch* is one physical wheel detent. We send each step on its own
        ``syn`` (like a real wheel) so apps that count discrete scroll events,
        not summed magnitude, behave correctly. We also emit the high-resolution
        axis, which modern (libinput) stacks prefer.
        """
        if notches == 0:
            return
        e = self._e
        step = 1 if notches > 0 else -1
        for i in range(abs(notches)):
            self.input.write(e.EV_REL, e.REL_WHEEL, step)
            self.input.write(e.EV_REL, e.REL_WHEEL_HI_RES, step * self.WHEEL_HI_RES_PER_NOTCH)
            self.input.syn()
            if i < abs(notches) - 1:
                time.sleep(interval)

    def close(self):
        self.input.close()


class PynputMouseImpl:
    """Windows mouse via ``pynput`` — move, left-click, scroll.

    The found position arrives relative to the *capture frame* (size
    ``width``x``height``). We map it to the actual primary-screen coordinate the
    same way :class:`EvdevMouseImpl` does — by fraction of the frame — except the
    target range is the real screen size instead of evdev's normalized
    ``0..65535`` (pynput's cursor takes real pixels, the compositor isn't doing
    the stretch for us). See :meth:`_to_screen`, the analogue of
    :meth:`EvdevMouseImpl._to_abs`.

    Assumes a **single monitor**. The primary screen size is queried once via
    ``user32.GetSystemMetrics`` and cached.

    TODO(HiDPI): ``GetSystemMetrics(SM_CXSCREEN/SM_CYSCREEN)`` and pynput's
    cursor coordinates only agree when the process is DPI-aware. Under display
    scaling (e.g. 150%) a non-DPI-aware process sees the *logical* size here, so
    clicks land off by the scale factor. The fix is to either mark the process
    DPI-aware (``user32.SetProcessDPIAware()`` / a manifest) so both sides are
    physical pixels, or divide by the scale factor. Deferred.
    TODO(multimonitor): this uses only the primary monitor's size and assumes a
    (0, 0) origin. Multi-monitor needs the virtual-desktop origin offset
    (SM_XVIRTUALSCREEN/SM_YVIRTUALSCREEN) and per-monitor sizes, plus a
    per-window offset if we ever capture a single window instead of the screen.
    """

    def __init__(self, name=None, warmup=None):
        from pynput.mouse import Button, Controller

        self._Button = Button
        self._mouse = Controller()
        self._screen_w, self._screen_h = self._query_screen_size()

    @staticmethod
    def _query_screen_size():
        """Primary-monitor size, in the coordinate space pynput's cursor uses.

        Single-monitor assumption (see class TODOs). ``SM_CXSCREEN`` is 0 and
        ``SM_CYSCREEN`` is 1.
        """
        import ctypes

        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

    @staticmethod
    def _to_screen(value, frame_size, screen_size):
        """Map a pixel in ``0..frame_size-1`` onto ``0..screen_size-1`` by fraction.

        Symmetric to :meth:`EvdevMouseImpl._to_abs`: same degenerate-frame
        convention (collapse to the screen center) and the same
        ``value / (frame_size - 1)`` fraction, but the destination range is the
        real screen rather than the normalized absolute axis. The result is
        clamped into ``0..screen_size-1``.
        """
        if frame_size <= 1:
            return screen_size // 2
        frac = min(max(value / (frame_size - 1), 0.0), 1.0)
        pos = round(frac * (screen_size - 1))
        return min(max(pos, 0), screen_size - 1)

    def move_to(self, x, y, width, height):
        sx = self._to_screen(x, width, self._screen_w)
        sy = self._to_screen(y, height, self._screen_h)
        self._mouse.position = (sx, sy)

    def left_click(self):
        self._mouse.click(self._Button.left)

    def scroll(self, notches):
        # pynput scroll: positive dy scrolls up, matching our notch convention.
        if notches == 0:
            return
        self._mouse.scroll(0, notches)

    def close(self):
        pass


def make_mouse_impl(name="yambot-virtual-mouse", warmup=0.3):
    """Pick the mouse impl for the current OS.

    Linux -> evdev/uinput (unchanged); Windows -> pynput.
    """
    if sys.platform.startswith("linux"):
        return EvdevMouseImpl(name=name, warmup=warmup)
    if sys.platform == "win32":
        return PynputMouseImpl(name=name, warmup=warmup)
    raise RuntimeError(f"yambot: no mouse backend for platform {sys.platform!r}")
