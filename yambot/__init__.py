"""yambot — a screenshot-driven autoclicker for My Singing Monsters on Wayland.

The helpers are split into single-purpose modules:

* :mod:`yambot.screen`   — *eyes*: grab the screen, find a button (OpenCV).
* :mod:`yambot.mouse`    — *hands*: a virtual absolute mouse via evdev/uinput.
* :mod:`yambot.keyboard` — *ears*: read the real keyboard via evdev.

One *cycle* is: wait a few seconds (so you can switch to the game), grab the
screen, find the button, draw a circle on it for the record, then move the
virtual mouse there and click. After each cycle we listen to the real keyboard
and run another cycle when you press **1**; **q** or **Esc** quits.
"""
import sys
import time

from evdev import ecodes as e
import structlog

from .keyboard import key_name, wait_for_keys
from .mouse import VirtualMouse
from .screen import TEMPLATE_ISL_COLLECT_BUTTON, find_on_image, box, mark, save, screenshot, TEMPLATE_MAP_MAIN_PLANT, \
    TEMPLATE_MAP_SEPARATOR
from .timer_cm import TinyProfiler

DEBUG_DIR = "captures"
SWITCH_DELAY = 5.0  # seconds to switch screens before a cycle fires

REPEAT_KEY = e.KEY_1
QUIT_KEYS = (e.KEY_Q, e.KEY_ESC)

shared_processors = [
    # Processors that have nothing to do with output,
    # e.g., add timestamps or log level names.
]
if sys.stderr.isatty():
    # Pretty printing when we run in a terminal session.
    # Automatically prints pretty tracebacks when "rich" is installed
    processors = shared_processors + [
        structlog.dev.ConsoleRenderer(),
    ]
else:
    # Print JSON when we run, e.g., in a Docker container.
    # Also print structured tracebacks.
    processors = shared_processors + [
        structlog.processors.dict_tracebacks,
        structlog.processors.JSONRenderer(),
    ]
structlog.configure(processors)

logger = structlog.get_logger()

def run_cycle(mouse, *, template=TEMPLATE_ISL_COLLECT_BUTTON, delay=SWITCH_DELAY, debug_dir=DEBUG_DIR):
    """Wait, screenshot, find the button, annotate it, then move + click."""
    print(f"waiting {delay:g}s — switch to the game window...")
    time.sleep(delay)

    print("screenshotting...")
    frame = screenshot()
    height, width = frame.shape[:2]

    print("finding button...")
    target = find_on_image(frame, template)
    if target is None:
        print("no target found")
        return False

    x, y, is_ok, score, w, h = target
    print(f"Best found at ({x}, {y}) with score {score} is OK? {is_ok}")
    if not is_ok:
        print("Target is not OK. Looks we didn't found")

    annotated = box(frame, x, y, w, h)   # green square around the matched region
    annotated = mark(annotated, x, y)    # red circle at the click point
    save(annotated, debug_dir, suffix="mark")
    mouse.click_at(x, y, width, height)
    print("clicked")
    return True


def run_map(mouse: VirtualMouse, *,  delay=SWITCH_DELAY, debug_dir=DEBUG_DIR):
    """Wait, screenshot, find the button, annotate it, then move + click."""
    print(f"Map navigation {delay:g}s — switch to the game window...")
    time.sleep(delay)

    print("   Screenshotting...")
    frame = screenshot()
    height, width = frame.shape[:2]

    print("   Finding islands column...")
    with TinyProfiler("   Finding image"):
        target = find_on_image(frame, TEMPLATE_MAP_SEPARATOR)
        if target is None:
            print("no target found")
            return False

    x, y, is_ok, score, w, h = target
    print(f"Best found at ({x}, {y}) with score {score} is OK? {is_ok}")
    if not is_ok:
        print("Target is not OK. Looks we didn't found")

    annotated = box(frame, x, y, w, h)   # green square around the matched region
    annotated = mark(annotated, x, y)    # red circle at the click point
    save(annotated, debug_dir, suffix="mark")
    # mouse.click_at(x, y, width, height)
    mouse.move_to(x, y, height, width)
    mouse.scroll_up(30)
    print("scrolled")
    time.sleep(2.00)

    print("   Screenshotting...")
    frame = screenshot()
    height, width = frame.shape[:2]

    print("   Finding islands column...")
    with TinyProfiler("   Finding island "):
        target = find_on_image(frame, TEMPLATE_MAP_MAIN_PLANT)
        if target is None:
            print("no target found")
            return False

    x, y, is_ok, score, *_ = target
    print(f"Best found at ({x}, {y}) with score {score} is OK? {is_ok}")
    if not is_ok:
        print("Target is not OK. Looks we didn't found")

    # mouse.click_at(x, y, width, height)
    mouse.move_to(x, y, height, width)
    mouse.scroll_up(30)
    print("scrolled")
    time.sleep(2.00)

    return True

def main():

    logger.info("yambot: starting")
    with VirtualMouse() as mouse:
        run_map(mouse)
        while True:
            print("\npress [1] to run again, [q]/[esc] to quit — listening...")
            pressed = wait_for_keys((REPEAT_KEY, *QUIT_KEYS), log=print)
            if pressed is None:
                print("no keyboards found to read — quitting")
                break
            if pressed in QUIT_KEYS:
                print(f"{key_name(pressed)} pressed — quitting")
                break
            print(f"{key_name(pressed)} pressed — running again")
            run_map(mouse)
