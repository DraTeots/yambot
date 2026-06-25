# yambot — Rust workspace

Two small Rust programs in one Cargo *workspace*:

| crate | what it is |
|-------|------------|
| [`input-tracker`](input-tracker/) | **Project 1.** Reads your real mouse + keyboard with `evdev`, logs button presses (with an estimated pointer position) and key presses, and — when you press the **`1`** key — moves the pointer to the **middle of the screen** and **right-clicks** (via a `uinput` virtual mouse). |
| [`gui`](gui/) | **Project 2.** A desktop window built with `egui`/`eframe`, based on [emilk/eframe_template](https://github.com/emilk/eframe_template). A resizable left panel with 3 buttons, and a central terminal-like log. |

The two are independent for now (the GUI does not display the tracker's events — that could be wired up later).

---

## Build & run

From inside this `rust/` folder:

```fish
cargo build                 # compile both crates

cargo run -p gui            # run project 2 (a window opens) — no special permissions needed

cargo run -p input-tracker  # run project 1 — needs input-device access (see below)
```

> First build downloads dependencies and takes a minute or two; later builds are fast.

---

## Project 1 needs device permissions (one-time setup)

`input-tracker` reads `/dev/input/event*` and creates a virtual mouse at
`/dev/uinput`. Both normally require root — the clean fix is to join the **`input`
group** and allow that group to use `uinput`. Run these once:

```fish
# 1. Load the uinput kernel module now and on every boot.
sudo modprobe uinput
echo uinput | sudo tee /etc/modules-load.d/uinput.conf

# 2. Let the 'input' group read/write /dev/uinput.
echo 'KERNEL=="uinput", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"' \
  | sudo tee /etc/udev/rules.d/99-uinput.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# 3. Add yourself to the 'input' group.
sudo usermod -aG input $USER
```

**The group change does not apply to your current session.** Either log out and
back in, or, to test in *this* terminal without re-logging, start a subshell that
already has the group:

```fish
exec sg input fish        # 'input' is now one of your active groups in this shell
```

Check it worked — `input` should appear:

```fish
id -nG          # should list ... input ...
```

Then run the tracker (press keys / click to see logs; press `1` to center+right-click; `Ctrl+C` to quit):

```fish
cargo run -p input-tracker
```

If it prints `WARNING: could not open /dev/uinput`, the `uinput` permission isn't
in effect yet (re-check steps 1–2 and your active groups). If it prints
`No input devices could be opened`, the `input` group isn't active in this shell
(re-login or use the `exec sg input fish` trick above).

---

## Note on "move to the middle of the screen" under Wayland

You're on Wayland, where an app can't directly set the cursor position. We instead
create an *absolute* virtual pointer via `uinput` and send it the centre
coordinate (half of a 0..65535 range), which the compositor maps onto your screen.
This is the same low-level mechanism `ydotool` uses. Most compositors honor it; if
yours ignores absolute virtual pointers, the right-click still fires but the move
may not land — tell me and we can switch to a relative-movement strategy.

The logged mouse position is an **estimate**: mice report relative movement
(deltas), not an absolute position, so we add the deltas up. It drifts from the
real cursor and is only there to give a rough idea on each click.
