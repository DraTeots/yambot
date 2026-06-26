# Monster... Monitored Step
from yambot import screenshot, TinyProfiler, find_on_image, TEMPLATE_MAP_SEPARATOR

from .screen import TEMPLATE_ISL_COLLECT_BUTTON, find_on_image, box, mark, save, screenshot, TEMPLATE_MAP_MAIN_PLANT, \
    TEMPLATE_MAP_SEPARATOR


def find_on_screen():
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