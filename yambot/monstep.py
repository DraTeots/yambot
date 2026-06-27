# Monster... Monitored Step
import time
from pathlib import Path

import structlog


from .screen import find_on_image, mark_box, mark_circle, save_to_folder, screenshot
from .resources import TEMPLATE_ISL_COLLECT_BUTTON, TEMPLATE_MAP_MAIN_PLANT, TEMPLATE_MAP_SEPARATOR
from .timer_cm import TinyProfiler

import functools

def step(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        result = method(self, *args, **kwargs)
        self.last_step = result
        return result
    return wrapper

class StepResult:
    def __init__(self, is_ok: bool):
        self.is_ok = is_ok

    def __bool__(self):
        return self.is_ok

class FailedStep(StepResult):
    def __init__(self):
        super().__init__(False)

class FindStep(StepResult):
    def __init__(self, image, title, suffix, x, y, w: int, h: int, score: float, is_ok: bool):
        super().__init__(is_ok)
        self.position=(x,y)
        self.width = w
        self.height = h
        self.is_ok = is_ok
        self.score = score
        self.image = image
        self.title = title
        self.suffix = suffix


class AutoMonstrator:
    """Class to provide higher level automation functions (with finer logging and annotations)
    Its state only serves to centralize the logging and annotation configs
    """
    captures_dir: Path = "captures"
    annotate: bool = True

    def __init__(self, mouse: VirtualMouse):
        self.last_step = None
        self.mouse = mouse

    @step
    def find_on_screen(self, template, title, suffix):
        log = structlog.get_logger(title, title=title, suffix=suffix)

        # Take a screenshot.
        log.info("Step: %s", title)
        log.info("   Screenshotting...")
        image = screenshot()
        height, width = image.shape[:2]

        print("   Finding template...")
        with TinyProfiler("   Finding image"):
            target = find_on_image(image, template)
            if target is None:
                print("   No target found")
                return FailedStep()

        x, y, w, h, score, is_ok = target
        print(f"   Best found at ({x}, {y}) with score {score}. Is OK? {is_ok}")
        if not is_ok:
            print("   Target is not OK. Looks we didn't found")
            return FailedStep()

        if self.annotate:
            annotated = mark_box(image, x, y, w, h)   # green square around the matched region
            annotated = mark_circle(annotated, x, y)    # red circle at the click point
            save_to_folder(annotated, self.captures_dir, suffix=suffix)

        return FindStep(image, title, suffix, x, y, w, h, score, is_ok)


    def click_on_found(self, result: FindStep):
        """Making mouse click using previous find result"""
        log = structlog.get_logger()

        if not result:
            raise ValueError("Given step is not set or failed")
        if not isinstance(result, FindStep):
            raise ValueError("Then click only may be used after Find steps")

        (x, y), width, height = (result.position, result.width, result.height)

        if self.annotate:
            annotated = mark_circle(result.image, x, y)  # red circle at the click point
            save_to_folder(annotated, self.captures_dir, suffix=result.suffix + "_click")

        log.info(f"   clicking at {result.title}...", x=x, y=y, width=width, height=height)
        self.mouse.click_at(x, y, width, height)


    def then_click(self, title):
        """Making mouse click using previous find result"""
        log = structlog.get_logger()
        log.bind(self.last_step)

        if not self.last_step:
            raise ValueError("Last step is not set or failed")
        self.click_on_found(self.last_step)


    def scroll_up_on_found(self, clicks, result: FindStep, force_annotate: bool=False):
        """Making mouse click using previous find result"""
        log = structlog.get_logger()

        if not result:
            raise ValueError("Given step is not set or failed")
        if not isinstance(result, FindStep):
            raise ValueError("Then scroll_up only may be used after Find steps")

        (x, y), width, height = (result.position, result.width, result.height)

        log.info(f"   scrolling up at {result.title}...")

        # By default we not annotate scrolling
        if force_annotate:
            annotated = mark_circle(result.image, x, y)  # red circle at the click point
            save_to_folder(annotated, self.captures_dir, suffix=result.suffix + "_scroll_up")

        self.mouse.move_to(x, y, height, width)
        time.sleep(0.1)
        self.mouse.scroll_up(clicks)
        time.sleep(0.1)


    def scroll_down_on_found(self, clicks, result: FindStep, force_annotate: bool=False):
        """Making mouse scroll down using xy from previous find result"""
        log = structlog.get_logger()

        if not result:
            raise ValueError("Given step is not set or failed")
        if not isinstance(result, FindStep):
            raise ValueError("Then scroll_down only may be used after Find steps")

        (x, y), width, height = (result.position, result.width, result.height)

        log.info(f"   scrolling up at {result.title}...")

        # By default we not annotate scrolling
        if force_annotate:
            annotated = mark_circle(result.image, x, y)  # red circle at the click point
            save_to_folder(annotated, self.captures_dir, suffix=result.suffix + "_scroll_up")

        self.mouse.move_to(x, y, height, width)
        self.mouse.scroll_down(clicks)