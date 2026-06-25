"""Capturing real keyboard input with evdev — yambot's *ears*.

The Linux kernel exposes every input device as a file under ``/dev/input/``
(e.g. ``/dev/input/event5``). We open the keyboards and read their events
*passively* — we do **not** ``grab()`` them, so your keystrokes still reach the
focused window as usual. We just also get to see them, which is how the "press
1 to run again" feature works.

Reading these files needs membership in the ``input`` group (see the README).
"""

import selectors

from evdev import InputDevice, list_devices
from evdev import ecodes as e


def find_keyboards():
    """Open every device that looks like a real keyboard.

    Heuristic: it must report key events and have the letter keys A–Z plus
    space. That filters out mice, lid switches, power buttons and the like,
    which also speak ``EV_KEY`` but only for a handful of buttons.
    """
    keyboards = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except (PermissionError, OSError):
            continue
        keys = dev.capabilities().get(e.EV_KEY, [])
        if e.KEY_A in keys and e.KEY_Z in keys and e.KEY_SPACE in keys:
            keyboards.append(dev)
        else:
            dev.close()
    return keyboards


def key_name(code):
    """Human-readable name for a key code, e.g. ``30`` -> ``'KEY_A'``."""
    name = e.KEY.get(code, code)
    return name if isinstance(name, str) else f"KEY_{code}"


def wait_for_keys(targets, *, log=None):
    """Block until one of ``targets`` (key codes) is pressed; return that code.

    Watches every keyboard at once via :mod:`selectors`. Every other key press
    seen while waiting is reported through ``log`` (a callable taking a string)
    so the user gets feedback that input is being captured. Returns ``None`` if
    no keyboards could be opened.
    """
    targets = set(targets)
    keyboards = find_keyboards()
    if not keyboards:
        return None

    selector = selectors.DefaultSelector()
    for dev in keyboards:
        selector.register(dev, selectors.EVENT_READ)
    try:
        while True:
            for ready, _ in selector.select():
                for event in ready.fileobj.read():
                    if event.type != e.EV_KEY or event.value != 1:  # key-down only
                        continue
                    if event.code in targets:
                        return event.code
                    if log is not None:
                        log(f"captured {key_name(event.code)}")
    finally:
        selector.close()
        for dev in keyboards:
            dev.close()
