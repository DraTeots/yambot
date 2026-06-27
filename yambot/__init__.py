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





