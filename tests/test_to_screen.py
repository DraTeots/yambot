"""Pure-math checks for ``PynputMouseImpl._to_screen``.

Runs on any OS: ``_to_screen`` is a staticmethod doing only arithmetic, and
importing :mod:`yambot.mouse_impl` does not import ``pynput`` (it's lazy, inside
``PynputMouseImpl.__init__``). Run with ``python tests/test_to_screen.py``.
"""

from yambot.mouse_impl import PynputMouseImpl

to_screen = PynputMouseImpl._to_screen


def test_fraction_zero_maps_to_zero():
    assert to_screen(0, 1920, 2560) == 0


def test_fraction_half_maps_to_half():
    # value at the middle of the frame -> middle of the screen range.
    assert to_screen((1920 - 1) / 2, 1920, 2560) == round((2560 - 1) / 2)  # 1280 -> 1280


def test_fraction_max_maps_to_screen_minus_one():
    assert to_screen(1920 - 1, 1920, 2560) == 2560 - 1


def test_degenerate_frame_maps_to_center():
    assert to_screen(123, 0, 2560) == 2560 // 2
    assert to_screen(123, 1, 2560) == 2560 // 2


def test_result_is_clamped_into_bounds():
    # Out-of-frame inputs clamp to the screen edges, never escape the range.
    assert to_screen(-50, 1920, 2560) == 0
    assert to_screen(10_000, 1920, 2560) == 2560 - 1


def test_identity_when_frame_equals_screen():
    # Same size in and out: corners and middle land on themselves.
    assert to_screen(0, 1000, 1000) == 0
    assert to_screen(999, 1000, 1000) == 999
    assert to_screen(500, 1000, 1000) == 500


if __name__ == "__main__":
    checks = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for check in checks:
        check()
        print(f"ok  {check.__name__}")
    print(f"=== {len(checks)} _to_screen checks passed ===")
