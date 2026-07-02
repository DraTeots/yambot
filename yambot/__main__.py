import sys
import time
from pathlib import Path
import structlog

from .keys import Key
from .keyboard import key_name, wait_for_keys
from .monstep import AutoMonstrator, FailedStep
from .mouse import VirtualMouse
from .screen import find_on_image, images_similar, mark_box, mark_circle, save_to_folder, screenshot
from .resources import (
    TEMPLATE_ISL_COLLECT_BUTTON, TEMPLATE_MAP_MAIN_PLANT, TEMPLATE_MAP_SEPARATOR, ISLANDS_MAIN,
    TEMPLATE_CONFIRM_BUTTON,
    TEMPLATE_FRIEND_BACK_ACTIVE, TEMPLATE_FRIEND_BACK_INACTIVE,
    TEMPLATE_FRIEND_NEXT_ACTIVE, TEMPLATE_FRIEND_NEXT_INACTIVE,
    TEMPLATE_FRIEND_QUICK_LIGHT,
    TEMPLATE_FRIEND_LIGHT_ACTIVE, TEMPLATE_FRIEND_LIGHT_INACTIVE, TEMPLATE_FRIEND_LIGHT,
    TEMPLATE_FRIEND_MAP_CLOSE, TEMPLATE_FRIEND_ISLAND_BUTTON, TEMPLATE_GO_BUTTON,
    TEMPLATE_MAP_GO_TO_MAIN_WORLD,
    TEMPLATE_ISL_CLOSE_BUTTON, TEMPLATE_MAP_BUTTON, TEMPLATE_MAP_YOU_HERE_BUTTON,
    TEMPLATE_MAP_HAS_CRYSTALS, TEMPLATE_MAP_HAS_MONEY,
    TEMPLATE_MAP_HAS_DIAMONDS, TEMPLATE_MAP_HAS_MIXEDRES,
    TEMPLATE_ISL_COLLECT_DIAMONDS,
)
from .timer_cm import TinyProfiler


DEBUG_DIR = "captures"
SWITCH_DELAY = 5.0  # seconds to switch screens before a cycle fires

REPEAT_KEY = Key.K1
FRIENDS_KEY = Key.K2
ADVANCED_FRIENDS_KEY = Key.K3
COLLECT_KEY = Key.K5
COMBINED_FRIENDS_KEY = Key.K6
QUIT_KEYS = (Key.Q, Key.ESC)

#: Friends routine pacing. Generous waits — the game animates page turns and the
#: confirm dialog, and we'd rather be slow than click into a half-drawn screen.
CONFIRM_WAIT = 1.0   # after a quick-light tap, before the confirm dialog appears
PAGE_WAIT = 0.5      # after a page turn, before the new friends are drawn

#: Advanced flow extra pacing — visiting a friend's map is animation-heavy.
MAP_LOAD_WAIT = 4.0    # after confirm, while the friend's map opens
GO_WAIT = 8.0          # after pressing Go, while their island loads (per spec)
MAP_CLOSE_WAIT = 8.0   # after closing a friend's map (per spec)
BACK_TO_MAIN_WAIT = 4.0  # after backing out of a sub-island to the friend's main map

#: Hunting the fire on a friend's island map: scroll the island list to the top,
#: then step down through it re-checking for the fire before giving up.
MAP_FIRE_SCROLL_UP = 30    # clicks to reach the top of the friend's island list
MAP_FIRE_SCROLL_DOWN = 3   # clicks to advance the list between checks
MAP_FIRE_SCROLL_TRIES = 10 # how many down-steps to try before escaping
MAP_SCROLL_WAIT = 1.0      # let the list settle after each scroll

#: Loop backstops so a misread never turns into an endless click storm. The
#: list is 18 pages (see "1/18"); a page shows 5 friends. Bump if you outgrow them.
MAX_PAGES = 30
MAX_LIGHTS_PER_PAGE = 12

#: Friend "fingerprint" crop, as multiples of the located fire/light button box.
#: The fire button sits at the card's bottom-left, so we expand up and to the
#: right to grab the *portrait* — the part that actually differs between friends
#: (the card chrome/banner/buttons are identical, so including them would make
#: different friends look alike). All four are offsets *above*/around the button
#: center; tune by eyeballing the saved ``*_served`` crops in captures/.
CARD_LEFT = 0.8    # extend left of the button center by this × button width
CARD_RIGHT = 2.0   # extend right by this × button width
CARD_TOP = 7.0     # top edge, this × button height *above* the button center
CARD_BOTTOM = 2.0  # bottom edge, this × button height above center (above banner)

#: How alike two portrait crops must be (0..1) to count as the same friend. High,
#: because the shared card frame already inflates similarity. Lower if a served
#: friend keeps getting re-served; raise if distinct friends get skipped.
SERVED_MATCH_THRESHOLD = 0.90

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

    # Then we will have the second confirm light
    confirm = m.find_on_screen(TEMPLATE_CONFIRM_BUTTON, "Confirm button2", "confirm2")
    if not confirm:
        raise RuntimeError("Pressed quick-light confirm but no final confirm dialog appeared")
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


# --- Advanced friends (button 3): light each friend via their own map ------

def advance_to_next_page(m: AutoMonstrator) -> bool:
    """Turn to the next friends page if the pager's next button is active.

    Returns True if we moved to a new page, False if the next button is missing
    or inactive (no more pages).
    """
    nxt = m.find_on_screen(TEMPLATE_FRIEND_NEXT_ACTIVE, "Next button", "friend_next")
    if not nxt:
        print("   No next button found — done.")
        return False
    if not m.check_active_on_found(nxt, TEMPLATE_FRIEND_NEXT_ACTIVE,
                                   TEMPLATE_FRIEND_NEXT_INACTIVE, force_annotate=True):
        print("   Next button inactive — all pages processed.")
        return False
    m.click_on_found(nxt)
    time.sleep(PAGE_WAIT)
    return True


def leave_friend_map(m: AutoMonstrator):
    """Escape a friend's map back to the friends list.

    Used whenever the map didn't offer what we expected: close the map, give it
    a beat (per spec, 3s), then press the island button that returns to the list.
    """
    close = m.find_on_screen(TEMPLATE_FRIEND_MAP_CLOSE, "Friend map close", "map_close")
    if close:
        m.click_on_found(close)
    time.sleep(MAP_CLOSE_WAIT)
    return_to_friend_list(m)


def return_to_friend_list(m: AutoMonstrator):
    """Press the island button to go from a friend's map back to the list."""
    island = m.find_on_screen(TEMPLATE_FRIEND_ISLAND_BUTTON, "Friend island button", "island")
    if island:
        m.click_on_found(island)
    time.sleep(MAP_LOAD_WAIT)


def card_fingerprint(light):
    """Crop a friend's portrait from a located list light/fire button.

    The fire button sits at the card's bottom-left, so we expand up and to the
    right (in button-box units) to grab the portrait — the part unique to each
    friend. Clamped to the frame. This crop is what we store/compare to tell
    *which friend* a light belongs to. Returns the BGR crop (possibly empty if
    the button sat at the very edge).
    """
    (x, y) = light.position
    w, h = light.width, light.height
    x0 = max(int(x - CARD_LEFT * w), 0)
    x1 = min(int(x + CARD_RIGHT * w), light.image.shape[1])
    y0 = max(int(y - CARD_TOP * h), 0)
    y1 = max(int(y - CARD_BOTTOM * h), 0)
    return light.image[y0:y1, x0:x1]


def first_active_light(m: AutoMonstrator, served):
    """Return ``(light, fingerprint)`` for the first friend worth serving, else ``(None, None)``.

    A friend is worth serving when their list light reads **active** (tone, not
    just shape — already-lit friends read inactive) *and* they aren't one we've
    already visited this run. The served check is what breaks the relentless
    loop: when we escape a friend's map without lighting, their list light stays
    active, so without remembering them we'd pick the same friend forever.
    """
    for light in m.find_all_on_screen(TEMPLATE_FRIEND_LIGHT_ACTIVE, "Friend light", "friend_light"):
        if not m.check_active_on_found(light, TEMPLATE_FRIEND_LIGHT_ACTIVE,
                                       TEMPLATE_FRIEND_LIGHT_INACTIVE):
            continue  # already lit by the game

        fingerprint = card_fingerprint(light)
        scores = [images_similar(fingerprint, s, SERVED_MATCH_THRESHOLD) for s in served]
        if any(is_match for is_match, _ in scores):
            best = max(score for _, score in scores)
            print(f"   Skipping a friend already served this run (match {best:.2f}).")
            continue

        return light, fingerprint
    return None, None


def find_fire_on_friend_map(m: AutoMonstrator):
    """Find the fire (light) on a friend's island map, scrolling the list if needed.

    Glance for the fire where we land. If it's not in view, scroll the friend's
    island list to the top (move to the separator, scroll up), then step down
    through the list re-checking each time — the same scan-and-scroll pattern as
    :func:`find_island_on_map`. Returns the fire FindStep, or None if it never
    surfaces (caller then escapes).
    """
    fire = m.find_on_screen(TEMPLATE_FRIEND_LIGHT, "Friend light (map)", "light_map")
    if fire:
        return fire

    print("   No fire in view — scrolling the friend's island list to look for it.")
    sep = m.find_on_screen(TEMPLATE_MAP_SEPARATOR, "Separator area", "sep_area")
    if not sep:
        print("   No island-list separator on the friend's map — can't scroll.")
        return None

    m.scroll_up_on_found(MAP_FIRE_SCROLL_UP, sep, True)
    time.sleep(MAP_SCROLL_WAIT)

    for i in range(MAP_FIRE_SCROLL_TRIES):
        print(f"   ==== Fire scroll try {i + 1} of {MAP_FIRE_SCROLL_TRIES} ====")
        fire = m.find_on_screen(TEMPLATE_FRIEND_LIGHT, "Friend light (map)", "light_map")
        if fire:
            return fire
        m.scroll_down_on_found(MAP_FIRE_SCROLL_DOWN, sep, True)
        time.sleep(MAP_SCROLL_WAIT)

    return None


def process_advanced_light(m: AutoMonstrator, light):
    """Light one friend the long way: open their map, light it there, return.

    Press the (already-confirmed active) list light and confirm. Then, on the
    friend's map, find the on-map fire (scrolling the island list to hunt for it):
    if it never surfaces, bail back to the list; if it does, press it and press Go
    (no Go ⇒ also bail). After Go we wait for their island, press the on-map light
    once more (whether or not it lands), and finally return to the list.
    """
    m.click_on_found(light)
    time.sleep(CONFIRM_WAIT)

    confirm = m.find_on_screen(TEMPLATE_CONFIRM_BUTTON, "Confirm button", "confirm")
    if not confirm:
        raise RuntimeError("Pressed friend light but no confirm dialog appeared")
    m.click_on_found(confirm)
    time.sleep(MAP_LOAD_WAIT)

    # The map may open in mirror world/map. If a "back to main map" button is
    # showing, press it first so the fire hunt starts from the friend's main map.
    back_to_main = m.find_on_screen(TEMPLATE_MAP_GO_TO_MAIN_WORLD, "Back to main map", "back_to_main")
    if back_to_main:
        m.click_on_found(back_to_main)
        time.sleep(BACK_TO_MAIN_WAIT)

    # Now on the friend's map. Hunt for the on-map fire, scrolling if not in view.
    light_map = find_fire_on_friend_map(m)
    if not light_map:
        print("   No on-map fire even after scrolling — leaving this friend's map.")
        leave_friend_map(m)
        return

    m.click_on_found(light_map)
    time.sleep(CONFIRM_WAIT)

    go = m.find_on_screen(TEMPLATE_GO_BUTTON, "Go button", "go")
    if not go:
        print("   No Go button — leaving this friend's map.")
        leave_friend_map(m)
        return

    m.click_on_found(go)
    time.sleep(GO_WAIT)

    # Their island is up. Light it once more if the on-map light is present.
    light_again = m.find_on_screen(TEMPLATE_FRIEND_LIGHT, "Friend light (island)", "light_again")
    if light_again:
        m.click_on_found(light_again)
        time.sleep(CONFIRM_WAIT)

    # Whether or not that landed, head back to the friends list.
    return_to_friend_list(m)


def process_advanced_page(m: AutoMonstrator, served):
    """Light every still-unserved active friend on the page, one map visit each.

    Scan for all light buttons, act on the first active friend we haven't served
    yet, record their fingerprint, then re-scan — each map round-trip redraws the
    page. ``served`` carries the run's fingerprints so escapes (which leave the
    light active) don't get retried. Stop when no servable friend remains.
    """
    for _ in range(MAX_LIGHTS_PER_PAGE):
        light, fingerprint = first_active_light(m, served)
        if not light:
            print("   No more unserved active lights on this page.")
            return
        process_advanced_light(m, light)
        # Remember this friend so we never revisit them, even if the escape path
        # left their list light active. Save the crop for eyeballing/tuning.
        served.append(fingerprint)
        if fingerprint.size:  # skip the annotation if the crop came out empty
            save_to_folder(fingerprint, DEBUG_DIR, suffix=f"served_{len(served)}")
    print(f"   Hit the {MAX_LIGHTS_PER_PAGE}-light cap on one page — moving on.")


def run_advanced_friends(mouse: VirtualMouse):
    """Walk every friends page, lighting each active friend via their own map.

    Triggered by pressing **3** with the friends list open. Same page walk as the
    quick-light routine, but each friend is lit by opening their map (see
    :func:`process_advanced_light`).
    """
    m = AutoMonstrator(mouse)
    served = []  # portrait fingerprints of friends visited this run (see first_active_light)
    print("=== Advanced friends routine: rewinding to the first page ===")
    rewind_friends_to_first_page(m)

    for page in range(1, MAX_PAGES + 1):
        print(f"=== Advanced friends page {page} ===")
        process_advanced_page(m, served)
        if not advance_to_next_page(m):
            print("   All pages processed. Done.")
            return
    print(f"   Reached the {MAX_PAGES}-page cap — stopping.")


# --- Combined friends (button 6): quick-light AND fire, in one sweep --------

def process_combined_page(m: AutoMonstrator, served):
    """Light every friend on the page by *both* methods, consecutively.

    Fuses the two per-page routines into one pass: first clear all the
    quick-lights (the fast, direct list torches — :func:`process_friends_page`),
    then walk the remaining active fire-lights the long way, opening each
    friend's map (:func:`process_advanced_page`). A friend's list button is
    either a quick-light or a regular fire, so the two passes don't overlap;
    running quick-lights first just gets the cheap ones out of the way before the
    map round-trips. ``served`` is shared so an advanced map escape isn't retried.
    """
    process_friends_page(m)           # 1) all quick-lights on this page
    process_advanced_page(m, served)  # 2) then the fires that need a map visit


def run_combined_friends(mouse: VirtualMouse):
    """Walk every friends page, lighting each friend by quick-light **and** fire.

    Triggered by pressing **6** with the friends list open. Combines the quick
    (key 2) and advanced (key 3) routines: rewind to the first page, then on each
    page run both light passes consecutively (see :func:`process_combined_page`)
    and advance until the pager runs out. One ``served`` fingerprint set spans the
    whole run so friends reached via their map aren't revisited.
    """
    m = AutoMonstrator(mouse)
    served = []  # portrait fingerprints of friends visited this run (see first_active_light)
    print("=== Combined friends routine: rewinding to the first page ===")
    rewind_friends_to_first_page(m)

    for page in range(1, MAX_PAGES + 1):
        print(f"=== Combined friends page {page} ===")
        process_combined_page(m, served)
        if not advance_to_next_page(m):
            print("   All pages processed. Done.")
            return
    print(f"   Reached the {MAX_PAGES}-page cap — stopping.")



# --- Collect resources (button 5): sweep the map for crystals/money ---------

#: Pacing/limits for the resource-collection sweep. Generous waits because the
#: game animates entering an island, the collect dialog, and the trip back to
#: the map; we'd rather be slow than click into a half-drawn screen.
COLLECT_SCROLL_UP = 30        # clicks to reach the top of the island list
COLLECT_SCROLL_DOWN = 3       # clicks to advance the list between marker scans
COLLECT_SCROLL_TRIES = 20     # how many down-steps to try before giving up the sweep
COLLECT_SCROLL_WAIT = 1.0     # let the list settle after each scroll (per spec)
COLLECT_SELECT_WAIT = 3.0     # after clicking a marker, before the Go button shows
COLLECT_GO_WAIT = 8.0         # after Go, while the island loads (per spec)
COLLECT_DIALOG_WAIT = 2.0     # after collect-all, before the confirm dialog appears
COLLECT_CONFIRM_WAIT = 4.0    # after confirm, before pressing the map button (per spec)
COLLECT_DIAMONDS_WAIT = 2.0   # let the coin-collect animation clear so the diamonds button shows
COLLECT_MAP_WAIT = 10.0       # after the map button, while the world map redraws (per spec)
COLLECT_POPUP_WAIT = 1.0      # after closing a promo popup, before re-checking

#: How many promo popups we'll close before deciding the island is stuck.
COLLECT_MAX_POPUPS = 5
#: Backstop so a marker that never clears can't loop us forever.
MAX_COLLECT_ISLANDS = 40


#: Map-row markers meaning "this island has something to collect", each paired
#: with a label/suffix for logging. We scan for all of them and act on whichever
#: sits highest on screen.
COLLECT_MARKERS = (
    (TEMPLATE_MAP_HAS_CRYSTALS, "Map has crystals", "has_crystals"),
    (TEMPLATE_MAP_HAS_MONEY, "Map has money", "has_money"),
    (TEMPLATE_MAP_HAS_DIAMONDS, "Map has diamonds", "has_diamonds"),
    (TEMPLATE_MAP_HAS_MIXEDRES, "Map has mixed resources", "has_mixedres"),
)


def find_resource_marker(m: AutoMonstrator):
    """Find the topmost island with resources ready in the *current* map view.

    Scan for every collect marker and return the one highest on screen (smallest
    y), or None if none is in view. Going top-down matters: after collecting we
    come back to the map and re-scan, so if we acted on a lower marker first we'd
    scroll past — and skip — any that sit above it. No scrolling here; the caller
    drives the scroll-and-rescan loop.
    """
    # One screenshot, matched against every marker template — no need to grab a
    # fresh frame per type.
    frame = screenshot()
    candidates = []
    for template, title, suffix in COLLECT_MARKERS:
        candidates.extend(m.find_all_on_screen(template, title, suffix, image=frame))
    if not candidates:
        return None
    # Across all marker types, pick the one highest on screen.
    candidates.sort(key=lambda r: r.position[1])
    return candidates[0]


def close_island_popups(m: AutoMonstrator) -> bool:
    """Dismiss any promo popups stacked on a freshly-loaded island.

    Press the close button up to ``COLLECT_MAX_POPUPS`` times, re-checking each
    pass (popups can stack). Returns True once nothing's left to close, or False
    if one is still showing after all attempts — the caller treats that as a
    hard failure (per spec).
    """
    for i in range(COLLECT_MAX_POPUPS):
        close = m.find_on_screen(TEMPLATE_ISL_CLOSE_BUTTON, "Close popup", "collect_close")
        if not close:
            return True  # nothing (left) to close
        print(f"   Closing a promo popup ({i + 1}/{COLLECT_MAX_POPUPS})...")
        m.click_on_found(close)
        time.sleep(COLLECT_POPUP_WAIT)
    # One last look — if it's gone now we're fine, otherwise we're stuck.
    return not m.find_on_screen(TEMPLATE_ISL_CLOSE_BUTTON, "Close popup", "collect_close_final")


def collect_from_island(m: AutoMonstrator, marker) -> bool:
    """Enter the marked island, collect its resources, and return to the map.

    Click the resource marker, press Go to enter the island, close any promo
    popups, then collect-all + confirm. Finally press the map button to get back.
    Returns True if we entered the island (and are back on the map), False if no
    Go button appeared (we never left the map — caller should scroll past it).
    Raises on a stuck popup, which signals a genuinely broken state.
    """
    m.click_on_found(marker)
    time.sleep(COLLECT_SELECT_WAIT)

    # Press whatever enters the island: the Go button (same one the friends flow
    # uses), or — if the selected island is the one we're already on — the
    # "you are here" button. Either one proceeds.
    enter = m.find_on_screen(TEMPLATE_GO_BUTTON, "Go button", "collect_go")
    if not enter:
        enter = m.find_on_screen(TEMPLATE_MAP_YOU_HERE_BUTTON, "You-are-here button", "collect_here")
    if not enter:
        print("   No Go / you-are-here button after selecting the marker — skipping this island.")
        return False
    m.click_on_found(enter)
    time.sleep(COLLECT_GO_WAIT)

    # The island may open with promotion popups on top — clear them first.
    if not close_island_popups(m):
        raise RuntimeError("Promo popup still showing after "
                           f"{COLLECT_MAX_POPUPS} close attempts — giving up")

    # Collect everything, then confirm.
    collect = m.find_on_screen(TEMPLATE_ISL_COLLECT_BUTTON, "Collect all", "collect_all")
    if collect:
        m.click_on_found(collect)
        time.sleep(COLLECT_DIALOG_WAIT)
        confirm = m.find_on_screen(TEMPLATE_CONFIRM_BUTTON, "Confirm collect", "collect_confirm")
        if confirm:
            m.click_on_found(confirm)
            time.sleep(COLLECT_CONFIRM_WAIT)
        else:
            print("   No confirm dialog after collect-all — heading back anyway.")
    else:
        print("   No collect-all button on this island — heading back anyway.")

    # Diamonds collect separately, with their own button and no confirm dialog.
    # Always check before leaving: let the coin-collect animation settle first
    # (otherwise the button can still be hidden), then press it if it's there.
    time.sleep(COLLECT_DIAMONDS_WAIT)
    diamonds = m.find_on_screen(TEMPLATE_ISL_COLLECT_DIAMONDS, "Collect diamonds", "collect_diamonds", threshold=0.73)
    if diamonds:
        print("   Collecting diamonds...")
        m.click_on_found(diamonds)
        time.sleep(COLLECT_DIALOG_WAIT)
    else:
        print("   No diamonds to collect on this island.")

    # Back to the world map for the next island.
    map_btn = m.find_on_screen(TEMPLATE_MAP_BUTTON, "Map button", "collect_map")
    if not map_btn:
        raise RuntimeError("No map button to return to the world map — giving up")
    m.click_on_found(map_btn)
    time.sleep(COLLECT_MAP_WAIT)
    return True


def run_collect_resources(mouse: VirtualMouse):
    """Sweep the world map collecting from every island with resources ready.

    Triggered by pressing **5** with the world map open. Scroll the island list
    to the top, then step down through it. Whenever an island shows a crystals or
    money marker, enter it, collect, and come back — then re-check where we land
    before scrolling on (a collected island stops showing its marker, so we won't
    loop on it). Finish when a full pass turns up no more markers.
    """
    m = AutoMonstrator(mouse)
    print("=== Collect resources: scrolling the island list to the top ===")

    sep = m.find_on_screen(TEMPLATE_MAP_SEPARATOR, "Separator area", "collect_sep")
    if not sep:
        print("   No island-list separator — probably not on the map. Aborting.")
        return
    m.scroll_up_on_found(COLLECT_SCROLL_UP, sep, True)
    time.sleep(COLLECT_SCROLL_WAIT)

    collected = 0
    scrolls = 0  # consecutive down-steps with nothing found — our give-up budget
    while scrolls < COLLECT_SCROLL_TRIES and collected < MAX_COLLECT_ISLANDS:
        marker = find_resource_marker(m)
        if marker:
            entered = collect_from_island(m, marker)
            if entered:
                collected += 1
                # Re-check the view we landed on before scrolling (per spec).
                scrolls = 0
                continue
            # Couldn't enter — nudge past this marker so we don't re-hit it.
        print(f"   ==== Scroll {scrolls + 1} of {COLLECT_SCROLL_TRIES} "
              f"(collected {collected} so far) ====")
        m.scroll_down_on_found(COLLECT_SCROLL_DOWN, sep)
        time.sleep(COLLECT_SCROLL_WAIT)
        scrolls += 1

    if collected >= MAX_COLLECT_ISLANDS:
        print(f"   Reached the {MAX_COLLECT_ISLANDS}-island cap — stopping.")
    else:
        print(f"   No more resource markers — done. Collected {collected} island(s).")


def main():
    logger.info(f"Waiting {SWITCH_DELAY}s before running")
    logger.info("starting")

    with VirtualMouse() as mouse:
        while True:
            print("\npress [1] map, [2] friends, [3] advanced friends, [6] combined friends, [5] collect resources, [q]/[esc] to quit — listening...")
            pressed = wait_for_keys((REPEAT_KEY, FRIENDS_KEY, ADVANCED_FRIENDS_KEY, COLLECT_KEY, COMBINED_FRIENDS_KEY, *QUIT_KEYS), log=print)
            if pressed is None:
                print("no keyboards found to read — quitting")
                break
            if pressed in QUIT_KEYS:
                print(f"{key_name(pressed)} pressed — quitting")
                break
            if pressed == FRIENDS_KEY:
                print(f"{key_name(pressed)} pressed — running friends routine")
                run_friends(mouse)
            elif pressed == ADVANCED_FRIENDS_KEY:
                print(f"{key_name(pressed)} pressed — running advanced friends routine")
                run_advanced_friends(mouse)
            elif pressed == COLLECT_KEY:
                print(f"{key_name(pressed)} pressed — running collect resources routine")
                run_collect_resources(mouse)
            elif pressed == COMBINED_FRIENDS_KEY:
                print(f"{key_name(pressed)} pressed — running combined friends routine")
                run_combined_friends(mouse)
            else:
                print(f"{key_name(pressed)} pressed — running map")
                run_map(mouse)

if __name__ == "__main__":
    main()
