"""Capturing real keyboard input with evdev — yambot's *ears*.

The Linux kernel exposes every input device as a file under ``/dev/input/``
(e.g. ``/dev/input/event5``). We open the keyboards and read their events
*passively* — we do **not** ``grab()`` them, so your keystrokes still reach the
focused window as usual. We just also get to see them, which is how the "press
1 to run again" feature works.

Reading these files needs membership in the ``input`` group (see the README).
"""

import selectors
import time

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


def wait_for_keys(targets, *, log=None, rescan_interval=1.0):
    """Block until one of ``targets`` (key codes) is pressed; return that code.

    Watches every keyboard at once via :mod:`selectors`. Every other key press
    seen while waiting is reported through ``log`` (a callable taking a string)
    so the user gets feedback that input is being captured.

    Resilient to keyboards coming and going: a wireless keyboard that sleeps
    drops its ``/dev/input`` device, and reading it then raises ``OSError``
    (ENODEV). We treat that as a disconnect — drop the dead device and keep
    watching the rest, polling every ``rescan_interval`` seconds for it (or any
    keyboard) to reappear, instead of crashing. Returns ``None`` only if there
    is no keyboard to open at the very start.
    """
    targets = set(targets)
    selector = selectors.DefaultSelector()
    devices = {}  # path -> InputDevice, the keyboards we're currently watching

    def register_new():
        """Open and watch any keyboard we're not already tracking."""
        for dev in find_keyboards():
            if dev.path in devices:
                dev.close()  # already watching this one
                continue
            devices[dev.path] = dev
            selector.register(dev, selectors.EVENT_READ)

    def drop(dev):
        """Stop watching a device that errored or vanished."""
        try:
            selector.unregister(dev)
        except (KeyError, ValueError):
            pass
        devices.pop(dev.path, None)
        try:
            dev.close()
        except OSError:
            pass

    register_new()
    if not devices:
        return None

    try:
        while True:
            # All keyboards gone (e.g. the only one slept) — poll for a comeback
            # rather than busy-spin on an empty selector.
            if not devices:
                if log is not None:
                    log("no keyboard — waiting for one to (re)connect...")
                while not devices:
                    time.sleep(rescan_interval)
                    register_new()
                if log is not None:
                    log("keyboard connected")

            ready = selector.select(timeout=rescan_interval)
            if not ready:
                register_new()  # idle tick: pick up any reconnected keyboard
                continue

            for key, _ in ready:
                dev = key.fileobj
                try:
                    events = dev.read()
                except OSError:
                    # Device went away mid-read (wireless sleep / unplug). Drop
                    # it; we'll re-adopt it if it comes back.
                    if log is not None:
                        log(f"keyboard {dev.path} disconnected")
                    drop(dev)
                    continue
                for event in events:
                    if event.type != e.EV_KEY or event.value != 1:  # key-down only
                        continue
                    if event.code in targets:
                        return event.code
                    if log is not None:
                        log(f"captured {key_name(event.code)}")
    finally:
        selector.close()
        for dev in list(devices.values()):
            try:
                dev.close()
            except OSError:
                pass
