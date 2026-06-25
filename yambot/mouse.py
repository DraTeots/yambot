"""A virtual mouse built on evdev / uinput — yambot's *hands*.

On Wayland an app can't just "set the cursor position". Instead we create a
brand-new virtual input device through ``/dev/uinput`` and feed it events,
exactly like a real mouse would. We declare ABSOLUTE X/Y axes spanning
``0..=65535``; the compositor maps that whole range onto the real screen, so a
value of ``32767`` lands dead-center no matter the resolution. That means we
never need to know the screen's pixel size — we map a pixel found in a
screenshot into the ``0..65535`` range using the *screenshot's own* dimensions.

This mirrors the Rust ``input-tracker`` crate in this repo; same recipe, Python.

Creating the device needs write access to ``/dev/uinput`` — join the ``input``
group (see the README).
"""

import time

from evdev import AbsInfo, UInput
from evdev import ecodes as e

#: Absolute-axis range. The compositor stretches this onto the whole screen.
ABS_MIN = 0
ABS_MAX = 65535
ABS_CENTER = (ABS_MIN + ABS_MAX) // 2

#: libinput convention: 120 high-resolution wheel units == one wheel detent.
WHEEL_HI_RES_PER_NOTCH = 120


def _to_abs(value, span):
    """Map a pixel coordinate in ``0..span-1`` onto the ``ABS_MIN..ABS_MAX`` range."""
    if span <= 1:
        return ABS_CENTER
    frac = min(max(value / (span - 1), 0.0), 1.0)
    return ABS_MIN + round(frac * (ABS_MAX - ABS_MIN))


class VirtualMouse:
    """A synthetic absolute-positioning mouse we create and drive ourselves.

    Use it as a context manager so the uinput device is always torn down::

        with VirtualMouse() as mouse:
            mouse.click_at(x, y, width, height)
    """

    def __init__(self, name="yambot-virtual-mouse", warmup=0.3):
        abs_axis = AbsInfo(
            value=ABS_CENTER, min=ABS_MIN, max=ABS_MAX, fuzz=0, flat=0, resolution=0
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

    def move_to(self, x, y, width, height):
        """Jump the pointer to pixel ``(x, y)`` of a ``width``x``height`` frame."""
        self.input.write(e.EV_ABS, e.ABS_X, _to_abs(x, width))
        self.input.write(e.EV_ABS, e.ABS_Y, _to_abs(y, height))
        self.input.syn()

    def click(self, button=e.BTN_LEFT, hold=0.02):
        """Press and release ``button`` (default left)."""
        self.input.write(e.EV_KEY, button, 1)  # 1 = press
        self.input.syn()
        time.sleep(hold)
        self.input.write(e.EV_KEY, button, 0)  # 0 = release
        self.input.syn()

    def click_at(self, x, y, width, height, button=e.BTN_LEFT):
        """Move to pixel ``(x, y)`` of a ``width``x``height`` frame, then click."""
        self.move_to(x, y, width, height)
        time.sleep(0.02)  # let the move register before the button event
        self.click(button)

    def scroll(self, notches, interval=0.01):
        """Emit ``abs(notches)`` discrete wheel steps. Positive = up, negative = down.

        One *notch* is one physical wheel detent. We send each step on its own
        ``syn`` (like a real wheel) so apps that count discrete scroll events,
        not summed magnitude, behave correctly. We also emit the high-resolution
        axis, which modern (libinput) stacks prefer.
        """
        if notches == 0:
            return
        step = 1 if notches > 0 else -1
        for i in range(abs(notches)):
            self.input.write(e.EV_REL, e.REL_WHEEL, step)
            self.input.write(e.EV_REL, e.REL_WHEEL_HI_RES, step * WHEEL_HI_RES_PER_NOTCH)
            self.input.syn()
            if i < abs(notches) - 1:
                time.sleep(interval)

    def scroll_up(self, clicks=1):
        """Scroll the wheel up by ``clicks`` notches."""
        self.scroll(abs(clicks))

    def scroll_down(self, clicks=1):
        """Scroll the wheel down by ``clicks`` notches."""
        self.scroll(-abs(clicks))

    def close(self):
        self.input.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
