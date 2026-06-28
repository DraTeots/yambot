"""Lower implementation layer for keyboard listening — yambot's *ears*.

:func:`yambot.keyboard.wait_for_keys` is the public upper layer; it speaks in
:class:`yambot.keys.Key` and delegates to one of the impls here, chosen per OS.
The Linux impl reads evdev ``/dev/input/event*`` exactly as before and only
translates :class:`Key` ↔ evdev codes at the edges, so its behaviour (which
devices it opens, its reconnection handling, its log lines) is unchanged. The
Windows impl uses ``pynput``'s global listener.

Third-party libraries are imported lazily inside each impl so importing this
module pulls in neither ``evdev`` on Windows nor ``pynput`` on Linux.
"""

import sys
import time

from .keys import Key


class EvdevKeyboardImpl:
    """Linux keyboard listener via evdev. Unchanged passive-read behaviour.

    The kernel exposes every input device as a file under ``/dev/input/``. We
    open the keyboards and read their events *passively* — we never ``grab()``
    them, so your keystrokes still reach the focused window; we just also see
    them. Reading these files needs membership in the ``input`` group.
    """

    def __init__(self):
        from evdev import ecodes as e

        self._e = e
        # Translate the platform-neutral keys we listen for into evdev codes.
        self._key_to_code = {
            Key.K1: e.KEY_1,
            Key.K2: e.KEY_2,
            Key.K3: e.KEY_3,
            Key.Q: e.KEY_Q,
            Key.ESC: e.KEY_ESC,
        }
        self._code_to_key = {code: key for key, code in self._key_to_code.items()}

    def _find_keyboards(self):
        """Open every device that looks like a real keyboard.

        Heuristic: it must report key events and have the letter keys A–Z plus
        space. That filters out mice, lid switches, power buttons and the like,
        which also speak ``EV_KEY`` but only for a handful of buttons.
        """
        from evdev import InputDevice, list_devices

        e = self._e
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

    def _evdev_key_name(self, code):
        """Human-readable name for an evdev key code, e.g. ``30`` -> ``'KEY_A'``."""
        name = self._e.KEY.get(code, code)
        return name if isinstance(name, str) else f"KEY_{code}"

    def wait_for_keys(self, targets, *, log=None, rescan_interval=1.0):
        """Block until one of ``targets`` (:class:`Key`) is pressed; return it.

        Watches every keyboard at once via :mod:`selectors`. Every other key
        press seen while waiting is reported through ``log`` so the user gets
        feedback that input is being captured.

        Resilient to keyboards coming and going: a wireless keyboard that sleeps
        drops its ``/dev/input`` device, and reading it then raises ``OSError``
        (ENODEV). We treat that as a disconnect — drop the dead device and keep
        watching the rest, polling every ``rescan_interval`` seconds for it (or
        any keyboard) to reappear. Returns ``None`` only if there is no keyboard
        to open at the very start.
        """
        import selectors

        e = self._e
        target_codes = {self._key_to_code[k] for k in targets}
        selector = selectors.DefaultSelector()
        devices = {}  # path -> InputDevice, the keyboards we're currently watching

        def register_new():
            """Open and watch any keyboard we're not already tracking."""
            for dev in self._find_keyboards():
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
                # All keyboards gone (e.g. the only one slept) — poll for a
                # comeback rather than busy-spin on an empty selector.
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
                        # Device went away mid-read (wireless sleep / unplug).
                        # Drop it; we'll re-adopt it if it comes back.
                        if log is not None:
                            log(f"keyboard {dev.path} disconnected")
                        drop(dev)
                        continue
                    for event in events:
                        if event.type != e.EV_KEY or event.value != 1:  # key-down only
                            continue
                        if event.code in target_codes:
                            return self._code_to_key[event.code]
                        if log is not None:
                            log(f"captured {self._evdev_key_name(event.code)}")
        finally:
            selector.close()
            for dev in list(devices.values()):
                try:
                    dev.close()
                except OSError:
                    pass


class PynputKeyboardImpl:
    """Windows keyboard listener via ``pynput``'s global hook.

    Like the Linux path it's passive — keystrokes still reach the focused
    window. Blocks until one of ``targets`` is pressed and returns that
    :class:`Key`. ``rescan_interval`` is unused (the OS manages the hook).
    """

    def wait_for_keys(self, targets, *, log=None, rescan_interval=1.0):
        import threading

        from pynput import keyboard

        target_set = set(targets)
        result = {}
        done = threading.Event()

        def to_key(k):
            ch = getattr(k, "char", None)
            if ch == "1":
                return Key.K1
            if ch == "2":
                return Key.K2
            if ch == "3":
                return Key.K3
            if ch is not None and ch.lower() == "q":
                return Key.Q
            if k == keyboard.Key.esc:
                return Key.ESC
            return None

        def on_press(k):
            mapped = to_key(k)
            if mapped in target_set:
                result["key"] = mapped
                done.set()
                return False  # stop the listener
            if log is not None:
                label = getattr(k, "char", None) or str(k)
                log(f"captured {label}")
            return None

        listener = keyboard.Listener(on_press=on_press)
        listener.start()
        done.wait()
        listener.stop()
        return result.get("key")


def make_keyboard_impl():
    """Pick the keyboard impl for the current OS.

    Linux -> evdev (unchanged); Windows -> pynput.
    """
    if sys.platform.startswith("linux"):
        return EvdevKeyboardImpl()
    if sys.platform == "win32":
        return PynputKeyboardImpl()
    raise RuntimeError(f"yambot: no keyboard backend for platform {sys.platform!r}")
