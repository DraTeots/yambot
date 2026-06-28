"""Platform-neutral key identity.

The brains (``__main__``) and the keyboard upper layer talk in terms of these
:class:`Key` members instead of evdev's integer key codes, so the hotkey logic
isn't tied to Linux. Each input backend translates between :class:`Key` and its
own native codes (the Linux backend maps ``Key`` ↔ evdev ``ecodes``).

Only the handful of keys yambot actually listens for are modelled here.
"""

from enum import Enum


class Key(Enum):
    """A key yambot cares about, named by what you press."""

    K1 = "1"   # map routine
    K2 = "2"   # friends routine
    K3 = "3"   # advanced friends routine
    Q = "q"    # quit
    ESC = "esc"  # quit

    @property
    def display(self) -> str:
        """Human-readable name, kept identical to the old evdev key names.

        e.g. :data:`Key.K1` -> ``"KEY_1"``, :data:`Key.ESC` -> ``"KEY_ESC"``.
        The friends/map log lines used to print evdev's ``key_name`` output, so
        we mirror it here to keep that output unchanged.
        """
        suffix = {Key.K1: "1", Key.K2: "2", Key.K3: "3", Key.Q: "Q", Key.ESC: "ESC"}[self]
        return f"KEY_{suffix}"
