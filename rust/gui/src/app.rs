//! The egui application itself.
//!
//! Layout:
//!   * a **left side panel** with 3 buttons; its width can be dragged,
//!   * a **central panel** showing a scrolling, terminal-like log.
//!
//! It keeps the `TemplateApp` type and `eframe::App` shape from
//! emilk/eframe_template, but the widgets inside are our own.

use std::time::{Duration, Instant};

/// Everything the app needs to remember lives in this struct.
///
/// Deriving `serde::Deserialize`/`Serialize` lets eframe save and restore the
/// app between runs (the "persistence" feature). Fields marked `#[serde(skip)]`
/// are NOT saved — they reset every run. We skip all of ours because logs and
/// timers are runtime-only, and because `Instant` can't be serialized anyway.
#[derive(serde::Deserialize, serde::Serialize)]
#[serde(default)] // any missing field falls back to its default when loading old saves
pub struct TemplateApp {
    /// The lines shown in the central "terminal", newest at the bottom.
    #[serde(skip)]
    log: Vec<String>,

    /// Whether the "print hello every second" timer is currently running.
    #[serde(skip)]
    timer_running: bool,

    /// When we last printed a timer "hello". `None` until the timer starts.
    #[serde(skip)]
    last_tick: Option<Instant>,
}

impl Default for TemplateApp {
    fn default() -> Self {
        Self {
            log: vec!["Welcome! Use the buttons on the left.".to_owned()],
            timer_running: false,
            last_tick: None,
        }
    }
}

impl TemplateApp {
    /// Called once before the first frame. `cc` can give us previously saved state.
    pub fn new(cc: &eframe::CreationContext<'_>) -> Self {
        // If there is saved state, load it; otherwise start from defaults.
        if let Some(storage) = cc.storage {
            return eframe::get_value(storage, eframe::APP_KEY).unwrap_or_default();
        }
        Self::default()
    }

    /// Small helper: append one line to the terminal log.
    fn log_line(&mut self, text: impl Into<String>) {
        self.log.push(text.into());
    }
}

impl eframe::App for TemplateApp {
    /// Called by eframe to save our state just before the app closes.
    fn save(&mut self, storage: &mut dyn eframe::Storage) {
        eframe::set_value(storage, eframe::APP_KEY, self);
    }

    /// Called every frame to (re)build the UI. `ui` represents the whole window.
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        // ---- Timer ----------------------------------------------------------
        // egui normally only repaints when something happens (a click, a key,
        // the mouse moving). For a timer that must fire while the app sits idle
        // we (a) check the elapsed time every frame and (b) explicitly ask egui
        // to wake us again in ~1 second so the next tick can fire on time.
        if self.timer_running {
            let now = Instant::now();
            let one_second_passed = self
                .last_tick
                .is_some_and(|t| now.duration_since(t) >= Duration::from_secs(1));
            if one_second_passed {
                self.last_tick = Some(now);
                self.log_line("hello (timer)");
            }
            ui.ctx().request_repaint_after(Duration::from_secs(1));
        }

        // ---- Left panel: the buttons (resizable width) ----------------------
        egui::Panel::left("button_panel")
            .resizable(true) // <- the user can drag the panel's right edge to resize it
            .default_size(190.0)
            .size_range(120.0..=400.0) // smallest / largest width when dragging
            .show_inside(ui, |ui| {
                ui.heading("Actions");
                ui.separator();

                // Button 1 — print "hello" once.
                if ui.button("Print hello").clicked() {
                    self.log_line("hello");
                }

                ui.add_space(6.0);

                // Button 2 — start/stop the every-second timer (the label toggles).
                let timer_label = if self.timer_running {
                    "Stop timer"
                } else {
                    "Start timer (hello / 1s)"
                };
                if ui.button(timer_label).clicked() {
                    self.timer_running = !self.timer_running;
                    if self.timer_running {
                        self.last_tick = Some(Instant::now());
                        self.log_line("[timer started]");
                    } else {
                        self.log_line("[timer stopped]");
                    }
                }

                ui.add_space(6.0);

                // Button 3 — reset everything back to defaults.
                if ui.button("Reset to defaults").clicked() {
                    // Reset our own state (clears the log, stops the timer)...
                    *self = Self::default();
                    // ...and wipe egui's own memory, which resets remembered UI
                    // state such as the dragged panel width, so the whole layout
                    // returns to its defaults too.
                    ui.ctx().memory_mut(|mem| *mem = Default::default());
                    self.log_line("[reset to defaults]");
                }

                // A faint hint pinned to the bottom of the panel.
                ui.with_layout(egui::Layout::bottom_up(egui::Align::LEFT), |ui| {
                    ui.label(
                        egui::RichText::new("Tip: drag the right edge →")
                            .weak()
                            .small(),
                    );
                });
            });

        // ---- Central panel: the terminal-like log ---------------------------
        egui::CentralPanel::default().show_inside(ui, |ui| {
            ui.heading("Log");
            ui.separator();

            // A scrolling region that sticks to the bottom, like a real terminal.
            egui::ScrollArea::vertical()
                .auto_shrink([false, false]) // fill all the available space
                .stick_to_bottom(true)
                .show(ui, |ui| {
                    for line in &self.log {
                        ui.monospace(line); // monospace font for the terminal feel
                    }
                });
        });
    }
}
