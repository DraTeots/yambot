# yambot
Yet Another My Singing Monsters Bot

Input and output both go through evdev/uinput directly — no `ydotool` daemon
needed. The only setup is granting your user access to `/dev/uinput` and
`/dev/input/event*`, which the `input` group below covers.

## 1. System setup (one time)

```fish
# load the uinput module now and on every boot
sudo modprobe uinput
echo uinput | sudo tee /etc/modules-load.d/uinput.conf

# grant the 'input' group access to /dev/uinput
echo 'KERNEL=="uinput", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"' \
  | sudo tee /etc/udev/rules.d/99-uinput.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# add yourself to the input group
sudo usermod -aG input $USER
```

The group change doesn't apply to your running session. Log out and back in. To test in the current terminal without relogging, start a subshell that has the group:

```fish
newgrp input
```

Verify both are right:

```fish
ls -l /dev/uinput      # should show: crw-rw---- ... root input
id | grep -o input     # should print: input
```

The `input` group also covers reading `/dev/input/event*`, so the same setup gives you key listening later if you want it.

