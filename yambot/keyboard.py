"""yambot's *ears* — the public keyboard listener.

The bot talks in :class:`yambot.keys.Key`; the OS-specific listening (evdev on
Linux, ``pynput`` on Windows) lives in the lower layer,
:mod:`yambot.keyboard_impl`, picked automatically by
:func:`~yambot.keyboard_impl.make_keyboard_impl`.

On Linux this passively reads ``/dev/input/event*`` (no ``grab()``), so your
keystrokes still reach the focused window — that behaviour is unchanged from
before this layer existed. Reading those files needs membership in the ``input``
group (see the README).
"""

from .keyboard_impl import make_keyboard_impl
from .keys import Key

#: The keyboard backend, selected per-OS at import.
_keyboard_impl = make_keyboard_impl()


def key_name(key: Key) -> str:
    """Human-readable name for a :class:`Key`, e.g. :data:`Key.K1` -> ``'KEY_1'``."""
    return key.display


def wait_for_keys(targets, *, log=None, rescan_interval=1.0):
    """Block until one of ``targets`` (:class:`Key`) is pressed; return that key.

    Returns ``None`` if there is no keyboard to read at all (Linux only).
    """
    return _keyboard_impl.wait_for_keys(targets, log=log, rescan_interval=rescan_interval)
