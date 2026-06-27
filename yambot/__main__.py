import sys
import time
from pathlib import Path
from evdev import ecodes as e
import structlog

from .keyboard import key_name, wait_for_keys
from .monstep import AutoMonstrator, FailedStep
from .mouse import VirtualMouse
from .screen import find_on_image, mark_box, mark_circle, save_to_folder, screenshot
from .resources import TEMPLATE_ISL_COLLECT_BUTTON, TEMPLATE_MAP_MAIN_PLANT, TEMPLATE_MAP_SEPARATOR, ISLANDS_MAIN
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

    annotated = mark_box(frame, x, y, w, h)   # green square around the matched region
    annotated = mark_circle(annotated, x, y)    # red circle at the click point
    save_to_folder(annotated, debug_dir, suffix="mark")
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

    annotated = mark_box(frame, x, y, w, h)   # green square around the matched region
    annotated = mark_circle(annotated, x, y)    # red circle at the click point
    save_to_folder(annotated, debug_dir, suffix="mark")
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

def find_island_on_map(mouse: VirtualMouse, template: Path):
    m = AutoMonstrator(mouse)

    result = m.find_on_screen(template, "Target island", "island_initial")

    # We need to scroll to the top if this island is not visible
    if result:
        print(f"Island found first try: {template}")
        return result

    # We didn't find the island right on screen =(
    print("   We didn't find the island right on screen. Scrolling up and start searching...")

    # Let's scroll islands
    sep_find_result = m.find_on_screen(TEMPLATE_MAP_SEPARATOR, "Separator area", "sep_area")
    if not sep_find_result:
        print("   We didn't find Map separator. Probably not on map")
        return FailedStep()
    m.scroll_up_on_found(30, sep_find_result, True)
    time.sleep(2.00)

    for i in range(0, len(ISLANDS_MAIN)):
        print(f"==== TRY {i+1} of {len(ISLANDS_MAIN)} ====")
        result = m.find_on_screen(template, "Target island", "island_initial")

        # Found it!
        if result:
            print(f"   Island found: {template}")
            return result

        # Still not found. Now we scroll down a bit
        m.scroll_down_on_found(2, sep_find_result, True)
        time.sleep(2.00)

    return FailedStep()



def run_friends(mouse: VirtualMouse):
    m = AutoMonstrator(mouse)

    #result = m.find_on_screen(TEMPLATE_MAP_MAIN_PLANT, "Plant island", "plant_initial")
    result = find_island_on_map(mouse, TEMPLATE_MAP_MAIN_PLANT)
    print("Found!!!")

    # result = m.find_on_screen(TEMPLATE_MAP_SEPARATOR, "separator area", "sep_area")
    # if not result:
    #     return
    #
    # m.scroll_up_on_found(30, result, True)





def main():
    logger.info(f"Waiting {SWITCH_DELAY}s before running")
    logger.info("starting")

    with VirtualMouse() as mouse:
        run_friends(mouse)
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

if __name__ == "__main__":
    main()
