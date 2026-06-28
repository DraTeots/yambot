"""yambot's *hands* — the public virtual mouse.

:class:`VirtualMouse` is the upper layer the bot talks to. The OS-specific work
(creating a uinput device on Linux, driving ``pynput`` on Windows) lives in the
lower implementation layer, :mod:`yambot.mouse_impl`, picked automatically by
:func:`~yambot.mouse_impl.make_mouse_impl`. Only three operations are ever
needed — move, left-click, scroll.

On Linux this drives an *absolute* virtual pointer via evdev/uinput: we map a
pixel found in a screenshot into a ``0..65535`` range using the *screenshot's
own* dimensions, and the compositor stretches that onto the real screen. That
behaviour is unchanged from before this layer existed; see
:class:`yambot.mouse_impl.EvdevMouseImpl`.

Creating the Linux device needs write access to ``/dev/uinput`` — join the
``input`` group (see the README).
"""

import time

from .mouse_impl import make_mouse_impl


class VirtualMouse:
    """A synthetic mouse we create and drive ourselves.

    Use it as a context manager so the underlying device is always torn down::

        with VirtualMouse() as mouse:
            mouse.click_at(x, y, width, height)
    """

    def __init__(self, name="yambot-virtual-mouse", warmup=0.3):
        self._impl = make_mouse_impl(name=name, warmup=warmup)

    def move_to(self, x, y, width, height):
        """Jump the pointer to pixel ``(x, y)`` of a ``width``x``height`` frame."""
        self._impl.move_to(x, y, width, height)

    def click(self):
        """Press and release the left button."""
        self._impl.left_click()

    def click_at(self, x, y, width, height):
        """Move to pixel ``(x, y)`` of a ``width``x``height`` frame, then left-click."""
        self.move_to(x, y, width, height)
        time.sleep(0.02)  # let the move register before the button event
        self.click()

    def scroll(self, notches):
        """Scroll ``notches`` wheel detents. Positive = up, negative = down."""
        self._impl.scroll(notches)

    def scroll_up(self, clicks=1):
        """Scroll the wheel up by ``clicks`` notches."""
        self.scroll(abs(clicks))

    def scroll_down(self, clicks=1):
        """Scroll the wheel down by ``clicks`` notches."""
        self.scroll(-abs(clicks))

    def close(self):
        self._impl.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
