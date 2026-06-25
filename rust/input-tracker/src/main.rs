//! # input-tracker (project 1)
//!
//! A small command-line program that watches your real input devices using the
//! Linux "evdev" interface and acts on them:
//!
//!   * every **key press** and **mouse-button press** is logged,
//!   * pressing the **"1" key** runs one *bot cycle*: take a screenshot, find a
//!     button inside it by template matching, and **left-click** it.
//!
//! ## How it reads input
//! The Linux kernel exposes every input device as a file under `/dev/input/`
//! (e.g. `/dev/input/event5`). Reading those files needs permission — normally
//! you must be in the `input` group (see the project README). We *passively*
//! read events; the events still reach your desktop as usual.
//!
//! ## How it finds the button
//! Pressing "1" shells out to `spectacle` for a full-screen PNG, then uses
//! OpenCV template matching (a multi-scale `TM_CCOEFF_NORMED` sweep) to locate
//! the button image. That gives us the target's **pixel** coordinates. We never
//! need to know where the real cursor is — a relative mouse can only ever
//! *estimate* that, and imprecisely (accel, no absolute origin, edge clamping).
//!
//! ## How it moves the mouse / clicks (the tricky part on Wayland)
//! An app can't just "set the cursor position" on Wayland. Instead we create a
//! brand-new *virtual* input device through `uinput` and feed it events, exactly
//! like a real mouse would. We declare ABSOLUTE X/Y axes spanning 0..=65535; the
//! compositor maps that whole range onto the real screen, so we can map a found
//! pixel into that range using the *screenshot's own* width/height and land
//! exactly on it. (Creating the device needs write access to `/dev/uinput` —
//! again, the `input` group; see the README.)
//!
//! ## Architecture
//! One background **thread per device** reads events and sends small messages
//! down a channel to the **main thread**, which prints them and runs the bot
//! cycle when asked. Centralising the virtual device in the main thread means we
//! never have to share it between threads.

use std::error::Error;
use std::io;
use std::process::Command;
use std::sync::mpsc::{self, Sender};
use std::thread;
use std::time::Duration;

// Types from the `evdev` crate. `uinput::VirtualDevice` is the virtual mouse we
// create; the rest are codes/helpers for reading and emitting events.
use evdev::uinput::VirtualDevice;
use evdev::{
    AbsInfo, AbsoluteAxisCode, AbsoluteAxisEvent, AttributeSet, Device, EventSummary, KeyCode,
    KeyEvent, RelativeAxisCode, UinputAbsSetup,
};

// OpenCV pieces. `prelude` brings in the Mat trait methods (.cols(), .rows(), ...).
use opencv::core::{min_max_loc, no_array, Mat, Point, Size};
use opencv::imgcodecs::{imread, IMREAD_COLOR, IMREAD_GRAYSCALE};
use opencv::imgproc::{
    cvt_color_def, match_template_def, resize, COLOR_BGR2GRAY, INTER_AREA, TM_CCOEFF_NORMED,
};
use opencv::prelude::*;

/// Messages sent from the per-device reader threads to the main thread.
enum Msg {
    /// A line of text to print to the terminal.
    Log(String),
    /// Request to run one bot cycle: screenshot -> find button -> click (the "1" key).
    RunCollect,
}

// --- Virtual-screen coordinate range -----------------------------------------
// We declare our virtual pointer's absolute axes as going from ABS_MIN..=ABS_MAX.
// The compositor maps that whole range onto the real screen, so a value of
// ABS_CENTER is the middle regardless of the actual pixel resolution.
const ABS_MIN: i32 = 0;
const ABS_MAX: i32 = 65535;
const ABS_CENTER: i32 = 32767; // (ABS_MIN + ABS_MAX) / 2

// --- Bot configuration -------------------------------------------------------
/// Where the full-screen grab is written before we read it back.
const SHOT_PATH: &str = "/tmp/yambot_shot.png";
/// The button we hunt for. Built at compile time relative to THIS crate so it
/// works no matter the current directory: <crate>/../../yambot/templates/...
const TEMPLATE_PATH: &str =
    concat!(env!("CARGO_MANIFEST_DIR"), "/../../yambot/templates/collect_all.png");
/// A match scoring below this (TM_CCOEFF_NORMED, higher = better) is treated as
/// "not really found" and we don't click.
const THRESHOLD: f64 = 0.80;

fn main() {
    // A channel is a one-way pipe: reader threads hold `tx` (the sending end) and
    // the main thread holds `rx` (the receiving end). `recv()` blocks until a
    // message arrives.
    let (tx, rx) = mpsc::channel::<Msg>();

    // Try to create the virtual mouse used for the click.
    // If it fails (usually no write access to /dev/uinput) we keep running as a
    // read-only logger and just disable injection, instead of crashing.
    let mut virtual_mouse = match VirtualMouse::new() {
        Ok(mouse) => {
            println!("[init] virtual mouse ready — press the '1' key to screenshot + click");
            Some(mouse)
        }
        Err(e) => {
            println!(
                "[init] WARNING: could not open /dev/uinput ({e}). \
                 Clicking is DISABLED. See README for the uinput permission."
            );
            None
        }
    };

    // Look at every input device and start a reader thread for the mice/keyboards.
    let mut threads_started = 0;
    for (path, device) in evdev::enumerate() {
        // A device is a "keyboard" if it can report the ENTER key, and a "mouse"
        // if it has a relative X axis. (`is_some_and` returns false when the
        // device reports no keys / no relative axes at all.)
        let is_keyboard = device
            .supported_keys()
            .is_some_and(|keys| keys.contains(KeyCode::KEY_ENTER));
        let is_mouse = device
            .supported_relative_axes()
            .is_some_and(|axes| axes.contains(RelativeAxisCode::REL_X));

        // Skip devices that are neither (power button, lid switch, etc.).
        if !(is_keyboard || is_mouse) {
            continue;
        }

        let name = device.name().unwrap_or("unknown").to_owned();
        let kind = match (is_keyboard, is_mouse) {
            (true, true) => "kbd+mouse",
            (true, false) => "keyboard",
            _ => "mouse",
        };
        println!("[init] listening to {kind:<9} {name:?}  ({})", path.display());

        // Each thread gets its own clone of the sending end of the channel.
        let tx = tx.clone();
        // `move` hands ownership of `device`, `name` and `tx` to the new thread.
        thread::spawn(move || run_device_thread(name, device, tx));
        threads_started += 1;
    }

    if threads_started == 0 {
        println!(
            "[init] No input devices could be opened. Are you in the 'input' group? See README."
        );
    }

    // Drop the main thread's own sender. Now the channel only stays open while at
    // least one reader thread is alive; if they all stop, `recv()` below returns
    // Err and we exit cleanly.
    drop(tx);

    // Main loop: print whatever the reader threads send us, and run the bot on request.
    while let Ok(msg) = rx.recv() {
        match msg {
            Msg::Log(line) => println!("{line}"),
            Msg::RunCollect => match virtual_mouse.as_mut() {
                Some(mouse) => {
                    if let Err(e) = run_collect(mouse) {
                        println!("[bot] failed: {e}");
                    }
                }
                None => println!("[bot] '1' pressed, but clicking is disabled (no /dev/uinput)"),
            },
        }
    }
}

/// Runs forever in its own thread: reads events from one device and reports them.
fn run_device_thread(name: String, mut device: Device, tx: Sender<Msg>) {
    loop {
        // `fetch_events` blocks until the kernel has events, then returns a batch.
        let events = match device.fetch_events() {
            Ok(events) => events,
            Err(e) => {
                // The device was probably unplugged — report it and end the thread.
                let _ = tx.send(Msg::Log(format!("[{name}] stopped reading: {e}")));
                return;
            }
        };

        for event in events {
            // We only care about *presses*. For Key events the value is
            // 1 = press, 0 = release, 2 = auto-repeat (held); match the literal 1.
            if let EventSummary::Key(_, key, 1) = event.destructure() {
                if is_mouse_button(key) {
                    let _ = tx.send(Msg::Log(format!("[{name}] mouse {key:?} pressed")));
                } else {
                    let _ = tx.send(Msg::Log(format!("[{name}] key pressed: {key:?}")));
                    // The headline feature: the "1" key triggers a bot cycle.
                    if key == KeyCode::KEY_1 {
                        let _ = tx.send(Msg::RunCollect);
                    }
                }
            }
        }
    }
}

/// True if this key code is actually a mouse button rather than a keyboard key.
fn is_mouse_button(key: KeyCode) -> bool {
    matches!(
        key,
        KeyCode::BTN_LEFT
            | KeyCode::BTN_RIGHT
            | KeyCode::BTN_MIDDLE
            | KeyCode::BTN_SIDE
            | KeyCode::BTN_EXTRA
    )
}

// --- The bot cycle -----------------------------------------------------------

/// A located button: its center pixel, the match score, and whether that score
/// cleared the threshold.
struct Found {
    x: i32,
    y: i32,
    score: f64,
    is_ok: bool,
}

/// One cycle: grab the screen, find the button, and left-click it if found.
fn run_collect(mouse: &mut VirtualMouse) -> Result<(), Box<dyn Error>> {
    println!("[bot] screenshotting...");
    let screen = screenshot(SHOT_PATH)?;
    let (width, height) = (screen.cols(), screen.rows());

    println!("[bot] finding button on {width}x{height} screen...");
    match find_button(&screen, TEMPLATE_PATH, THRESHOLD)? {
        None => println!("[bot] no candidate at any scale"),
        Some(found) => {
            println!(
                "[bot] best ({}, {}) score={:.3} ok={}",
                found.x, found.y, found.score, found.is_ok
            );
            if found.is_ok {
                mouse.click_at_pixel(found.x, found.y, width, height)?;
                println!("[bot] clicked");
            } else {
                println!("[bot] below threshold {THRESHOLD:.2}, not clicking");
            }
        }
    }
    Ok(())
}

/// Capture the whole screen via Spectacle and read it back as a BGR `Mat`.
fn screenshot(path: &str) -> Result<Mat, Box<dyn Error>> {
    // -b background (no GUI), -n no notification, -f full screen, -o output file.
    let status = Command::new("spectacle")
        .args(["-b", "-n", "-f", "-o", path])
        .status()?;
    if !status.success() {
        return Err(format!("spectacle exited with {status}").into());
    }
    let img = imread(path, IMREAD_COLOR)?;
    if img.empty() {
        return Err(format!("could not read screenshot at {path}").into());
    }
    Ok(img)
}

/// Locate `template_path` inside `screen_bgr` by template matching.
///
/// Sweeps a range of scales so a minified template still matches a larger
/// on-screen button (a direct port of the Python `find_button`). Returns the
/// best candidate found at any scale, or `None` if no scale even fit the screen.
fn find_button(
    screen_bgr: &Mat,
    template_path: &str,
    threshold: f64,
) -> Result<Option<Found>, Box<dyn Error>> {
    let template = imread(template_path, IMREAD_GRAYSCALE)?;
    if template.empty() {
        return Err(format!("template not found or unreadable: {template_path}").into());
    }

    let mut screen_gray = Mat::default();
    cvt_color_def(screen_bgr, &mut screen_gray, COLOR_BGR2GRAY)?;

    let (tw, th) = (template.cols(), template.rows());
    let (gw, gh) = (screen_gray.cols(), screen_gray.rows());

    // template is minified -> on-screen button is bigger -> scale template up.
    // 18 steps from 0.8x to 2.5x, same sweep as the Python version.
    const STEPS: i32 = 18;
    let mut best: Option<Found> = None;
    for i in 0..STEPS {
        let s = 0.8 + (2.5 - 0.8) * (i as f64) / ((STEPS - 1) as f64);
        let (w, h) = ((tw as f64 * s) as i32, (th as f64 * s) as i32);
        if w < 8 || h < 8 || w > gw || h > gh {
            continue;
        }

        let mut resized = Mat::default();
        resize(&template, &mut resized, Size::new(w, h), 0.0, 0.0, INTER_AREA)?;

        let mut result = Mat::default();
        match_template_def(&screen_gray, &resized, &mut result, TM_CCOEFF_NORMED)?;

        // The brightest spot in the result is the best match for this scale.
        let mut score = 0f64;
        let mut loc = Point::default();
        min_max_loc(&result, None, Some(&mut score), None, Some(&mut loc), &no_array())?;

        if best.as_ref().map_or(true, |b| score > b.score) {
            best = Some(Found {
                x: loc.x + w / 2,
                y: loc.y + h / 2,
                score,
                is_ok: score >= threshold,
            });
        }
    }
    Ok(best)
}

/// Map a pixel coordinate in `0..span-1` onto the `ABS_MIN..=ABS_MAX` range.
fn to_abs(value: i32, span: i32) -> i32 {
    if span <= 1 {
        return ABS_CENTER;
    }
    let frac = (value as f64 / (span - 1) as f64).clamp(0.0, 1.0);
    ABS_MIN + (frac * (ABS_MAX - ABS_MIN) as f64).round() as i32
}

// --- The virtual mouse -------------------------------------------------------

/// A synthetic mouse we create through `uinput` and drive ourselves, to move the
/// pointer and click. The kernel and compositor treat it like a real input device.
struct VirtualMouse {
    device: VirtualDevice,
}

impl VirtualMouse {
    /// Create the virtual mouse. Needs write access to `/dev/uinput`.
    fn new() -> io::Result<Self> {
        // Which buttons our virtual mouse is allowed to press.
        let mut buttons = AttributeSet::<KeyCode>::new();
        buttons.insert(KeyCode::BTN_LEFT);
        buttons.insert(KeyCode::BTN_RIGHT);

        // Two absolute axes, each spanning ABS_MIN..=ABS_MAX.
        // AbsInfo::new(value, minimum, maximum, fuzz, flat, resolution).
        let abs = AbsInfo::new(ABS_CENTER, ABS_MIN, ABS_MAX, 0, 0, 0);
        let abs_x = UinputAbsSetup::new(AbsoluteAxisCode::ABS_X, abs);
        let abs_y = UinputAbsSetup::new(AbsoluteAxisCode::ABS_Y, abs);

        // Build and register the device with the kernel. The `?` operator returns
        // early with the error if any step fails.
        let device = VirtualDevice::builder()?
            .name("yambot-virtual-pointer")
            .with_keys(&buttons)?
            .with_absolute_axis(&abs_x)?
            .with_absolute_axis(&abs_y)?
            .build()?;

        // Give the compositor a moment to notice the new device before we use it.
        thread::sleep(Duration::from_millis(300));
        Ok(Self { device })
    }

    /// Move to pixel `(x, y)` of a `width`x`height` frame, then left-click.
    fn click_at_pixel(&mut self, x: i32, y: i32, width: i32, height: i32) -> io::Result<()> {
        // 1) Jump to the target using absolute coordinates. `emit` sends the
        //    events and automatically appends the SYN_REPORT "end of batch"
        //    marker. `*` turns the typed event into a plain InputEvent.
        self.device.emit(&[
            *AbsoluteAxisEvent::new(AbsoluteAxisCode::ABS_X, to_abs(x, width)),
            *AbsoluteAxisEvent::new(AbsoluteAxisCode::ABS_Y, to_abs(y, height)),
        ])?;
        thread::sleep(Duration::from_millis(20)); // let the move register first

        // 2) Press, then release, the left button.
        self.device.emit(&[*KeyEvent::new(KeyCode::BTN_LEFT, 1)])?; // 1 = press
        thread::sleep(Duration::from_millis(20));
        self.device.emit(&[*KeyEvent::new(KeyCode::BTN_LEFT, 0)])?; // 0 = release
        Ok(())
    }
}
