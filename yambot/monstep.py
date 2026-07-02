# Monster... Monitored Step
import time
from pathlib import Path

import structlog


from .screen import check_is_active, find_all_on_image, find_on_image, mark_box, mark_circle, save_to_folder, screenshot
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
    def find_on_screen(self, template, title, suffix, threshold=0.80):
        log = structlog.get_logger(title, title=title, suffix=suffix)

        # Take a screenshot.
        log.info("Step: %s", title)
        log.info("   Screenshotting...")
        image = screenshot()
        height, width = image.shape[:2]

        print("   Finding template...")
        with TinyProfiler("   Finding image"):
            target = find_on_image(image, template, threshold=threshold)
            if target is None:
                print("   No target found")
                return FailedStep()

        x, y, w, h, score, is_ok = target
        print(f"   Best found at ({x}, {y}) with score {score}. Is OK? {is_ok}")
        if not is_ok:
            print("   Target is not OK. Looks we didn't found")
            if self.annotate:
                annotated = mark_box(image, x, y, w, h)  # green square around the matched region
                save_to_folder(annotated, self.captures_dir, suffix=suffix)
            return FailedStep()

        if self.annotate:
            annotated = mark_box(image, x, y, w, h)   # green square around the matched region
            save_to_folder(annotated, self.captures_dir, suffix=suffix)

        return FindStep(image, title, suffix, x, y, w, h, score, is_ok)


    def find_all_on_screen(self, template, title, suffix, sort=None, image=None):
        """Like :meth:`find_on_screen`, but return *every* match above threshold.

        Wraps :func:`yambot.screen.find_all_on_image` for repeated buttons (e.g.
        the five friend-light icons on a page). Returns a list of FindStep,
        strongest-first, all sharing the one screenshot; an empty list means
        nothing matched. Not a ``@step`` — it doesn't set ``last_step`` (there's
        no single result to act on with ``then_*``).

        ``sort`` re-orders the returned list by screen position instead of match
        strength: ``"y_asc"`` (topmost first), ``"y_desc"`` (bottommost first),
        ``"x_asc"`` (leftmost first) or ``"x_desc"`` (rightmost first). ``None``
        keeps the strongest-first order.

        Pass ``image`` to match against an already-taken frame instead of
        screenshotting afresh — handy for scanning several templates against one
        screenshot.
        """
        log = structlog.get_logger(title, title=title, suffix=suffix)
        log.info("Step (all): %s", title)
        if image is None:
            image = screenshot()

        print("   Finding all templates...")
        with TinyProfiler("   Finding all images"):
            matches = find_all_on_image(image, template)

        print(f"   Found {len(matches)} match(es)")
        if not matches:
            return []

        results = [
            FindStep(image, title, f"{suffix}_{i}", x, y, w, h, score, True)
            for i, (x, y, w, h, score) in enumerate(matches)
        ]

        if sort is not None:
            axis, _, direction = sort.partition("_")
            if axis not in ("x", "y") or direction not in ("asc", "desc"):
                raise ValueError(f"Unknown sort {sort!r}; expected x/y _asc/_desc")
            idx = 0 if axis == "x" else 1  # position is (x, y)
            results.sort(key=lambda r: r.position[idx], reverse=(direction == "desc"))

        if self.annotate:
            annotated = image
            for x, y, w, h, score in matches:
                annotated = mark_box(annotated, x, y, w, h)
            save_to_folder(annotated, self.captures_dir, suffix=suffix + "_all")

        return results


    def click_on_found(self, result: FindStep):
        """Making mouse click using previous find result"""
        log = structlog.get_logger()

        if not result:
            raise ValueError("Given step is not set or failed")
        if not isinstance(result, FindStep):
            raise ValueError("Then click only may be used after Find steps")

        (x, y) = result.position
        # move_to/click_at map the pixel into the absolute axis range using the
        # *frame* dimensions, not the matched box's. Read them off the screenshot.
        frame_h, frame_w = result.image.shape[:2]

        if self.annotate:
            annotated = mark_circle(result.image, x, y)  # red circle at the click point
            save_to_folder(annotated, self.captures_dir, suffix=result.suffix + "_click")

        log.info(f"   clicking at {result.title}...", x=x, y=y, width=frame_w, height=frame_h)
        self.mouse.click_at(x, y, frame_w, frame_h)


    def then_click(self, title):
        """Making mouse click using previous find result"""
        log = structlog.get_logger()
        log.bind(self.last_step)

        if not self.last_step:
            raise ValueError("Last step is not set or failed")
        self.click_on_found(self.last_step)


    def check_active_on_found(self, result: FindStep, active_template, passive_template,
                              force_annotate: bool = False):
        """Tell whether a previously found button is active (enabled) or disabled.

        Same shape, different tone: we crop the matched box out of the *color*
        frame and let :func:`yambot.screen.check_is_active` pick the nearest of
        two reference images. Returns the ``is_active`` bool. The two distances
        are logged so a near-tie (a weak/misaligned match) is visible.
        """
        log = structlog.get_logger(result.title if result else "check_active")

        if not result:
            raise ValueError("Given step is not set or failed")
        if not isinstance(result, FindStep):
            raise ValueError("check_active only may be used after Find steps")

        (x, y) = result.position
        w, h = result.width, result.height
        # Crop the matched region (not the whole frame) — that's what we compare.
        x0, y0 = max(x - w // 2, 0), max(y - h // 2, 0)
        crop = result.image[y0:y0 + h, x0:x0 + w]

        is_active, dist_active, dist_passive = check_is_active(
            crop, active_template, passive_template
        )

        log.info(
            f"   {result.title} is {'ACTIVE' if is_active else 'disabled'}",
            is_active=is_active,
            dist_active=round(dist_active, 2),
            dist_passive=round(dist_passive, 2),
        )

        # By default we don't annotate; on request, mark the crop's state.
        if force_annotate:
            state = "active" if is_active else "passive"
            annotated = mark_circle(result.image, x, y,
                                    color=(0, 255, 0) if is_active else (0, 0, 255))
            save_to_folder(annotated, self.captures_dir,
                           suffix=result.suffix + "_" + state)

        return is_active


    def then_check_active(self, active_template, passive_template, force_annotate: bool = False):
        """Run :meth:`check_active_on_found` against the last find result."""
        if not self.last_step:
            raise ValueError("Last step is not set or failed")
        return self.check_active_on_found(self.last_step, active_template, passive_template,
                                          force_annotate)


    def scroll_up_on_found(self, clicks, result: FindStep, force_annotate: bool=False):
        """Making mouse click using previous find result"""
        log = structlog.get_logger()

        if not result:
            raise ValueError("Given step is not set or failed")
        if not isinstance(result, FindStep):
            raise ValueError("Then scroll_up only may be used after Find steps")

        (x, y) = result.position
        frame_h, frame_w = result.image.shape[:2]

        log.info(f"   scrolling up at {result.title}...")

        # By default we not annotate scrolling
        if force_annotate:
            annotated = mark_circle(result.image, x, y)  # red circle at the click point
            save_to_folder(annotated, self.captures_dir, suffix=result.suffix + "_scroll_up")

        self.mouse.move_to(x, y, frame_w, frame_h)
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

        (x, y) = result.position
        frame_h, frame_w = result.image.shape[:2]

        log.info(f"   scrolling down at {result.title}...")

        # By default we not annotate scrolling
        if force_annotate:
            annotated = mark_circle(result.image, x, y)  # red circle at the click point
            save_to_folder(annotated, self.captures_dir, suffix=result.suffix + "_scroll_down")

        self.mouse.move_to(x, y, frame_w, frame_h)
        self.mouse.scroll_down(clicks)