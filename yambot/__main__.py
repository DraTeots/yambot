import sys
import time
from pathlib import Path
from evdev import ecodes as e
import structlog

from .keyboard import key_name, wait_for_keys
from .monstep import AutoMonstrator, FailedStep
from .mouse import VirtualMouse
from .screen import find_on_image, mark_box, mark_circle, save_to_folder, screenshot
from .resources import (
    TEMPLATE_ISL_COLLECT_BUTTON, TEMPLATE_MAP_MAIN_PLANT, TEMPLATE_MAP_SEPARATOR, ISLANDS_MAIN,
    TEMPLATE_CONFIRM_BUTTON,
    TEMPLATE_FRIEND_BACK_ACTIVE, TEMPLATE_FRIEND_BACK_INACTIVE,
    TEMPLATE_FRIEND_NEXT_ACTIVE, TEMPLATE_FRIEND_NEXT_INACTIVE,
    TEMPLATE_FRIEND_QUICK_LIGHT,
)
from .timer_cm import TinyProfiler


DEBUG_DIR = "captures"
SWITCH_DELAY = 5.0  # seconds to switch screens before a cycle fires

REPEAT_KEY = e.KEY_1
FRIENDS_KEY = e.KEY_2
QUIT_KEYS = (e.KEY_Q, e.KEY_ESC)

#: Friends routine pacing. Generous waits — the game animates page turns and the
#: confirm dialog, and we'd rather be slow than click into a half-drawn screen.
CONFIRM_WAIT = 1.0   # after a quick-light tap, before the confirm dialog appears
PAGE_WAIT = 1.5      # after a page turn, before the new friends are drawn

#: Loop backstops so a misread never turns into an endless click storm. The
#: list is 18 pages (see "1/18"); a page shows 5 friends. Bump if you outgrow them.
MAX_PAGES = 30
MAX_LIGHTS_PER_PAGE = 12

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

    x, y, w, h, score, is_ok = target
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

    x, y, w, h, score, is_ok = target
    print(f"Best found at ({x}, {y}) with score {score} is OK? {is_ok}")
    if not is_ok:
        print("Target is not OK. Looks we didn't found")

    annotated = mark_box(frame, x, y, w, h)   # green square around the matched region
    annotated = mark_circle(annotated, x, y)    # red circle at the click point
    save_to_folder(annotated, debug_dir, suffix="mark")
    # mouse.click_at(x, y, width, height)
    mouse.move_to(x, y, width, height)
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

    x, y, w, h, score, is_ok = target
    print(f"Best found at ({x}, {y}) with score {score} is OK? {is_ok}")
    if not is_ok:
        print("Target is not OK. Looks we didn't found")

    # mouse.click_at(x, y, width, height)
    mouse.move_to(x, y, width, height)
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



def rewind_friends_to_first_page(m: AutoMonstrator):
    """Press the pager's back button until it goes inactive (page 1).

    The back button keeps the same shape whether enabled or greyed, so the BW
    matcher locates it in either state; we then read its *tone* to decide if
    there's an earlier page. Inactive back == we're on the first page.
    """
    for _ in range(MAX_PAGES):
        back = m.find_on_screen(TEMPLATE_FRIEND_BACK_ACTIVE, "Back button", "friend_back")
        if not back:
            # No pager at all — likely a single page of friends. Treat as page 1.
            print("   No back button found — assuming a single page.")
            return
        if not m.check_active_on_found(back, TEMPLATE_FRIEND_BACK_ACTIVE,
                                       TEMPLATE_FRIEND_BACK_INACTIVE, force_annotate=True):
            print("   Back button inactive — on the first page.")
            return
        m.click_on_found(back)
        time.sleep(PAGE_WAIT)
    raise RuntimeError(f"Back button still active after {MAX_PAGES} presses — giving up rewind")


def process_quick_light(m: AutoMonstrator):
    """Light one friend: tap the quick-light, then confirm.

    Tap the quick-light button, wait for the confirm dialog, and press it. A
    missing confirm dialog means the flow broke (out of torches, a popup, a
    misclick) — we fail loudly rather than march on blindly.
    """
    light = m.find_on_screen(TEMPLATE_FRIEND_QUICK_LIGHT, "Quick light", "quick_light")
    if not light:
        return False  # nothing left to light on this page

    m.click_on_found(light)
    time.sleep(CONFIRM_WAIT)

    confirm = m.find_on_screen(TEMPLATE_CONFIRM_BUTTON, "Confirm button", "confirm")
    if not confirm:
        raise RuntimeError("Pressed quick-light but no confirm dialog appeared")
    m.click_on_found(confirm)
    time.sleep(CONFIRM_WAIT)
    return True


def process_friends_page(m: AutoMonstrator):
    """Light every friend on the current page until no quick-light remains.

    We pretend each scan finds at most one quick-light: light it, and the next
    scan surfaces the next one (the lit friend drops out). Loop until a scan
    comes up empty.
    """
    for _ in range(MAX_LIGHTS_PER_PAGE):
        if not process_quick_light(m):
            print("   No more quick-lights on this page.")
            return
    print(f"   Hit the {MAX_LIGHTS_PER_PAGE}-light cap on one page — moving on.")


def run_friends(mouse: VirtualMouse):
    """Walk every friends page from the first, lighting torches as we go.

    Triggered by pressing **2** with the friends list open. Rewind to page 1,
    then on each page light all torches and advance via the next button until it
    goes inactive (no more pages) — a clean, successful finish.
    """
    m = AutoMonstrator(mouse)
    print("=== Friends routine: rewinding to the first page ===")
    rewind_friends_to_first_page(m)

    for page in range(1, MAX_PAGES + 1):
        print(f"=== Friends page {page} ===")
        process_friends_page(m)

        nxt = m.find_on_screen(TEMPLATE_FRIEND_NEXT_ACTIVE, "Next button", "friend_next")
        if not nxt:
            print("   No next button found — done.")
            return
        if not m.check_active_on_found(nxt, TEMPLATE_FRIEND_NEXT_ACTIVE,
                                       TEMPLATE_FRIEND_NEXT_INACTIVE, force_annotate=True):
            print("   Next button inactive — all pages processed. Done.")
            return
        m.click_on_found(nxt)
        time.sleep(PAGE_WAIT)
    print(f"   Reached the {MAX_PAGES}-page cap — stopping.")





def main():
    logger.info(f"Waiting {SWITCH_DELAY}s before running")
    logger.info("starting")

    with VirtualMouse() as mouse:
        while True:
            print("\npress [1] map, [2] friends, [q]/[esc] to quit — listening...")
            pressed = wait_for_keys((REPEAT_KEY, FRIENDS_KEY, *QUIT_KEYS), log=print)
            if pressed is None:
                print("no keyboards found to read — quitting")
                break
            if pressed in QUIT_KEYS:
                print(f"{key_name(pressed)} pressed — quitting")
                break
            if pressed == FRIENDS_KEY:
                print(f"{key_name(pressed)} pressed — running friends routine")
                run_friends(mouse)
            else:
                print(f"{key_name(pressed)} pressed — running map")
                run_map(mouse)

if __name__ == "__main__":
    main()
