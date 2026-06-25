# Credits
# https://github.com/mherrmann/timer-cm
#
# timer-cm
# A Python context manager for measuring execution time.
# Useful in conjunction with [Python's profilers](https://docs.python.org/3.5/library/profile.html), or on its own.
#
# ```python
# from timer_cm import Timer
# with Timer('Simple task'):
#     sleep(1)
# ```
#
# Often you want to know where a long running code block spends its time. Use `timer.child(name)` to track individual steps:
#
# ```python
# with Timer('Long task') as timer:
#     with timer.child('large step'):
#         sleep(1)
#     for _ in range(5):
#         with timer.child('small step'):
#             sleep(.5)
# ```
#
# To measure times throughout the entire run of your application and report total running times at the end:
#
# ```python
# from timer_cm import Timer
#
# _TIMER = Timer('my_fn')
#
# def my_fn():
#     # Suppose this function is called throughout your application.
#     with _TIMER.child('step 1'):
#         ...
#     with _TIMER.child('step 2'):
#         ...
#     ...
#
# import atexit
# atexit.register(_TIMER.print_results)
#
# ```

from decimal import Decimal
from math import ceil, log10
from timeit import default_timer

class TinyProfiler(object):
    def __init__(self, name, print_results=True):
        self.elapsed = Decimal()
        self._name = name
        self._print_results = print_results
        self._start_time = None
        self._children = {}
        self._count = 0
    def __enter__(self):
        self.start()
        return self
    def __exit__(self, *_):
        self.stop()
        if self._print_results:
            self.print_results()
    def child(self, name):
        try:
            return self._children[name]
        except KeyError:
            result = TinyProfiler(name, print_results=False)
            self._children[name] = result
            return result
    def start(self):
        self._count += 1
        self._start_time = self._get_time()
    def stop(self):
        self.elapsed += self._get_time() - self._start_time
    def print_results(self):
        print(self._format_results())
    def _format_results(self, indent='  '):
        children = self._children.values()
        elapsed = self.elapsed or sum(c.elapsed for c in children)
        result = '%s: %.3fs' % (self._name, elapsed)
        max_count = max(c._count for c in children) if children else 0
        count_digits = 0 if max_count <= 1 else int(ceil(log10(max_count + 1)))
        for child in sorted(children, key=lambda c: c.elapsed, reverse=True):
            lines = child._format_results(indent).split('\n')
            child_percent = child.elapsed / elapsed * 100
            lines[0] += ' (%d%%)' % child_percent
            if count_digits:
                # `+2` for the 'x' and the space ' ' after it:
                lines[0] = ('%dx ' % child._count).rjust(count_digits + 2) \
                           + lines[0]
            for line in lines:
                result += '\n' + indent + line
        return result
    def _get_time(self):
        return Decimal(default_timer())